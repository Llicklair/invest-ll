"""El par de contado de una moneda en un exchange (lo usan Operar → Hyperliquid y los bots).

La moneda es la de la gráfica (la de Hyperliquid: BTC, SOL…); el par, el del exchange: misma base
(o con la U de los tokens envueltos de Hyperliquid: UBTC, USOL) y cotizada en USDC antes que en
USDT. Solo contado: sin apalancamiento.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.exchanges.conector import Conector, Mercado

COTIZADAS: Final = ("USDC", "USDT")
"""Las monedas con que se paga, por orden de preferencia (Hyperliquid cotiza en USDC)."""


def mercado_de(conector: Conector, coin: str) -> Mercado | None:
    """El par de contado de esa moneda en el exchange del conector, o None si no tiene."""
    nombres = {coin.upper(), f"U{coin.upper()}"}
    candidatos = [
        m for m in conector.mercados() if m.base.upper() in nombres and m.cotizada in COTIZADAS
    ]
    candidatos.sort(key=lambda m: (COTIZADAS.index(m.cotizada), m.base.upper() != coin.upper()))
    return candidatos[0] if candidatos else None


def al_paso(cantidad: Decimal, paso: Decimal | None) -> Decimal:
    """Al paso del mercado, hacia abajo: nunca se pide de más."""
    if paso is None or paso <= 0:
        return cantidad
    return (cantidad / paso).to_integral_value(rounding=ROUND_DOWN) * paso
