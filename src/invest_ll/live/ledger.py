"""Registro auditable de todo lo que se ha enviado a un mercado.

**El modo se guarda en cada entrada, no una vez por sesión.** Así se puede demostrar después que
una orden concreta salió en pruebas y no con dinero real — que es exactamente la pregunta que uno
se hace cuando algo ha ido mal.

Solo añade. Un registro de órdenes que se puede reescribir no sirve para auditar nada.

**Panel v4: varios exchanges y bots reales.** Cada entrada puede llevar también el `exchange` y el
`bot` que la enviaron. Son opcionales y compatibles hacia atrás: las líneas viejas no los tienen y
se leen con `None`, que en el exchange significa Binance (el único que había antes de v4; ver
`exchange_de`). Solo se escriben cuando se saben, así una orden manual de v2 deja la misma línea
que siempre.
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
EXCHANGE_ANTERIOR_A_V4 = "binance"
"""El exchange de las entradas que no lo dicen: antes de v4 solo se operaba con Binance."""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Una orden enviada, con el modo en que se envió (y, desde v4, el exchange y el bot)."""

    result: OrderResult
    mode_name: str
    recorded_at: datetime
    exchange: str | None = None
    bot: str | None = None

    @property
    def was_real_money(self) -> bool:
        return self.mode_name == "REAL"

    @property
    def exchange_de(self) -> str:
        """El exchange de la orden; las entradas de antes de v4 son de Binance."""
        return self.exchange or EXCHANGE_ANTERIOR_A_V4


class ExecutionLedger:
    """Histórico de órdenes enviadas."""

    __slots__ = ("_root",)

    def __init__(self, root: Path = RAIZ) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / FICHERO

    def record(
        self,
        result: OrderResult,
        *,
        mode_name: str,
        exchange: str | None = None,
        bot: str | None = None,
    ) -> LedgerEntry:
        entrada = LedgerEntry(
            result=result,
            mode_name=mode_name,
            recorded_at=datetime.now(UTC),
            exchange=exchange,
            bot=bot,
        )
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
            if e.exchange is not None:
                marca += f" {e.exchange}"
            if e.bot is not None:
                marca += f" (bot {e.bot})"
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
    contenido: dict[str, Any] = {
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
        # Ausente en las entradas anteriores a que se guardara: al leerlas vale None, que
        # significa "no se sabe" y no "no cobraron nada".
        "commission": str(r.commission) if r.commission is not None else None,
    }
    # Panel v4. Solo si se saben: una orden de v2 deja la misma línea de siempre.
    if e.exchange is not None:
        contenido["exchange"] = e.exchange
    if e.bot is not None:
        contenido["bot"] = e.bot
    return contenido


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
            commission=Decimal(c["commission"]) if c.get("commission") is not None else None,
        ),
        mode_name=c["mode"],
        recorded_at=datetime.fromisoformat(c["recorded_at"]),
        exchange=c.get("exchange"),
        bot=c.get("bot"),
    )
