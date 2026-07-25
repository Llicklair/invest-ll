"""Cuántas veces has probado algo sobre los mismos datos.

`sweep.py` corrige por el número de pruebas **dentro de una ejecución**. Este módulo lo hace
**entre ejecuciones**, que es donde el error de verdad se cuela: si pruebas 40 configuraciones
hoy, 40 mañana y 40 pasado, cada barrido dice "0 de 40" y ninguno sabe que llevas 120.

La idea es de QuantConnect, que muestra el número de backtests ejecutados como estimación del
riesgo de sobreajuste. Ver `docs/research-aplicaciones.md`.

**Por qué importa aquí**: el caso documentado de `dual momentum` —una estrategia célebre cuya
rentabilidad cayó a un tercio tras publicarse— se atribuye a minería de datos. Nadie lleva la
cuenta de cuántas cosas probó antes de quedarse con la que funcionaba.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from invest_ll.research.sweep import probabilidad_por_azar

RAIZ = Path("attempts")
FICHERO = "attempts.json"
LONGITUD_CLAVE = 16

# A partir de aquí, la advertencia deja de ser informativa y pasa a ser el titular.
UMBRAL_AVISO = 50


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Cuántas pruebas se han hecho sobre un universo concreto."""

    universe_key: str
    symbols: tuple[str, ...]
    count: int
    first_at: datetime
    last_at: datetime

    @property
    def expected_by_chance(self) -> float:
        """Cuántas darían positivo por azar si ninguna tuviera ventaja."""
        return self.count / 2

    @property
    def needs_warning(self) -> bool:
        return self.count >= UMBRAL_AVISO

    def probability_of(self, survivors: int) -> float:
        """Probabilidad de obtener esos supervivientes o más, en TODAS las pruebas acumuladas."""
        return probabilidad_por_azar(survivors, self.count)

    def render(self) -> str:
        activos = ", ".join(self.symbols)
        lineas = [
            f"Llevas {self.count} evaluacion(es) sobre este universo ({activos})",
            f"  desde {self.first_at.date()}",
        ]

        if self.count < 2:
            return "\n".join(lineas)

        lineas.append(
            f"  Con {self.count} pruebas sin ventaja real, esperarias que "
            f"~{self.expected_by_chance:.0f} salieran positivas por puro azar."
        )

        if self.needs_warning:
            lineas += [
                "",
                "  [!] Cuantas mas cosas pruebas sobre los mismos datos, mas facil es encontrar",
                "      una que 'funciona' sin que signifique nada. Un resultado bueno ahora",
                "      necesita ser bastante mejor que el de la prueba numero 1 para valer lo",
                "      mismo. Es lo que le paso a dual momentum: ver docs/research-estrategias.md",
            ]
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def universe_key(symbols: Sequence[str], *, interval: str = "") -> str:
    """Identifica un universo por sus activos, sin depender del orden.

    Preguntar por [GLD, TLT] o por [TLT, GLD] es probar sobre los mismos datos: contarlo como dos
    universos distintos dejaría el contador a cero justo cuando más útil sería.
    """
    material = ",".join(sorted(symbols)) + "|" + interval
    return sha256(material.encode("utf-8")).hexdigest()[:LONGITUD_CLAVE]


class AttemptLog:
    """Registro persistente de evaluaciones por universo.

    Vive fuera del control de versiones: es historial local del operador, no código.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / FICHERO

    def record(self, symbols: Sequence[str], *, interval: str = "") -> AttemptRecord:
        """Anota una evaluación más y devuelve el acumulado."""
        clave = universe_key(symbols, interval=interval)
        ahora = datetime.now(UTC)
        datos = self._leer()

        previo = datos.get(clave)
        if previo is None:
            entrada: dict[str, Any] = {
                "symbols": sorted(symbols),
                "count": 1,
                "first_at": ahora.isoformat(),
                "last_at": ahora.isoformat(),
            }
        else:
            entrada = dict(previo)
            entrada["count"] = int(entrada.get("count", 0)) + 1
            entrada["last_at"] = ahora.isoformat()

        datos[clave] = entrada
        self._escribir(datos)
        return _leer_registro(clave, entrada)

    def get(self, symbols: Sequence[str], *, interval: str = "") -> AttemptRecord | None:
        """Lo acumulado hasta ahora, sin incrementar."""
        clave = universe_key(symbols, interval=interval)
        entrada = self._leer().get(clave)
        return None if entrada is None else _leer_registro(clave, entrada)

    def all_records(self) -> list[AttemptRecord]:
        return [_leer_registro(k, v) for k, v in self._leer().items()]

    def _leer(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        crudo: object
        try:
            crudo = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):  # pragma: no cover - fichero corrupto
            return {}
        if not isinstance(crudo, dict):  # pragma: no cover - formato inesperado
            return {}
        # Frontera con JSON: comprobado que es un dict, se afirma su forma.
        return cast("dict[str, Any]", crudo)

    def _escribir(self, datos: dict[str, Any]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._root, delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(datos, tmp, ensure_ascii=False, indent=2)
            temporal = Path(tmp.name)
        os.replace(temporal, self.path)  # noqa: PTH105 - mismo patron que el resto del proyecto


def _leer_registro(clave: str, entrada: dict[str, Any]) -> AttemptRecord:
    return AttemptRecord(
        universe_key=clave,
        symbols=tuple(entrada.get("symbols", ())),
        count=int(entrada.get("count", 0)),
        first_at=datetime.fromisoformat(entrada["first_at"]),
        last_at=datetime.fromisoformat(entrada["last_at"]),
    )
