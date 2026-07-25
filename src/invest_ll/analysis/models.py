"""Qué hay detrás de un activo.

**La separación entre hecho e interpretación es la razón de ser de este módulo** (FR-049). Un dato
del proveedor se puede contrastar contra su fuente; lo que añade un LLM, no. Presentarlos juntos
convertiría un informe comprobable en uno del que no se sabe qué parte creerse — y el operador ha
declarado no tener criterio propio para distinguirlos.

Un `Fact` sin fuente o sin fecha **no se construye**. Si no se puede decir de dónde sale un dato,
no se presenta como dato.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

ADVERTENCIA_TEMPORAL = (
    "Estos datos son ACTUALES. No sirven para analizar decisiones del pasado: la empresa de "
    "entonces no es la de ahora, y usarlos para juzgar 2018 seria mirar el futuro."
)


@dataclass(frozen=True, slots=True)
class Fact:
    """Un dato verificable, con su origen y su fecha."""

    label: str
    value: str
    source: str
    as_of: date

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("un dato necesita una etiqueta")
        if not self.source.strip():
            raise ValueError(
                f"el dato {self.label!r} no indica su fuente; sin fuente no es un dato "
                "verificable y no se puede presentar como tal (FR-017)"
            )

    def render(self) -> str:
        return f"{self.label}: {self.value}  [{self.source}, {self.as_of}]"


@dataclass(frozen=True, slots=True)
class AssetAnalysis:
    """Lo que se sabe de un activo, separando lo comprobable de lo interpretado."""

    symbol: str
    kind: str
    facts: tuple[Fact, ...]
    narrative: str
    scenarios: tuple[str, ...]
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("un analisis necesita un simbolo")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("la fecha de obtencion necesita zona horaria")

    @property
    def has_entity(self) -> bool:
        """Si hay una empresa detrás. El oro y los índices no la tienen (FR-019)."""
        return self.kind == "empresa"

    def render(self) -> str:
        lineas = [
            f"{self.symbol} — {self.kind}",
            "=" * 72,
            "",
            "DATOS VERIFICABLES",
            "-" * 72,
        ]
        if self.facts:
            lineas.extend(f"  {f.render()}" for f in self.facts)
        else:
            lineas.append("  (sin datos disponibles para este activo)")

        lineas += ["", "INTERPRETACION", "-" * 72]
        lineas.append(
            "  Lo de abajo no es verificable contra ninguna fuente: es una lectura, y puede"
        )
        lineas.append("  estar equivocada.")
        lineas.append("")
        lineas.append(f"  {self.narrative or '(sin interpretacion disponible)'}")

        if self.scenarios:
            lineas += ["", "ESCENARIOS POSIBLES", "-" * 72]
            lineas.append(
                "  NO son previsiones. Son cosas que podrian pasar, no que vayan a pasar."
            )
            lineas.append("")
            lineas.extend(f"  - {e}" for e in self.scenarios)

        lineas += ["", ADVERTENCIA_TEMPORAL]
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()
