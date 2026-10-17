"""Comprobar de verdad, sin claves, que cada exchange responde: mercados, precio, libro y velas.

    uv run python -m invest_ll.exchanges.comprobar            # los seis
    uv run python -m invest_ll.exchanges.comprobar okx kraken # solo esos
    uv run python -m invest_ll.exchanges.comprobar --pruebas  # sus redes de pruebas

**Sale a la red** (por `registro.conector_publico`, como el panel) y no usa ninguna clave: solo
datos públicos. Sirve para ver que una ficha sigue valiendo después de actualizar ccxt o cuando un
exchange cambia algo. No forma parte de la suite (que corre sin red).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from invest_ll.exchanges import registro
from invest_ll.exchanges.conector import ExchangeError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from invest_ll.exchanges.conector import Conector, Mercado, Red

BASES_DE_BTC = ("BTC", "UBTC", "XBT")
COTIZADAS = ("USDT", "USDC", "USD")


@dataclass
class Resultado:
    exchange: str
    par: str | None = None
    pasos: list[tuple[str, bool, str]] = field(default_factory=list[tuple[str, bool, str]])

    @property
    def ok(self) -> bool:
        return bool(self.pasos) and all(bien for _, bien, _ in self.pasos)


def par_de_btc(mercados: Sequence[Mercado], preferido: str) -> str | None:
    """El par de BTC del exchange: el de su ficha si lo tiene; si no, el primero que encaje."""
    pares = {m.par for m in mercados}
    if preferido in pares:
        return preferido
    for cotizada in COTIZADAS:
        for base in BASES_DE_BTC:
            if f"{base}/{cotizada}" in pares:
                return f"{base}/{cotizada}"
    return None


def _paso(resultado: Resultado, nombre: str, hacer: Callable[[], str]) -> None:
    inicio = time.monotonic()
    try:
        detalle = hacer()
        bien = True
    except (ExchangeError, ValueError) as error:
        detalle, bien = str(error)[:200], False
    resultado.pasos.append((nombre, bien, f"{detalle} ({time.monotonic() - inicio:.1f} s)"))


def comprobar(exchange: str, conector: Conector | None = None, red: Red = "real") -> Resultado:
    ficha = registro.ficha(exchange)
    resultado = Resultado(exchange)
    try:
        c = conector or registro.conector_publico(exchange, red)
    except ExchangeError as error:
        resultado.pasos.append(("construir", False, str(error)))
        return resultado
    mercados: list[Mercado] = []

    def leer_mercados() -> str:
        mercados.extend(c.mercados())
        if red == "pruebas" and ficha.par_de_pruebas is not None:
            resultado.par = (
                ficha.par_de_pruebas
                if any(m.par == ficha.par_de_pruebas for m in mercados)
                else None
            )
        else:
            resultado.par = par_de_btc(mercados, ficha.par_de_referencia)
        if resultado.par is None:
            raise ValueError(f"{len(mercados)} pares de contado, ninguno de referencia")
        m = next(m for m in mercados if m.par == resultado.par)
        return (
            f"{len(mercados)} pares de contado; {m.par}: paso {m.paso_cantidad}, "
            f"mínimo {m.minimo_importe} {m.cotizada}, comisión {m.comision_tomador}"
        )

    _paso(resultado, "mercados", leer_mercados)
    par = resultado.par
    if par is None:
        return resultado
    _paso(resultado, "precio", lambda: f"{c.precio(par)}")

    def leer_libro() -> str:
        libro = c.libro(par, 5)
        if libro is None or not libro.compras or not libro.ventas:
            raise ValueError("libro vacío")
        return f"{len(libro.compras)}x{len(libro.ventas)} niveles, {libro.mejor_compra} / {libro.mejor_venta}"

    _paso(resultado, "libro", leer_libro)

    def leer_velas() -> str:
        velas = c.velas(par, "1h", limite=5)
        if not velas:
            raise ValueError("ninguna vela")
        ultima = velas[-1]
        return (
            f"{len(velas)} velas de 1h, la última {ultima.inicio:%Y-%m-%d %H:%M} cierre "
            f"{ultima.cierre} ({'cerrada' if ultima.cerrada else 'en curso'})"
        )

    _paso(resultado, "velas", leer_velas)
    return resultado


def main(argv: Sequence[str] | None = None) -> int:
    lector = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    lector.add_argument("exchanges", nargs="*", default=registro.disponibles())
    lector.add_argument(
        "--pruebas", action="store_true", help="las redes de pruebas (los que la tienen)"
    )
    args = lector.parse_args(argv)
    red: Red = "pruebas" if args.pruebas else "real"
    todo_bien = True
    for exchange in args.exchanges:
        if red == "pruebas" and not registro.ficha(exchange).tiene_pruebas:
            continue
        resultado = comprobar(exchange, red=red)
        todo_bien &= resultado.ok
        print(f"{exchange} [{'bien' if resultado.ok else 'MAL'}] par {resultado.par}")
        for nombre, bien, detalle in resultado.pasos:
            print(f"  {'ok ' if bien else 'MAL'} {nombre}: {detalle}")
    return 0 if todo_bien else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
