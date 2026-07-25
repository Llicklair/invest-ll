"""Almacén de decisiones en disco.

No es una optimización de coste — aunque también lo sea. Es **el único mecanismo de
reproducibilidad disponible**: `temperature` está eliminada en los modelos actuales, y aunque
existiera nunca garantizó salidas idénticas. Sin guardar cada decisión, dos ejecuciones del mismo
experimento darían cifras distintas y compararlas no significaría nada (FR-043, FR-044).

Solo depende de `models`: nada de red, nada de proveedores.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invest_ll.decision.models import Action, AssetDecision, Decision

RAIZ_DECISIONES = Path("decisions")


class DecisionStore:
    """Decisiones guardadas, una por fichero, indexadas por la clave de su petición.

    Un fichero por decisión y no una base de datos porque así se puede mirar a mano lo que el
    modelo respondió, y borrar una decisión concreta es borrar un fichero.
    """

    __slots__ = ("_memoria", "_root")

    def __init__(self, root: Path = RAIZ_DECISIONES) -> None:
        self._root = root
        self._memoria: dict[str, Decision] = {}

    @property
    def root(self) -> Path:
        return self._root

    def get(self, key: str) -> Decision | None:
        """La decisión guardada, o `None`. Nunca improvisa una."""
        if key in self._memoria:
            return self._memoria[key]

        fichero = self._path(key)
        if not fichero.exists():
            return None

        try:
            decision = _leer(json.loads(fichero.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError):
            # Un fichero corrupto se trata como ausencia: se volvera a preguntar. Devolver algo
            # a medias seria peor que pagar la llamada otra vez.
            return None

        self._memoria[key] = decision
        return decision

    def put(self, key: str, decision: Decision) -> None:
        """Guarda de forma atómica: o está entera o no está."""
        self._memoria[key] = decision
        self._root.mkdir(parents=True, exist_ok=True)
        destino = self._path(key)

        # Fichero temporal en el MISMO directorio: os.replace solo es atomico dentro del mismo
        # sistema de ficheros. Es el patron que ya usa la feature 002.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._root, delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(_escribir(decision), tmp, ensure_ascii=False, indent=2)
            temporal = Path(tmp.name)

        # PTH105 sugiere Path.replace(). Se mantiene os.replace() por coherencia con
        # fetch/store.py: es el punto donde la escritura pasa a ser visible, y ese detalle
        # merece leerse igual en todo el proyecto.
        os.replace(temporal, destino)  # noqa: PTH105

    def count(self) -> int:
        if not self._root.exists():
            return 0
        return sum(1 for _ in self._root.glob("*.json"))

    def has(self, key: str) -> bool:
        return key in self._memoria or self._path(key).exists()

    def _path(self, key: str) -> Path:
        return self._root / f"{key}.json"


def _escribir(decision: Decision) -> dict[str, Any]:
    return {
        "timestamp": decision.timestamp.isoformat(),
        "model": decision.model,
        "summary": decision.summary,
        "assets": [
            {
                "symbol": a.symbol,
                "action": a.action.value,
                "weight": str(a.weight),
                "reasoning": a.reasoning,
            }
            for a in decision.assets
        ],
    }


def _leer(crudo: dict[str, Any]) -> Decision:
    return Decision(
        timestamp=datetime.fromisoformat(crudo["timestamp"]),
        model=crudo["model"],
        summary=crudo["summary"],
        assets=tuple(
            AssetDecision(
                symbol=a["symbol"],
                action=Action(a["action"]),
                weight=Decimal(a["weight"]),
                reasoning=a["reasoning"],
            )
            for a in crudo["assets"]
        ),
    )
