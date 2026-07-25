"""Lo que el sistema estimó, y lo que realmente pasó.

**Es la única evidencia sobre el LLM que no está contaminada.** Un backtest sobre el pasado no
sirve: el modelo fue entrenado con datos posteriores al periodo simulado, y eso no tiene arreglo.
Comparar lo que dice hoy con lo que ocurra mañana sí lo es.

Por eso las estimaciones son **inmutables y solo-añadir**: un registro que se puede editar a
posteriori no prueba nada, y borrar los fallos convierte el historial en publicidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

LONGITUD_ID = 16


@dataclass(frozen=True, slots=True)
class Holding:
    """Un activo dentro de una estimación."""

    symbol: str
    quantity: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("un holding necesita simbolo")
        if self.quantity <= 0:
            raise ValueError(f"cantidad no positiva en {self.symbol}: {self.quantity}")


@dataclass(frozen=True, slots=True)
class Forecast:
    """Lo que el sistema esperaba, congelado en el momento de decirlo."""

    issued_at: datetime
    horizon_days: int
    portfolio: tuple[Holding, ...]
    expected_value: Decimal
    basis: str
    model: str = ""

    def __post_init__(self) -> None:
        if self.issued_at.tzinfo is None:
            raise ValueError("la fecha de emision necesita zona horaria")
        if self.horizon_days <= 0:
            raise ValueError(f"el horizonte debe ser positivo, recibido {self.horizon_days}")
        if not self.basis.strip():
            raise ValueError(
                "una estimacion sin explicar en que se basa no se puede evaluar despues"
            )
        simbolos = [h.symbol for h in self.portfolio]
        if len(simbolos) != len(set(simbolos)):
            raise ValueError(f"simbolos repetidos: {simbolos}")

    @property
    def forecast_id(self) -> str:
        """Identificador derivado del contenido.

        Derivarlo del contenido y no de un contador significa que **no se puede reescribir una
        estimación fingiendo que es la misma**: cambiar cualquier cosa cambia el identificador.
        """
        material = "|".join(
            (
                self.issued_at.isoformat(),
                str(self.horizon_days),
                ",".join(
                    f"{h.symbol}:{h.quantity}"
                    for h in sorted(self.portfolio, key=lambda x: x.symbol)
                ),
                str(self.expected_value),
                self.model,
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()[:LONGITUD_ID]

    @property
    def due_at(self) -> datetime:
        """Cuándo se puede evaluar."""
        return self.issued_at + timedelta(days=self.horizon_days)

    def is_due(self, now: datetime) -> bool:
        return now >= self.due_at


@dataclass(frozen=True, slots=True)
class Outcome:
    """Lo que pasó de verdad."""

    forecast_id: str
    measured_at: datetime
    actual_value: Decimal

    def __post_init__(self) -> None:
        if self.measured_at.tzinfo is None:
            raise ValueError("la fecha de medicion necesita zona horaria")
        if not self.forecast_id.strip():
            raise ValueError("un resultado necesita saber a que estimacion corresponde")


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Una estimación puesta frente a su resultado."""

    forecast: Forecast
    outcome: Outcome

    @property
    def error(self) -> Decimal:
        """Positivo: el sistema se quedó corto. Negativo: se pasó de optimista."""
        return self.outcome.actual_value - self.forecast.expected_value

    @property
    def relative_error(self) -> Decimal:
        if self.forecast.expected_value == 0:
            return Decimal(0)
        return self.error / self.forecast.expected_value

    @property
    def overestimated(self) -> bool:
        return self.error < 0


@dataclass(frozen=True, slots=True)
class TrackRecord:
    """El historial completo. Con los fallos dentro (FR-023)."""

    evaluations: tuple[Evaluation, ...] = field(default_factory=tuple)

    @property
    def count(self) -> int:
        return len(self.evaluations)

    @property
    def overestimates(self) -> int:
        return sum(1 for e in self.evaluations if e.overestimated)

    @property
    def mean_relative_error(self) -> Decimal:
        if not self.evaluations:
            return Decimal(0)
        total = sum((e.relative_error for e in self.evaluations), start=Decimal(0))
        return total / Decimal(self.count)

    @property
    def tendency(self) -> str:
        """Si el sistema tiende a pasarse o a quedarse corto (FR-024)."""
        if not self.evaluations:
            return "sin datos suficientes"
        proporcion = self.overestimates / self.count
        if proporcion > 0.6:
            return "tiende a ser demasiado optimista"
        if proporcion < 0.4:
            return "tiende a quedarse corto"
        return "no muestra un sesgo claro"

    def render(self) -> str:
        if not self.evaluations:
            return (
                "Todavia no hay ninguna estimacion evaluada.\n"
                "Es lo normal al principio: hay que esperar a que venza el horizonte."
            )

        lineas = [
            "Estimado frente a lo que paso",
            "=" * 72,
            f"{'emitida':<22}{'ESTIMADO':>14}{'REAL':>14}{'ERROR':>14}",
            "-" * 72,
        ]
        for e in self.evaluations:
            lineas.append(
                f"{e.forecast.issued_at.date()!s:<22}"
                f"{e.forecast.expected_value:>14,.0f}"
                f"{e.outcome.actual_value:>14,.0f}"
                f"{e.error:>14,.0f}"
            )

        lineas += [
            "-" * 72,
            f"  Evaluadas               {self.count}",
            f"  Sobreestimaciones       {self.overestimates} de {self.count}",
            f"  Error medio relativo    {self.mean_relative_error:.1%}",
            f"  Veredicto               {self.tendency}",
            "",
            "  Los fallos siguen en la lista a proposito. Un historial que solo guarda los",
            "  aciertos no mide nada.",
        ]
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()
