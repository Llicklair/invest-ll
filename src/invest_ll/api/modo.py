"""El modo con el que trabaja la API y la cartera que le corresponde. **Un solo sitio.**

Toda ruta que dependa del modo (la cabecera, la cartera, las órdenes, el plan, el inicio) lo pide
aquí, para que ninguna se quede leyendo solo el entorno mientras las demás ya usan lo elegido en el
panel: el modo efectivo sale de `live.modo_panel` (entorno primero, panel después), y la cartera,
de ese modo (pruebas → `portfolio-pruebas/`; real y simulación → `portfolio/`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from invest_ll.live.mode import Testnet
from invest_ll.live.modo_panel import ModoEfectivo, fuentes_actuales, resolver
from invest_ll.nombres import moneda_de
from invest_ll.portfolio.store import ActivityStore, raiz_del_modo

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

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


MONEDA_DE_LA_CARTERA: Final[dict[CarteraDelModo, str]] = {"real": "EUR", "pruebas": "USDT"}
"""En qué se cuenta cada cartera: la real, en euros (lo que pones y lo que el plan reparte); la de
pruebas, en los USDT ficticios de la red de pruebas. Es la moneda del efectivo que se anota."""


def moneda_de_la_cartera(cartera: CarteraDelModo) -> str:
    return MONEDA_DE_LA_CARTERA[cartera]


def nota_de_moneda(cartera: CarteraDelModo, simbolos: Iterable[str]) -> str | None:
    """Si sumar estas posiciones en la moneda de la cartera es aproximado, lo que hay que decir.

    Bolsa y cripto cotizan en dólares (USD, USDT) y se suman sin convertir: en la cartera real,
    que se cuenta en euros, eso es no contar el cambio euro-dólar. `None` si no hay nada que
    convertir.
    """
    propia = MONEDA_DE_LA_CARTERA[cartera]
    otras = {moneda_de(s) for s in simbolos} - {propia}
    if not otras:
        return None
    if propia == "EUR":
        return "Aproximado: sin contar el cambio euro-dólar."
    juntas = " y ".join(sorted({*otras, propia}))
    return f"Aproximado: se suman cifras en {juntas} sin convertir de una moneda a otra."


def almacen_activo() -> ActivityStore:
    """La cartera del modo efectivo."""
    return almacen_del_modo(modo_efectivo().modo)


def almacen_del_broker() -> ActivityStore:
    """Donde se anota lo que compras en tu bróker: la cartera real, en cualquier modo.

    El modo (simulación, pruebas, real) es de Binance. En modo pruebas, apuntar una compra del
    bróker en la cartera de pruebas la daba por dinero ficticio y, al volver, la misma compra salía
    otra vez como pendiente: invitaba a comprarla dos veces.
    """
    return ActivityStore(raiz_del_modo("real"))
