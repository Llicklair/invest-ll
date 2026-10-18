"""Los bots de pruebas y reales (docs/panel-v4-real.md §3), siempre contra `ConectorFalso`: nada sale
a un exchange de verdad. Límites antes de cada orden, id guardado antes de enviar, estado
desconocido, conciliación, pérdida máxima, activar real, «Parar todo lo real» y el límite diario."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, NoReturn

import pytest

from invest_ll.bots import real
from invest_ll.bots.decisiones import Decision, Orden
from invest_ll.bots.motor import CADA_CONCILIACION, CADA_PRECIO_EXCHANGE, Motor, limites_suben
from invest_ll.bots.plantillas import BotInvalidoError
from invest_ll.bots.registro import Limites
from invest_ll.exchanges.conector import ExchangeError, OrdenExchange
from invest_ll.exchanges.falso import ConectorFalso

from .bots_apoyo import Mercado

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.bots.decisiones import Situacion
    from invest_ll.bots.motor import Bot
    from invest_ll.exchanges.conector import Conector, Red

D = Decimal
PAR = "BTC/USDT"
REJILLA = {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"}
LIM = Limites(
    capital_max=D(500),
    orden_max=D(100),
    perdida_max_pct=0.2,
    vender_al_parar=True,
    operaciones_max_dia=5,
)


class Guion:
    """Una plantilla de mentira: en cada decisión da las órdenes que la prueba le ponga."""

    def __init__(self) -> None:
        self.cola: list[tuple[Orden, ...]] = []

    def __call__(self, _: Situacion) -> Decision:
        return Decision(ordenes=self.cola.pop(0) if self.cola else ())

    def compra(self, importe: str, coin: str = "BTC") -> None:
        self.cola.append((Orden(coin=coin, lado="compra", porque="prueba", importe=D(importe)),))

    def venta(self, coin: str = "BTC") -> None:
        self.cola.append((Orden(coin=coin, lado="venta", porque="prueba"),))


@dataclass
class Banco:
    """El motor con su mercado de Hyperliquid falso y dos exchanges falsos (pruebas y real)."""

    raiz: Path
    mercado: Mercado = field(default_factory=Mercado)
    falsos: dict[tuple[str, str], ConectorFalso] = field(
        default_factory=dict[tuple[str, str], ConectorFalso]
    )
    anotadas: list[tuple[OrdenExchange, str, str, str]] = field(
        default_factory=list[tuple[OrdenExchange, str, str, str]]
    )
    motor: Motor = field(init=False)

    def __post_init__(self) -> None:
        self.mercado.precio("BTC", 100)
        for red in ("pruebas", "real"):
            f = ConectorFalso(
                exchange_="binance",
                red_=red,
                saldo_inicial={"USDT": D(1000)},
                reloj=self.mercado.reloj,
            )
            f.poner_precio(PAR, D(100))
            self.falsos[("binance", red)] = f
        self.motor = self.nuevo_motor()

    def nuevo_motor(self) -> Motor:
        return Motor(
            self.mercado.fuente,
            self.raiz / "bots",
            reloj=self.mercado.reloj,
            zona=UTC,
            umbral_hueco=timedelta(days=3650),
            conector_de=self.conector,
            anotar_orden=lambda o, ex, red, bot: self.anotadas.append((o, ex, red, bot)),
            globales=self.raiz / "config" / "bots_real.json",
        )

    def conector(self, exchange: str, red: Red) -> Conector:
        f = self.falsos.get((exchange, red))
        if f is None:
            raise ExchangeError(f"{exchange} no está activo en {red}.")
        return f

    @property
    def pruebas(self) -> ConectorFalso:
        return self.falsos[("binance", "pruebas")]

    @property
    def real(self) -> ConectorFalso:
        return self.falsos[("binance", "real")]

    def desplegar(self, capital: str = "300", limites: Limites = LIM) -> tuple[Bot, Guion]:
        bot = self.motor.desplegar(
            "rejilla",
            "Rejilla",
            ["BTC"],
            D(capital),
            REJILLA,
            modo="pruebas",
            exchange="binance",
            limites=limites,
        )
        return bot, self.guion(bot)

    @staticmethod
    def guion(bot: Bot) -> Guion:
        g = Guion()
        bot.plantilla = replace(bot.plantilla, decidir=g, aplicar=None)
        return g

    def precio(self, valor: float, *, conector: ConectorFalso | None = None) -> None:
        """Mueve el precio en Hyperliquid y en el exchange, y deja pasar lo que tarda en leerse."""
        self.mercado.precio("BTC", valor)
        for f in [conector] if conector is not None else self.falsos.values():
            f.poner_precio(PAR, D(str(valor)))
        self.mercado.reloj.avanzar(CADA_PRECIO_EXCHANGE)

    def tipos(self, bot: Bot) -> list[str]:
        return [e.tipo for e in self.motor.eventos(bot.id)]


@pytest.fixture
def banco(tmp_path: Path) -> Banco:
    return Banco(tmp_path)


class TestDesplegar:
    def test_en_pruebas_con_exchange_y_limites(self, banco: Banco) -> None:
        bot, _ = banco.desplegar()
        d = bot.definicion
        assert (d.modo, d.exchange, d.limites) == ("pruebas", "binance", LIM)
        assert bot.estado.ultimos_precios["BTC"] == D(100)
        assert "en pruebas en Binance" in banco.motor.eventos(bot.id)[0].texto
        # Lo que se lee de disco es lo mismo.
        cargado = banco.nuevo_motor()
        cargado.cargar()
        assert cargado.bot(bot.id).definicion == d

    @pytest.mark.parametrize(
        ("cambio", "texto"),
        [
            ({"exchange": None}, "necesita su exchange"),
            ({"limites": None}, "necesita sus límites"),
            ({"capital": D(600)}, "pasa de su capital máximo"),
            ({"exchange": "kraken"}, "no está activo"),
        ],
    )
    def test_lo_que_falta_se_dice(
        self, banco: Banco, cambio: dict[str, object], texto: str
    ) -> None:
        args: dict[str, object] = {"capital": D(300), "exchange": "binance", "limites": LIM}
        args.update(cambio)
        with pytest.raises(BotInvalidoError, match=texto):
            banco.motor.desplegar(
                "rejilla",
                "Rejilla",
                ["BTC"],
                args["capital"],  # pyright: ignore[reportArgumentType]
                REJILLA,
                modo="pruebas",
                exchange=args["exchange"],  # pyright: ignore[reportArgumentType]
                limites=args["limites"],  # pyright: ignore[reportArgumentType]
            )

    def test_sin_saldo_bastante_no_se_crea(self, banco: Banco) -> None:
        banco.pruebas.saldos["USDT"] = D(100)
        with pytest.raises(BotInvalidoError, match="No hay saldo bastante"):
            banco.desplegar()

    def test_con_dinero_real_no_se_crea(self, banco: Banco) -> None:
        with pytest.raises(BotInvalidoError, match="no se crea con dinero real"):
            banco.motor.desplegar(
                "rejilla",
                "R",
                ["BTC"],
                D(100),
                REJILLA,
                modo="real",
                exchange="binance",
                limites=LIM,
            )


class TestOrdenes:
    def test_compra_y_venta_salen_al_exchange(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("50")
        banco.motor.paso()
        assert len(banco.pruebas.creadas) == 1
        orden = banco.pruebas.creadas[0]
        assert orden.id_cliente.startswith("ilb")
        assert (orden.lado, orden.tipo, orden.estado) == ("compra", "mercado", "ejecutada")
        assert bot.cuenta.posiciones["BTC"].cantidad == orden.ejecutada
        assert bot.cuenta.efectivo + bot.cuenta.posiciones["BTC"].coste == D(300)
        assert banco.pruebas.saldos["BTC"] == orden.ejecutada
        assert banco.anotadas == [(orden, "binance", "pruebas", bot.id)]
        assert bot.estado.operaciones_hoy == 1
        assert bot.estado.pausa is None

        guion.venta()
        banco.motor.paso()
        venta = banco.pruebas.creadas[1]
        assert (venta.lado, venta.cantidad) == ("venta", orden.ejecutada)
        assert "BTC" not in bot.cuenta.posiciones
        assert [o.lado for o in banco.motor.operaciones(bot.id)] == ["venta", "compra"]

    def test_no_opera_hasta_cuadrar_el_saldo_al_cargar(self, banco: Banco) -> None:
        bot, _ = banco.desplegar()
        del banco.falsos[("binance", "pruebas")]
        cargado = banco.nuevo_motor()
        cargado.cargar()
        Banco.guion(cargado.bot(bot.id)).compra("50")
        cargado.paso()
        aviso = cargado.aviso(cargado.bot(bot.id))
        assert aviso is not None
        assert "No se pudo leer el saldo" in aviso

    def test_lo_ejecutado_guarda_la_comision_en_la_moneda_comprada(self) -> None:
        orden = OrdenExchange(
            id_exchange="1",
            id_cliente="x",
            par=PAR,
            lado="compra",
            tipo="mercado",
            cantidad=D(1),
            ejecutada=D(1),
            precio_medio=D(100),
            comision=D("0.001"),
            comision_moneda="BTC",
            estado="ejecutada",
            at=datetime(2026, 10, 1, tzinfo=UTC),
        )
        hecha = real.hecha_de(orden, "BTC")
        assert hecha is not None
        assert hecha.cantidad == D("0.999")
        assert hecha.importe + hecha.comision == D(100)


class TestLimites:
    def test_una_compra_mayor_que_el_maximo_no_sale_y_se_dice_una_vez(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("150")
        guion.compra("150")
        banco.motor.paso()
        banco.motor.paso()
        assert banco.pruebas.creadas == []
        assert banco.tipos(bot).count("limite") == 1
        assert "máximo por orden" in banco.motor.eventos(bot.id)[0].texto

    def test_no_gasta_mas_que_su_capital_maximo(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        for _ in range(2):
            guion.compra("100")
            banco.motor.paso()
        # Bajar el capital máximo por debajo de lo invertido: no vende, pero no compra más.
        banco.motor.cambiar_limites(bot.id, replace(LIM, capital_max=D(250)))
        guion.compra("100")
        banco.motor.paso()
        assert len(banco.pruebas.creadas) == 2
        assert "capital máximo" in banco.motor.eventos(bot.id)[0].texto
        assert "Límites cambiados" in banco.motor.eventos(bot.id)[1].texto

    def test_operaciones_del_dia_frenan_compras_pero_no_ventas(self, banco: Banco) -> None:
        bot, guion = banco.desplegar(limites=replace(LIM, operaciones_max_dia=2))
        guion.compra("20")
        guion.compra("20")
        guion.compra("20")
        guion.venta()
        for _ in range(4):
            banco.motor.paso()
        assert [o.lado for o in banco.pruebas.creadas] == ["compra", "compra", "venta"]
        assert "máximo por día" in next(
            e.texto for e in banco.motor.eventos(bot.id) if e.tipo == "limite"
        )
        banco.mercado.reloj.avanzar(timedelta(days=1))
        guion.compra("20")
        banco.motor.paso()
        assert len(banco.pruebas.creadas) == 4
        assert bot.estado.operaciones_hoy == 1

    def test_al_perder_su_maximo_se_para_y_vende_todo(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("100")
        banco.motor.paso()
        banco.precio(10)
        banco.motor.paso()
        assert bot.estado.estado == "parado"
        assert "BTC" not in bot.cuenta.posiciones
        assert banco.pruebas.creadas[-1].lado == "venta"
        assert "se para" in next(e.texto for e in banco.motor.eventos(bot.id) if e.tipo == "limite")

    def test_subir_y_bajar_limites(self) -> None:
        assert not limites_suben(LIM, replace(LIM, orden_max=D(50)))
        assert limites_suben(LIM, replace(LIM, orden_max=D(150)))
        assert limites_suben(LIM, replace(LIM, vender_al_parar=False))
        assert limites_suben(None, LIM)


class TestEstadoDesconocido:
    def test_si_se_corta_tras_ejecutar_se_pausa_y_al_reanudar_se_apunta(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        banco.pruebas.cortar_siguiente(ejecutada=True)
        guion.compra("50")
        banco.motor.paso()
        pausa = bot.estado.pausa
        assert pausa is not None
        assert (pausa.motivo, pausa.coin, pausa.lado) == ("desconocido", "BTC", "compra")
        assert bot.cuenta.posiciones == {}
        assert "desconocido" in banco.tipos(bot)
        # En pausa no decide: la orden siguiente no sale.
        guion.compra("50")
        banco.motor.paso()
        assert len(banco.pruebas.creadas) == 1
        banco.motor.reanudar_bot(bot.id)
        assert bot.estado.pausa is None
        assert bot.cuenta.posiciones["BTC"].cantidad == banco.pruebas.creadas[0].ejecutada
        assert len(banco.anotadas) == 1

    def test_si_no_llego_a_salir_no_se_apunta_nada(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        banco.pruebas.cortar_siguiente(ejecutada=False)
        guion.compra("50")
        banco.motor.paso()
        assert bot.estado.pausa is not None
        banco.motor.reanudar_bot(bot.id)
        assert bot.estado.pausa is None
        assert bot.cuenta.posiciones == {}
        assert "no llegó a ejecutarse" in banco.motor.eventos(bot.id)[1].texto

    def test_el_id_se_guarda_antes_de_enviar(
        self, banco: Banco, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot, guion = banco.desplegar()

        def muere(*_: object, **__: object) -> NoReturn:
            raise RuntimeError("el proceso se muere a mitad")

        monkeypatch.setattr(banco.pruebas, "enviar", muere)
        guion.compra("50")
        banco.motor.paso()
        cargado = banco.nuevo_motor()
        cargado.cargar()
        pausa = cargado.bot(bot.id).estado.pausa
        assert pausa is not None
        assert pausa.motivo == "desconocido"
        assert pausa.id_cliente is not None
        assert pausa.id_cliente.startswith("ilb")
        with pytest.raises(real.NoSePuedeError, match="orden de la que no se sabe"):
            cargado.borrar_bot(bot.id)


class TestConciliacion:
    def test_si_falta_algo_en_el_exchange_se_pausa(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("50")
        banco.motor.paso()
        tenia = banco.pruebas.saldos["BTC"]
        banco.pruebas.saldos["BTC"] = D(0)
        banco.mercado.reloj.avanzar(CADA_CONCILIACION)
        banco.motor.paso()
        pausa = bot.estado.pausa
        assert pausa is not None
        assert pausa.motivo == "conciliacion"
        assert pausa.diferencia is not None
        assert pausa.diferencia.startswith(
            "Bitcoin: los bots creen tener 0,49455 y en Binance hay 0"
        )
        with pytest.raises(real.NoSePuedeError, match="Sigue sin cuadrar"):
            banco.motor.reanudar_bot(bot.id)
        banco.pruebas.saldos["BTC"] = tenia
        banco.motor.reanudar_bot(bot.id)
        assert bot.estado.pausa is None

    def test_lo_de_marcos_fuera_de_los_bots_no_descuadra(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("50")
        banco.motor.paso()
        banco.pruebas.saldos["BTC"] += D(3)
        banco.mercado.reloj.avanzar(CADA_CONCILIACION)
        banco.motor.paso()
        assert bot.estado.pausa is None


class TestDineroReal:
    def activar(self, banco: Banco) -> Bot:
        ficticio = banco.motor.desplegar("rejilla", "Rejilla", ["BTC"], D(1000), REJILLA)
        banco.motor.paso()
        return banco.motor.activar_real(ficticio.id, "binance", LIM)

    def test_activar_empieza_de_cero_con_su_capital_maximo(self, banco: Banco) -> None:
        bot = self.activar(banco)
        d = bot.definicion
        assert (d.modo, d.exchange, d.capital, d.limites) == ("real", "binance", D(500), LIM)
        assert bot.cuenta.efectivo == D(500)
        assert banco.tipos(bot)[0] == "real"
        archivadas = list((banco.raiz / "bots" / bot.id).glob("curva-ficticio-*.jsonl"))
        assert len(archivadas) == 1
        assert banco.motor.aviso(bot) == "Comprobando el saldo en su exchange antes de operar."
        Banco.guion(bot).compra("50")
        banco.motor.paso()
        assert len(banco.real.creadas) == 1
        assert banco.pruebas.creadas == []

    def test_sin_saldo_real_no_se_activa(self, banco: Banco) -> None:
        banco.real.saldos["USDT"] = D(100)
        with pytest.raises(BotInvalidoError, match="No hay saldo bastante"):
            self.activar(banco)

    def test_un_bot_de_pruebas_con_monedas_no_se_activa(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("50")
        banco.motor.paso()
        with pytest.raises(real.NoSePuedeError, match="aún tiene monedas"):
            banco.motor.activar_real(bot.id, "binance", LIM)

    def test_parar_todo_lo_real(self, banco: Banco) -> None:
        bot = self.activar(banco)
        de_pruebas, _ = banco.desplegar()
        banco.real.enviar(PAR, "compra", D("0.1"), id_cliente="manual", tipo="limite", precio=D(50))
        banco.real.enviar(
            PAR, "compra", D("0.1"), id_cliente="ilbsuya", tipo="limite", precio=D(50)
        )
        bot.abiertas.add((PAR, "ilbsuya"))

        parados, canceladas, avisos = banco.motor.parar_todo_real()
        assert (parados, canceladas, avisos) == ([bot.id], 1, [])
        assert banco.real.ordenes["manual"].estado == "abierta", "las de Marcos no se tocan"
        assert banco.real.ordenes["ilbsuya"].estado == "cancelada"
        assert de_pruebas.estado.estado == "en_marcha"
        assert banco.motor.globales().parado_todo
        with pytest.raises(real.NoSePuedeError, match="Parar todo lo real"):
            banco.motor.reanudar_bot(bot.id)
        with pytest.raises(real.NoSePuedeError, match="Parar todo lo real"):
            banco.motor.activar_real(de_pruebas.id, "binance", LIM)

        banco.motor.reanudar_todo_real()
        assert bot.estado.estado == "parado", "cada uno se reanuda a mano"
        banco.motor.reanudar_bot(bot.id)
        assert bot.estado.estado == "en_marcha"

    def test_al_llegar_al_limite_diario_se_para_todo(self, banco: Banco) -> None:
        bot = self.activar(banco)
        banco.motor.cambiar_limite_diario(D(20))
        Banco.guion(bot).compra("100")
        banco.motor.paso()
        assert bot.estado.estado == "en_marcha"
        banco.precio(70)
        banco.motor.paso()
        assert banco.motor.perdida_hoy() >= D(20)
        assert bot.estado.estado == "parado"
        g = banco.motor.globales()
        assert g.parado_todo
        assert g.motivo is not None
        assert "límite diario" in g.motivo

    def test_borrar_no_vende_y_pide_pararlo(self, banco: Banco) -> None:
        bot, guion = banco.desplegar()
        guion.compra("50")
        banco.motor.paso()
        with pytest.raises(real.NoSePuedeError, match="Páralo antes"):
            banco.motor.borrar_bot(bot.id)
        banco.motor.parar_bot(bot.id)
        tenia = banco.pruebas.saldos["BTC"]
        banco.motor.borrar_bot(bot.id)
        assert banco.pruebas.saldos["BTC"] == tenia
        assert len(banco.pruebas.creadas) == 1


class TestGlobales:
    def test_se_guardan_y_se_leen(self, tmp_path: Path) -> None:
        ruta = tmp_path / "bots_real.json"
        assert real.leer_globales(ruta) == real.Globales()
        g = real.Globales(D("250.5"), True, datetime(2026, 10, 1, tzinfo=UTC), "Lo paraste tú.")
        real.guardar_globales(g, ruta)
        assert real.leer_globales(ruta) == g
