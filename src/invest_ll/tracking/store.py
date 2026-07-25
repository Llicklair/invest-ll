"""Almacén de estimaciones: solo añade, nunca reescribe.

Un fichero de estimaciones que se puede reescribir no es un registro, es una excusa. Por eso
`append()` **falla** si el identificador ya existe en vez de sobrescribir en silencio (FR-021).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invest_ll.errors import InvestLLError
from invest_ll.tracking.models import Forecast, Holding, Outcome

RAIZ = Path("forecasts")
FICHERO_ESTIMACIONES = "forecasts.jsonl"
FICHERO_RESULTADOS = "outcomes.jsonl"


class ForecastAlreadyRecordedError(InvestLLError):
    """Se intentó registrar dos veces la misma estimación."""


class ForecastStore:
    """Estimaciones y resultados, en ficheros de solo-añadir."""

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def append(self, forecast: Forecast) -> str:
        """Registra una estimación. Falla si ya estaba: no se reescribe la historia."""
        if any(f.forecast_id == forecast.forecast_id for f in self.forecasts()):
            raise ForecastAlreadyRecordedError(
                f"la estimacion {forecast.forecast_id} ya esta registrada; "
                "las estimaciones no se modifican (FR-021)"
            )
        _anadir(self._root / FICHERO_ESTIMACIONES, _escribir_forecast(forecast))
        return forecast.forecast_id

    def record_outcome(self, outcome: Outcome) -> None:
        _anadir(self._root / FICHERO_RESULTADOS, _escribir_outcome(outcome))

    def forecasts(self) -> list[Forecast]:
        return [_leer_forecast(c) for c in _leer(self._root / FICHERO_ESTIMACIONES)]

    def outcomes(self) -> list[Outcome]:
        return [_leer_outcome(c) for c in _leer(self._root / FICHERO_RESULTADOS)]


def _anadir(fichero: Path, contenido: dict[str, Any]) -> None:
    """Añade una línea de forma atómica.

    Se reescribe el fichero entero a un temporal y se reemplaza: con ficheros de este tamaño es
    barato, y garantiza que una interrupcion no deja una linea a medias.
    """
    fichero.parent.mkdir(parents=True, exist_ok=True)
    previo = fichero.read_text(encoding="utf-8") if fichero.exists() else ""

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=fichero.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(previo)
        tmp.write(json.dumps(contenido, ensure_ascii=False) + "\n")
        temporal = Path(tmp.name)

    os.replace(temporal, fichero)  # noqa: PTH105


def _leer(fichero: Path) -> list[dict[str, Any]]:
    if not fichero.exists():
        return []
    salida: list[dict[str, Any]] = []
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:  # pragma: no cover - linea corrupta
            continue
    return salida


def _escribir_forecast(f: Forecast) -> dict[str, Any]:
    return {
        "id": f.forecast_id,
        "issued_at": f.issued_at.isoformat(),
        "horizon_days": f.horizon_days,
        "portfolio": [{"symbol": h.symbol, "quantity": str(h.quantity)} for h in f.portfolio],
        "expected_value": str(f.expected_value),
        "basis": f.basis,
        "model": f.model,
    }


def _leer_forecast(c: dict[str, Any]) -> Forecast:
    return Forecast(
        issued_at=datetime.fromisoformat(c["issued_at"]),
        horizon_days=int(c["horizon_days"]),
        portfolio=tuple(
            Holding(symbol=h["symbol"], quantity=Decimal(h["quantity"])) for h in c["portfolio"]
        ),
        expected_value=Decimal(c["expected_value"]),
        basis=c["basis"],
        model=c.get("model", ""),
    )


def _escribir_outcome(o: Outcome) -> dict[str, Any]:
    return {
        "forecast_id": o.forecast_id,
        "measured_at": o.measured_at.isoformat(),
        "actual_value": str(o.actual_value),
    }


def _leer_outcome(c: dict[str, Any]) -> Outcome:
    return Outcome(
        forecast_id=c["forecast_id"],
        measured_at=datetime.fromisoformat(c["measured_at"]),
        actual_value=Decimal(c["actual_value"]),
    )
