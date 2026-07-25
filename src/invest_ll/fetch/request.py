"""Solicitud de histórico (T014)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Interval

_INSEGURO = re.compile(r"[^A-Za-z0-9._-]+")


class Market(Enum):
    """Determina el proveedor y el calendario aplicable."""

    CRYPTO = "crypto"
    EQUITY = "equity"


@dataclass(frozen=True, slots=True)
class FetchRequest:
    """Qué histórico quiere el operador."""

    symbol: str
    interval: Interval
    start: datetime
    end: datetime
    market: Market

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("el símbolo del activo no puede estar vacío")

        for nombre in ("start", "end"):
            momento: datetime = getattr(self, nombre)
            if momento.tzinfo is None:
                raise ValueError(
                    f"{nombre} debe llevar zona horaria: sin ella no se sabe qué periodo se pide"
                )

        if self.start >= self.end:
            raise ValueError(
                f"el rango debe ser creciente: start ({self.start}) debe ser anterior a end "
                f"({self.end})"
            )

    @property
    def is_continuous(self) -> bool:
        """¿El mercado opera sin interrupción? Cripto sí; bolsa no."""
        return self.market is Market.CRYPTO

    @property
    def path_key(self) -> str:
        """Nombre del activo utilizable como carpeta.

        Los símbolos de cripto llevan barra (`BTC/USDT`), que no vale como nombre de directorio en
        ningún sistema de ficheros.
        """
        return _INSEGURO.sub("-", self.symbol.strip()).strip("-")
