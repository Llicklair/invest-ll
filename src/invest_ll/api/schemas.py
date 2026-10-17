"""El contrato del panel: lo que la API devuelve y lo que acepta.

El frontend (Next.js, en `web/`) genera sus tipos desde el OpenAPI de estos modelos, así que este
fichero es la frontera entre los dos. Tres convenciones que lo atraviesan todo:

- **El dinero viaja como cadena.** Importes, cantidades y precios son `Decimal`, que en JSON sale
  como texto (`"100.5"`): un float convertiría 0,1 + 0,2 en 0,30000000000000004 y una cartera no
  puede permitírselo. Es la misma regla que el `--json` de la línea de comandos. Lo que solo se
  dibuja (variaciones en %, puntos de una gráfica) va en `float`.
- **Toda cifra de mercado lleva su fecha.** Con históricos parados, un valor sin fecha parecería de
  hoy. Si un modelo tiene un precio, tiene al lado de qué día es.
- **Los avisos no se pierden por el camino.** Lo que el panel de Streamlit enseñaba como aviso
  viaja aquí en campos `avisos` (o equivalentes) para que el frontend tenga que pintarlos.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------------
# Comunes
# --------------------------------------------------------------------------------------------

Tramo = Literal["3m", "1a", "5a", "todo"]
"""Ventana de una gráfica: 3 meses (63 sesiones), 1 año (252), 5 años (1260) o todo."""

Celda = str | float | int | bool | None


class Tabla(BaseModel):
    """Una tabla genérica (métricas, operaciones...): columnas en orden y filas alineadas."""

    columnas: list[str]
    filas: list[list[Celda]]


class Friccion(BaseModel):
    """Los costes son obligatorios en toda simulación (Principio IV): sin defaults en la API."""

    comision: Decimal = Field(ge=0, le=Decimal("0.05"), description="Fracción: 0.001 = 0,1%")
    slippage: Decimal = Field(ge=0, le=Decimal("0.05"), description="Fracción: 0.0005 = 0,05%")


class Error(BaseModel):
    """Forma de todos los errores: un texto que se le puede enseñar al operador."""

    detail: str


# --------------------------------------------------------------------------------------------
# Estado general (cabecera del panel)
# --------------------------------------------------------------------------------------------


class Modo(BaseModel):
    nombre: str = Field(description="simulacion | pruebas | REAL")
    envia_ordenes: bool = Field(description="True en pruebas y REAL: las órdenes salen de verdad")
    es_real: bool = Field(description="True solo con dinero de verdad")


class Activo(BaseModel):
    """Un histórico descargado. `id` es estable y es lo que se manda en las peticiones."""

    id: str = Field(description="proveedor:símbolo:intervalo, p.ej. 'yfinance:GLD:DAY_1'")
    symbol: str
    nombre: str = Field(description="Nombre llano: 'Oro', 'Bitcoin'")
    moneda: str = Field(description="Moneda de su precio: 'USD', 'USDT'")
    provider: str
    interval: str
    is_crypto: bool
    label: str
    desde: date
    hasta: date


class Estado(BaseModel):
    modo: Modo
    reserva: str | None = Field(description="Aviso de reserva de datos, si hay una declarada")
    activos: list[Activo]
    pausa: str | None = Field(description="Motivo y fecha de la pausa de entradas, si la hay")


# --------------------------------------------------------------------------------------------
# Mercado
# --------------------------------------------------------------------------------------------


class FilaRendimiento(BaseModel):
    """Una fila de la mesa densa. `None` = no hay histórico suficiente, NO un 0%."""

    activo: str
    nombre: str = Field(description="Nombre llano: 'Bitcoin', 'Bolsa de EE.UU.'")
    que_es: str
    moneda: str = Field(description="Moneda del precio: 'USD', 'USDT'")
    ultimo: float
    var_1d: float | None
    var_1s: float | None
    var_1m: float | None
    var_3m: float | None
    ytd: float | None
    var_1a: float | None
    var_5a: float | None
    desde_maximo: float | None = Field(description="La columna que más importa")
    sparkline: list[float] = Field(description="Últimas 63 sesiones, termina en el último cierre")
    desde: date
    datos_hasta: date


class Rendimiento(BaseModel):
    bolsa: list[FilaRendimiento]
    cripto: list[FilaRendimiento]


class Punto(BaseModel):
    fecha: datetime
    valor: float


class Serie(BaseModel):
    symbol: str
    tramo: Tramo
    puntos: list[Punto]
    sesiones: int
    hasta: date


class PuntoComparado(BaseModel):
    fecha: datetime
    activo: str
    valor: float = Field(description="Base 100 al inicio del tramo")


class Comparacion(BaseModel):
    puntos: list[PuntoComparado]


class FilaDatos(BaseModel):
    activo: str
    ultimo_cierre: float
    variacion: float = Field(description="Fracción respecto al cierre anterior")
    fecha: date
    velas: int
    descargado: date | None


class DatosDescargados(BaseModel):
    filas: list[FilaDatos]
    desfasados: list[str] = Field(description="Históricos que no llegan a datos recientes")


class Cotizacion(BaseModel):
    activo: str
    nombre: str = Field(description="Nombre llano: 'Bitcoin', 'Bolsa de EE.UU.'")
    precio: float
    var_24h: float | None = Field(description="En %")
    volumen_24h_m: float | None = Field(description="Millones")
    descargado: bool = Field(description="True si ya tiene histórico completo")


class Cotizaciones(BaseModel):
    """Una foto fechada, no un chorro: se pide al pulsar y lleva su hora."""

    at: datetime
    bolsa: list[Cotizacion]
    cripto: list[Cotizacion]
    errores: list[str]


class PeticionDescarga(BaseModel):
    symbol: str
    mercado: Literal["equity", "crypto"]


class ResultadoDescarga(BaseModel):
    symbol: str
    ok: bool
    detalle: str


class ResultadoActualizacion(BaseModel):
    resultados: list[ResultadoDescarga]
    saltados: list[str] = Field(description="Sin metadatos de procedencia: no se adivina")


# --------------------------------------------------------------------------------------------
# Mi cartera y órdenes
# --------------------------------------------------------------------------------------------


class PosicionAbierta(BaseModel):
    """Su P&L es una VALORACIÓN, con la fecha de los datos al lado."""

    activo: str
    nombre: str = Field(description="Nombre llano del activo")
    moneda: str = Field(
        description=(
            "Moneda de los importes (invertido, valor, lo que ganas o pierdes): la de su "
            "cotización ('USD', 'USDT'); 'EUR' si `es_referencia`, porque entonces son lo que "
            "pagaste en euros, valorado con el fondo de referencia sin contar el cambio "
            "euro-dólar (y `precio` y `coste_medio` son de ese fondo, en dólares)"
        )
    )
    es_referencia: bool = Field(
        description=(
            "True si la posición se anotó en unidades del fondo de EE.UU. de referencia (compras "
            "de tu bróker hechas desde el plan): `cantidad` y `coste_medio` NO son tus "
            "participaciones ni tu precio; enseña importes, no unidades."
        )
    )
    cantidad: Decimal
    coste_medio: Decimal
    invertido: Decimal
    abierta: datetime
    precio: Decimal | None
    precio_fecha: date | None
    valor: Decimal | None
    pnl_no_realizado: Decimal | None


class PosicionRetirada(BaseModel):
    """Su P&L es REALIZADO: un hecho que ya no cambia."""

    activo: str
    nombre: str = Field(description="Nombre llano del activo")
    moneda: str
    abierta: date
    retirada: date
    dias: int
    invertido: Decimal
    recuperado: Decimal
    pnl_realizado: Decimal


class Cartera(BaseModel):
    cartera: Literal["real", "pruebas"] = Field(description="'pruebas' = dinero ficticio")
    moneda: str = Field(
        description=(
            "Moneda de los totales (`valor_total`, `invertido_abiertas`, `efectivo`, "
            "`realizado_total`): 'EUR' la real, 'USDT' la de pruebas. Suman posiciones en "
            "dólares sin convertir y `nota_moneda` lo dice"
        )
    )
    nota_moneda: str | None = Field(
        description="P. ej. 'Aproximado: sin contar el cambio euro-dólar.'; None si no hace falta"
    )
    vacia: bool
    error: str | None = Field(description="El ledger cuenta una historia imposible")
    avisos: list[str]
    abiertas: list[PosicionAbierta]
    retiradas: list[PosicionRetirada]
    invertido_abiertas: Decimal
    valor_total: Decimal | None = Field(description="None si falta el precio de alguna abierta")
    efectivo: Decimal
    realizado_total: Decimal


class NuevoMovimiento(BaseModel):
    """Escribe en el ledger. NO envía ninguna orden."""

    tipo: Literal["compra", "venta", "ingreso", "retirada"]
    simbolo: str | None = Field(default=None, description="Solo compra/venta")
    fecha: date
    cantidad: Decimal = Field(description="Cantidad, o importe si es efectivo")
    precio: Decimal | None = Field(default=None, description="Solo compra/venta")
    comision: Decimal = Decimal(0)


class MovimientoRegistrado(BaseModel):
    activity_id: str


class FilaOrden(BaseModel):
    cuando: datetime
    modo: str
    activo: str
    nombre: str = Field(description="Nombre llano: 'Bitcoin'")
    moneda: str = Field(description="Moneda del precio y la comisión: 'USDT'")
    lado: str
    pedida: Decimal
    ejecutada: Decimal
    precio: Decimal | None
    comision: Decimal | None
    estado: str
    referencia: str


class OrdenesEnviadas(BaseModel):
    filas: list[FilaOrden] = Field(description="La más reciente primero")
    total: int
    reales: int
    atencion: list[str] = Field(description="Órdenes que no salieron como se pidieron")
    sin_comision: int
    registro: str


class ComprobacionEnvio(BaseModel):
    cantidad: Decimal
    escrito: str


class EstadoEnvio(BaseModel):
    """Si se puede enviar. El botón del frontend se habilita SOLO con `puede` en True."""

    puede: bool
    motivo: str | None


class PeticionOrden(BaseModel):
    """Una orden. `escrito` es la cantidad tecleada a mano: la confirmación del Principio I."""

    par: str
    lado: Literal["buy", "sell"]
    cantidad: Decimal
    escrito: str


class ResultadoOrden(BaseModel):
    estado: str = Field(description="filled | partial | rejected | unknown")
    descripcion: str = Field(description="El texto técnico de siempre (registro, terminal)")
    resumen: str = Field(
        description=(
            "En llano, para el usuario: 'Compraste 0,00122 Bitcoin a 82.245,93 USDT. Ya está en "
            "tu cartera.' / 'No se sabe si se ejecutó: compruébalo en Binance antes de volver "
            "a operar.'"
        )
    )
    necesita_atencion: bool
    modo: str
    pedida: Decimal
    ejecutada: Decimal
    precio: Decimal | None
    comision: Decimal | None
    moneda: str = Field(description="Moneda del precio y la comisión: 'USDT'")
    en_cartera: bool = Field(description="True si lo ejecutado ya se anotó en tu cartera")


# --------------------------------------------------------------------------------------------
# Simular
# --------------------------------------------------------------------------------------------


class OpcionesSimular(BaseModel):
    frecuencias: list[str]
    sugeridos: list[str] = Field(description="Ids de activos compatibles entre sí")
    estrategias: list[str]
    pausa: str | None


class PeticionPropuesta(Friccion):
    activos: list[str] = Field(min_length=1, description="Ids de activos")
    importe: Decimal = Field(gt=0)
    frecuencia: str


class CompraPropuesta(BaseModel):
    symbol: str
    importe: Decimal
    precio: Decimal | None
    fecha: date | None = Field(description="Fecha del cierre usado como precio de referencia")
    cantidad: Decimal | None = Field(description="None si no hay precio descargado")


class Propuesta(BaseModel):
    texto: str = Field(description="El informe de texto, igual que invest-ll-propose")
    compras: list[CompraPropuesta]
    comandos: list[str] = Field(description="Los invest-ll-execute equivalentes")


class PeticionRegistrarPropuesta(BaseModel):
    compras: list[CompraPropuesta]


class RegistroPropuesta(BaseModel):
    registradas: int
    problemas: list[str]


class Consistencia(BaseModel):
    periodos: int
    positivos: int
    proporcion: float
    peor_periodo: Decimal
    racha_en_rojo: int
    asimetria: float
    aviso: str | None


class ComprarYMantener(BaseModel):
    resultado: Decimal
    drawdown: Decimal
    no_hizo_nada: bool


class Informe(BaseModel):
    """Un backtest, en el mismo orden de lectura que el informe de texto (win rate al final)."""

    concluyente: bool
    motivo_no_concluyente: str | None
    resultado_neto: Decimal
    drawdown_maximo: Decimal
    operaciones: int
    costes: Decimal
    comprar_y_mantener: ComprarYMantener | None
    bate_al_mercado: bool | None
    diferencia: Decimal | None
    curva: list[Punto]
    consistencia: Consistencia | None
    metricas: Tabla
    registro: Tabla


class PeticionUnActivo(Friccion):
    activo: str
    estrategia: Literal["cruce-medias", "precio-vs-media", "ruptura-maximos"]
    corta: int = Field(default=10, ge=2, le=200)
    larga: int = Field(default=30, ge=3, le=400)
    periodos: int = Field(default=50, ge=2, le=400)
    margen: float = Field(default=0.0, ge=0, le=0.10)
    lookback: int = Field(default=20, ge=2, le=400)
    fraccion: Decimal = Field(default=Decimal(1), gt=0, le=1)
    capital: Decimal = Field(default=Decimal(10000), ge=100)


class PeticionUniverso(BaseModel):
    activos: list[str] = Field(min_length=2)


class Par(BaseModel):
    par: str
    correlacion: float


class AnalisisCartera(BaseModel):
    fechas_comunes: int
    desde: date
    hasta: date
    activos: int
    activos_efectivos: float
    correlacion_media: float
    diversificada: bool
    aviso: str | None
    pares: list[Par]


class PeticionAportaciones(Friccion):
    activos: list[str] = Field(min_length=2)
    aportacion: Decimal = Field(gt=0)
    cada: int = Field(ge=1, le=250)


class InformeAportaciones(BaseModel):
    aportado: Decimal
    valor_final: Decimal
    ganancia: Decimal
    rentabilidad: float
    costes: Decimal
    bate_a_todo_de_golpe: bool
    valor_todo_de_golpe: Decimal
    texto: str


class PeticionRotacion(Friccion):
    activos: list[str] = Field(min_length=2)
    lookback: int = Field(default=60, ge=5, le=400)
    capital: Decimal = Field(default=Decimal(10000), ge=100)


class FilaLLM(BaseModel):
    estrategia: str
    resultado: Decimal
    drawdown: Decimal
    operaciones: int
    costes: Decimal


class ComparacionLLM(BaseModel):
    disponible: bool
    motivo: str | None = Field(description="Por qué no se puede reproducir, si no se puede")
    filas: list[FilaLLM]
    ninguna_bate: bool
    advertencia: str


# --------------------------------------------------------------------------------------------
# Vigilar
# --------------------------------------------------------------------------------------------


class Alerta(BaseModel):
    symbol: str | None
    nivel: Literal["revisar", "informativo"]
    mensaje: str


class Alertas(BaseModel):
    alertas: list[Alerta]
    nada_que_contar: str | None = Field(description="Lo mirado y lo no mirado, sin 'todo bien'")


class TriggerArmado(BaseModel):
    trigger_id: str
    symbol: str
    nombre: str = Field(description="Nombre llano del activo: 'Oro', 'Bitcoin'")
    regla: str
    umbral: Decimal
    armado: datetime
    descripcion: str


class Triggers(BaseModel):
    triggers: list[TriggerArmado]
    reglas: list[str]
    pausa: str | None


class NuevoTrigger(BaseModel):
    simbolo: str
    regla: str
    umbral_pct: int = Field(ge=1, le=99)


class Pausa(BaseModel):
    motivo: str


class Disparo(BaseModel):
    trigger_id: str
    symbol: str
    nombre: str = Field(description="Nombre llano del activo: 'Oro', 'Bitcoin'")
    medido: Decimal
    umbral: Decimal
    cantidad_propuesta: Decimal
    precio: Decimal
    precio_fecha: date
    comando: str = Field(description="Texto para leer: nada se ha enviado")


class ComprobacionTriggers(BaseModel):
    disparados: list[Disparo]
    sin_evaluar: list[str] = Field(description="No poder mirar NO es 'todo en orden'")
    armados: int


# --------------------------------------------------------------------------------------------
# Estimado vs real
# --------------------------------------------------------------------------------------------


class FilaSeguimiento(BaseModel):
    emitida: date
    estimado: Decimal
    real: Decimal
    error: Decimal


class Seguimiento(BaseModel):
    evaluadas: int
    pendientes: int
    sobreestimaciones: int
    tendencia: str | None
    filas: list[FilaSeguimiento]


# --------------------------------------------------------------------------------------------
# Investigación
# --------------------------------------------------------------------------------------------


class PesoObjetivo(BaseModel):
    moneda: str
    peso: float
    usdt: float


class PruebaAdelante(BaseModel):
    clave: str
    etiqueta: str
    registros: int
    desde: date | None
    valor_final: float | None = Field(description="Desde 10.000")
    mantener_btc: float | None
    peor_caida: float | None
    nota: str | None = Field(description="Por qué no hay cifras, si no las hay")


class Estudio(BaseModel):
    ruta: str
    generado: datetime


class Investigacion(BaseModel):
    disponible: bool
    motivo: str | None
    ultimo_dato: date | None
    dias_desfase: int | None
    objetivo: list[PesoObjetivo]
    prueba_adelante: list[PruebaAdelante]
    estudio: Estudio | None


# --------------------------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------------------------


class PeticionChat(BaseModel):
    pregunta: str = Field(min_length=1)
    sesion: str | None = Field(default=None, description="Id devuelto por la primera respuesta")


class MensajeChat(BaseModel):
    autor: Literal["operador", "claude"]
    texto: str


class RespuestaChat(BaseModel):
    sesion: str
    respuesta: str
    historial: list[MensajeChat]
