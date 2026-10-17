"""El ledger de cartera en disco: solo añade, nunca reescribe.

`append()` **falla** ante un duplicado exacto en vez de aceptarlo: un doble-import duplicaría la
posición sin que nadie lo note. Y una línea que no se puede leer **no se salta**: es una compra o
una venta que desaparecería de tus cifras, y la cartera derivada cuadraría igual consigo misma.

Vive en `portfolio/` (fuera del control de versiones): son datos tuyos, no código.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from invest_ll.errors import InvestLLError
from invest_ll.portfolio.models import Activity, ActivityType

RAIZ = Path("portfolio")
RAIZ_PRUEBAS = Path("portfolio-pruebas")
"""La cartera de la red de pruebas: sus precios no son los del mercado y no se mezclan."""
FICHERO = "activities.jsonl"


def raiz_del_modo(nombre_modo: str) -> Path:
    """La carpeta de la cartera de un modo: la de pruebas para "pruebas"; la real para lo demás.

    En simulación se ve la cartera real: es lo que tienes, y simular no la cambia.
    """
    return RAIZ_PRUEBAS if nombre_modo == "pruebas" else RAIZ


class DuplicateActivityError(InvestLLError):
    """Se intentó registrar un movimiento idéntico a uno que ya estaba."""


class CorruptLedgerError(InvestLLError):
    """Una línea del registro no se puede leer. No se ignora: se dice cuál."""


class ActivityStore:
    """Movimientos de la cartera, en un fichero de solo-añadir."""

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def path(self) -> Path:
        return self._root / FICHERO

    def append(self, activity: Activity) -> str:
        """Registra un movimiento y devuelve su identificador. Falla si ya estaba."""
        identificador = activity.activity_id
        if identificador in self.known_ids():
            raise DuplicateActivityError(
                f"ese movimiento ya esta registrado (id {identificador}): registrarlo dos veces "
                "duplicaria la posicion. Si de verdad son dos operaciones identicas, anota la "
                "segunda con su hora (--date AAAA-MM-DDTHH:MM)."
            )
        anadir_linea(self.path, _escribir(activity))
        return identificador

    def activities(self) -> list[Activity]:
        """Todos los movimientos, en orden temporal.

        El orden lo pone la fecha del movimiento, no la de escritura: un CSV importado tarde no
        puede romper la historia. Ante la misma fecha se respeta el orden en que se escribieron.
        """
        leidas: list[Activity] = []
        for numero, contenido in leer_jsonl(self.path):
            try:
                leidas.append(_leer(contenido))
            except (KeyError, ValueError, TypeError, InvalidOperation) as error:
                raise CorruptLedgerError(
                    f"{self.path}, linea {numero}: movimiento ilegible ({error}). No se deriva la "
                    "cartera saltandosela: seria un movimiento que desaparece de tus cifras."
                ) from error
        return sorted(leidas, key=lambda a: a.timestamp)

    def known_ids(self) -> set[str]:
        return {a.activity_id for a in self.activities()}


def anadir_linea(fichero: Path, contenido: dict[str, Any]) -> None:
    """Añade una línea JSON de forma atómica.

    Se reescribe el fichero entero a un temporal y se reemplaza: con ficheros de este tamaño es
    barato, y garantiza que una interrupción no deja una línea a medias. Mismo patrón que
    `ExecutionLedger` y `ForecastStore`.
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


def leer_jsonl(fichero: Path) -> list[tuple[int, dict[str, Any]]]:
    """Las líneas del fichero con su número. Vacío si no existe.

    A diferencia de otros registros del proyecto, una línea corrupta **no se salta**: aquí cada
    línea es dinero o una regla de protección, y perder una en silencio cambia el resultado.
    """
    if not fichero.exists():
        return []
    salida: list[tuple[int, dict[str, Any]]] = []
    for numero, linea in enumerate(fichero.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            crudo: object = json.loads(linea)
        except json.JSONDecodeError as error:
            raise CorruptLedgerError(
                f"{fichero}, linea {numero}: no es JSON valido ({error.msg}). Revisala a mano: "
                "no se ignora porque perderla cambiaria lo que se deriva del registro."
            ) from error
        if not isinstance(crudo, dict):
            raise CorruptLedgerError(f"{fichero}, linea {numero}: se esperaba un objeto JSON")
        salida.append((numero, cast("dict[str, Any]", crudo)))
    return salida


def _escribir(a: Activity) -> dict[str, Any]:
    linea: dict[str, Any] = {
        "timestamp": a.timestamp.isoformat(),
        "type": a.type.value,
        "symbol": a.symbol,
        "quantity": str(a.quantity),
        "unit_price": str(a.unit_price),
        "fee": str(a.fee),
        "source": a.source,
        # Cuando se ESCRIBIO, que no es cuando ocurrio: solo para auditar.
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    if a.nota is not None:
        linea["nota"] = a.nota
    return linea


def _leer(c: dict[str, Any]) -> Activity:
    simbolo = c["symbol"]
    nota = c.get("nota")  # las lineas de antes de la nota no la llevan
    return Activity(
        timestamp=datetime.fromisoformat(c["timestamp"]),
        type=ActivityType(c["type"]),
        symbol=str(simbolo) if simbolo is not None else None,
        quantity=Decimal(c["quantity"]),
        unit_price=Decimal(c["unit_price"]),
        fee=Decimal(c["fee"]),
        source=str(c["source"]),
        nota=None if nota is None else str(nota),
    )
