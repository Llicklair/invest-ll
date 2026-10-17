"""Cifras y fechas como las lee una persona en España: `1.234,56`, `+4,6 %`, "16 oct 2026".

Los textos que escribe el servidor para el panel (explicaciones, resúmenes, avisos) usan esto para
que una cifra dentro de una frase se lea igual que las que pinta el frontend. Sin locale del
sistema: el resultado no puede depender de la máquina en que corra.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

MESES_CORTOS: Final = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
MESES: Final = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def fecha_corta(d: date) -> str:
    """'16 oct 2026'."""
    return f"{d.day} {MESES_CORTOS[d.month - 1]} {d.year}"


def fecha_larga(d: date) -> str:
    """'1 de noviembre'."""
    return f"{d.day} de {MESES[d.month - 1]}"


def mes(d: date) -> str:
    """'octubre'."""
    return MESES[d.month - 1]


def numero(valor: Decimal | float, decimales: int = 2) -> str:
    """'1.234,56' (separador de miles con punto y decimales con coma)."""
    cuanto = Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    texto = f"{cuanto:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def euros(valor: Decimal | float) -> str:
    """'1.234 €' sin céntimos si es una cifra redonda; con ellos si no."""
    cuanto = Decimal(str(valor))
    decimales = 0 if cuanto == cuanto.to_integral_value() else 2
    return f"{numero(cuanto, decimales)} €"


SIMBOLOS: Final = {"EUR": "€", "USD": "$"}


def cantidad(valor: Decimal, max_decimales: int = 8) -> str:
    """'0,00122', '5,437', '1.234,5': la cifra tal cual, sin ceros de más ni notación científica."""
    cuanto = Decimal(str(valor)).quantize(Decimal(1).scaleb(-max_decimales), rounding=ROUND_HALF_UP)
    exponente = cuanto.normalize().as_tuple().exponent
    decimales = -exponente if isinstance(exponente, int) and exponente < 0 else 0
    return numero(cuanto, decimales)


def dinero(valor: Decimal | float, moneda: str) -> str:
    """'1.234,56 $', '82.245,93 USDT', '650 €'.

    Con céntimos, salvo en euros redondos (como `euros`); por debajo de 1, con las cifras que
    hagan falta para que no se lea 0,00 (una moneda que vale 0,0000123).
    """
    if moneda == "EUR":
        return euros(valor)
    cuanto = Decimal(str(valor))
    texto = numero(cuanto, 2) if abs(cuanto) >= 1 or cuanto == 0 else cantidad(cuanto)
    return f"{texto} {SIMBOLOS.get(moneda, moneda)}"


def porcentaje(fraccion: float, decimales: int = 0) -> str:
    """'57 %' a partir de 0.57."""
    return f"{numero(fraccion * 100, decimales)} %"
