"""Lo que tiene una wallet: en Ethereum, Arbitrum y Base (ETH, USDC, USDT) y en Hyperliquid
(contado y perpetuos), valorado en USD donde haya precio (docs/panel-v5.md §5).

Todo de solo lectura y en paralelo: una cadena que no contesta no tumba las demás (se dice cuál).
Las stablecoins valen 1 USD; el resto, al precio de Hyperliquid si lo tiene; si no, "sin precio".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from invest_ll.wallets import red

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.wallets.red import Cadena

ESTABLES: Final = frozenset({"USDC", "USDT", "USDT0", "USDE"})
CERO: Final = Decimal(0)
CENTIMO: Final = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Saldo:
    simbolo: str
    cantidad: Decimal
    valor_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class SaldosCadena:
    cadena: str
    nombre: str
    saldos: list[Saldo] = field(default_factory=list[Saldo])
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SaldosWallet:
    cadenas: list[SaldosCadena]
    total_usd: Decimal
    sin_precio: bool
    """Si algo no se pudo valorar (y el total no lo cuenta)."""


def _valor(simbolo: str, cantidad: Decimal, precios: dict[str, Decimal]) -> Decimal | None:
    s = simbolo.upper()
    if s in ESTABLES:
        return cantidad
    precio = precios.get(s) or precios.get(s.removeprefix("U"))
    return cantidad * precio if precio is not None else None


def _cadena(cadena: Cadena, direccion: str, precios: dict[str, Decimal]) -> SaldosCadena:
    info = red.CADENAS[cadena]
    try:
        nativo = red.saldo_nativo(cadena, direccion)
        saldos = [Saldo(info.nativo, nativo, _valor(info.nativo, nativo, precios))]
        for t in red.TOKENS[cadena]:
            c = red.saldo_token(cadena, t, direccion)
            saldos.append(Saldo(t.simbolo, c, c))
    except red.RedWalletError as error:
        return SaldosCadena(cadena, info.nombre, error=str(error))
    return SaldosCadena(cadena, info.nombre, [s for s in saldos if s.cantidad > 0])


def _hyperliquid(direccion: str, precios: dict[str, Decimal]) -> SaldosCadena:
    try:
        contado = red.hyperliquid_contado("real", direccion)
        perpetuos = red.hyperliquid_perpetuos("real", direccion)
    except red.RedWalletError as error:
        return SaldosCadena("hyperliquid", "Hyperliquid", error=str(error))
    saldos = [Saldo(c, q, _valor(c, q, precios)) for c, q in contado if q > 0]
    if perpetuos:
        saldos.append(Saldo("Perpetuos (USDC)", perpetuos, perpetuos))
    return SaldosCadena("hyperliquid", "Hyperliquid", saldos)


def saldos(direccion: str) -> SaldosWallet:
    """Todo lo de esa dirección, cadena a cadena."""
    try:
        precios = red.hyperliquid_precios("real")
    except red.RedWalletError:
        precios = {}
    cadenas: tuple[Cadena, ...] = ("ethereum", "arbitrum", "base")
    with ThreadPoolExecutor(max_workers=4) as hilos:
        futuros = [hilos.submit(_cadena, c, direccion, precios) for c in cadenas]
        futuro_hl = hilos.submit(_hyperliquid, direccion, precios)
        lista = [f.result() for f in futuros] + [futuro_hl.result()]
    valores = [s.valor_usd for c in lista for s in c.saldos]
    total = sum((v for v in valores if v is not None), CERO)
    return SaldosWallet(lista, total, any(v is None for v in valores))
