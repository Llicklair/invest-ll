"""Construir el exchange de ccxt: **el único módulo del paquete `exchanges` que sale a la red**.

`tests/unit/test_no_network_in_suite.py` lo vigila: cualquier otro módulo del paquete que importe
ccxt (o cualquier cliente de red) falla. Aquí solo se construye el objeto de ccxt con lo de su
ficha y, si las hay, las claves; lo que se hace con él vive en `ccxt_conector`, que se prueba sin
red. ccxt se importa dentro de la función: cargarlo cuesta, y solo hace falta al conectar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from invest_ll.exchanges.conector import ExchangeError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping

    from invest_ll.exchanges.conector import Red
    from invest_ll.exchanges.fichas import Ficha

TIEMPO_MAXIMO_MS: Final = 15_000


class RedEquivocadaError(ExchangeError):
    """Se pidió la red de pruebas y el objeto de ccxt no apunta a ella. Nunca debería pasar; si
    pasa, se para antes de enviar nada."""


def construir(ficha: Ficha, red: Red, claves: Mapping[str, str] | None) -> Any:
    """El objeto de ccxt de ese exchange y esa red, con las claves si se dan."""
    import ccxt

    clase = getattr(ccxt, ficha.id_ccxt, None)
    if clase is None:
        raise ExchangeError(f"ccxt no tiene {ficha.id_ccxt!r}: actualiza ccxt.")
    config: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": TIEMPO_MAXIMO_MS,
        "options": dict(ficha.opciones_ccxt),
    }
    if claves is not None:
        config.update(claves)
    exchange = clase(config)
    if red == "pruebas":
        if not ficha.tiene_pruebas:
            raise ExchangeError(f"{ficha.nombre} no tiene red de pruebas.")
        exchange.set_sandbox_mode(True)
        if not apunta_a_pruebas(ficha, exchange):
            raise RedEquivocadaError(
                f"La conexión con {ficha.nombre} no apunta a la red de pruebas: no se ha hecho "
                "nada. Es un fallo del programa, no de tus claves: avisa antes de seguir."
            )
    return exchange


def apunta_a_pruebas(ficha: Ficha, exchange: Any) -> bool:
    """Si el objeto de ccxt habla con la red de pruebas (OKX: la cabecera del modo demo)."""
    if ficha.id == "okx":
        return dict(getattr(exchange, "headers", None) or {}).get("x-simulated-trading") == "1"
    destino = str(getattr(exchange, "urls", {}).get("api", "")).lower()
    return "testnet" in destino or "sandbox" in destino
