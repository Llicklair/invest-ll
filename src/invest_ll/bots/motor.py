"""El motor que hace correr los bots en el proceso del panel.

ESQUELETO DEL CONTRATO v3. `crear_app(en_vivo=True)` llama a `arrancar()` después de
`invest_ll.vivo.servicio.arrancar()` (necesita su fuente de precios) y a `parar()` antes de cerrarla.
"""

from __future__ import annotations


async def arrancar() -> None:
    """Carga los bots de `bots/` y pone en marcha los que lo estaban (apuntando el hueco)."""


async def parar() -> None:
    """Para el bucle y deja el estado de cada bot guardado."""
