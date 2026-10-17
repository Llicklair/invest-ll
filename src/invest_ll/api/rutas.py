"""Las rutas del panel: una sección por pestaña, en el orden en que se usan.

ESQUELETO DEL CONTRATO. Las rutas, sus métodos, sus parámetros y sus modelos de respuesta están
fijados (el frontend genera sus tipos desde el OpenAPI que salen de aquí, y
`tests/unit/test_api_contrato.py` comprueba que no se desvían). Lo que falta es el cuerpo de cada
función: toda la lógica ya existe en el motor, la cartera, las alertas, etc.; aquí solo se traduce.

Reglas que vienen del panel de Streamlit y no se pierden al cambiar de tecnología:
- **Nada de aquí envía órdenes salvo `POST /api/ordenes`**, y esa exige la cantidad tecleada
  (`escrito`) y un modo que lo permita, con la misma comprobación que `invest-ll-execute`.
- Registrar en el ledger es contabilidad, no una orden, y se dice en la respuesta.
- Los errores del dominio (`InvestLLError`, `ValueError`) salen como 422 con su texto; la pausa
  de entradas como 409; enviar sin modo que lo permita como 403.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from invest_ll.api.schemas import (
    Alertas,
    AnalisisCartera,
    Cartera,
    Comparacion,
    ComparacionLLM,
    ComprobacionEnvio,
    ComprobacionTriggers,
    Cotizaciones,
    DatosDescargados,
    Estado,
    EstadoEnvio,
    Friccion,
    Informe,
    InformeAportaciones,
    Investigacion,
    MovimientoRegistrado,
    NuevoMovimiento,
    NuevoTrigger,
    OpcionesSimular,
    OrdenesEnviadas,
    Pausa,
    PeticionAportaciones,
    PeticionChat,
    PeticionDescarga,
    PeticionOrden,
    PeticionPropuesta,
    PeticionRegistrarPropuesta,
    PeticionRotacion,
    PeticionUnActivo,
    PeticionUniverso,
    Propuesta,
    RegistroPropuesta,
    Rendimiento,
    RespuestaChat,
    ResultadoActualizacion,
    ResultadoDescarga,
    ResultadoOrden,
    Seguimiento,
    Serie,
    Tramo,
    TriggerArmado,
    Triggers,
)

router = APIRouter(prefix="/api")

PENDIENTE = "pendiente de implementar"

# -- Estado (cabecera) ------------------------------------------------------------------------


@router.get("/estado", tags=["estado"])
def estado() -> Estado:
    """Modo de operación, reserva de datos, activos descargados y pausa de entradas."""
    raise NotImplementedError(PENDIENTE)


# -- Mercado ----------------------------------------------------------------------------------


@router.get("/mercado/rendimiento", tags=["mercado"])
def rendimiento() -> Rendimiento:
    """La mesa densa por periodo, separada en bolsa y cripto (`market_overview`)."""
    raise NotImplementedError(PENDIENTE)


@router.get("/mercado/serie", tags=["mercado"])
def serie(symbol: str, tramo: Tramo = "1a") -> Serie:
    """Cierres de un activo para su gráfica. 404 si no hay histórico de ese símbolo."""
    raise NotImplementedError(PENDIENTE)


@router.get("/mercado/comparacion", tags=["mercado"])
def comparacion(
    activos: list[str] = Query(description="Ids de activos"),  # noqa: B008
    ventana: str | None = Query(default=None, description="'1 mes', '3 meses', '1 año', '5 años'"),
) -> Comparacion:
    """Base 100 al inicio del tramo (`normalised_series`); sin ventana, todo el histórico común."""
    raise NotImplementedError(PENDIENTE)


@router.get("/mercado/datos", tags=["mercado"])
def datos() -> DatosDescargados:
    """Último cierre de cada histórico descargado, y cuáles están desfasados."""
    raise NotImplementedError(PENDIENTE)


@router.post("/mercado/cotizaciones", tags=["mercado"])
def cotizaciones() -> Cotizaciones:
    """Foto al pulsar de Binance (pares USDT) y del catálogo de bolsa. Toca la red."""
    raise NotImplementedError(PENDIENTE)


@router.post("/mercado/descargar", tags=["mercado"])
def descargar(peticion: PeticionDescarga) -> ResultadoDescarga:
    """Descarga el histórico completo (desde 2015) de un activo con `invest-ll-fetch`."""
    raise NotImplementedError(PENDIENTE)


@router.post("/mercado/actualizar", tags=["mercado"])
def actualizar() -> ResultadoActualizacion:
    """Re-descarga todos los históricos con los parámetros de su procedencia (`fetch_args`)."""
    raise NotImplementedError(PENDIENTE)


# -- Mi cartera y órdenes ---------------------------------------------------------------------


@router.get("/cartera", tags=["cartera"])
def cartera() -> Cartera:
    """La cartera derivada del ledger, valorada con el último cierre y SU fecha."""
    raise NotImplementedError(PENDIENTE)


@router.post("/cartera/movimientos", tags=["cartera"], status_code=201)
def registrar_movimiento(movimiento: NuevoMovimiento) -> MovimientoRegistrado:
    """Escribe un movimiento en el ledger (fuente 'panel'). No envía ninguna orden."""
    raise NotImplementedError(PENDIENTE)


@router.get("/ordenes", tags=["ordenes"])
def ordenes() -> OrdenesEnviadas:
    """Lo que de verdad salió al mercado, con el modo de cada orden a la vista."""
    raise NotImplementedError(PENDIENTE)


@router.post("/ordenes/comprobar", tags=["ordenes"])
def comprobar_envio(comprobacion: ComprobacionEnvio) -> EstadoEnvio:
    """Si con el modo actual y lo tecleado se podría enviar (`motivo_para_no_enviar`)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/ordenes", tags=["ordenes"])
