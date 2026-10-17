"""Probar unas claves de cualquier exchange: leer el saldo y los permisos, y contarlo en llano.

**No envía ninguna orden.** Leer el saldo es la llamada más barata que exige claves válidas; los
permisos dicen si la clave puede operar y, sobre todo, si puede retirar (`fichas`). Generaliza
`live/prueba_conexion.py` (Binance) a cualquier conector: aquí no se habla con la red, se le pide
al conector, que en las pruebas es uno falso.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from invest_ll.exchanges.conector import ExchangeError, Permisos

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.exchanges.conector import Conector, Red
    from invest_ll.exchanges.fichas import Ficha

MONEDAS_DE_REFERENCIA: Final = ("USDT", "USDC", "USD", "EUR", "FDUSD", "BTC", "ETH")
"""Las redes de pruebas reparten saldo en cientos de monedas: estas van primero."""


@dataclass(frozen=True, slots=True)
class Prueba:
    ok: bool
    detalle: str
    saldo: tuple[tuple[str, Decimal], ...] = ()
    permisos: Permisos | None = None


def ordenar_saldo(saldo: dict[str, Decimal]) -> tuple[tuple[str, Decimal], ...]:
    """Las monedas con saldo: primero las de referencia, después el resto por orden alfabético."""
    con_saldo = {m: c for m, c in saldo.items() if c > 0}
    primero = [(m, con_saldo[m]) for m in MONEDAS_DE_REFERENCIA if m in con_saldo]
    resto = sorted((m, c) for m, c in con_saldo.items() if m not in MONEDAS_DE_REFERENCIA)
    return tuple(primero + resto)


def donde(ficha: Ficha, red: Red) -> str:
    if red == "pruebas":
        return f"la red de pruebas de {ficha.nombre} ({ficha.red_de_pruebas})"
    return f"{ficha.nombre} (dinero real)"


def probar(ficha: Ficha, red: Red, conector: Conector) -> Prueba:
    """Lee el saldo y los permisos con el conector (con claves) y lo cuenta. No envía nada."""
    try:
        saldo = ordenar_saldo(conector.saldo())
    except ExchangeError as error:
        return Prueba(ok=False, detalle=f"No se pudo leer el saldo de {donde(ficha, red)}: {error}")
    permisos = conector.permisos()
    if not saldo:
        vacio = (
            "Las claves funcionan, pero la cuenta de pruebas no tiene saldo."
            if red == "pruebas"
            else "Las claves funcionan, pero tu cuenta no tiene saldo."
        )
        return Prueba(ok=True, detalle=f"{vacio} {permisos.texto}", permisos=permisos)
    ficticio = " (dinero ficticio)" if red == "pruebas" else ""
    return Prueba(
        ok=True,
        detalle=(
            f"Conexión correcta con {donde(ficha, red)}: {len(saldo)} monedas con saldo"
            f"{ficticio}. {permisos.texto}"
        ),
        saldo=saldo,
        permisos=permisos,
    )
