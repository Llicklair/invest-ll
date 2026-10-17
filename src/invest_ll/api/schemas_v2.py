"""Panel v2 (docs/panel-v2.md): invertir sin saber de inversiones.

Mismas convenciones que `schemas.py`: el dinero viaja como cadena (Decimal), toda cifra de mercado
lleva su fecha y los avisos tienen campo propio. Lo que solo se dibuja (porcentajes, curvas) va en
`float`. Los textos que el usuario lee (`frase`, `explicacion`, `por_que`, `avisos`...) los escribe
el servidor en castellano llano: el diccionario de docs/panel-v2.md (sección 2) es obligatorio.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MercadoEstrategia = Literal["bolsa", "cripto"]
Ejecucion = Literal["binance", "broker"]
Red = Literal["pruebas", "real"]
ModoPanel = Literal["simulacion", "pruebas", "real"]
CarteraDelModo = Literal["real", "pruebas"]


# -- Inicio -----------------------------------------------------------------------------------


class Patrimonio(BaseModel):
    """Tu dinero hoy. `valor` es None si falta el precio de algo (y `incompleto` lo dice)."""

    valor: Decimal | None = Field(description="Lo que vale hoy lo que tienes (+ efectivo)")
    puesto: Decimal = Field(description="Lo que has puesto (coste de lo que tienes)")
    ganancia: Decimal | None = Field(description="Lo que ganas o pierdes si vendieras hoy")
    ganancia_pct: float | None = Field(description="Fracción: 0.046 = +4,6 %")
    realizado: Decimal = Field(description="Lo ganado o perdido en lo que ya vendiste")
    fecha_precios: date | None = Field(description="Fecha del cierre más antiguo usado")
    incompleto: bool
    cartera: CarteraDelModo = Field(description="'pruebas' = dinero ficticio")
    efectivo: Decimal = Field(
        description="Efectivo incluido en `valor` (0 si no hay o si sale negativo: no se suma)"
    )
    moneda: str = Field(
        description=(
            "Moneda en que se expresan las cifras ('EUR'). Bolsa y cripto cotizan en dólares; "
            "se suman sin convertir y `nota_moneda` lo dice."
        )
    )
    nota_moneda: str | None = Field(
        description="P. ej. 'Aproximado: sin contar el cambio euro-dólar.'"
    )


class ParteResumen(BaseModel):
    estrategia: str
    nombre: str
    mercado: MercadoEstrategia
    valor: Decimal | None
    puesto: Decimal
    moneda: str = Field(
        description=(
            "Moneda de `valor` y `puesto`, la misma que la de sus acciones de hoy: 'EUR' en "
            "bolsa (lo pagado en tu bróker), 'USDT' en cripto"
        )
    )


class MiniMercado(BaseModel):
    nombre: str = Field(description="Nombre llano: 'Bitcoin', 'Bolsa de EE.UU.', 'Oro'")
    symbol: str
    precio: float
    var_1m: float | None = Field(description="En %")
    fecha: date


class Inicio(BaseModel):
    patrimonio: Patrimonio
    hay_movimientos: bool
    plan: list[ParteResumen] | None = Field(description="None si no hay plan guardado")
    acciones_pendientes: int
    proxima_fecha: date | None = Field(description="Próxima aportación del plan")
    avisos: list[str]
    mercado: list[MiniMercado]


# -- Estrategias ------------------------------------------------------------------------------


class Evidencia(BaseModel):
    tipo: Literal["pasado", "prueba_real"]
    desde: date | None = Field(description="Desde cuándo está en prueba real, si lo está")
    texto: str = Field(description="En llano: 'Probada sobre el pasado' / 'En prueba real desde…'")


class Historico(BaseModel):
    """Lo que hizo con 10.000 desde el principio de los datos. Calculado, no escrito a mano."""

    desde: date
    hasta: date
    valor_final: float = Field(description="Desde 10.000")
    crecimiento_anual: float = Field(description="Fracción media anual compuesta")
    peor_caida: float = Field(description="Fracción negativa: -0.65 = cayó un 65 %")
    peor_caida_fecha: date
    peor_racha_anios: float = Field(description="Lo más que tardó en volver a su máximo, en años")
    tiempo_invertido: float = Field(description="Fracción del tiempo dentro del mercado")
    operaciones_al_anio: float = Field(description="Operaciones del motor (técnico: Laboratorio)")
    cambios_al_anio: float = Field(
        description=(
            "Veces al año que, siguiendo esta estrategia, te tocaría hacer algo además de tus "
            "aportaciones (entrar, salir o cambiar el reparto de forma apreciable). Es la cifra "
            "que se le enseña al usuario, no `operaciones_al_anio`."
        )
    )


class Estrategia(BaseModel):
    clave: str
    nombre: str
    frase: str = Field(description="Qué es, en una frase llana")
    para_quien: str
    mercado: MercadoEstrategia
    ejecucion: Ejecucion
    riesgo: int = Field(ge=1, le=5)
    riesgo_texto: str = Field(description="Tranquila · Suave · Moderada · Movida · Muy movida")
    como_funciona: list[str] = Field(description="Tres pasos llanos")
    avisos: list[str]
    evidencia: Evidencia
    activos: list[str] = Field(description="Nombres llanos de lo que compra")
    laboratorio: bool = Field(description="True: solo se enseña en Laboratorio")
    retirada: bool = Field(description="True: ya no se recomienda (se explica en avisos)")
    disponible: bool = Field(description="False si faltan datos para calcularla")
    motivo: str | None = Field(description="Qué falta, si no está disponible")
    historico: Historico | None


class Catalogo(BaseModel):
    estrategias: list[Estrategia]
    nota: str = Field(description="El aviso general: el pasado no es una promesa")


class PorcentajeEstrategia(BaseModel):
    estrategia: str
    porcentaje: int = Field(ge=1, le=100)


class PeticionSimulacion(BaseModel):
    estrategias: list[str] = Field(min_length=1, max_length=4)
    reparto: list[PorcentajeEstrategia] | None = Field(
        default=None,
        description=(
            "Si se da (suma 100), además se calcula `combinado`: tu dinero repartido así, con "
            "cada parte en su estrategia. Sus estrategias no tienen por qué estar también en "
            "`estrategias`: se calculan igual."
        ),
    )
    inicial: Decimal = Field(ge=0)
    mensual: Decimal = Field(ge=0)
    desde_anio: int = Field(ge=2008, le=2100, description="Año de inicio (1 de enero)")


class PuntoSimulado(BaseModel):
    fecha: date
    valor: float
    aportado: float


class ResultadoSimulado(BaseModel):
    clave: str
    nombre: str
    desde: date = Field(description="Primer día con datos (puede ser posterior a lo pedido)")
    hasta: date
    puntos: list[PuntoSimulado] = Field(description="Muestreado semanalmente")
    aportado: float
    valor_final: float
    ganancia: float
    peor_momento_fecha: date
    peor_momento_valor: float = Field(description="El valor en el peor momento relativo")
    peor_momento_aportado: float = Field(description="Lo puesto hasta ese momento")
    peor_caida: float = Field(description="Fracción negativa desde el máximo anterior")
    meses_por_debajo: int = Field(description="Meses en que valía menos de lo puesto")
    aviso: str | None = Field(description="P. ej. 'los datos empiezan en 2018'")


class Simulacion(BaseModel):
    resultados: list[ResultadoSimulado]
    combinado: ResultadoSimulado | None = Field(
        description="Tu reparto entero (clave 'reparto'), si se pidió en la petición"
    )
    nota: str


class Perfil(BaseModel):
    inicial: Decimal = Field(ge=0)
    mensual: Decimal = Field(ge=0)
    horizonte: Literal["menos-2", "2-5", "5-10", "mas-10"]
    ante_caida: Literal["vender", "esperar", "comprar"]
    cripto: Literal["no", "poco", "si"]


class Parte(BaseModel):
    estrategia: str
    nombre: str
    porcentaje: int = Field(ge=0, le=100)
    inicial: Decimal
    mensual: Decimal


class Recomendacion(BaseModel):
    no_invertir: bool = Field(description="True si el horizonte no da para invertir en esto")
    partes: list[Parte]
    por_que: list[str] = Field(description="Frases que citan las respuestas")
    avisos: list[str]
    alternativas: list[str] = Field(description="Claves de otras estrategias razonables")


# -- Plan -------------------------------------------------------------------------------------


class ParteDelPlan(BaseModel):
    estrategia: str
    inicial: Decimal = Field(ge=0)
    mensual: Decimal = Field(ge=0)


class NuevoPlan(BaseModel):
    """Como mucho una estrategia de bolsa y una de cripto."""

    partes: list[ParteDelPlan] = Field(min_length=1, max_length=2)
    dia_del_mes: int = Field(ge=1, le=28)


class Plan(BaseModel):
    partes: list[ParteDelPlan]
    dia_del_mes: int
    creado: datetime
    actualizado: datetime


class PlanGuardado(BaseModel):
    plan: Plan | None


class Accion(BaseModel):
    """Algo que toca hacer hoy.

    En Binance se ejecuta con `POST /api/ordenes` (par, lado, cantidad); en tu bróker lo compras tú
    y lo anotas con `POST /api/plan/hoy/{id}/hecho`.
    """

    id: str
    donde: Ejecucion
    estrategia: str
    titulo: str = Field(description="'Comprar Bitcoin', 'Compra unos 108 € de…'")
    explicacion: str = Field(description="El porqué en una frase")
    activo: str = Field(description="Nombre llano")
    simbolo: str
    par: str | None = Field(description="Par de Binance (BTC/USDT) si donde=binance")
    lado: Literal["buy", "sell"]
    cantidad: Decimal | None = Field(description="Exacta (binance) o aproximada (bróker)")
    importe: Decimal = Field(description="Importe aproximado en la moneda de cotización")
    moneda: str = Field(description="USDT, USD...")
    precio_ref: Decimal | None
    precio_ref_moneda: str | None = Field(description="Moneda de `precio_ref`: 'USD', 'USDT'")
    referencia: str | None = Field(
        description=(
            "Bróker: el fondo de EE.UU. con que se calcula (p. ej. 'SPY'); `cantidad` y "
            "`precio_ref` son de ese fondo, no del que compras."
        )
    )
    precio_fecha: date | None
    equivalente: str | None = Field(description="Qué comprar desde España (bróker)")


class Hoy(BaseModel):
    sin_plan: bool
    modo: ModoPanel
    acciones: list[Accion]
    resumen: str = Field(description="'No toca hacer nada. Tu próxima aportación es…'")
    proxima_fecha: date | None
    avisos: list[str]


class AccionHecha(BaseModel):
    cantidad: Decimal = Field(gt=0)
    precio: Decimal = Field(gt=0)
    comision: Decimal = Field(default=Decimal(0), ge=0)
    fecha: date


# -- Cartera: movimientos legibles --------------------------------------------------------------


class Movimiento(BaseModel):
    id: str
    fecha: datetime
    tipo: Literal["compra", "venta", "ingreso", "retirada"]
    activo: str | None = Field(description="Nombre llano, si es una compra/venta")
    simbolo: str | None
    cantidad: Decimal
    precio: Decimal | None
    comision: Decimal
    importe: Decimal = Field(description="Cantidad por precio (o el importe si es efectivo)")
    origen: str = Field(description="manual, panel, csv:…, ledger:…, plan")
    moneda: str = Field(
        description=(
            "Moneda del importe y la comisión: la de cotización del activo ('USD', 'USDT'); en "
            "el efectivo, la de la cartera ('EUR' la real, 'USDT' la de pruebas); 'EUR' si "
            "`es_referencia` (lo que pagaste; el `precio` es el del fondo de referencia, en "
            "dólares)"
        )
    )
    es_referencia: bool = Field(
        description="True: cantidad/precio son del fondo de EE.UU. de referencia (ver `nota`)"
    )
    nota: str | None = Field(
        description="En llano, p. ej. 'Compraste 5,437 participaciones a 650 € en tu bróker.'"
    )


class Movimientos(BaseModel):
    cartera: CarteraDelModo
    movimientos: list[Movimiento] = Field(description="El más reciente primero")


# -- Conexión con Binance y modo ----------------------------------------------------------------


class Cerrojo(BaseModel):
    nombre: str
    ok: bool
    detalle: str


class EstadoRed(BaseModel):
    red: Red
    claves_guardadas: bool
    origen: Literal["panel", "entorno", "ninguno"]
    verificada: bool = Field(description="Pruebas: hay al menos una orden ejecutada en el registro")


class ModoDisponible(BaseModel):
    modo: ModoPanel
    disponible: bool
    que_falta: list[str]


class Conexion(BaseModel):
    modo: ModoPanel
    modo_origen: Literal["panel", "entorno"]
    redes: list[EstadoRed]
    modos: list[ModoDisponible]
    cerrojos_real: list[Cerrojo]


class NuevasClaves(BaseModel):
    clave: str = Field(min_length=8)
    secreto: str = Field(min_length=8)


class SaldoMoneda(BaseModel):
    moneda: str
    cantidad: Decimal


class PruebaConexion(BaseModel):
    ok: bool
    detalle: str = Field(description="En llano; si falla, qué revisar (p. ej. tipo HMAC)")
    saldo: list[SaldoMoneda] = Field(description="Solo monedas con saldo, ordenadas")


class CambioModo(BaseModel):
    modo: ModoPanel
    confirmacion: str | None = Field(
        default=None, description="Para pasar a real hay que escribir exactamente 'DINERO REAL'"
    )


class Saldo(BaseModel):
    modo: ModoPanel
    saldo: list[SaldoMoneda]
    at: datetime


# -- Datos: que estén al día sin abrir una terminal ----------------------------------------------


class FuenteDatos(BaseModel):
    clave: str = Field(description="historicos | fondos | cripto")
    nombre: str = Field(description="En llano: 'Precios de bolsa y cripto', 'Fondos', ...")
    hasta: date | None = Field(description="Último día con datos")
    dias: int | None = Field(description="Días desde ese último dato")
    al_dia: bool


class PasoDatos(BaseModel):
    nombre: str
    estado: Literal["pendiente", "en_marcha", "bien", "mal"]
    detalle: str | None


class TrabajoDatos(BaseModel):
    en_marcha: bool
    empezado: datetime
    terminado: datetime | None
    pasos: list[PasoDatos]


class EstadoDatos(BaseModel):
    """Lo que usa el panel (mercado, estrategias, plan) y de cuándo es."""

    fuentes: list[FuenteDatos]
    al_dia: bool
    aviso: str | None = Field(description="En llano, si algo está viejo o falta")
    trabajo: TrabajoDatos | None = Field(description="La última actualización (en curso o hecha)")
