"""El servicio en vivo del panel: la conexión con Hyperliquid y la cuenta de práctica.

ESQUELETO DEL CONTRATO v3. `crear_app(en_vivo=True)` (solo el lanzador del panel; nunca los tests)
llama a `arrancar()` al empezar y a `parar()` al terminar. `fuente()` da la fuente de precios en
vivo a quien la necesite (la cuenta de práctica, el motor de bots, las rutas de `/api/vivo`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.vivo.fuente import FuentePrecios


async def arrancar() -> None:
    """Abre la conexión con Hyperliquid y empieza a mantener los precios al día."""


async def parar() -> None:
    """Cierra la conexión y deja todo guardado."""


def fuente() -> FuentePrecios:
    """La fuente de precios en vivo del proceso."""
    raise NotImplementedError("pendiente de implementar")
