"""Aportaciones periódicas."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.data.universe import Universe, build_universe
from invest_ll.engine.config import FrictionConfig
from invest_ll.engine.dca import run_dca

from ..fixtures.builders import series_from_closes

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
CON_FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))


def universo(a: list[float], b: list[float]) -> Universe:
    return build_universe([series_from_closes(a, symbol="A"), series_from_closes(b, symbol="B")])


def sube(n: int, tasa: float = 1.0) -> list[float]:
    return [100.0 + tasa * i for i in range(n)]


def baja(n: int, tasa: float = 0.3) -> list[float]:
    return [200.0 - tasa * i for i in range(n)]


def plano(n: int) -> list[float]:
    return [100.0] * n


class TestAportaciones:
    def test_aporta_con_la_periodicidad_indicada(self) -> None:
        informe = run_dca(
            universo(plano(200), plano(200)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.contributions == 10
        assert informe.total_contributed == D(1000)

    def test_en_un_mercado_plano_se_conserva_lo_aportado(self) -> None:
        informe = run_dca(
            universo(plano(200), plano(200)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert abs(informe.net_result) < D("0.01")

    def test_en_un_mercado_alcista_se_gana(self) -> None:
        informe = run_dca(
            universo(sube(300, 2.0), sube(300, 2.0)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.net_result > 0

    def test_en_un_mercado_bajista_se_pierde(self) -> None:
        """No es magia: aportar poco a poco en un mercado que cae sigue perdiendo."""
        informe = run_dca(
            universo(baja(300, 0.4), baja(300, 0.4)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.net_result < 0

    def test_nunca_se_vende(self) -> None:
        """El plan es acumular. Solo hay compras, y sus comisiones."""
        informe = run_dca(
            universo(sube(300), sube(300)),
            contribution=D(100),
            friction=CON_FRICCION,
            every_periods=20,
        )
        # Con solo compras, el coste es proporcional a lo aportado y muy pequeño.
        assert 0 < informe.total_costs < informe.total_contributed * D("0.01")


class TestBenchmark:
    def test_se_compara_con_invertir_todo_de_golpe(self) -> None:
        informe = run_dca(
            universo(sube(300, 2.0), sube(300, 2.0)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.lump_sum_value > 0

    def test_en_un_mercado_que_solo_sube_gana_invertir_de_golpe(self) -> None:
        """Lo esperable: entrar antes con todo el dinero rinde mas si el mercado solo sube."""
        informe = run_dca(
            universo(sube(300, 2.0), sube(300, 2.0)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert not informe.beats_lump_sum

    def test_si_el_mercado_cae_y_recupera_gana_aportar_poco_a_poco(self) -> None:
        """El caso que justifica la estrategia: comprar barato durante la caida."""
        v = [*baja(150, 0.6), *[110.0 + i * 0.6 for i in range(150)]]
        informe = run_dca(
            universo(v, v), contribution=D(100), friction=SIN_FRICCION, every_periods=20
        )
        assert informe.beats_lump_sum


class TestRegularidadHonesta:
    def test_la_curva_analizada_es_la_ganancia_no_el_saldo(self) -> None:
        """La trampa que este modulo evita.

        Sobre el saldo, un mercado bajista daria meses en verde igualmente, porque cada mes entra
        dinero nuevo. Sobre la ganancia, no.
        """
        informe = run_dca(
            universo(baja(400, 0.3), baja(400, 0.3)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.consistency.periods > 0
        assert informe.consistency.positive_ratio < 0.5

    def test_el_drawdown_es_de_la_ganancia(self) -> None:
        informe = run_dca(
            universo(baja(400, 0.3), baja(400, 0.3)),
            contribution=D(100),
            friction=SIN_FRICCION,
            every_periods=20,
        )
        assert informe.max_drawdown < 0


class TestValidacion:
    def test_aportacion_no_positiva_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="positiva"):
            run_dca(
                universo(plano(100), plano(100)),
                contribution=D(0),
                friction=SIN_FRICCION,
            )

    def test_periodicidad_invalida_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="al menos 1"):
            run_dca(
                universo(plano(100), plano(100)),
                contribution=D(100),
                friction=SIN_FRICCION,
                every_periods=0,
            )


def test_el_informe_es_imprimible_en_consola_windows() -> None:
    informe = run_dca(
        universo(sube(300), sube(300)),
        contribution=D(100),
        friction=CON_FRICCION,
        every_periods=20,
    )
    informe.render().encode("cp1252")
