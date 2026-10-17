"""Cómo se ejecuta una orden ficticia: contra el libro REAL del momento, nivel a nivel.

Es lo que hace creíble la cuenta de práctica y los bots. Ejecutar al precio medio regalaría el
diferencial y el impacto de las órdenes grandes; aquí, quien compra a mercado más de lo que hay en
el primer nivel paga los siguientes, como pasaría de verdad, y paga su comisión.

Si el libro no tiene bastante, **no se inventa un precio**: `LibroInsuficienteError` dice cuánto
había. Puro: no toca la red ni el disco.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.vivo.fuente import Libro, Nivel

Lado = Literal["compra", "venta"]
CERO = Decimal(0)
TOLERANCIA = Decimal("1e-12")


class LibroInsuficienteError(InvestLLError):
    """El libro no tiene bastante para ejecutar la orden entera."""


@dataclass(frozen=True, slots=True)
class Comisiones:
    """Las de Hyperliquid de nivel base: quien se come el libro (tomador) paga más que quien
    espera en él (creador)."""

    tomador: Decimal = Decimal("0.00045")
    creador: Decimal = Decimal("0.00015")


COMISIONES = Comisiones()


@dataclass(frozen=True, slots=True)
class Ejecucion:
    """Lo que pasó. `importe` es la cantidad por el precio medio, SIN la comisión.

    Al comprar pagas `importe + comision`; al vender cobras `importe - comision` (`neto`).
    """

    lado: Lado
    cantidad: Decimal
    precio_medio: Decimal
    importe: Decimal
    comision: Decimal
    niveles: int

    @property
    def neto(self) -> Decimal:
        """Lo que sale (compra, en positivo) o entra (venta) de USDC, comisión incluida."""
        return (
            self.importe + self.comision if self.lado == "compra" else self.importe - self.comision
        )


def _lado_del_libro(libro: Libro, lado: Lado) -> tuple[Nivel, ...]:
    return libro.ventas if lado == "compra" else libro.compras


def a_mercado(
    libro: Libro,
    lado: Lado,
    *,
    cantidad: Decimal | None = None,
    importe: Decimal | None = None,
    comisiones: Comisiones = COMISIONES,
) -> Ejecucion:
    """Ejecuta a mercado recorriendo el libro. Se da `cantidad` (en la moneda) o `importe` (en
    USDC, sin comisión), no las dos."""
    if (cantidad is None) == (importe is None):
        raise ValueError("di la cantidad o el importe de la orden, no las dos ni ninguna")
    objetivo = cantidad if cantidad is not None else importe
    assert objetivo is not None
    if objetivo <= 0:
        raise ValueError("la orden tiene que ser mayor que cero")

    niveles = _lado_del_libro(libro, lado)
    llevada = CERO
    gastado = CERO
    usados = 0
    for nivel in niveles:
        if nivel.cantidad <= 0:
            continue
        usados += 1
        if cantidad is not None:
            toma = min(nivel.cantidad, cantidad - llevada)
        else:
            toma = min(nivel.cantidad, (objetivo - gastado) / nivel.precio)
        llevada += toma
        gastado += toma * nivel.precio
        restante = (cantidad - llevada) if cantidad is not None else (objetivo - gastado)
        # Margen para el redondeo de Decimal al dividir el importe entre el precio.
        if restante <= TOLERANCIA:
            break
    else:
        disponible = sum((n.cantidad for n in niveles), CERO)
        raise LibroInsuficienteError(
            f"el libro de {libro.coin} solo tiene {disponible.normalize()} "
            f"{'a la venta' if lado == 'compra' else 'pidiendo comprar'} en sus {len(niveles)} "
            "niveles visibles: prueba con una orden más pequeña"
        )

    if llevada <= 0:  # pragma: no cover - solo con un libro de cantidades cero
        raise LibroInsuficienteError(f"el libro de {libro.coin} está vacío por ese lado")
    return Ejecucion(
        lado=lado,
        cantidad=llevada,
        precio_medio=gastado / llevada,
        importe=gastado,
        comision=gastado * comisiones.tomador,
        niveles=usados,
    )


def limite_cruza(libro: Libro, lado: Lado, precio_limite: Decimal) -> bool:
    """Si una orden con límite pendiente se ejecutaría ya: comprar a 100 se ejecuta cuando alguien
    vende a 100 o menos; vender a 100, cuando alguien compra a 100 o más."""
    if lado == "compra":
        return libro.mejor_venta is not None and libro.mejor_venta <= precio_limite
    return libro.mejor_compra is not None and libro.mejor_compra >= precio_limite


def a_limite(
    lado: Lado, cantidad: Decimal, precio_limite: Decimal, *, comisiones: Comisiones = COMISIONES
) -> Ejecucion:
    """Ejecuta una orden con límite que ya cruzó: a su precio y con comisión de creador."""
    if cantidad <= 0 or precio_limite <= 0:
        raise ValueError("cantidad y precio tienen que ser mayores que cero")
    importe = cantidad * precio_limite
    return Ejecucion(
        lado=lado,
        cantidad=cantidad,
        precio_medio=precio_limite,
        importe=importe,
        comision=importe * comisiones.creador,
        niveles=1,
    )
