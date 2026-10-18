"""La cuenta de un bot: su capital ficticio en USDC y lo que ha comprado con él.

Las órdenes se ejecutan con `vivo.ejecucion.a_mercado` contra el libro real del momento, nivel a
nivel y con comisión de tomador (las de Hyperliquid de nivel base). Ningún bot gasta más efectivo
del que tiene ni vende lo que no tiene: no hay apalancamiento. Si el libro no da para la orden, no
se inventa un precio (`LibroInsuficienteError`, de `vivo.ejecucion`).

Las cantidades se guardan con 8 decimales (redondeadas hacia abajo al comprar: nunca se apunta más
de lo comprado) y el dinero con 6, como el USDC.

"Mantener" es la comparación de la tarjeta: el mismo capital repartido a partes iguales entre sus
monedas al precio de arranque (pagando la comisión de tomador una vez), valorado a precio de ahora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Final

from invest_ll.bots.decisiones import CANTIDAD, CERO, MINIMO_ORDEN
from invest_ll.errors import InvestLLError
from invest_ll.vivo.ejecucion import COMISIONES, Comisiones, a_mercado

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.bots.decisiones import Lado
    from invest_ll.vivo.fuente import Libro

USDC: Final = Decimal("1e-6")


class OrdenPequenaError(InvestLLError):
    """La orden no llega al mínimo de Hyperliquid (o no queda nada que vender): no se hace."""


def usdc(valor: Decimal) -> Decimal:
    return valor.quantize(USDC, rounding=ROUND_HALF_EVEN)


@dataclass(slots=True)
class Posicion:
    cantidad: Decimal
    coste: Decimal
    """USDC pagados por lo que queda, comisiones incluidas."""

    @property
    def precio_medio(self) -> Decimal:
        return self.coste / self.cantidad


@dataclass(frozen=True, slots=True)
class Hecha:
    """Una orden ejecutada. `importe` es cantidad por precio medio, sin la comisión."""

    coin: str
    lado: Lado
    cantidad: Decimal
    precio: Decimal
    importe: Decimal
    comision: Decimal


@dataclass(slots=True)
class Cuenta:
    efectivo: Decimal
    posiciones: dict[str, Posicion] = field(default_factory=dict[str, Posicion])
    comisiones: Comisiones = COMISIONES

    def cantidades(self) -> dict[str, Decimal]:
        return {c: p.cantidad for c, p in self.posiciones.items()}

    def comprar(self, libro: Libro, gastar: Decimal) -> Hecha:
        """Compra a mercado gastando como mucho `gastar` USDC, comisión incluida, y nunca más
        del efectivo que hay."""
        gastar = min(gastar, self.efectivo)
        if gastar < MINIMO_ORDEN:
            raise OrdenPequenaError(
                f"una compra de {gastar} USDC no llega al mínimo de {MINIMO_ORDEN} USDC"
            )
        tanteo = a_mercado(
            libro,
            "compra",
            importe=gastar / (1 + self.comisiones.tomador),
            comisiones=self.comisiones,
        )
        cantidad = tanteo.cantidad.quantize(CANTIDAD, rounding=ROUND_DOWN)
        if cantidad <= 0:  # pragma: no cover - solo con precios de miles de millones
            raise OrdenPequenaError("con ese dinero no llega a la cantidad mínima")
        e = a_mercado(libro, "compra", cantidad=cantidad, comisiones=self.comisiones)
        importe, comision = usdc(e.importe), usdc(e.comision)
        # Redondear a 6 decimales puede pasarse del efectivo en una millonésima: nunca se gasta más.
        coste = min(importe + comision, self.efectivo)
        self.efectivo -= coste
        actual = self.posiciones.get(libro.coin)
        if actual is None:
            self.posiciones[libro.coin] = Posicion(cantidad, coste)
        else:
            actual.cantidad += cantidad
            actual.coste += coste
        return Hecha(libro.coin, "compra", cantidad, e.precio_medio, importe, comision)

    def vender(self, libro: Libro, cantidad: Decimal | None = None) -> Hecha:
        """Vende a mercado `cantidad` (como mucho, lo que hay) o toda la posición."""
        actual = self.posiciones.get(libro.coin)
        if actual is None or actual.cantidad <= 0:
            raise OrdenPequenaError(f"no queda {libro.coin} que vender")
        vende = actual.cantidad if cantidad is None else min(cantidad, actual.cantidad)
        if vende <= 0:
            raise OrdenPequenaError(f"no queda {libro.coin} que vender")
        e = a_mercado(libro, "venta", cantidad=vende, comisiones=self.comisiones)
        importe, comision = usdc(e.importe), usdc(e.comision)
        self.efectivo += importe - comision
        if vende == actual.cantidad:
            del self.posiciones[libro.coin]
        else:
            actual.coste -= usdc(actual.coste * vende / actual.cantidad)
            actual.cantidad -= vende
        return Hecha(libro.coin, "venta", vende, e.precio_medio, importe, comision)

    def anotar(self, hecha: Hecha) -> None:
        """Lo que ejecutó un exchange de verdad (bots de pruebas y reales): se apunta tal cual, con
        su cantidad, su precio medio y su comisión (en la moneda cotizada), sin simular nada. Una
        venta de más de lo que hay se apunta hasta lo que hay."""
        if hecha.lado == "compra":
            coste = usdc(hecha.importe + hecha.comision)
            self.efectivo -= coste
            actual = self.posiciones.get(hecha.coin)
            if actual is None:
                self.posiciones[hecha.coin] = Posicion(hecha.cantidad, coste)
            else:
                actual.cantidad += hecha.cantidad
                actual.coste += coste
            return
        self.efectivo += usdc(hecha.importe - hecha.comision)
        actual = self.posiciones.get(hecha.coin)
        if actual is None:
            return
        if hecha.cantidad >= actual.cantidad:
            del self.posiciones[hecha.coin]
        else:
            actual.coste -= usdc(actual.coste * hecha.cantidad / actual.cantidad)
            actual.cantidad -= hecha.cantidad

    def valor(self, precios: Mapping[str, Decimal]) -> Decimal | None:
        """Efectivo más posiciones a esos precios; None si falta el de alguna posición."""
        total = self.efectivo
        for coin, p in self.posiciones.items():
            precio = precios.get(coin)
            if precio is None:
                return None
            total += p.cantidad * precio
        return total


def cantidades_mantener(
    capital: Decimal,
    monedas: Sequence[str],
    precios_arranque: Mapping[str, Decimal],
    comisiones: Comisiones = COMISIONES,
) -> dict[str, Decimal] | None:
    """Lo que tendría quien hubiera repartido el capital entre las monedas al arrancar (pagando
    una vez la comisión de tomador). None si falta el precio de arranque de alguna."""
    if any(c not in precios_arranque for c in monedas):
        return None
    parte = capital / len(monedas) * (1 - comisiones.tomador)
    return {c: parte / precios_arranque[c] for c in monedas}


def valor_mantener(
    cantidades: Mapping[str, Decimal] | None, precios: Mapping[str, Decimal]
) -> Decimal | None:
    if cantidades is None or any(c not in precios for c in cantidades):
        return None
    return sum((q * precios[c] for c, q in cantidades.items()), CERO)
