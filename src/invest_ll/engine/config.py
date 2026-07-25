"""Configuración de fricción y riesgo (T028).

Ningún campo tiene valor por defecto, y es intencionado: el Principio IV dice que una simulación
sin fricción es una mentira optimista. Al no haber defaults, "cero comisiones" solo puede ser una
decisión escrita por el operador, nunca un descuido heredado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FrictionConfig:
    """Coste de operar en el mercado simulado (FR-007, FR-008).

    Ambas tasas son proporciones sobre el importe de la operación: `0.001` es un 0,1%.
    """

    commission_rate: Decimal
    slippage_rate: Decimal

    def __post_init__(self) -> None:
        for nombre in ("commission_rate", "slippage_rate"):
            valor: Decimal = getattr(self, nombre)
            if valor < 0:
                raise ValueError(f"{nombre} no puede ser negativa: {valor}")

    def describe(self) -> str:
        return f"comision {self.commission_rate} - slippage {self.slippage_rate}"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Cuánto capital arriesga cada entrada (FR-026).

    `position_fraction` es la porción del capital disponible que compromete cada entrada.
    Invertirlo todo (`1`) está permitido: el drawdown máximo del informe dirá lo que eso cuesta.
    """

    position_fraction: Decimal
    stop_loss_pct: Decimal | None = None
    take_profit_pct: Decimal | None = None

    def __post_init__(self) -> None:
        if not (0 < self.position_fraction <= 1):
            raise ValueError(
                f"la fracción de posición debe estar en (0, 1], recibido {self.position_fraction}"
            )
        for nombre in ("stop_loss_pct", "take_profit_pct"):
            valor: Decimal | None = getattr(self, nombre)
            if valor is not None and valor <= 0:
                raise ValueError(f"{nombre} debe ser positivo, recibido {valor}")

    def describe(self) -> str:
        return f"fraccion por entrada {self.position_fraction}"
