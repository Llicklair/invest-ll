"""Procedencia y avisos de calidad (T016).

Responde a la pregunta que se hace uno cuando un resultado sorprende: ¿de dónde han salido estos
números? Y avisa de lo que puede estar falseándolos.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.fetch.protocol import ProviderCapabilities


class WarningKind(Enum):
    """Cada uno señala una forma concreta en que un backtest puede mentir."""

    GAP = "gap"
    UNADJUSTED_PRICES = "unadjusted_prices"
    SURVIVORSHIP_BIAS = "survivorship_bias"
    PARTIAL_RANGE = "partial_range"


@dataclass(frozen=True, slots=True)
class QualityWarning:
    """Algo que el operador debe saber antes de creerse un resultado."""

    kind: WarningKind
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "message": self.message}


def warnings_from_capabilities(
    capabilities: ProviderCapabilities, *, is_equity: bool
) -> tuple[QualityWarning, ...]:
    """Deriva los avisos de lo que el proveedor declara (FR-018, FR-030).

    Derivarlos en vez de escribirlos a mano en cada sitio es lo que garantiza que aparezcan. Un
    aviso que depende de que alguien se acuerde acaba faltando justo cuando importa.
    """
    avisos: list[QualityWarning] = []

    if is_equity and not capabilities.adjusts_prices:
        avisos.append(
            QualityWarning(
                kind=WarningKind.UNADJUSTED_PRICES,
                message=(
                    f"{capabilities.name} no ajusta los precios por splits ni dividendos. "
                    "Cada split aparecera como un desplome que nunca ocurrio y cada dividendo "
                    "como una perdida. Las estrategias de tendencia reaccionaran a fantasmas."
                ),
            )
        )

    if is_equity and not capabilities.includes_delisted:
        avisos.append(
            QualityWarning(
                kind=WarningKind.SURVIVORSHIP_BIAS,
                message=(
                    f"{capabilities.name} solo incluye activos que siguen cotizando. Un backtest "
                    "sobre ellos ignora a los que quebraron o salieron de bolsa, y sale mejor de "
                    "lo que la realidad fue. Este sesgo se advierte, NO se corrige."
                ),
            )
        )

    return tuple(avisos)


@dataclass(frozen=True, slots=True)
class Provenance:
    """De dónde salen los datos (FR-016)."""

    provider: str
    symbol: str
    interval: str
    market: str
    downloaded_at: datetime
    range_start: datetime
    range_end: datetime
    bar_count: int
    prices_adjusted: bool
    quality_warnings: tuple[QualityWarning, ...] = field(default_factory=tuple)

    def to_json(self) -> str:
        datos: dict[str, Any] = asdict(self)
        for campo in ("downloaded_at", "range_start", "range_end"):
            datos[campo] = getattr(self, campo).isoformat()
        datos["quality_warnings"] = [w.to_dict() for w in self.quality_warnings]
        return json.dumps(datos, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, texto: str) -> Provenance:
        datos: dict[str, Any] = json.loads(texto)
        avisos = tuple(
            QualityWarning(kind=WarningKind(w["kind"]), message=w["message"])
            for w in datos.pop("quality_warnings", [])
        )
        for campo in ("downloaded_at", "range_start", "range_end"):
            datos[campo] = datetime.fromisoformat(datos[campo]).astimezone(UTC)
        return cls(**datos, quality_warnings=avisos)

    def describe(self) -> str:
        lineas = [
            f"  Proveedor    {self.provider}",
            f"  Activo       {self.symbol} ({self.market})",
            f"  Granularidad {self.interval}",
            f"  Cobertura    {self.range_start.date()} a {self.range_end.date()}"
            f"  ({self.bar_count} velas)",
            f"  Descargado   {self.downloaded_at.isoformat()}",
            f"  Ajustado     {'si' if self.prices_adjusted else 'NO'}",
        ]
        return "\n".join(lineas)


def as_data_warnings(avisos: Sequence[QualityWarning]) -> tuple[Any, ...]:
    """Convierte los avisos al tipo que el informe de la feature 001 ya sabe mostrar.

    Los avisos tienen que llegar hasta el informe. Uno que se queda en un fichero de metadatos no
    lo lee nadie en el momento en que importa, que es cuando se está mirando el resultado.
    """
    from invest_ll.data.loader import DataWarning

    return tuple(DataWarning(message=a.message) for a in avisos)
