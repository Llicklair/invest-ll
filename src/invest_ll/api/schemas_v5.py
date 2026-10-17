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
