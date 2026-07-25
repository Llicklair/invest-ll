"""T024 — configuración de fricción y riesgo (FR-007, FR-008, FR-026).

El Principio IV se hace cumplir por la firma: no existe un backtest sin costes declarados.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.engine.config import FrictionConfig, RiskConfig


class TestFrictionConfig:
    def test_no_se_puede_construir_sin_declarar_costes(self) -> None:
        """Cero comisiones debe ser una decisión escrita, nunca un descuido."""
        with pytest.raises(TypeError):
            FrictionConfig()  # type: ignore[call-arg]

    def test_costes_explicitos_se_aceptan(self) -> None:
        friction = FrictionConfig(commission_rate=Decimal("0.001"), slippage_rate=Decimal("0.0005"))
        assert friction.commission_rate == Decimal("0.001")

    def test_cero_explicito_es_valido(self) -> None:
        """Se permite, pero hay que escribirlo: queda registrado en el informe."""
        friction = FrictionConfig(commission_rate=Decimal(0), slippage_rate=Decimal(0))
        assert friction.commission_rate == Decimal(0)

    @pytest.mark.parametrize("campo", ["commission_rate", "slippage_rate"])
    def test_tasa_negativa_se_rechaza(self, campo: str) -> None:
        kwargs = {"commission_rate": Decimal("0.001"), "slippage_rate": Decimal("0.001")}
        kwargs[campo] = Decimal("-0.001")
        with pytest.raises(ValueError, match="negativ"):
            FrictionConfig(**kwargs)

    def test_es_inmutable(self) -> None:
        friction = FrictionConfig(commission_rate=Decimal(0), slippage_rate=Decimal(0))
        with pytest.raises((AttributeError, TypeError)):
            friction.commission_rate = Decimal(1)  # type: ignore[misc]


class TestRiskConfig:
    def test_fraccion_obligatoria(self) -> None:
        with pytest.raises(TypeError):
            RiskConfig()  # type: ignore[call-arg]

    def test_fraccion_valida(self) -> None:
        assert RiskConfig(position_fraction=Decimal("0.2")).position_fraction == Decimal("0.2")

    @pytest.mark.parametrize("fraccion", ["0", "-0.1", "1.5"])
    def test_fraccion_fuera_de_rango_se_rechaza(self, fraccion: str) -> None:
        with pytest.raises(ValueError, match=r"fracción|fraction"):
            RiskConfig(position_fraction=Decimal(fraccion))

    def test_fraccion_completa_es_valida(self) -> None:
        """Invertir todo el capital se permite; el drawdown lo dirá."""
        assert RiskConfig(position_fraction=Decimal(1)).position_fraction == Decimal(1)
