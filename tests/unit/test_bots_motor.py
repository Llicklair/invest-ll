"""El motor de bots con `FuenteFalsa` y un reloj que avanza a mano: bots que operan de verdad sobre
series sintéticas, huecos al reabrir, cortes de precios, fallos aislados y el ciclo de vida."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import replace
from datetime import UTC, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, NoReturn

import pytest

from invest_ll.bots import motor as modulo_motor
from invest_ll.bots.motor import UMBRAL_HUECO, Motor, tramo
from invest_ll.bots.registro import BotNoEncontradoError, Registro

from .bots_apoyo import INICIO, Mercado, libro, onda

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Coroutine, Iterator
    from pathlib import Path

    from invest_ll.bots.decisiones import Decision, Situacion
    from invest_ll.bots.motor import Bot

D = Decimal
TENDENCIA = {"media_corta": "5", "media_larga": "20", "intervalo": "1h"}
REJILLA = {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"}
_SOCKET_REAL = socket.socket  # antes de que el fixture de la suite corte la red


@pytest.fixture(autouse=True)
def sin_motor_del_panel() -> Iterator[None]:
    yield
    modulo_motor.usar(None)


def nuevo_motor(mercado: Mercado, raiz: Path, *, vela_a_vela: bool = False) -> Motor:
    """`vela_a_vela`: la prueba da una sola vuelta por vela (una hora o un día entre vueltas), que
    sin esto el motor tomaría por un panel cerrado."""
    umbral = timedelta(days=3650) if vela_a_vela else UMBRAL_HUECO
    return Motor(mercado.fuente, raiz / "bots", reloj=mercado.reloj, zona=UTC, umbral_hueco=umbral)


def lados(m: Motor, bot: Bot) -> list[str]:
    return [o.lado for o in reversed(m.operaciones(bot.id))]


class TestTendencia:
    def desplegar(self, mercado: Mercado, raiz: Path) -> tuple[Motor, Bot]:
        mercado.poner("BTC", "1h", onda(400, periodo=120))
        mercado.al_cierre(30)
        m = nuevo_motor(mercado, raiz, vela_a_vela=True)
        return m, m.desplegar("tendencia", "Tendencia", ["BTC"], D(1000), TENDENCIA)

    def test_opera_de_verdad_sobre_una_onda(self, tmp_path: Path) -> None:
        mercado = Mercado()
        m, bot = self.desplegar(mercado, tmp_path)
        mercado.recorrer(m, 30, 400)
        ops = list(reversed(m.operaciones(bot.id)))
        assert len(ops) >= 6
        assert [o.lado for o in ops[:4]] == ["compra", "venta", "compra", "venta"]
        cierres = {v.fin for v in mercado.velas[("BTC", "1h")]}
        assert all(o.at in cierres for o in ops), "solo decide al cierre de una vela"
        assert ops[1].motivo.startswith("Vendí ")
        assert "la media de 5 velas cruzó por debajo de la de 20" in ops[1].motivo
        assert all(o.comision > 0 for o in ops)
        assert bot.estado.operaciones == len(ops)

    def test_no_decide_dos_veces_con_la_misma_vela(self, tmp_path: Path) -> None:
        mercado = Mercado()
        m, bot = self.desplegar(mercado, tmp_path)
        m.paso()
        hechas = bot.estado.operaciones
        for _ in range(30):
            mercado.reloj.avanzar(timedelta(seconds=1))
            m.paso()
        assert bot.estado.operaciones == hechas

    def test_la_vela_en_curso_no_cuenta_aunque_se_dispare(self, tmp_path: Path) -> None:
        """La misma serie, con la vela en curso marcando un precio disparatado (el que tendrá
        al cerrar no se sabe aún): las operaciones son exactamente las mismas."""
        normal, loca = Mercado(), Mercado()
        m1, b1 = self.desplegar(normal, tmp_path / "a")
        m2, b2 = self.desplegar(loca, tmp_path / "b")
        for i in range(30, 200):
            normal.al_cierre(i)
            m1.paso()
            loca.al_cierre(i)
            serie_loca = loca.fuente.series[("BTC", "1h")]
            en_curso = serie_loca[-1]
            serie_loca[-1] = replace(
                en_curso, cierre=en_curso.cierre * (1000 if i % 2 else D("0.001"))
            )
            m2.paso()
        resumen = [(o.at, o.lado, o.cantidad) for o in m1.operaciones(b1.id)]
        assert resumen == [(o.at, o.lado, o.cantidad) for o in m2.operaciones(b2.id)]
        assert resumen

    def test_sin_libro_no_se_inventa_la_orden_y_se_reintenta(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.poner("BTC", "1h", [10.0] * 25 + [5.0] * 10 + [30.0] * 10)
        mercado.al_cierre(29)
        m = nuevo_motor(mercado, tmp_path, vela_a_vela=True)
        bot = m.desplegar("tendencia", "T", ["BTC"], D(1000), TENDENCIA)
        mercado.recorrer(m, 29, 35)
        assert bot.estado.operaciones == 0
        mercado.al_cierre(35, sin_libro=frozenset({"BTC"}))
        for _ in range(5):
            m.paso()
            mercado.reloj.avanzar(timedelta(seconds=1))
        assert bot.estado.operaciones == 0
        esperas = [e for e in m.eventos(bot.id) if "Sin libro" in e.texto]
        assert len(esperas) == 1, "el evento se apunta una vez, no en cada vuelta"
        assert m.aviso(bot) == "Sin libro de órdenes de BTC: la compra espera."
        mercado.fuente.libros["BTC"] = libro("BTC", mercado.velas[("BTC", "1h")][35].cierre)
        m.paso()  # la misma vela: se reintenta sin esperar a la siguiente
        assert lados(m, bot) == ["compra"]
        assert m.aviso(bot) is None


class TestRejilla:
    def desplegar(self, mercado: Mercado, raiz: Path) -> tuple[Motor, Bot]:
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, raiz)
        return m, m.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)

    def mover(self, m: Motor, mercado: Mercado, precios: list[float]) -> None:
        for p in precios:
            mercado.precio("BTC", p)
            mercado.reloj.avanzar(timedelta(seconds=1))
            m.paso()

    def test_gana_si_el_precio_oscila_dentro_del_rango(self, tmp_path: Path) -> None:
        mercado = Mercado()
        m, bot = self.desplegar(mercado, tmp_path)
        ida_y_vuelta = [97.0, 94.0, 97.0, 101.0, 106.0, 104.0, 101.0, 97.0]
        self.mover(m, mercado, [100.0] + ida_y_vuelta * 5 + [100.0])
        ops = lados(m, bot)
        assert ops[0] == "compra"  # el arranque: los escalones de encima del precio
        assert ops.count("venta") >= 10
        valor, mantener = bot.valor(), bot.mantener()
        assert valor is not None
        assert mantener is not None
        assert valor > D(1000) > mantener
        primera = m.operaciones(bot.id)[-1]
        assert "arranque de la rejilla: compro los 2 escalones" in primera.motivo

    def test_si_sale_por_abajo_lo_tiene_todo_comprado_y_pierde(self, tmp_path: Path) -> None:
        mercado = Mercado()
        m, bot = self.desplegar(mercado, tmp_path)
        self.mover(m, mercado, [100.0, 96.0, 92.0, 85.0, 80.0])
        assert bot.cuenta.efectivo < D(15)
        valor = bot.valor()
        assert valor is not None
        assert valor < D(1000)
        aviso = m.aviso(bot)
        assert aviso is not None
        assert "por debajo del rango" in aviso
        assert any("por debajo del rango" in e.texto for e in m.eventos(bot.id))


class TestPeriodica:
    def test_compra_segun_su_horario(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar(
            "periodica", "P", ["BTC"], D(1000), {"importe": "100", "cada_horas": "24"}
        )
        m.paso()
        assert bot.estado.operaciones == 1
        for _ in range(24 * 60 - 1):
            mercado.reloj.avanzar(timedelta(minutes=1))
            m.paso()
        assert bot.estado.operaciones == 1  # a las 23:59 aún no le toca
        mercado.reloj.avanzar(timedelta(minutes=1))
        m.paso()
        assert bot.estado.operaciones == 2
        assert bot.cuenta.efectivo == pytest.approx(D(800), abs=D("0.01"))


class TestBtcFreno:
    def test_entra_cuando_sube_y_sale_cuando_baja(self, tmp_path: Path) -> None:
        mercado = Mercado()
        cierres = [100.0 + i for i in range(40)] + [140.0 - 3 * i for i in range(40)]
        mercado.poner("BTC", "1d", cierres)
        mercado.al_cierre(31)
        m = nuevo_motor(mercado, tmp_path, vela_a_vela=True)
        bot = m.desplegar("btc-freno", "Freno", ["BTC"], D(1000), {})
        mercado.recorrer(m, 31, 80)
        assert lados(m, bot) == ["compra", "venta"]
        assert "respecto a hace 30 días: paso a USDC" in m.operaciones(bot.id)[0].motivo


class TestHuecos:
    def test_al_reabrir_el_panel_apunta_el_hueco_y_sigue_donde_estaba(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        mercado.reloj.t = INICIO.replace(hour=14, minute=2)
        m1 = nuevo_motor(mercado, tmp_path)
        bot = m1.desplegar(
            "periodica", "P", ["BTC"], D(1000), {"importe": "100", "cada_horas": "24"}
        )
        m1.paso()
        efectivo = bot.cuenta.efectivo
        m1.guardar()

        mercado.reloj.t = INICIO.replace(hour=18, minute=30)
        m2 = nuevo_motor(mercado, tmp_path)
        m2.cargar()
        m2.paso()
        otro = m2.bot(bot.id)
        texto = "Panel cerrado de 14:02 a 18:30: no pudo operar."
        assert m2.eventos(bot.id)[0].texto == texto
        assert m2.eventos(bot.id)[0].tipo == "hueco"
        assert m2.aviso(otro) == texto
        assert otro.cuenta.efectivo == efectivo
        assert otro.estado.operaciones == 1

    def test_el_aviso_del_hueco_dura_un_dia(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m1 = nuevo_motor(mercado, tmp_path)
        bot = m1.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m1.paso()
        m1.guardar()
        mercado.reloj.avanzar(timedelta(hours=3))
        m2 = nuevo_motor(mercado, tmp_path)
        m2.cargar()
        m2.paso()
        assert m2.aviso(m2.bot(bot.id)) is not None
        mercado.reloj.avanzar(timedelta(hours=25))
        assert m2.aviso(m2.bot(bot.id)) is None

    def test_un_bot_parado_no_tiene_huecos(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m1 = nuevo_motor(mercado, tmp_path)
        bot = m1.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m1.paso()
        m1.parar_bot(bot.id)
        mercado.reloj.avanzar(timedelta(hours=5))
        m2 = nuevo_motor(mercado, tmp_path)
        m2.cargar()
        m2.paso()
        assert not [e for e in m2.eventos(bot.id) if e.tipo == "hueco"]

    def test_si_cambia_el_dia_lo_dice(self) -> None:
        desde = INICIO.replace(hour=23)
        assert tramo(desde, desde + timedelta(hours=2), UTC) == (
            "del 1 oct 2026, 23:00, al 2 oct 2026, 01:00"
        )

    def test_un_corte_de_los_precios_no_deja_operar_y_se_apunta(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        mercado.reloj.t = INICIO.replace(hour=10)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m.paso()
        hechas = bot.estado.operaciones
        mercado.fuente.conectada_ = False
        mercado.precio("BTC", 91)  # bajaría escalones, pero sin precios fiables no opera
        for _ in range(30):
            mercado.reloj.avanzar(timedelta(seconds=10))
            m.paso()
        assert bot.estado.operaciones == hechas
        assert (
            m.aviso(bot)
            == "Sin precios de Hyperliquid desde las 10:00: no opera hasta que vuelvan."
        )
        mercado.fuente.conectada_ = True
        m.paso()
        assert m.eventos(bot.id)[0].texto == (
            "Sin precios de Hyperliquid de 10:00 a 10:05: no pudo operar."
        )
        assert bot.estado.operaciones > hechas

    def test_un_corte_de_unos_segundos_no_se_apunta(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m.paso()
        mercado.fuente.conectada_ = False
        for _ in range(5):
            mercado.reloj.avanzar(timedelta(seconds=1))
            m.paso()
        mercado.fuente.conectada_ = True
        m.paso()
        assert not [e for e in m.eventos(bot.id) if e.tipo == "hueco"]


class TestFallosYEstados:
    def test_un_bot_que_falla_queda_con_error_y_los_demas_siguen(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        malo = m.desplegar("rejilla", "Malo", ["BTC"], D(1000), REJILLA)
        bueno = m.desplegar("periodica", "Bueno", ["BTC"], D(1000), {})

        def falla(_: Situacion) -> NoReturn:
            raise ZeroDivisionError("división entre cero")

        malo.plantilla = replace(malo.plantilla, decidir=falla)
        m.paso()
        assert malo.estado.estado == "error"
        assert malo.estado.motivo_error == "Falló al decidir u operar: división entre cero"
        assert m.eventos(malo.id)[0].tipo == "error"
        assert bueno.estado.estado == "en_marcha"
        assert bueno.estado.operaciones == 1
        mercado.reloj.avanzar(timedelta(seconds=1))
        m.paso()  # sigue en error, sin repetir el evento
        assert [e.tipo for e in m.eventos(malo.id)].count("error") == 1

        def bien(s: Situacion) -> Decision:
            from invest_ll.bots.decisiones import rejilla

            return rejilla(s)

        malo.plantilla = replace(malo.plantilla, decidir=bien)
        m.reanudar_bot(malo.id)
        assert malo.estado.estado == "en_marcha"
        assert malo.estado.motivo_error is None
        m.paso()
        assert malo.estado.operaciones == 1

    def test_parado_no_opera_pero_se_sigue_valorando(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m.paso()
        antes = bot.valor()
        m.parar_bot(bot.id)
        mercado.precio("BTC", 120)
        m.paso()
        assert bot.estado.operaciones == 1
        despues = bot.valor()
        assert antes is not None
        assert despues is not None
        assert despues > antes

    def test_borrar(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        m.borrar_bot(bot.id)
        with pytest.raises(BotNoEncontradoError):
            m.bot(bot.id)
        assert Registro(tmp_path / "bots").ids() == []

    def test_sigue_las_monedas_con_su_libro_y_sus_velas(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        mercado.precio("ETH", 10)
        m = nuevo_motor(mercado, tmp_path)
        dos = m.desplegar("tendencia", "T", ["BTC", "ETH"], D(1000), TENDENCIA)
        m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        assert m.eventos(dos.id)[0].texto == (
            "Desplegado con 1.000,00 USDC ficticios en Bitcoin y Ethereum."
        )
        assert mercado.fuente.seguidas == {
            ("BTC", True, ("1h",)),
            ("ETH", True, ("1h",)),
            ("BTC", True, ()),
        }


class TestCurvaYMantener:
    def test_un_punto_por_minuto_como_mucho_y_unos_100_en_la_tarjeta(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "R", ["BTC"], D(1000), REJILLA)
        for _ in range(6 * 300):
            mercado.reloj.avanzar(timedelta(seconds=10))
            m.paso()
        assert 300 <= len(bot.curva) <= 302
        guardada = Registro(tmp_path / "bots").curva(bot.id)
        assert len(guardada) == len(bot.curva)
        muestra = bot.curva_muestreada(mercado.reloj.t)
        assert len(muestra) <= 100
        assert muestra[0].at == bot.definicion.creado
        assert muestra[-1].at == mercado.reloj.t

    def test_mantener_y_peor_caida(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("periodica", "P", ["BTC"], D(1000), {"importe": "1000"})
        m.paso()
        mercado.precio("BTC", 120)
        m.paso()
        mercado.precio("BTC", 90)
        m.paso()
        mantener = bot.mantener()
        assert mantener == D(1000) * (1 - D("0.00045")) * D("0.9")
        assert bot.estado.peor_caida == pytest.approx(-0.25, abs=0.001)


def correr[T](corrutina: Coroutine[object, object, T]) -> T:
    """Un bucle de asyncio con el socket real solo mientras se crea (ver
    tests/integration/conftest.py): en Windows el bucle se despierta con un par de sockets."""
    bloqueado = socket.socket
    socket.socket = _SOCKET_REAL  # type: ignore[misc]
    try:
        bucle = asyncio.SelectorEventLoop()
    finally:
        socket.socket = bloqueado  # type: ignore[misc]
    try:
        return bucle.run_until_complete(corrutina)
    finally:
        bucle.close()


def test_arrancar_y_parar_el_motor_del_panel(tmp_path: Path) -> None:
    mercado = Mercado()
    mercado.precio("BTC", 100)
    previo = nuevo_motor(mercado, tmp_path)
    bot = previo.desplegar("periodica", "P", ["BTC"], D(1000), {})

    async def panel() -> int:
        await modulo_motor.arrancar(
            mercado.fuente, raiz=tmp_path / "bots", reloj=mercado.reloj, cada=0.001
        )
        activo = modulo_motor.activo()
        assert activo is not None
        for _ in range(200):
            await asyncio.sleep(0.005)
            if activo.bot(bot.id).estado.operaciones:
                break
        await modulo_motor.parar()
        return activo.bot(bot.id).estado.operaciones

    assert correr(panel()) == 1
    assert modulo_motor.activo() is None
    assert Registro(tmp_path / "bots").estado(bot.id).operaciones == 1


def test_sin_fuente_los_bots_no_operan_y_lo_dicen(tmp_path: Path) -> None:
    mercado = Mercado()
    mercado.precio("BTC", 100)
    bot = nuevo_motor(mercado, tmp_path).desplegar("periodica", "P", ["BTC"], D(1000), {})
    m = Motor(None, tmp_path / "bots", reloj=mercado.reloj, zona=UTC)
    m.cargar()
    m.paso()
    otro = m.bot(bot.id)
    assert otro.estado.operaciones == 0
    aviso = m.aviso(otro)
    assert aviso is not None
    assert aviso.startswith("Sin precios de Hyperliquid")
