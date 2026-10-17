"""Apoyo de las pruebas de los bots: velas sintéticas, libros, un reloj que avanza a mano y un
mercado falso que se mueve vela a vela sobre `FuenteFalsa`, sin red ni esperas."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from invest_ll.vivo.fuente import FuenteFalsa, Libro, Nivel, Vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.bots.motor import Motor

D = Decimal
INICIO: Final = datetime(2026, 10, 1, tzinfo=UTC)
DURACION: Final = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "1d": timedelta(days=1)}


def vela(
    coin: str, intervalo: str, inicio: datetime, cierre: float, *, cerrada: bool = True
) -> Vela:
    c = D(str(round(cierre, 6)))
    return Vela(
        coin=coin,
        intervalo=intervalo,
        inicio=inicio,
        fin=inicio + DURACION[intervalo],
        apertura=c,
        maximo=c,
        minimo=c,
        cierre=c,
        volumen=D(1),
        cerrada=cerrada,
    )


def serie(
    coin: str, intervalo: str, cierres: Sequence[float], desde: datetime = INICIO
) -> list[Vela]:
    paso = DURACION[intervalo]
    return [vela(coin, intervalo, desde + paso * i, c) for i, c in enumerate(cierres)]


def onda(
    n: int, *, centro: float = 100.0, amplitud: float = 10.0, periodo: int = 120
) -> list[float]:
    """Un precio que sube y baja con regularidad: da cruces de medias y vueltas en la rejilla."""
    return [centro + amplitud * math.sin(2 * math.pi * i / periodo) for i in range(n)]


def libro(coin: str, precio: Decimal | float, *, cantidad: str = "1000") -> Libro:
    """Un libro de cinco niveles por lado, con un diferencial de 0,02 % alrededor del precio."""
    p = D(str(precio))
    medio_diferencial = p * D("0.0001")
    compras = tuple(
        Nivel(p - medio_diferencial - p * D("0.0002") * i, D(cantidad)) for i in range(5)
    )
    ventas = tuple(
        Nivel(p + medio_diferencial + p * D("0.0002") * i, D(cantidad)) for i in range(5)
    )
    return Libro(coin=coin, compras=compras, ventas=ventas, at=INICIO)


@dataclass(slots=True)
class Reloj:
    """Un reloj que solo avanza cuando la prueba lo dice."""

    t: datetime = INICIO

    def __call__(self) -> datetime:
        return self.t

    def avanzar(self, cuanto: timedelta) -> None:
        self.t += cuanto


@dataclass(slots=True)
class Mercado:
    """Un mercado falso que se mueve vela a vela: en cada cierre la fuente da las velas cerradas
    hasta entonces (y la siguiente en curso), el precio del cierre y un libro a su alrededor."""

    fuente: FuenteFalsa = field(default_factory=FuenteFalsa)
    reloj: Reloj = field(default_factory=Reloj)
    velas: dict[tuple[str, str], list[Vela]] = field(
        default_factory=dict[tuple[str, str], list[Vela]]
    )

    def poner(self, coin: str, intervalo: str, cierres: Sequence[float]) -> None:
        self.velas[(coin, intervalo)] = serie(coin, intervalo, cierres)

    def al_cierre(self, i: int, *, sin_libro: frozenset[str] = frozenset()) -> None:
        """Lleva el reloj al cierre de la vela `i` y deja la fuente como estaría entonces."""
        for (coin, intervalo), velas in self.velas.items():
            hecha = velas[i]
            self.reloj.t = hecha.fin
            en_curso = vela(coin, intervalo, hecha.fin, float(hecha.cierre), cerrada=False)
            self.fuente.series[(coin, intervalo)] = [*velas[: i + 1], en_curso]
            self.fuente.precios[coin] = hecha.cierre
            if coin in sin_libro:
                self.fuente.libros.pop(coin, None)
            else:
                self.fuente.libros[coin] = libro(coin, hecha.cierre)

    def recorrer(self, motor: Motor, desde: int, hasta: int) -> None:
        for i in range(desde, hasta):
            self.al_cierre(i)
            motor.paso()

    def precio(self, coin: str, precio: float) -> None:
        """Mueve el precio de una moneda (la rejilla decide con cada precio)."""
        self.fuente.precios[coin] = D(str(precio))
        self.fuente.libros[coin] = libro(coin, precio)
