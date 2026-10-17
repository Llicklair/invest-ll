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


def porcentaje(fraccion: float, decimales: int = 0) -> str:
    """'57 %' a partir de 0.57."""
    return f"{numero(fraccion * 100, decimales)} %"
