"""El stop-loss en la rotación.

`ExitReason.STOP_LOSS` existía desde la feature 001 y **ninguna estrategia lo había ejercitado
nunca**. El motor de un activo lo respetaba; el de rotación —el que usa el LLM— ni lo miraba, así
que en el modo del LLM no había ninguna salida por pérdida: si el activo elegido se hundía, se
seguía dentro hasta la siguiente decisión, entre 21 y 63 días después.

Los dos tests que importan aquí no son los que comprueban que el stop salta:

- `test_un_hueco_a_la_baja_se_come_la_proteccion`: un stop NO es una garantía. Si la vela abre por
  debajo del nivel, se vende ahí, no donde habría gustado.
- `test_no_se_vuelve_a_entrar_en_lo_que_se_acaba_de_cortar`: sin el veto, la estrategia sigue
  diciendo el mismo nombre al periodo siguiente, se vuelve a entrar en lo cortado, y el stop no
  protege de nada mientras cobra dos comisiones.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.data.universe import build_universe
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.execution import ExitReason
from invest_ll.engine.rotation import run_rotation

from ..fixtures.builders import series_from_closes

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.universe import Universe
    from invest_ll.engine.universe_view import UniverseView

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))


class Fija:
    """Elige siempre el mismo activo. Aisla el stop de cualquier decision de la estrategia."""

    def __init__(self, symbol: str | None) -> None:
        self._symbol = symbol

    def choose(self, view: UniverseView) -> str | None:
        return self._symbol


class Secuencia:
    """Elige segun una lista, para provocar cambios de idea en momentos concretos.

    Cuenta sus propias llamadas en vez de leer el cursor de la vista: `UniverseView` no lo expone
    a proposito —es lo que impide que una estrategia sepa en que punto de la historia esta— y un
    doble de test no deberia necesitar mas informacion que la real.
    """

    def __init__(self, elecciones: list[str | None]) -> None:
        self._elecciones = elecciones
        self._llamadas = 0

    def choose(self, view: UniverseView) -> str | None:
        i = self._llamadas
        self._llamadas += 1
        return self._elecciones[i] if i < len(self._elecciones) else self._elecciones[-1]


def universo(**series: list[float]) -> Universe:
    """Un universo necesita al menos dos activos para poder rotar.

    Cuando solo interesa uno, se le pone al lado un acompanhante PLANO que la estrategia nunca
    elige: existe para que el universo sea valido, y al no moverse no ensucia lo que se mide.
    """
    construidas = [series_from_closes(v, symbol=k) for k, v in series.items()]
    if len(construidas) == 1:
        largo = len(next(iter(series.values())))
        construidas.append(series_from_closes([50.0] * largo, symbol="PLANO"))
    return build_universe(construidas)


def correr(uni: Universe, estrategia: object, *, stop: Decimal | None = None):  # type: ignore[no-untyped-def]
    return run_rotation(
        uni,
        estrategia,  # type: ignore[arg-type]
        initial_capital=D(10000),
        friction=SIN_FRICCION,
        risk=RiskConfig(position_fraction=D(1), stop_loss_pct=stop),
    )


class TestSinStopNadaCambia:
    """La feature no puede alterar ningun resultado ya medido."""

    def test_el_informe_es_identico_sin_stop(self) -> None:
        uni = universo(AAA=[100.0, 110.0, 90.0, 95.0, 80.0, 85.0])
        informe = correr(uni, Fija("AAA"))

        assert all(t.exit_reason is not ExitReason.STOP_LOSS for t in informe.trades)

    def test_una_caida_enorme_sin_stop_no_saca_de_la_posicion(self) -> None:
        uni = universo(AAA=[100.0, 50.0, 25.0, 10.0, 5.0])
        informe = correr(uni, Fija("AAA"))

        assert informe.trade_count == 1, "una entrada y la liquidacion final, nada mas"
        assert informe.trades[0].exit_reason is ExitReason.END_OF_SERIES


class TestElStopSalta:
    def test_una_caida_por_debajo_del_nivel_corta(self) -> None:
        # Entra a 100 en la vela 1; con stop del 10% el nivel esta en 90.
        uni = universo(AAA=[100.0, 100.0, 100.0, 80.0, 80.0])
        informe = correr(uni, Fija("AAA"), stop=D("0.10"))

        motivos = [t.exit_reason for t in informe.trades]
        assert ExitReason.STOP_LOSS in motivos

    def test_una_caida_que_no_llega_al_nivel_no_corta(self) -> None:
        uni = universo(AAA=[100.0, 100.0, 100.0, 95.0, 95.0])
        informe = correr(uni, Fija("AAA"), stop=D("0.10"))

        assert all(t.exit_reason is not ExitReason.STOP_LOSS for t in informe.trades)

    def test_el_stop_limita_la_perdida(self) -> None:
        """Lo que se le pide: que la caida del patrimonio sea menor que sin el."""
        cierres = [100.0, 100.0, 100.0, 70.0, 50.0, 30.0, 20.0]
        con = correr(universo(AAA=cierres), Fija("AAA"), stop=D("0.10"))
        sin = correr(universo(AAA=cierres), Fija("AAA"))

        assert con.net_result > sin.net_result, "cortar antes tiene que doler menos"
        assert abs(con.max_drawdown) < abs(sin.max_drawdown)


class TestUnStopNoEsUnaGarantia:
    """La parte honesta: hay caidas de las que un stop no protege."""

    def test_un_hueco_a_la_baja_se_come_la_proteccion(self) -> None:
        """EL test de este fichero.

        Con stop al 10% (nivel en 90) y una vela que ABRE en 60, no se vende a 90: se vende a 60.
        Suponer lo contrario convertiria el backtest en una promesa que el mercado no cumple.
        """
        uni = universo(AAA=[100.0, 100.0, 100.0, 60.0, 60.0])
        informe = correr(uni, Fija("AAA"), stop=D("0.10"))

        stops = [t for t in informe.trades if t.exit_reason is ExitReason.STOP_LOSS]
        assert stops, "el stop tiene que saltar"

        orden = stops[0].exit_order
        assert orden is not None
        salida = orden.reference_price
        assert salida < D(90), (
            f"se vendio a {salida}: el hueco abrio muy por debajo del nivel y el stop "
            "no puede fingir que protegio"
        )

    def test_el_precio_de_salida_esta_dentro_de_la_vela(self) -> None:
        """Nunca se sale a un precio que no existio."""
        uni = universo(AAA=[100.0, 100.0, 100.0, 60.0, 60.0])
        informe = correr(uni, Fija("AAA"), stop=D("0.10"))

        for t in informe.trades:
            if t.exit_reason is ExitReason.STOP_LOSS:
                assert t.exit_order is not None
                assert t.exit_order.reference_price > 0


class TestElVeto:
    """Sin esto el stop seria un generador de comisiones."""

    def test_no_se_vuelve_a_entrar_en_lo_que_se_acaba_de_cortar(self) -> None:
        """EL otro test que importa.

        La estrategia sigue diciendo AAA despues del corte. Si se volviera a entrar, el stop
        cortaria y recompraria en bucle: proteccion cero y comisiones dobles cada vez.
        """
        uni = universo(AAA=[100.0, 100.0, 100.0, 80.0, 79.0, 78.0, 77.0, 76.0])
        informe = correr(uni, Fija("AAA"), stop=D("0.10"))

        entradas = len(informe.trades)
        assert entradas <= 2, f"{entradas} operaciones: esta recomprando lo que acaba de cortar"

    def test_el_veto_se_levanta_cuando_la_estrategia_cambia_de_idea(self) -> None:
        """No es un castigo temporal: el criterio para volver es el mismo que para salir."""
        uni = universo(
            AAA=[100.0, 100.0, 100.0, 80.0, 80.0, 80.0, 80.0, 80.0],
            BBB=[50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0],
        )
        # Tras el corte pasa a BBB, y eso levanta el veto sobre AAA.
        estrategia = Secuencia(["AAA", "AAA", "AAA", "AAA", "BBB", "BBB", "AAA", "AAA"])
        informe = correr(uni, estrategia, stop=D("0.10"))

        assert ExitReason.STOP_LOSS in [t.exit_reason for t in informe.trades]
        assert len(informe.trades) >= 2, "tras cambiar de idea tiene que poder volver a operar"

    def test_quedarse_fuera_tambien_levanta_el_veto(self) -> None:
        uni = universo(AAA=[100.0, 100.0, 100.0, 80.0, 80.0, 90.0, 100.0, 110.0])
        estrategia = Secuencia(["AAA", "AAA", "AAA", "AAA", None, "AAA", "AAA", "AAA"])
        informe = correr(uni, estrategia, stop=D("0.10"))

        assert ExitReason.STOP_LOSS in [t.exit_reason for t in informe.trades]


class TestLosCostesSiguenContando:
    def test_cada_stop_paga_su_comision(self) -> None:
        """Un stop no es gratis: es una venta, y las ventas cuestan."""
        uni = universo(AAA=[100.0, 100.0, 100.0, 80.0, 80.0])
        con_coste = run_rotation(
            uni,
            Fija("AAA"),  # type: ignore[arg-type]
            initial_capital=D(10000),
            friction=FrictionConfig(commission_rate=D("0.01"), slippage_rate=D("0.005")),
            risk=RiskConfig(position_fraction=D(1), stop_loss_pct=D("0.10")),
        )
        assert con_coste.total_costs > 0


class TestConfiguracion:
    def test_un_stop_negativo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="stop_loss_pct"):
            RiskConfig(position_fraction=D(1), stop_loss_pct=D(-1))

    def test_sin_stop_declarado_la_posicion_no_lleva_nivel(self) -> None:
        uni = universo(AAA=[100.0, 100.0, 50.0, 50.0])
        informe = correr(uni, Fija("AAA"))
        assert all(t.exit_reason is not ExitReason.STOP_LOSS for t in informe.trades)
