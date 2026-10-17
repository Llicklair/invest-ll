"""Dónde se piden los conectores. **Un solo sitio** (como `live/factory.py` para Binance en v2).

ESQUELETO DEL CONTRATO v4. Lo implementa el paquete de exchanges; lo usan los bots reales (para
ejecutar) y las pruebas de estrategias sobre el pasado (para las velas). Las pruebas sustituyen
estas funciones por conectores falsos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.exchanges.conector import Conector, Red


def disponibles() -> list[str]:
    """Los ids de los exchanges que se pueden conectar ('binance', 'hyperliquid', …)."""
    raise NotImplementedError("pendiente de implementar")


def conector(exchange: str, red: Red) -> Conector:
    """El conector con claves de ese exchange y red (para operar). `ExchangeError` en llano si no
    está conectado en esa red."""
    raise NotImplementedError("pendiente de implementar")


def conector_publico(exchange: str) -> Conector:
    """Un conector sin claves, solo para datos públicos (mercados, precio, libro, velas)."""
    raise NotImplementedError("pendiente de implementar")
