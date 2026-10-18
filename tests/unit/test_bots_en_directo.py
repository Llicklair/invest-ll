"""Los bots en directo (docs/panel-v5.md §4): el feed de movimientos del motor, las métricas
sacadas de las operaciones y "qué hará después", con `FuenteFalsa` y un reloj a mano."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.bots import motor as modulo_motor
from invest_ll.bots.cuenta import Posicion
from invest_ll.bots.metricas import metricas, resultados
from invest_ll.bots.motor import Motor
from invest_ll.bots.pendientes import pendientes, proximo_cierre
from invest_ll.bots.registro import Operacion

from .bots_apoyo import INICIO, Mercado

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator
    from pathlib import Path

    from invest_ll.bots.decisiones import Lado

D = Decimal
REJILLA = {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"}


@pytest.fixture(autouse=True)
def sin_motor_del_panel() -> Iterator[None]:
    yield
    modulo_motor.usar(None)


def nuevo_motor(mercado: Mercado, raiz: Path) -> Motor:
    return Motor(mercado.fuente, raiz / "bots", reloj=mercado.reloj, zona=UTC)


def op(lado: Lado, cantidad: str, precio: str, *, coin: str = "BTC", minutos: int = 0) -> Operacion:
    c, p = D(cantidad), D(precio)
    return Operacion(
        at=INICIO + timedelta(minutes=minutos),
        coin=coin,
        lado=lado,
        cantidad=c,
        precio=p,
        importe=c * p,
        comision=D("0.1"),
        motivo="prueba",
    )


class TestResultados:
    def test_una_venta_gana_lo_cobrado_menos_lo_que_costo(self) -> None:
        # Compra 2 a 100 (200 + 0,1 de comisión) y vende 1 a 110: se lleva la mitad del coste.
        r = resultados([op("compra", "2", "100"), op("venta", "1", "110", minutos=1)])
        assert r == [None, D("110") - D("0.1") - D("100.05")]

    def test_vender_todo_se_lleva_todo_el_coste(self) -> None:
        ops = [
            op("compra", "1", "100"),
            op("compra", "1", "120", minutos=1),
            op("venta", "2", "105", minutos=2),
        ]
        assert resultados(ops)[-1] == D("210") - D("0.1") - D("220.2")

    def test_cada_moneda_lleva_su_coste(self) -> None:
        ops = [
            op("compra", "1", "100"),
            op("compra", "10", "2", coin="SOL", minutos=1),
            op("venta", "10", "3", coin="SOL", minutos=2),
        ]
        assert resultados(ops)[-1] == D("30") - D("0.1") - D("20.1")

    def test_vender_lo_que_no_constaba_no_tiene_resultado(self) -> None:
        assert resultados([op("venta", "1", "100")]) == [None]


class TestMetricas:
    def test_aciertos_factor_y_medias(self) -> None:
        ops = [
            op("compra", "1", "100"),
            op("venta", "1", "110", minutos=10),  # +9,8
            op("compra", "1", "100", minutos=20),
            op("venta", "1", "95", minutos=30),  # -5,2
        ]
        m = metricas(ops, desde=INICIO, ahora=INICIO + timedelta(days=2), posiciones={}, precios={})
        assert m.operaciones == 4
        assert (m.compras, m.ventas, m.cerradas) == (2, 2, 2)
        assert m.aciertos == pytest.approx(0.5)
        assert m.factor_beneficio == pytest.approx(9.8 / 5.2)
        assert m.ganancia_media == D("9.8")
        assert m.perdida_media == D("-5.2")
        assert m.realizada == D("4.6")
        assert m.comisiones == D("0.4")
        assert m.operaciones_dia == pytest.approx(2.0)
        assert m.sin_realizar == D(0)
        assert m.aviso is not None
        assert "2 ventas cerradas" in m.aviso

    def test_tiempo_dentro_y_lo_que_ganaria_si_vendiera(self) -> None:
        ops = [op("compra", "1", "100"), op("venta", "1", "101", minutos=60)]
        ops.append(op("compra", "2", "100", minutos=180))
        m = metricas(
            ops,
            desde=INICIO,
            ahora=INICIO + timedelta(hours=4),
            posiciones={"BTC": Posicion(D(2), D("200.1"))},
            precios={"BTC": D(105)},
        )
        # Dentro de 0:00 a 1:00 y de 3:00 a 4:00: la mitad del tiempo.
        assert m.tiempo_dentro == pytest.approx(0.5)
        assert m.sin_realizar == D("9.9")
        assert m.operaciones_dia is None  # aún no lleva un día

    def test_sin_operar_lo_dice(self) -> None:
        m = metricas([], desde=INICIO, ahora=INICIO, posiciones={}, precios={})
        assert m.aciertos is None
        assert m.factor_beneficio is None
        assert m.aviso == "Aún no ha operado: no hay nada que medir."

    def test_sin_perdidas_no_hay_factor(self) -> None:
        ops = [op("compra", "1", "100"), op("venta", "1", "110", minutos=1)]
        m = metricas(ops, desde=INICIO, ahora=INICIO, posiciones={}, precios={})
        assert m.factor_beneficio is None
        assert m.aciertos == 1.0


class TestActividad:
    def test_cada_operacion_y_cada_evento_entran_en_el_feed(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)
        numero, lista = m.actividad()
        assert [x.tipo for x in lista] == ["arranque"]
        for p in (100.0, 106.0):
            mercado.precio("BTC", p)
            mercado.reloj.avanzar(timedelta(seconds=1))
            m.paso()
        nuevo, recientes = m.actividad(desde=numero)
        assert nuevo > numero
        tipos = [x.tipo for x in recientes]
        assert tipos[0] == "venta"  # el más reciente primero
        assert "compra" in tipos
        venta = recientes[0]
        assert venta.bot_id == bot.id
        assert venta.bot_nombre == "Rejilla"
        assert venta.resultado is not None
        assert venta.resultado > 0  # vendió más caro de lo que compró
        # El resultado del feed es el mismo que sale de repasar las operaciones del disco.
        repaso = resultados(m.todas_las_operaciones(bot.id))
        assert venta.resultado == repaso[-1]

    def test_al_reabrir_el_feed_sale_del_disco_con_los_mismos_ids(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        m.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)
        for p in (100.0, 106.0, 97.0):
            mercado.precio("BTC", p)
            mercado.reloj.avanzar(timedelta(seconds=1))
            m.paso()
        _, antes = m.actividad()
        otro = nuevo_motor(mercado, tmp_path)
        otro.cargar()
        _, despues = otro.actividad()
        assert [x.id for x in despues] == [x.id for x in antes]
        assert [x.resultado for x in despues] == [x.resultado for x in antes]

    def test_por_bot_y_al_borrarlo_se_van_sus_movimientos(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        a = m.desplegar("rejilla", "A", ["BTC"], D(1000), REJILLA)
        b = m.desplegar("rejilla", "B", ["BTC"], D(1000), REJILLA)
        assert {x.bot_id for x in m.actividad(bot_id=a.id)[1]} == {a.id}
        m.borrar_bot(a.id)
        assert {x.bot_id for x in m.actividad()[1]} == {b.id}


class TestPendientes:
    def test_la_rejilla_cuenta_sus_escalones(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)
        assert pendientes(bot, m.ahora(), {}, UTC)[0].tipo == "mirar"  # aún no ha arrancado
        m.paso()
        lista = pendientes(bot, m.ahora(), {}, UTC)
        # Escalones de 5: compró los de encima de 100 (100-105 y 105-110), espera los de abajo.
        assert [(p.tipo, p.precio) for p in lista] == [
            ("venta", D(110)),
            ("venta", D(105)),
            ("compra", D(95)),
            ("compra", D(90)),
        ]
        assert lista[-1].texto == "Comprará el escalón 1 (unos 250,00 USDC) si baja a 90,00."
        assert lista[0].texto.startswith("Venderá el escalón 4 (")

    def test_la_periodica_dice_su_proxima_compra(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar(
            "periodica", "P", ["BTC"], D(1000), {"importe": "100", "cada_horas": "24"}
        )
        m.paso()
        [p] = pendientes(bot, m.ahora(), {}, UTC)
        assert p.tipo == "compra"
        assert p.cuando == m.ahora() + timedelta(hours=24)
        assert p.importe == D(100)
        assert "Próxima compra el " in p.texto
        assert "100,00 USDC de Bitcoin" in p.texto

    def test_bitcoin_con_freno_dice_el_precio_que_lo_hara_vender(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.poner("BTC", "1d", [100.0 + i for i in range(40)])
        mercado.al_cierre(35)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("btc-freno", "Freno", ["BTC"], D(1000), {})
        m.paso()
        assert bot.cuenta.posiciones  # sube: está dentro
        [p] = pendientes(bot, m.ahora(), m.velas_de(bot), UTC)
        assert p.tipo == "venta"
        # Cerradas las velas 0 a 35 (100…135): al cerrar la 36, "hace 30 días" será la 6.
        assert p.precio == D(106)
        assert "venderá todo su Bitcoin si vale menos de 106,00 USDC" in p.texto

    def test_parado_no_hara_nada(self, tmp_path: Path) -> None:
        mercado = Mercado()
        mercado.precio("BTC", 100)
        m = nuevo_motor(mercado, tmp_path)
        bot = m.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)
        m.parar_bot(bot.id)
        [p] = pendientes(bot, m.ahora(), {}, UTC)
        assert p.tipo == "nada"

    def test_el_proximo_cierre_de_una_vela(self) -> None:
        ahora = datetime(2026, 10, 17, 23, 7, tzinfo=UTC)
        assert proximo_cierre("15m", ahora) == datetime(2026, 10, 17, 23, 15, tzinfo=UTC)
        assert proximo_cierre("1d", ahora) == datetime(2026, 10, 18, tzinfo=UTC)
        assert proximo_cierre("1M", ahora) is None
