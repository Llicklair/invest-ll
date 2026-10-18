"""Panel v3 (docs/panel-v3-vivo.md): Operar y Bots, en vivo y con dinero ficticio.

Mismas convenciones que `schemas.py` y `schemas_v2.py`: el dinero (saldos, importes, cantidades,
ganancias) viaja como cadena (Decimal); lo que solo se dibuja (precios del gráfico, variaciones en
%, curvas) en `float`; toda cifra lleva su hora; los textos para el usuario, en castellano llano.
Los eventos del stream SSE (`GET /api/vivo/stream`) llevan exactamente el JSON de una ruta REST, así
que comparten estos modelos.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from invest_ll.api.schemas_v5 import MetricasBot, PendienteBot

LadoPractica = Literal["compra", "venta"]
TipoOrden = Literal["mercado", "limite"]
EstadoBot = Literal["en_marcha", "parado", "error"]


# -- Mercado en vivo (Hyperliquid) -----------------------------------------------------------------


class EstadoVivo(BaseModel):
    conectado: bool
    fuente: str = Field(description="'Hyperliquid'")
    desde: datetime | None = Field(description="Desde cuándo llegan datos sin cortes")
    aviso: str | None = Field(description="En llano, si está desconectado o reconectando")


class MonedaVivo(BaseModel):
    coin: str = Field(description="Nombre en Hyperliquid: 'BTC', 'ETH', 'kPEPE'")
    nombre: str = Field(description="Nombre llano: 'Bitcoin'")
    precio: float
    var_24h: float | None = Field(description="En %")
    volumen_24h: float | None = Field(description="En USDC")
    decimales_cantidad: int = Field(description="Cuántos decimales admite la cantidad")


class Monedas(BaseModel):
    estado: EstadoVivo
    at: datetime
    monedas: list[MonedaVivo] = Field(description="Las más negociadas primero")


class NivelLibro(BaseModel):
    precio: float
    cantidad: float
    ordenes: int


class LibroVivo(BaseModel):
    coin: str
    at: datetime
    compras: list[NivelLibro] = Field(description="De mayor a menor precio")
    ventas: list[NivelLibro] = Field(description="De menor a mayor precio")
    diferencial: float | None = Field(description="Venta más barata menos compra más cara")


class OperacionMercado(BaseModel):
    coin: str
    at: datetime
    precio: float
    cantidad: float
    lado: LadoPractica = Field(description="'compra' si la inició quien compraba")


class Operaciones(BaseModel):
    coin: str
    operaciones: list[OperacionMercado] = Field(description="La más reciente primero")


class VelaVivo(BaseModel):
    coin: str
    intervalo: str
    inicio: datetime
    apertura: float
    maximo: float
    minimo: float
    cierre: float
    volumen: float
    cerrada: bool = Field(description="False en la vela en curso, que aún se mueve")


class Velas(BaseModel):
    coin: str
    intervalo: str
    velas: list[VelaVivo] = Field(description="De la más antigua a la más reciente")


# -- Cuenta de práctica ------------------------------------------------------------------------------


class PosicionPractica(BaseModel):
    coin: str
    nombre: str
    cantidad: Decimal
    precio_medio: Decimal = Field(description="Comisiones incluidas")
    precio: Decimal | None = Field(description="Precio de ahora")
    valor: Decimal | None
    ganancia: Decimal | None = Field(description="Lo que ganas o pierdes si vendieras ahora")
    ganancia_pct: float | None = Field(description="Fracción")


class OrdenPractica(BaseModel):
    id: str
    coin: str
    nombre: str
    lado: LadoPractica
    cantidad: Decimal
    precio_limite: Decimal
    creada: datetime


class EjecucionPractica(BaseModel):
    id: str
    coin: str
    nombre: str
    lado: LadoPractica
    tipo: TipoOrden
    cantidad: Decimal
    precio: Decimal = Field(description="Precio medio de la ejecución")
    importe: Decimal
    comision: Decimal
    at: datetime


class CuentaPractica(BaseModel):
    """Dinero ficticio en USDC. Nada sale al exterior."""

    inicial: Decimal
    saldo: Decimal = Field(description="USDC sin invertir (lo reservado por órdenes con límite no)")
    reservado: Decimal = Field(description="USDC apartados por órdenes de compra con límite")
    valor_total: Decimal | None = Field(
        description="Saldo + reservado + posiciones a precio de ahora"
    )
    ganancia: Decimal | None
    ganancia_pct: float | None
    posiciones: list[PosicionPractica]
    ordenes: list[OrdenPractica] = Field(description="Órdenes con límite pendientes")
    historial: list[EjecucionPractica] = Field(description="La más reciente primero")
    at: datetime


class NuevaOrdenPractica(BaseModel):
    coin: str
    lado: LadoPractica
    tipo: TipoOrden
    cantidad: Decimal | None = Field(default=None, gt=0, description="En la moneda")
    importe: Decimal | None = Field(default=None, gt=0, description="En USDC (solo a mercado)")
    precio_limite: Decimal | None = Field(default=None, gt=0, description="Solo con límite")


class ResultadoPractica(BaseModel):
    resumen: str = Field(description="En llano: 'Compraste 0,0148 Bitcoin a 67.420,10 USDC…'")
    ejecucion: EjecucionPractica | None = Field(description="Si se ejecutó ya")
    orden: OrdenPractica | None = Field(description="Si queda pendiente (con límite)")
    cuenta: CuentaPractica


class ReinicioPractica(BaseModel):
    inicial: Decimal = Field(default=Decimal(10000), gt=0, description="USDC ficticios")


# -- Bots ------------------------------------------------------------------------------------------


class EvidenciaBot(BaseModel):
    tipo: Literal["pasado", "prueba_real", "ninguna"]
    texto: str = Field(description="En llano, para la tarjeta del bot")


class ParametroBot(BaseModel):
    clave: str
    nombre: str
    explicacion: str = Field(description="Qué cambia, en llano")
    tipo: Literal["entero", "decimal", "opcion", "intervalo"]
    defecto: str
    minimo: str | None
    maximo: str | None
    opciones: list[str] | None


class PlantillaBot(BaseModel):
    clave: str
    nombre: str
    frase: str
    como_funciona: list[str]
    avisos: list[str]
    evidencia: EvidenciaBot
    riesgo: int = Field(ge=1, le=5)
    riesgo_texto: str
    operaciones_esperadas: str = Field(description="'Una al mes', 'Decenas al día'…")
    monedas: Literal["una", "varias"]
    monedas_sugeridas: list[str]
    parametros: list[ParametroBot]


class Plantillas(BaseModel):
    plantillas: list[PlantillaBot]


ModoBot = Literal["ficticio", "pruebas", "real"]


class LimitesBot(BaseModel):
    """Los límites de un bot de pruebas o real (docs/panel-v4-real.md §3). Obligatorios en esos modos."""

    capital_max: Decimal = Field(gt=0, description="No gasta más que esto, aunque haya saldo")
    orden_max: Decimal = Field(gt=0, description="Ninguna orden mayor que esto")
    perdida_max_pct: float = Field(
        gt=0, lt=1, description="Fracción: si cae esto desde su capital, se para"
    )
    vender_al_parar: bool = Field(description="Al pararse por pérdida, vender todo lo suyo")
    operaciones_max_dia: int = Field(ge=1, le=1000)


class ConsumoLimites(BaseModel):
    gastado: Decimal = Field(description="Capital comprometido ahora")
    perdida_pct: float = Field(description="Fracción perdida desde su capital (0 si gana)")
    operaciones_hoy: int


class NuevoBot(BaseModel):
    plantilla: str = Field(description="Una de las plantillas, o 'medida' con `estrategia`")
    nombre: str = Field(min_length=1, max_length=60)
    monedas: list[str] = Field(min_length=1)
    capital: Decimal = Field(gt=0, description="USDC (ficticios en modo ficticio)")
    parametros: dict[str, str] = Field(
        default_factory=dict[str, str], description="Por clave; lo que falte, su valor por defecto"
    )
    modo: ModoBot = Field(
        default="ficticio",
        description=(
            "'real' NO se puede pedir al crear: se crea en pruebas o ficticio y se activa con "
            "POST /api/bots/{id}/activar-real"
        ),
    )
    exchange: str | None = Field(
        default=None,
        description="Obligatorio en pruebas y real; en ficticio, precios de Hyperliquid",
    )
    estrategia: str | None = Field(default=None, description="Id de una estrategia a medida")
    limites: LimitesBot | None = Field(default=None, description="Obligatorios en pruebas y real")


class PuntoBot(BaseModel):
    at: datetime
    valor: float


class ResumenBot(BaseModel):
    """Lo que enseña la tarjeta del bot (como un vault)."""

    id: str
    nombre: str
    plantilla: str
    nombre_plantilla: str
    monedas: list[str]
    estado: EstadoBot
    motivo_error: str | None
    desde: datetime
    dias: float
    capital: Decimal
    valor: Decimal | None = Field(description="Lo que vale ahora (USDC + posiciones)")
    ganancia: Decimal | None
    ganancia_pct: float | None = Field(description="Fracción")
    ganancia_24h_pct: float | None = Field(description="Fracción")
    mantener_pct: float | None = Field(
        description="Lo que habría ganado solo mantener sus monedas desde que arrancó (fracción)"
    )
    peor_caida: float | None = Field(description="Fracción negativa desde su máximo")
    operaciones: int
    evidencia: EvidenciaBot
    riesgo: int
    curva: list[PuntoBot] = Field(description="Unos 100 puntos desde que arrancó")
    ultima_actividad: datetime | None
    aviso: str | None = Field(description="P. ej. 'Panel cerrado de 14:02 a 18:30: no operó'")
    modo: ModoBot
    exchange: str | None
    estrategia: str | None = Field(description="Id de la estrategia a medida, si lo es")
    limites: LimitesBot | None
    consumo: ConsumoLimites | None
    probado_en_ficticio_dias: float | None = Field(
        description="Días que su estrategia lleva en ficticio (para activar real)"
    )


class EstadoReal(BaseModel):
    """Lo de dinero real, siempre a la vista: el interruptor general y el límite diario."""

    bots_reales: int
    en_marcha: int
    perdida_hoy: Decimal
    limite_diario: Decimal | None = Field(description="Pérdida máxima diaria de todos los reales")
    parado_todo: bool = Field(description="True si se pulsó 'Parar todo lo real' y no se reanudó")
    aviso: str | None


class Bots(BaseModel):
    bots: list[ResumenBot]
    capital: Decimal
    valor: Decimal | None
    ganancia: Decimal | None
    ganancia_pct: float | None
    real: EstadoReal
    at: datetime
    nota: str = Field(
        description="'Dinero ficticio. Los bots siguen aunque cierres el panel, mientras el ordenador esté encendido.'"
    )


class OperacionBot(BaseModel):
    at: datetime
    coin: str
    nombre: str
    lado: LadoPractica
    cantidad: Decimal
    precio: Decimal
    importe: Decimal
    comision: Decimal
    motivo: str = Field(description="El porqué, en llano")


class EventoBot(BaseModel):
    at: datetime
    tipo: Literal["arranque", "parada", "error", "hueco", "info"]
    texto: str


class DetalleBot(ResumenBot):
    parametros: dict[str, str]
    efectivo: Decimal = Field(description="USDC sin invertir")
    posiciones: list[PosicionPractica]
    lista_operaciones: list[OperacionBot] = Field(description="La más reciente primero")
    eventos: list[EventoBot] = Field(description="El más reciente primero")
    curva_mantener: list[PuntoBot] = Field(description="Mismo capital, solo manteniendo")
    metricas: MetricasBot = Field(description="v5: sus métricas, sacadas de sus operaciones")
    pendientes: list[PendienteBot] = Field(
        description="v5: qué hará después, lo más cercano primero"
    )
