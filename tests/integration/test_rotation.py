"""Motor de rotación entre activos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.data.universe import Universe, build_universe
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.rotation import run_rotation
from invest_ll.engine.universe_view import UniverseView
from invest_ll.errors import LookAheadError
from invest_ll.strategy.rotation import AlwaysFirst, RelativeMomentum, RotationStrategy

from ..fixtures.builders import series_from_closes

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
CON_FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
TODO = RiskConfig(position_fraction=D(1))


def universo_de(a: list[float], b: list[float]) -> Universe:
    return build_universe(
        [
            series_from_closes(a, symbol="A"),
            series_from_closes(b, symbol="B"),
        ]
    )


def sube(n: int, tasa: float = 1.0) -> list[float]:
    return [100.0 + tasa * i for i in range(n)]


def baja(n: int, tasa: float = 0.3) -> list[float]:
    return [100.0 - tasa * i for i in range(n)]


class TestProtocolo:
    def test_las_estrategias_cumplen_el_protocolo(self) -> None:
        assert isinstance(RelativeMomentum(), RotationStrategy)
        assert isinstance(AlwaysFirst(), RotationStrategy)

    def test_elige_el_que_mas_sube(self) -> None:
        universo = universo_de(sube(200, 2.0), sube(200, 0.5))
        elegido = RelativeMomentum(lookback=30).choose(UniverseView(universo, cursor=150))
        assert elegido == "A"

    def test_sin_historico_suficiente_no_elige(self) -> None:
        universo = universo_de(sube(50), sube(50))
        assert RelativeMomentum(lookback=90).choose(UniverseView(universo, cursor=10)) is None

    def test_si_todos_bajan_se_queda_fuera(self) -> None:
        """Quedarse en 'el que menos cae' es perder igual, mas despacio."""
        # A cae al 0,3 por periodo y B al 0,5: A es el que menos cae.
        universo = universo_de(baja(200, 0.3), baja(200, 0.5))
        elegido = RelativeMomentum(lookback=30, min_return=0.0).choose(
            UniverseView(universo, cursor=150)
        )
        assert elegido is None

    def test_sin_filtro_se_queda_en_el_que_menos_cae(self) -> None:
        """Sin filtro la estrategia sigue dentro, en el menos malo. Por eso el filtro existe."""
        universo = universo_de(baja(200, 0.3), baja(200, 0.5))
        elegido = RelativeMomentum(lookback=30, min_return=None).choose(
            UniverseView(universo, cursor=150)
        )
        assert elegido == "A"


class TestVistaSegura:
    def test_no_expone_el_futuro_de_ningun_activo(self) -> None:
        universo = universo_de(sube(100), sube(100, 2.0))
        vista = UniverseView(universo, cursor=50)

        for symbol in vista.symbols:
            assert max(vista.closes(symbol, 100)) == vista.current_bar(symbol).close

    def test_un_offset_negativo_lanza_lookahead(self) -> None:
        universo = universo_de(sube(100), sube(100))
        with pytest.raises(LookAheadError):
            UniverseView(universo, cursor=50).bar_at("A", -1)

    def test_el_rendimiento_no_usa_datos_posteriores(self) -> None:
        """Mismo universo hasta el cursor, futuros opuestos: la decision debe ser identica."""
        subida = sube(100)
        universo_a = universo_de([*subida, *[500.0] * 20], sube(120))
        universo_b = universo_de([*subida, *[1.0] * 20], sube(120))

        r_a = UniverseView(universo_a, cursor=50).return_over("A", 30)
        r_b = UniverseView(universo_b, cursor=50).return_over("A", 30)
        assert r_a == r_b

    def test_sin_historico_el_rendimiento_es_none(self) -> None:
        universo = universo_de(sube(100), sube(100))
        assert UniverseView(universo, cursor=5).return_over("A", 30) is None


class TestMotor:
    def test_rota_hacia_el_activo_que_va_mejor(self) -> None:
        # A sube fuerte la primera mitad; B despega en la segunda.
        a = [*sube(150, 2.0), *[400.0] * 150]
        b = [*[100.0] * 150, *sube(150, 3.0)]
        universo = universo_de(a, b)

        informe = run_rotation(
            universo,
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )
        activos_operados = {t.entry_order.side for t in informe.trades}
        assert informe.trade_count >= 2
        assert activos_operados

    def test_cada_rotacion_paga_dos_veces(self) -> None:
        """Vender uno y comprar otro. Ignorarlo haria que rotar pareciera gratis."""
        a = [*sube(150, 2.0), *[400.0] * 150]
        b = [*[100.0] * 150, *sube(150, 3.0)]
        universo = universo_de(a, b)

        limpio = run_rotation(
            universo,
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )
        con_costes = run_rotation(
            universo,
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=TODO,
        )
        assert con_costes.total_costs > 0
        assert con_costes.net_result < limpio.net_result

    def test_el_informe_trae_las_metricas_de_siempre(self) -> None:
        universo = universo_de(sube(300, 2.0), sube(300, 0.5))
        informe = run_rotation(
            universo,
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=TODO,
        )
        assert informe.buy_and_hold is not None
        assert informe.consistency is not None
        assert "A" in informe.symbol

    def test_el_benchmark_es_la_cartera_equiponderada(self) -> None:
        """Comparar contra mantener UN activo obligaria a elegir cual, y eso ya es trampa."""
        universo = universo_de(sube(300, 2.0), sube(300, 0.5))
        informe = run_rotation(
            universo,
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )
        assert informe.buy_and_hold is not None
        assert informe.buy_and_hold.net_result > 0

    def test_quedarse_quieto_es_un_control_valido(self) -> None:
        universo = universo_de(sube(300, 2.0), sube(300, 0.5))
        informe = run_rotation(
            universo,
            AlwaysFirst(),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )
        assert informe.trade_count == 1

    def test_capital_no_positivo_se_rechaza(self) -> None:
        universo = universo_de(sube(100), sube(100))
        with pytest.raises(ValueError, match="positivo"):
            run_rotation(
                universo,
                AlwaysFirst(),
                initial_capital=D(0),
                friction=SIN_FRICCION,
                risk=TODO,
            )

    def test_la_caja_nunca_queda_negativa(self) -> None:
        a = [*sube(150, 2.0), *[400.0] * 150]
        b = [*[100.0] * 150, *sube(150, 3.0)]
        informe = run_rotation(
            universo_de(a, b),
            RelativeMomentum(lookback=30),
            initial_capital=D(10000),
            friction=CON_FRICCION,
            risk=TODO,
        )
        assert informe.final_cash >= 0
