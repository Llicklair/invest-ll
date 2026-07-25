"""Registro auditable de todo lo que se ha enviado a un mercado.

**El modo se guarda en cada entrada, no una vez por sesión.** Así se puede demostrar después que
una orden concreta salió en pruebas y no con dinero real — que es exactamente la pregunta que uno
se hace cuando algo ha ido mal.

Solo añade. Un registro de órdenes que se puede reescribir no sirve para auditar nada.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side

RAIZ = Path("ledger")
FICHERO = "orders.jsonl"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Una orden enviada, con el modo en que se envió."""

    result: OrderResult
    mode_name: str
    recorded_at: datetime

    @property
    def was_real_money(self) -> bool:
        return self.mode_name == "REAL"


class ExecutionLedger:
    """Histórico de órdenes enviadas."""

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / FICHERO

    def record(self, result: OrderResult, *, mode_name: str) -> LedgerEntry:
        entrada = LedgerEntry(result=result, mode_name=mode_name, recorded_at=datetime.now(UTC))
        self._append(_escribir(entrada))
        return entrada

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        salida: list[LedgerEntry] = []
        for linea in self.path.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                salida.append(_leer(json.loads(linea)))
            except (ValueError, KeyError):  # pragma: no cover - linea corrupta
                continue
        return salida

    def needing_attention(self) -> list[LedgerEntry]:
        """Órdenes que no salieron exactamente como se pidieron (FR-031)."""
        return [e for e in self.entries() if e.result.needs_attention]

    def render(self) -> str:
        entradas = self.entries()
        if not entradas:
            return "No se ha enviado ninguna orden todavia."

        lineas = ["Registro de ordenes", "=" * 72]
        for e in entradas:
            marca = " [DINERO REAL]" if e.was_real_money else f" [{e.mode_name}]"
            lineas.append(f"{e.recorded_at.isoformat(timespec='seconds')}{marca}")
            lineas.append(f"  {e.result.describe()}")

        pendientes = self.needing_attention()
        if pendientes:
            lineas += [
                "",
                f"  [!] {len(pendientes)} orden(es) no salieron como se pidieron.",
                "      Revisalas antes de seguir operando.",
            ]
        return "\n".join(lineas)

    def _append(self, contenido: dict[str, Any]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        previo = self.path.read_text(encoding="utf-8") if self.path.exists() else ""

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._root, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(previo)
            tmp.write(json.dumps(contenido, ensure_ascii=False) + "\n")
            temporal = Path(tmp.name)

        os.replace(temporal, self.path)  # noqa: PTH105


def _escribir(e: LedgerEntry) -> dict[str, Any]:
    r = e.result
    return {
        "recorded_at": e.recorded_at.isoformat(),
        "mode": e.mode_name,
        "symbol": r.request.symbol,
        "side": r.request.side.value,
        "requested_quantity": str(r.request.quantity),
        "requested_at": r.request.requested_at.isoformat(),
        "status": r.status.value,
        "filled_quantity": str(r.filled_quantity),
        "fill_price": str(r.fill_price) if r.fill_price is not None else None,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
        "broker_reference": r.broker_reference,
    }


def _leer(c: dict[str, Any]) -> LedgerEntry:
    peticion = OrderRequest(
        symbol=c["symbol"],
        side=Side(c["side"]),
        quantity=Decimal(c["requested_quantity"]),
        requested_at=datetime.fromisoformat(c["requested_at"]),
    )
    return LedgerEntry(
        result=OrderResult(
            request=peticion,
            status=OrderStatus(c["status"]),
            filled_quantity=Decimal(c["filled_quantity"]),
            fill_price=Decimal(c["fill_price"]) if c.get("fill_price") else None,
            executed_at=datetime.fromisoformat(c["executed_at"]) if c.get("executed_at") else None,
            broker_reference=c.get("broker_reference"),
        ),
        mode_name=c["mode"],
        recorded_at=datetime.fromisoformat(c["recorded_at"]),
    )
