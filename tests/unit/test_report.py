"""T023 — el informe no puede mentir (FR-011..FR-014, SC-002, SC-004)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import DEFAULT_MIN_TRADES, BacktestReport

D = Decimal

FRICTION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RISK = RiskConfig(position_fraction=D("0.2"))


NET_POR_DEFECTO = D(100)


def build_report(
    *, trade_count: int, net: Decimal | None = None, wins: float = 0.6
) -> BacktestReport:
    net = NET_POR_DEFECTO if net is None else net
    return BacktestReport(
        net_result=net,
        expectancy=net / trade_count if trade_count else D(0),
        max_drawdown=D(-10),
        trade_count=trade_count,
        total_costs=D(5),
        win_rate=wins,
        trades=(),
        friction=FRICTION,
        risk=RISK,
        symbol="TEST",
        min_trades=DEFAULT_MIN_TRADES,
        data_warnings=(),
    )


class TestMetricasObligatorias:
    def test_no_se_puede_construir_sin_las_seis_metricas(self) -> None:
        """SC-002: un informe incompleto no llega a existir."""
        with pytest.raises(TypeError):
            BacktestReport(net_result=D(100))  # type: ignore[call-arg]

    def test_informe_es_inmutable(self) -> None:
        report = build_report(trade_count=50)
        with pytest.raises((AttributeError, TypeError)):
            report.net_result = D(0)  # type: ignore[misc]


class TestConcluyente:
    def test_muestra_suficiente_es_concluyente(self) -> None:
        assert build_report(trade_count=50).conclusive

    def test_muestra_insuficiente_no_es_concluyente(self) -> None:
        assert not build_report(trade_count=5).conclusive

    def test_resultado_excelente_con_pocas_operaciones_sigue_sin_concluir(self) -> None:
        """FR-013: ganar mucho con 3 operaciones no demuestra nada."""
        report = build_report(trade_count=3, net=D(100000), wins=1.0)
        assert not report.conclusive
        assert report.inconclusive_reason is not None

    def test_cero_operaciones_no_es_neutro_sino_no_concluyente(self) -> None:
        report = build_report(trade_count=0, net=D(0))
        assert not report.conclusive
        assert report.inconclusive_reason is not None

    def test_el_motivo_explica_cuantas_faltan(self) -> None:
        report = build_report(trade_count=5)
        assert report.inconclusive_reason is not None
        assert "5" in report.inconclusive_reason

    def test_concluyente_no_tiene_motivo(self) -> None:
        assert build_report(trade_count=50).inconclusive_reason is None


class TestPresentacionHonesta:
    def test_el_win_rate_no_encabeza_la_salida(self) -> None:
        """FR-012: la primera cifra que se lee no puede ser la más engañosa."""
        texto = build_report(trade_count=50).render()
        primera_linea_con_cifra = next(
            linea for linea in texto.splitlines() if any(c.isdigit() for c in linea)
        )
        assert "win rate" not in primera_linea_con_cifra.lower()

    def test_la_salida_incluye_las_seis_metricas(self) -> None:
        texto = build_report(trade_count=50).render().lower()
        for etiqueta in ("resultado", "expectancy", "drawdown", "operaciones", "coste", "win rate"):
            assert etiqueta in texto

    def test_no_concluyente_avisa_antes_que_las_cifras(self) -> None:
        """Un resultado no concluyente no debe poder leerse como bueno de un vistazo."""
        texto = build_report(trade_count=3, net=D(100000))
        render = texto.render()
        pos_aviso = render.lower().find("no concluyente")
        pos_resultado = render.lower().find("resultado")
        assert pos_aviso != -1
        assert pos_aviso < pos_resultado

    def test_los_parametros_aplicados_aparecen(self) -> None:
        """FR-008: los costes usados forman parte del veredicto."""
        texto = build_report(trade_count=50).render()
        assert "0.001" in texto
