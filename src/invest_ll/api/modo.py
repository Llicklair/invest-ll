"""El modo con el que trabaja la API y la cartera que le corresponde. **Un solo sitio.**

Toda ruta que dependa del modo (la cabecera, la cartera, las órdenes, el plan, el inicio) lo pide
aquí, para que ninguna se quede leyendo solo el entorno mientras las demás ya usan lo elegido en el
panel: el modo efectivo sale de `live.modo_panel` (entorno primero, panel después), y la cartera,
de ese modo (pruebas → `portfolio-pruebas/`; real y simulación → `portfolio/`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.live.mode import Testnet
from invest_ll.live.modo_panel import ModoEfectivo, fuentes_actuales, resolver
from invest_ll.portfolio.store import ActivityStore, raiz_del_modo

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.api.schemas_v2 import CarteraDelModo
    from invest_ll.live.mode import OperatingMode


def modo_efectivo() -> ModoEfectivo:
    """El modo de ahora mismo, con su origen. Se resuelve en cada petición, nunca se guarda."""
    return resolver(fuentes_actuales())


def almacen_del_modo(modo: OperatingMode) -> ActivityStore:
    return ActivityStore(raiz_del_modo(modo.name))


def cartera_del_modo(modo: OperatingMode) -> CarteraDelModo:
    """'pruebas' es dinero ficticio; en simulación se ve la cartera real."""
    return "pruebas" if isinstance(modo, Testnet) else "real"


def almacen_activo() -> ActivityStore:
    """La cartera del modo efectivo."""
    return almacen_del_modo(modo_efectivo().modo)
