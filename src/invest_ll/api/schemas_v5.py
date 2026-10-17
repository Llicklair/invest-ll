"""Contrato v5: los bots en directo (docs/panel-v5.md §3 y §4).

- `Actividad` (`GET /api/actividad` y el canal `actividad` del stream): los movimientos de todos los
  bots según ocurren, el más reciente primero.
- `MetricasBot` y `PendienteBot`: lo que la ficha de un bot añade a v3 (`DetalleBot.metricas` y
  `DetalleBot.pendientes`).

Dinero y cantidades, como en v3: Decimal (texto en el JSON), en USDC.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TipoMovimiento = Literal["compra", "venta", "arranque", "parada", "error", "hueco", "info"]
TipoPendiente = Literal["compra", "venta", "mirar", "nada"]


class MovimientoBot(BaseModel):
    id: str = Field(description="Estable: el mismo al reabrir el panel (para no repetirlo)")
    at: datetime
    bot_id: str
    bot_nombre: str
    modo: Literal["ficticio", "pruebas", "real"]
    tipo: TipoMovimiento
    texto: str = Field(description="En llano: el porqué de la operación o lo que pasó")
    coin: str | None = None
    nombre_moneda: str | None = None
    cantidad: Decimal | None = None
    precio: Decimal | None = None
    importe: Decimal | None = Field(default=None, description="USDC, sin la comisión")
    comision: Decimal | None = None
    resultado: Decimal | None = Field(
        default=None,
        description="Solo en las ventas: lo cobrado menos la comisión y lo que costó lo vendido",
    )


class Actividad(BaseModel):
    movimientos: list[MovimientoBot] = Field(description="El más reciente primero")
    inicial: bool = Field(
        default=True,
        description="En el stream: true en el primer envío (lo último que hay); false en los "
        "siguientes, que solo traen lo nuevo",
    )
    at: datetime


class MetricasBot(BaseModel):
    operaciones: int
    compras: int
    ventas: int
    cerradas: int = Field(description="Ventas con resultado conocido")
    aciertos: float | None = Field(description="Fracción de las cerradas que ganó algo")
    factor_beneficio: float | None = Field(
        description="Lo ganado en las ventas que ganaron entre lo perdido en las que perdieron "
        "(None si aún no ha perdido en ninguna)"
    )
    ganancia_media: Decimal | None
    perdida_media: Decimal | None = Field(description="Negativa")
    realizada: Decimal = Field(description="La suma de los resultados de sus ventas")
    sin_realizar: Decimal | None = Field(
        description="Lo que ganaría o perdería si vendiera ahora lo que tiene"
    )
    comisiones: Decimal = Field(description="Todas las que ha pagado")
    tiempo_dentro: float | None = Field(
        description="Fracción del tiempo, desde que arrancó, con alguna moneda comprada"
    )
    operaciones_dia: float | None = Field(description="None hasta que lleva un día")
    frente_a_mantener: float | None = Field(
        description="Su ganancia menos la de solo mantener, en fracción (+0.02 = 2 puntos mejor)"
    )
    aviso: str | None = Field(description="Cuando con tan pocas operaciones no dicen nada")


class PendienteBot(BaseModel):
    tipo: TipoPendiente
    texto: str = Field(description="En llano y con sus datos")
    coin: str | None = None
    precio: Decimal | None = Field(
        default=None, description="Al que se dispara (rejilla) o con el que compara"
    )
    distancia: float | None = Field(
        default=None, description="Lo que tiene que moverse el precio de ahora hasta `precio`"
    )
    importe: Decimal | None = None
    cantidad: Decimal | None = None
    cuando: datetime | None = None


class EstadoClaude(BaseModel):
    """Claude con tu suscripción: lo que dice `claude auth status`, sin nada que identifique la
    cuenta."""

    instalado: bool = Field(description="Si Claude Code (el CLI `claude`) está en este equipo")
    conectado: bool
    con_suscripcion: bool = Field(
        description="Conectado con la suscripción de claude.ai (no con una clave de la API)"
    )
    plan: str | None = Field(description="'Max', 'Pro'… si se sabe")
    aviso: str | None
    usos: list[str] = Field(description="Lo que lo usa en el panel")


class ConectarClaude(BaseModel):
    abierto: bool
    texto: str


# -- Operar de verdad en un exchange (docs/panel-v5.md: Operar → Hyperliquid) ---------------------

RedReal = Literal["pruebas", "real"]
LadoReal = Literal["compra", "venta"]
TipoOrdenReal = Literal["mercado", "limite"]
EstadoOrdenReal = Literal[
    "ejecutada", "parcial", "abierta", "cancelada", "rechazada", "desconocido"
]


class SaldoReal(BaseModel):
    moneda: str
    cantidad: Decimal


class MercadoReal(BaseModel):
    """El par de contado del exchange para la moneda de la gráfica."""

    par: str
    base: str
    cotizada: str
    minimo_importe: Decimal | None
    minimo_cantidad: Decimal | None
    paso_cantidad: Decimal | None
    paso_precio: Decimal | None
    comision_tomador: Decimal | None


class OrdenAbiertaReal(BaseModel):
    id_cliente: str
    par: str
    lado: LadoReal
    tipo: TipoOrdenReal
    cantidad: Decimal
    ejecutada: Decimal
    precio: Decimal | None
    at: datetime


class EstadoOperarReal(BaseModel):
    exchange: str
    nombre: str
    red: RedReal | None = Field(description="Donde van las órdenes; None si no está conectado")
    conectado: bool
    que_falta: list[str] = Field(description="Por qué no se puede operar, en llano")
    coin: str
    mercado: MercadoReal | None
    aviso: str | None
    saldo: list[SaldoReal]
    ordenes_abiertas: list[OrdenAbiertaReal]
    at: datetime


class NuevaOrdenReal(BaseModel):
    coin: str = Field(min_length=1)
    lado: LadoReal
    tipo: TipoOrdenReal = "mercado"
    cantidad: Decimal = Field(gt=0, description="De la moneda base, ya al paso del mercado")
    precio: Decimal | None = Field(default=None, gt=0, description="Obligatorio en las límite")
    red: RedReal = Field(
        description="La red que se estaba viendo al confirmar: si no es la activa, no se envía"
    )
    escrito: str = Field(description="La cantidad tecleada como confirmación")


class ResultadoOrdenReal(BaseModel):
    estado: EstadoOrdenReal
    texto: str = Field(description="Lo que ha pasado, en llano y con sus cifras")
    id_cliente: str
    par: str
    lado: LadoReal
    red: RedReal
    cantidad: Decimal
    ejecutada: Decimal
    precio_medio: Decimal | None
    comision: Decimal | None
    comision_moneda: str | None
    anotada: bool = Field(description="Si quedó en el registro de órdenes (ledger/)")
