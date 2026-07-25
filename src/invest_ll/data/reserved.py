"""Datos que ningún backtest puede tocar.

Hoy el train/validation se parte a mano con `--split`. Nada impide mirar la validación, ajustar la
estrategia, y volver a mirar — que es exactamente cómo se fabrica un resultado que no significa
nada. La corrección por número de pruebas (`sweep.py`, `attempts.py`) mide el daño **después**;
esto lo evita **antes**.

La idea es de QuantConnect, que permite forzar que todos los backtests terminen N meses antes de
hoy. Ver `docs/research-aplicaciones.md`.

**Es la misma filosofía que `MarketView`**: hacer imposible lo que no debe pasar, en lugar de
recordar no hacerlo. La diferencia con un acuerdo verbal es que aquí saltarse la reserva exige
escribirlo, y queda anotado en el aviso que acompaña a la serie.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

FICHERO = Path("data/market/reserved.json")


@dataclass(frozen=True, slots=True)
class Reservation:
    """El corte: nada posterior a esta fecha entra en un backtest normal."""

    cutoff: date
    reason: str
    created_at: datetime

    def covers(self, moment: datetime) -> bool:
        """Si ese instante cae dentro de lo reservado."""
        return moment.date() > self.cutoff

    def render(self) -> str:
        return (
            f"Datos reservados a partir de {self.cutoff} — {self.reason}\n"
            f"  Fijada el {self.created_at.date()}. Los backtests se recortan ahi.\n"
            "  Saltarsela exige pedirlo explicitamente, y queda anotado en el informe."
        )

    def __str__(self) -> str:
        return self.render()


def load_reservation(path: Path = FICHERO) -> Reservation | None:
    """La reserva vigente, o `None` si no hay ninguna.

    Sin fichero no hay reserva y todo funciona como antes: esto no puede romper un proyecto que
    no la use.
    """
    if not path.exists():
        return None
    try:
        crudo: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return Reservation(
            cutoff=date.fromisoformat(crudo["cutoff"]),
            reason=str(crudo.get("reason", "")),
            created_at=datetime.fromisoformat(crudo["created_at"]),
        )
    except (ValueError, KeyError, OSError):  # pragma: no cover - fichero corrupto
        # Una reserva ilegible se trata como ausencia y NO como "todo permitido en silencio":
        # el aviso lo da quien la consulta. Fallar aqui impediria cargar cualquier serie.
        return None


def save_reservation(
    cutoff: date, *, reason: str, path: Path = FICHERO, now: datetime | None = None
) -> Reservation:
    """Fija la reserva. Sobrescribe la anterior si la había.

    Mover el corte **hacia atrás** (reservar más) es inocuo. Moverlo hacia delante libera datos
    que estaban protegidos: quien lo haga debería saber por qué, y por eso `reason` es obligatorio.
    """
    if not reason.strip():
        raise ValueError(
            "una reserva sin motivo no se puede evaluar despues: di por que reservas estos datos"
        )

    reserva = Reservation(cutoff=cutoff, reason=reason, created_at=now or datetime.now(UTC))
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(
            {
                "cutoff": reserva.cutoff.isoformat(),
                "reason": reserva.reason,
                "created_at": reserva.created_at.isoformat(),
            },
            tmp,
            ensure_ascii=False,
            indent=2,
        )
        temporal = Path(tmp.name)

    os.replace(temporal, path)  # noqa: PTH105 - mismo patron que el resto del proyecto
    return reserva


def aviso_al_saltarsela(reserva: Reservation) -> str:
    """El texto que acompaña a un resultado calculado sobre datos reservados."""
    return (
        f"[!] Este resultado USA los datos reservados desde {reserva.cutoff}.\n"
        f"    Se reservaron porque: {reserva.reason}\n"
        "    Un resultado medido sobre datos que ya has visto no es evidencia fuera de muestra:\n"
        "    es el mismo backtest otra vez."
    )