def enviar(peticion: PeticionOrden) -> ResultadoOrden:
    """Envía UNA orden con la confirmación tecleada (`enviar_orden`). 403 en simulación."""
    raise NotImplementedError(PENDIENTE)


# -- Simular ----------------------------------------------------------------------------------


@router.get("/simular/opciones", tags=["simular"])
def opciones_simular() -> OpcionesSimular:
    """Frecuencias, activos compatibles sugeridos, estrategias y si hay pausa."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/propuesta", tags=["simular"])
def propuesta(peticion: PeticionPropuesta) -> Propuesta:
    """Propuesta simple (`propose_portfolio`). 409 si hay pausa de entradas."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/propuesta/registrar", tags=["simular"])
def registrar_propuesta(peticion: PeticionRegistrarPropuesta) -> RegistroPropuesta:
    """Anota las compras de la propuesta en el ledger (fuente 'propuesta'). No compra nada."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/activo", tags=["simular"])
def un_activo(peticion: PeticionUnActivo) -> Informe:
    """Una estrategia sobre un activo (`run_backtest`)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/cartera/analisis", tags=["simular"])
def analisis_cartera(peticion: PeticionUniverso) -> AnalisisCartera:
    """Diversificación real del universo (`analyze_portfolio`)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/cartera/aportaciones", tags=["simular"])
def aportaciones(peticion: PeticionAportaciones) -> InformeAportaciones:
    """Aportaciones periódicas (`run_dca`)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/cartera/rotacion", tags=["simular"])
def rotacion(peticion: PeticionRotacion) -> Informe:
    """Rotación por momentum relativo (`run_rotation`)."""
    raise NotImplementedError(PENDIENTE)


@router.post("/simular/llm", tags=["simular"])
def llm(friccion: Friccion) -> ComparacionLLM:
    """El experimento del LLM con decisiones grabadas, contra momentum y no hacer nada."""
    raise NotImplementedError(PENDIENTE)


# -- Vigilar ----------------------------------------------------------------------------------


@router.get("/vigilar/alertas", tags=["vigilar"])
def alertas(
    dias: int = Query(default=7, ge=1, le=365),
    caida_pct: int = Query(default=15, ge=1, le=99),
) -> Alertas:
    """Alertas de riesgo sobre los históricos. Nunca de subidas."""
    raise NotImplementedError(PENDIENTE)


@router.get("/triggers", tags=["vigilar"])
def triggers() -> Triggers:
    raise NotImplementedError(PENDIENTE)


@router.post("/triggers", tags=["vigilar"], status_code=201)
def armar(nuevo: NuevoTrigger) -> TriggerArmado:
    raise NotImplementedError(PENDIENTE)


@router.delete("/triggers/{trigger_id}", tags=["vigilar"], status_code=204)
def desarmar(trigger_id: str) -> None:
    """404 si no existe: desarmar lo inexistente no es un éxito."""
    raise NotImplementedError(PENDIENTE)


@router.get("/triggers/comprobar", tags=["vigilar"])
def comprobar_triggers() -> ComprobacionTriggers:
    """Evalúa los triggers contra la cartera real; los disparos son texto, nada se envía."""
    raise NotImplementedError(PENDIENTE)


@router.post("/pausa", tags=["vigilar"], status_code=204)
def pausar(pausa: Pausa) -> None:
    """Nivel 1 del kill switch. 422 si el motivo está vacío."""
    raise NotImplementedError(PENDIENTE)


@router.delete("/pausa", tags=["vigilar"], status_code=204)
def reanudar() -> None:
    """404 si no había pausa."""
    raise NotImplementedError(PENDIENTE)


# -- Estimado vs real -------------------------------------------------------------------------


@router.get("/seguimiento", tags=["seguimiento"])
def seguimiento() -> Seguimiento:
    raise NotImplementedError(PENDIENTE)


# -- Investigación ----------------------------------------------------------------------------


@router.get("/investigacion", tags=["investigacion"])
def investigacion(capital: float = Query(default=1000.0, ge=0)) -> Investigacion:
    """La cartera prerregistrada hoy, su prueba hacia delante y el último estudio."""
    raise NotImplementedError(PENDIENTE)


@router.get("/investigacion/estudio", tags=["investigacion"], response_class=HTMLResponse)
def estudio() -> str:
    """El HTML del último estudio, para incrustarlo. 404 si no hay ninguno."""
    raise NotImplementedError(PENDIENTE)


# -- Chat -------------------------------------------------------------------------------------


@router.post("/chat", tags=["chat"])
def chat(peticion: PeticionChat) -> RespuestaChat:
    """Pregunta a Claude con tu situación delante (gasta cuota). No puede ejecutar nada."""
    raise NotImplementedError(PENDIENTE)
