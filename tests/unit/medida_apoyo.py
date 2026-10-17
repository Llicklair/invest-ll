"""Apoyo de las pruebas de estrategias a medida: velas sintéticas con máximo y mínimo, un conector
de exchange falso (sin red) y estrategias de partida."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal

from invest_ll.bots.decisiones import Situacion
from invest_ll.estrategias_custom.formato import DURACION, EJEMPLOS
from invest_ll.exchanges.conector import Mercado, OrdenExchange, Permisos
from invest_ll.vivo.fuente import Vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    from invest_ll.exchanges.conector import Lado, Red
    from invest_ll.vivo.fuente import Libro

D = Decimal
INICIO: Final = datetime(2025, 1, 1, tzinfo=UTC)
COMISION: Final = D("0.001")

CRUCE: Final[dict[str, Any]] = {
    "nombre": "Cruce de medias",
    "explicacion": "Compra cuando la media corta cruza por encima de la larga.",
    "monedas": ["BTC"],
    "intervalo": "1d",
    "indicadores": {"corta": {"tipo": "sma", "periodo": 3}, "larga": {"tipo": "sma", "periodo": 5}},
    "entrar": {"cruza_arriba": ["corta", "larga"]},
    "salir": {"cruza_abajo": ["corta", "larga"]},
}
"""Medias de 3 y 5 velas diarias: pocas velas bastan para ver cruces."""


def ejemplo(i: int) -> dict[str, Any]:
    return dict(EJEMPLOS[i])


def con(base: Mapping[str, Any], **cambios: Any) -> dict[str, Any]:
    return {**base, **cambios}


def vela(
    coin: str,
    inicio: datetime,
    cierre: float,
    *,
    intervalo: str = "1d",
    maximo: float | None = None,
    minimo: float | None = None,
    volumen: float = 1.0,
    cerrada: bool = True,
) -> Vela:
    c = D(str(round(cierre, 6)))
    return Vela(
        coin=coin,
        intervalo=intervalo,
        inicio=inicio,
        fin=inicio + DURACION[intervalo],
        apertura=c,
        maximo=D(str(round(maximo, 6))) if maximo is not None else c,
        minimo=D(str(round(minimo, 6))) if minimo is not None else c,
        cierre=c,
        volumen=D(str(volumen)),
        cerrada=cerrada,
    )


def serie(
    coin: str, cierres: Sequence[float], *, intervalo: str = "1d", desde: datetime = INICIO
) -> list[Vela]:
    paso = DURACION[intervalo]
    return [vela(coin, desde + paso * i, c, intervalo=intervalo) for i, c in enumerate(cierres)]


def onda(
    n: int,
    *,
    centro: float = 100.0,
    amplitud: float = 10.0,
    periodo: int = 30,
    tendencia: float = 0,
) -> list[float]:
    """Un precio que sube y baja con regularidad (da cruces), con una tendencia opcional."""
    return [
        centro + amplitud * math.sin(2 * math.pi * i / periodo) + tendencia * i for i in range(n)
    ]


def situacion(
    velas: Mapping[str, Sequence[Vela]],
    *,
    ahora: datetime | None = None,
    efectivo: str = "1000",
    posiciones: Mapping[str, Decimal] | None = None,
    memoria: Mapping[str, str] | None = None,
    monedas: tuple[str, ...] = ("BTC",),
) -> Situacion:
    """Por defecto, al cierre de la última vela de la primera moneda."""
    if ahora is None:
        ahora = next(iter(velas.values()))[-1].fin
    precios = {c: v[-1].cierre for c, v in velas.items() if v}
    return Situacion(
        ahora=ahora,
        capital=D(efectivo),
        monedas=monedas,
        parametros={},
        efectivo=D(efectivo),
        posiciones=dict(posiciones or {}),
        precios=precios,
        velas=velas,
        memoria=dict(memoria or {}),
    )


@dataclass(slots=True)
class ConectorFalso:
    """Un exchange en memoria: sus mercados y sus velas por par. Sin red y sin claves."""

    series: dict[tuple[str, str], list[Vela]] = field(
        default_factory=dict[tuple[str, str], list[Vela]]
    )
    comision: Decimal | None = COMISION
    nombre: str = "falso"
    pares: tuple[tuple[str, str], ...] = (("BTC", "USDT"), ("ETH", "USDT"), ("SOL", "USDC"))
    pedidas: list[tuple[str, str, datetime | None, int]] = field(default_factory=lambda: [])
    """Cada petición de velas: (par, intervalo, desde, límite)."""

    @property
    def exchange(self) -> str:
        return self.nombre

    @property
    def red(self) -> Red:
        return "real"

    def poner(self, par: str, velas: list[Vela], intervalo: str = "1d") -> None:
        self.series[(par, intervalo)] = velas

    def mercados(self) -> list[Mercado]:
        return [
            Mercado(
                par=f"{base}/{cotizada}",
                base=base,
                cotizada=cotizada,
                minimo_importe=D(5),
                minimo_cantidad=None,
                paso_cantidad=None,
                paso_precio=None,
                comision_tomador=self.comision,
                comision_creador=self.comision,
            )
            for base, cotizada in self.pares
        ]

    def velas(
        self, par: str, intervalo: str, desde: datetime | None = None, limite: int = 1000
    ) -> list[Vela]:
        self.pedidas.append((par, intervalo, desde, limite))
        todas = self.series.get((par, intervalo), [])
        if desde is not None:
            todas = [v for v in todas if v.inicio >= desde]
        return todas[:limite]

    # Lo que no hace falta para probar sobre el pasado.

    def precio(self, par: str) -> Decimal | None:
        raise AssertionError("una prueba sobre el pasado no pide precios de ahora")

    def libro(self, par: str, niveles: int = 20) -> Libro | None:
        raise AssertionError("una prueba sobre el pasado no pide el libro")

    def saldo(self) -> dict[str, Decimal]:
        raise AssertionError("sin claves")

    def permisos(self) -> Permisos:
        raise AssertionError("sin claves")

    def enviar(
        self,
        par: str,
        lado: Lado,
        cantidad: Decimal,
        *,
        id_cliente: str,
        tipo: Literal["mercado", "limite"] = "mercado",
        precio: Decimal | None = None,
    ) -> OrdenExchange:
        raise AssertionError("una prueba nunca envía órdenes")

    def orden(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        raise AssertionError("una prueba nunca envía órdenes")

    def cancelar(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        raise AssertionError("una prueba nunca envía órdenes")

    def ordenes_abiertas(self, par: str | None = None) -> list[OrdenExchange]:
        raise AssertionError("una prueba nunca envía órdenes")
