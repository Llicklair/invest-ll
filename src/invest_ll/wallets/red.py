"""Lo único de las wallets que sale a la red (docs/panel-v5.md §5).

- Saldos de solo lectura con RPC públicos (sin claves): el nativo de cada cadena (`eth_getBalance`)
  y el de USDC y USDT (`balanceOf` con `eth_call`) en Ethereum, Arbitrum y Base.
- Hyperliquid con su API pública de info (lo que tiene una dirección, contado y perpetuos, y los
  precios para valorarlo) y el envío de una acción firmada a `/exchange` (`approveAgent`).

`tests/unit/test_no_network_in_suite.py` lo tiene en su lista: es el sitio que la suite sustituye.
Las direcciones de los contratos se comprobaron el 18/10/2026 llamando a su `symbol()` y
`decimals()` en cada cadena.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Literal, cast

import httpx

Cadena = Literal["ethereum", "arbitrum", "base"]
RedHl = Literal["pruebas", "real"]

PLAZO: Final = 12.0


@dataclass(frozen=True, slots=True)
class Token:
    simbolo: str
    contrato: str
    decimales: int


@dataclass(frozen=True, slots=True)
class InfoCadena:
    nombre: str
    rpc: str
    chain_id: int
    nativo: str


CADENAS: Final[dict[Cadena, InfoCadena]] = {
    "ethereum": InfoCadena("Ethereum", "https://ethereum-rpc.publicnode.com", 1, "ETH"),
    "arbitrum": InfoCadena("Arbitrum", "https://arb1.arbitrum.io/rpc", 42161, "ETH"),
    "base": InfoCadena("Base", "https://mainnet.base.org", 8453, "ETH"),
}

TOKENS: Final[dict[Cadena, tuple[Token, ...]]] = {
    "ethereum": (
        Token("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
        Token("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
    ),
    "arbitrum": (
        Token("USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", 6),
        Token("USDT", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", 6),
    ),
    "base": (
        Token("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
        Token("USDT", "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", 6),
    ),
}

HYPERLIQUID: Final[dict[RedHl, str]] = {
    "real": "https://api.hyperliquid.xyz",
    "pruebas": "https://api.hyperliquid-testnet.xyz",
}


def _dict(valor: object) -> dict[str, Any]:
    return cast("dict[str, Any]", valor) if isinstance(valor, dict) else {}


def _lista(valor: object) -> list[Any]:
    return cast("list[Any]", valor) if isinstance(valor, list) else []


class RedWalletError(Exception):
    """No se pudo hablar con la cadena o con Hyperliquid. El texto, en llano."""


def _rpc(cadena: Cadena, metodo: str, params: list[Any]) -> str:
    info = CADENAS[cadena]
    try:
        r = httpx.post(
            info.rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params},
            timeout=PLAZO,
        )
        r.raise_for_status()
        datos = r.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RedWalletError(f"No se pudo leer {info.nombre}: {error}") from error
    resultado = _dict(datos).get("result")
    if not isinstance(resultado, str):
        raise RedWalletError(f"{info.nombre} no dio el dato: {datos!r:.200}")
    return resultado


def saldo_nativo(cadena: Cadena, direccion: str) -> Decimal:
    """Lo que tiene de la moneda de la cadena (ETH), en unidades enteras."""
    wei = int(_rpc(cadena, "eth_getBalance", [direccion, "latest"]), 16)
    return Decimal(wei) / Decimal(10**18)


def saldo_token(cadena: Cadena, token: Token, direccion: str) -> Decimal:
    """`balanceOf(direccion)` del contrato, en unidades enteras."""
    datos = "0x70a08231" + direccion.lower().removeprefix("0x").rjust(64, "0")
    crudo = _rpc(cadena, "eth_call", [{"to": token.contrato, "data": datos}, "latest"])
    return Decimal(int(crudo, 16) if crudo not in ("0x", "") else 0) / Decimal(10**token.decimales)


def _info(red: RedHl, cuerpo: dict[str, Any]) -> Any:
    try:
        r = httpx.post(f"{HYPERLIQUID[red]}/info", json=cuerpo, timeout=PLAZO)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RedWalletError(f"No se pudo leer Hyperliquid: {error}") from error


def hyperliquid_contado(red: RedHl, direccion: str) -> list[tuple[str, Decimal]]:
    """Lo que tiene esa dirección al contado en Hyperliquid: (moneda, total)."""
    datos = _dict(_info(red, {"type": "spotClearinghouseState", "user": direccion}))
    salida: list[tuple[str, Decimal]] = []
    for crudo in _lista(datos.get("balances")):
        b = _dict(crudo)
        if b.get("coin") and b.get("total") is not None:
            salida.append((str(b["coin"]), Decimal(str(b["total"]))))
    return salida


def hyperliquid_perpetuos(red: RedHl, direccion: str) -> Decimal | None:
    """El valor de la cuenta de perpetuos (margen más lo abierto), en USDC."""
    datos = _dict(_info(red, {"type": "clearinghouseState", "user": direccion}))
    valor = _dict(datos.get("marginSummary")).get("accountValue")
    return Decimal(str(valor)) if valor is not None else None


def hyperliquid_precios(red: RedHl) -> dict[str, Decimal]:
    """El precio medio de cada moneda (allMids), para valorar en USD."""
    datos = _dict(_info(red, {"type": "allMids"}))
    return {k: Decimal(str(v)) for k, v in datos.items() if not k.startswith("@")}


def hyperliquid_enviar(red: RedHl, cuerpo: dict[str, Any]) -> Any:
    """POST a `/exchange` de Hyperliquid: una acción ya firmada."""
    try:
        r = httpx.post(f"{HYPERLIQUID[red]}/exchange", json=cuerpo, timeout=PLAZO)
        return r.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RedWalletError(f"No se pudo hablar con Hyperliquid: {error}") from error
