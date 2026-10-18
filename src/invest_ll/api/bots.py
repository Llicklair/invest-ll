"""Bots al estilo de los vaults de Hyperliquid (docs/panel-v3-vivo.md §3): con dinero ficticio,
en la red de pruebas de un exchange o con dinero real (docs/panel-v4-real.md §3).

Las rutas solo traducen: qué es cada plantilla vive en `bots.plantillas`, lo que decide cada una en
`bots.decisiones` y el bucle que los hace correr, su cuenta y su registro en disco en `bots.motor`.
En el servicio de los bots (`bots.servicio`, que el panel arranca y al que le pasa estas rutas) hablan
con el motor en marcha; sin él
(los tests, la generación del contrato) leen y escriben `bots/` directamente, sin hacer operar a
nadie.

**Dinero real.** Activarlo, subir límites y subir el límite diario piden una confirmación tecleada
que se comprueba aquí, antes de llegar al motor. Son rutas del panel: el conector MCP no tiene
ninguna herramienta que las llame (docs/panel-v4-real.md §0.5). Parar todo no pide nada.

`lista()` se pide cada ~2 s desde el stream (`GET /api/vivo/stream`, evento `bots`): sale de
memoria, sin leer el disco.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Final, Literal, cast

from fastapi import APIRouter, Query

from invest_ll.api.errores import conflicto, del_dominio, invalido, no_encontrado
from invest_ll.api.schemas_v3 import (
    Bots,
    ConsumoLimites,
    DetalleBot,
    EstadoReal,
    EventoBot,
    EvidenciaBot,
    LimitesBot,
    NuevoBot,
    OperacionBot,
    ParametroBot,
    PausaBot,
    PlantillaBot,
    Plantillas,
    PosicionPractica,
    PuntoBot,
    ResumenBot,
    TotalModo,
)
from invest_ll.api.schemas_v4 import ActivarReal, CambioLimites, LimiteDiario, ParadaGeneral
from invest_ll.api.schemas_v5 import (
    Actividad,
    ActividadNueva,
    MetricasBot,
    MovimientoBot,
    PendienteBot,
)
from invest_ll.bots import motor, real
from invest_ll.bots.metricas import metricas as calcular_metricas
from invest_ll.bots.motor import NOTA, ZONA, Motor, limites_suben
from invest_ll.bots.pendientes import pendientes as calcular_pendientes
from invest_ll.bots.plantillas import MEDIDA, PLANTILLAS
from invest_ll.bots.registro import CARPETA, BotNoEncontradoError, Limites
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Mapping
    from datetime import datetime

    from invest_ll.bots.actividad import Movimiento
    from invest_ll.bots.motor import Bot
    from invest_ll.bots.plantillas import Evidencia, Plantilla
    from invest_ll.bots.registro import ModoBot, Pausa, Punto

log = logging.getLogger(__name__)
router = APIRouter()

CENTIMO: Final = Decimal("0.01")
SEGUNDOS_DIA: Final = 86_400
DIAS_EN_FICTICIO: Final = 7
"""Los que una estrategia tiene que llevar en ficticio para activarla sin «SIN PRUEBA EN FICTICIO»."""
SIN_FICTICIO: Final = "SIN PRUEBA EN FICTICIO"
DINERO_REAL: Final = "DINERO REAL"
NOTA_CON_EXCHANGE: Final = (
    "Cada bot dice con qué dinero opera: ficticio, de pruebas o real (en rojo). Los bots siguen "
    "aunque cierres el panel, mientras el ordenador esté encendido."
)
MODOS: Final[tuple[ModoBot, ...]] = ("ficticio", "pruebas", "real")


def _motor() -> Motor:
    """El motor del panel si está en marcha; si no, uno sin bucle sobre `bots/`."""
    activo = motor.activo()
    if activo is not None:
        return activo
    m = Motor(motor.fuente_del_servicio(), CARPETA)
    m.cargar()
    return m


def _bot(m: Motor, bot_id: str) -> Bot:
    try:
        return m.bot(bot_id)
    except BotNoEncontradoError as error:
        raise no_encontrado(str(error)) from error


def _dinero(valor: Decimal | None) -> Decimal | None:
    return valor.quantize(CENTIMO) if valor is not None else None


def _cantidad(valor: Decimal) -> Decimal:
    """Sin ceros de más ni notación científica: '0.0148', '2'."""
    return Decimal(format(valor.normalize(), "f"))


def _fraccion(parte: Decimal | None, total: Decimal | None) -> float | None:
    if parte is None or total is None or total == 0:
        return None
    return float(parte / total)


def _activacion(nombre: str) -> str:
    return f"ACTIVAR {nombre}"


def _limites(lim: Limites | None) -> LimitesBot | None:
    if lim is None:
        return None
    return LimitesBot(
        capital_max=lim.capital_max,
        orden_max=lim.orden_max,
        perdida_max_pct=lim.perdida_max_pct,
        vender_al_parar=lim.vender_al_parar,
        operaciones_max_dia=lim.operaciones_max_dia,
    )


def _limites_de(lim: LimitesBot) -> Limites:
    return Limites(
        capital_max=lim.capital_max,
        orden_max=lim.orden_max,
        perdida_max_pct=lim.perdida_max_pct,
        vender_al_parar=lim.vender_al_parar,
        operaciones_max_dia=lim.operaciones_max_dia,
    )


def _pausa(p: Pausa | None) -> PausaBot | None:
    if p is None:
        return None
    motivo = "conciliacion" if p.motivo == "conciliacion" else "desconocido"
    return PausaBot(motivo=motivo, texto=p.texto, diferencia=p.diferencia, at=p.at)


def _inicio(bot: Bot) -> datetime:
    """Desde cuándo cuenta: al activar el dinero real, empieza de cero."""
    return bot.definicion.activado or bot.definicion.creado


def _dias_en_ficticio(bots: Iterable[Bot], ahora: datetime) -> dict[tuple[str, str | None], float]:
    """Por plantilla (y estrategia a medida): los días del bot ficticio que más lleva con ella."""
    dias: dict[tuple[str, str | None], float] = {}
    for b in bots:
        d = b.definicion
        if d.modo != "ficticio":
            continue
        clave = (d.plantilla, d.estrategia)
        lleva = (ahora - _inicio(b)).total_seconds() / SEGUNDOS_DIA
        dias[clave] = max(dias.get(clave, 0.0), lleva)
    return dias


def _evidencia(e: Evidencia) -> EvidenciaBot:
    return EvidenciaBot(tipo=e.tipo, texto=e.texto)


def _plantilla(p: Plantilla) -> PlantillaBot:
    return PlantillaBot(
        clave=p.clave,
        nombre=p.nombre,
        frase=p.frase,
        como_funciona=list(p.como_funciona),
        avisos=list(p.avisos),
        evidencia=_evidencia(p.evidencia),
        riesgo=p.riesgo,
        riesgo_texto=p.riesgo_texto,
        operaciones_esperadas=p.operaciones_esperadas,
        monedas=p.monedas,
        monedas_sugeridas=list(p.monedas_sugeridas),
        parametros=[
            ParametroBot(
                clave=q.clave,
                nombre=q.nombre,
                explicacion=q.explicacion,
                tipo=q.tipo,
                defecto=q.defecto,
                minimo=q.minimo,
                maximo=q.maximo,
                opciones=list(q.opciones) if q.opciones is not None else None,
            )
            for q in p.parametros
        ],
    )


def _puntos(puntos: list[Punto]) -> list[PuntoBot]:
    return [PuntoBot(at=p.at, valor=float(p.valor)) for p in puntos]


def _resumen(
    m: Motor, bot: Bot, dias_ficticio: Mapping[tuple[str, str | None], float]
) -> ResumenBot:
    d, e = bot.definicion, bot.estado
    ahora = m.ahora()
    inicio = _inicio(bot)
    valor = bot.valor()
    ganancia = valor - d.capital if valor is not None else None
    mantener = bot.mantener()
    return ResumenBot(
        id=d.id,
        nombre=d.nombre,
        plantilla=d.plantilla,
        nombre_plantilla=bot.plantilla.nombre,
        monedas=list(d.monedas),
        estado=e.estado,
        motivo_error=e.motivo_error,
        desde=inicio,
        dias=round((ahora - inicio).total_seconds() / SEGUNDOS_DIA, 3),
        capital=d.capital,
        valor=_dinero(valor),
        ganancia=_dinero(ganancia),
        ganancia_pct=_fraccion(ganancia, d.capital),
        ganancia_24h_pct=bot.ganancia_24h_pct(ahora),
        mantener_pct=_fraccion(mantener - d.capital, d.capital) if mantener is not None else None,
        peor_caida=e.peor_caida,
        operaciones=e.operaciones,
        evidencia=_evidencia(bot.plantilla.evidencia_para(d.monedas)),
        riesgo=bot.plantilla.riesgo,
        curva=_puntos(bot.curva_muestreada(ahora)),
        ultima_actividad=e.ultima_operacion,
        aviso=m.aviso(bot),
        modo=d.modo,
        exchange=d.exchange,
        estrategia=d.estrategia,
        limites=_limites(d.limites),
        consumo=ConsumoLimites(
            gastado=real.gastado(bot.cuenta).quantize(CENTIMO),
            perdida_pct=real.perdida_pct(valor, d.capital),
            operaciones_hoy=e.operaciones_hoy,
        )
        if d.limites is not None
        else None,
        probado_en_ficticio_dias=round(dias_ficticio.get((d.plantilla, d.estrategia), 0.0), 3),
        pausa=_pausa(e.pausa),
    )


def _posiciones(bot: Bot) -> list[PosicionPractica]:
    posiciones: list[PosicionPractica] = []
    for coin, p in sorted(bot.cuenta.posiciones.items()):
        precio = bot.estado.ultimos_precios.get(coin)
        valor = p.cantidad * precio if precio is not None else None
        ganancia = valor - p.coste if valor is not None else None
        posiciones.append(
            PosicionPractica(
                coin=coin,
                nombre=nombre_hyperliquid(coin),
                cantidad=_cantidad(p.cantidad),
                precio_medio=_cantidad(p.precio_medio.quantize(Decimal("1e-8"))),
                precio=precio,
                valor=_dinero(valor),
                ganancia=_dinero(ganancia),
                ganancia_pct=_fraccion(ganancia, p.coste),
            )
        )
    return posiciones


def _metricas(m: Motor, bot: Bot, resumen: ResumenBot) -> MetricasBot:
    r = calcular_metricas(
        m.todas_las_operaciones(bot.id),
        desde=_inicio(bot),
        ahora=m.ahora(),
        posiciones=bot.cuenta.posiciones,
        precios=bot.estado.ultimos_precios,
    )
    frente = (
        resumen.ganancia_pct - resumen.mantener_pct
        if resumen.ganancia_pct is not None and resumen.mantener_pct is not None
        else None
    )
    return MetricasBot(
        operaciones=r.operaciones,
        compras=r.compras,
        ventas=r.ventas,
        cerradas=r.cerradas,
        aciertos=r.aciertos,
        factor_beneficio=r.factor_beneficio,
        ganancia_media=_dinero(r.ganancia_media),
        perdida_media=_dinero(r.perdida_media),
        realizada=r.realizada.quantize(CENTIMO),
        sin_realizar=_dinero(r.sin_realizar),
        comisiones=r.comisiones.quantize(CENTIMO),
        tiempo_dentro=r.tiempo_dentro,
        operaciones_dia=r.operaciones_dia,
        frente_a_mantener=frente,
        aviso=r.aviso,
    )


def _pendientes(m: Motor, bot: Bot) -> list[PendienteBot]:
    lista = calcular_pendientes(bot, m.ahora(), m.velas_de(bot), ZONA)
    precios = bot.estado.ultimos_precios
    salida: list[PendienteBot] = []
    for p in lista:
        actual = precios.get(p.coin) if p.coin is not None else None
        salida.append(
            PendienteBot(
                tipo=p.tipo,
                texto=p.texto,
                coin=p.coin,
                precio=_cantidad(p.precio) if p.precio is not None else None,
                distancia=float(p.precio / actual - 1) if p.precio is not None and actual else None,
                importe=_dinero(p.importe),
                cantidad=_cantidad(p.cantidad) if p.cantidad is not None else None,
                cuando=p.cuando,
            )
        )
    return salida


def movimiento(mov: Movimiento) -> MovimientoBot:
    """Del motor al contrato (lo usa también el canal `actividad` del stream)."""
    return MovimientoBot(
        id=mov.id,
        at=mov.at,
        bot_id=mov.bot_id,
        bot_nombre=mov.bot_nombre,
        modo=mov.modo,
        tipo=mov.tipo,
        texto=mov.texto,
        coin=mov.coin,
        nombre_moneda=nombre_hyperliquid(mov.coin) if mov.coin is not None else None,
        cantidad=_cantidad(mov.cantidad) if mov.cantidad is not None else None,
        precio=_cantidad(mov.precio) if mov.precio is not None else None,
        importe=_dinero(mov.importe),
        comision=_cantidad(mov.comision) if mov.comision is not None else None,
        resultado=_dinero(mov.resultado),
    )


def _detalle(m: Motor, bot: Bot) -> DetalleBot:
    with m.cerrojo:  # que el bucle no lo cambie a mitad
        resumen = _resumen(m, bot, _dias_en_ficticio(m.bots(), m.ahora()))
        curva = bot.curva_muestreada(m.ahora())
        return DetalleBot(
            **resumen.model_dump(),
            parametros=dict(bot.definicion.parametros),
            efectivo=bot.cuenta.efectivo.quantize(CENTIMO),
            posiciones=_posiciones(bot),
            lista_operaciones=[
                OperacionBot(
                    at=o.at,
                    coin=o.coin,
                    nombre=nombre_hyperliquid(o.coin),
                    lado=o.lado,
                    cantidad=_cantidad(o.cantidad),
                    precio=_cantidad(o.precio),
                    importe=o.importe.quantize(CENTIMO),
                    comision=_cantidad(o.comision),
                    motivo=o.motivo,
                )
                for o in m.operaciones(bot.id)
            ],
            eventos=[EventoBot(at=e.at, tipo=e.tipo, texto=e.texto) for e in m.eventos(bot.id)],
            curva_mantener=[
                PuntoBot(at=p.at, valor=float(p.mantener)) for p in curva if p.mantener is not None
            ],
            metricas=_metricas(m, bot, resumen),
            pendientes=_pendientes(m, bot),
        )


@router.get("/bots/plantillas", tags=["bots"])
def plantillas() -> Plantillas:
    return Plantillas(plantillas=[_plantilla(p) for p in PLANTILLAS.values()])


@router.get("/bots", tags=["bots"])
def lista() -> Bots:
    """Todos los bots con lo que llevan generado, valorados a precios de ahora."""
    m = _motor()
    with m.cerrojo:  # que el bucle no cambie un bot a mitad de leerlo
        bots = m.bots()
        dias = _dias_en_ficticio(bots, m.ahora())
        resumenes = [_resumen(m, b, dias) for b in bots]
        estado = _estado_real(m)
    por_modo = [_total(modo, resumenes) for modo in MODOS if any(r.modo == modo for r in resumenes)]
    ficticio = _total("ficticio", resumenes)
    return Bots(
        bots=resumenes,
        capital=ficticio.capital,
        valor=ficticio.valor,
        ganancia=ficticio.ganancia,
        ganancia_pct=ficticio.ganancia_pct,
        por_modo=por_modo,
        real=estado,
        at=m.ahora(),
        nota=NOTA if all(r.modo == "ficticio" for r in resumenes) else NOTA_CON_EXCHANGE,
    )


def _total(modo: ModoBot, resumenes: Iterable[ResumenBot]) -> TotalModo:
    suyos = [r for r in resumenes if r.modo == modo]
    capital = sum((r.capital for r in suyos), Decimal(0))
    valores = [r.valor for r in suyos]
    conocidos = [v for v in valores if v is not None]
    valor = sum(conocidos, Decimal(0)) if len(conocidos) == len(valores) else None
    ganancia = valor - capital if valor is not None else None
    return TotalModo(
        modo=modo,
        bots=len(suyos),
        capital=capital,
        valor=_dinero(valor),
        ganancia=_dinero(ganancia),
        ganancia_pct=_fraccion(ganancia, capital),
    )


def _estado_real(m: Motor) -> EstadoReal:
    reales = [b for b in m.bots() if b.definicion.modo == "real"]
    g = m.globales()
    en_pausa = [b for b in reales if b.estado.pausa is not None]
    if g.parado_todo:
        aviso = f"Todo lo real está parado. {g.motivo or ''}".strip()
    elif en_pausa:
        aviso = (
            "1 bot real en pausa: míralo."
            if len(en_pausa) == 1
            else f"{len(en_pausa)} bots reales en pausa: míralos."
        )
    else:
        aviso = None
    return EstadoReal(
        bots_reales=len(reales),
        en_marcha=sum(1 for b in reales if b.estado.estado == "en_marcha"),
        perdida_hoy=m.perdida_hoy().quantize(CENTIMO),
        limite_diario=g.limite_diario,
        parado_todo=g.parado_todo,
        parado_desde=g.parado_desde,
        aviso=aviso,
    )


@router.get("/actividad", tags=["bots"])
def actividad(bot: str | None = None, limite: int = Query(default=50, ge=1, le=200)) -> Actividad:
    """Los últimos movimientos de los bots (o de uno), el más reciente primero. En directo, por el
    canal `actividad` de `GET /api/vivo/stream`. 404 si se pide un bot que no existe."""
    m = _motor()
    if bot is not None:
        _bot(m, bot)
    _, lista = m.actividad(bot_id=bot, limite=limite)
    return Actividad(movimientos=[movimiento(x) for x in lista], inicial=True, at=m.ahora())


@router.get("/actividad/nueva", tags=["bots"])
def actividad_nueva(vista: int | None = None) -> ActividadNueva:
    """Para el stream del panel cuando los bots viven en su servicio: lo del feed posterior al
    número `vista` (sin él, lo último), y el número del último."""
    from invest_ll.api import vivo as rutas_vivo

    leida = rutas_vivo.actividad_local(vista)
    if leida is None:
        return ActividadNueva(numero=vista or 0, actividad=None)
    numero, nueva = leida
    return ActividadNueva(numero=numero, actividad=cast("Actividad | None", nueva))


@router.post("/bots", tags=["bots"], status_code=201)
def desplegar(nuevo: NuevoBot) -> DetalleBot:
    """Crea el bot y lo pone en marcha. 422 en llano si la plantilla, las monedas o los
    parámetros no valen. En pruebas, también si su exchange no está conectado en pruebas, faltan
    sus límites o no hay saldo; en real no se crea (se activa desde su ficha)."""
    m = _motor()
    with del_dominio():
        bot = m.desplegar(
            nuevo.plantilla,
            nuevo.nombre,
            nuevo.monedas,
            nuevo.capital,
            nuevo.parametros,
            modo=nuevo.modo,
            exchange=nuevo.exchange,
            estrategia=nuevo.estrategia,
            limites=_limites_de(nuevo.limites) if nuevo.limites is not None else None,
        )
    if bot.definicion.plantilla == MEDIDA and bot.definicion.estrategia:
        _marcar_estrategia(bot.definicion.estrategia, "ficticio")
    return _detalle(m, bot)


def _marcar_estrategia(estrategia_id: str, estado: Literal["ficticio", "real"]) -> None:
    """La biblioteca de estrategias apunta hasta dónde llegó cada una (solo sube)."""
    from invest_ll.estrategias_custom import biblioteca

    try:
        biblioteca.marcar_estado(estrategia_id, estado)
    except Exception:  # el bot ya está desplegado: que la ficha no se actualice no lo deshace
        log.exception("no se pudo marcar la estrategia %s como %s", estrategia_id, estado)


@router.get("/bots/{bot_id}", tags=["bots"])
def detalle(bot_id: str) -> DetalleBot:
    """404 si no existe."""
    m = _motor()
    return _detalle(m, _bot(m, bot_id))


@router.post("/bots/{bot_id}/parar", tags=["bots"])
def parar(bot_id: str) -> DetalleBot:
    """Deja de operar; conserva sus posiciones (siguen valorándose)."""
    m = _motor()
    _bot(m, bot_id)
    return _detalle(m, m.parar_bot(bot_id))


@router.post("/bots/{bot_id}/reanudar", tags=["bots"])
def reanudar(bot_id: str) -> DetalleBot:
    """Vuelve a operar. Uno de exchange en pausa la resuelve antes; 409 en llano si no se puede
    (sigue sin cuadrar, no se pudo consultar el exchange, «Parar todo lo real» puesto)."""
    m = _motor()
    _bot(m, bot_id)
    try:
        return _detalle(m, m.reanudar_bot(bot_id))
    except real.NoSePuedeError as error:
        raise conflicto(str(error)) from error


@router.delete("/bots/{bot_id}", tags=["bots"], status_code=204)
def borrar(bot_id: str) -> None:
    """Borra el bot y su registro. 404 si no existe. Uno de exchange tiene que estar parado (409);
    lo que tenga se queda en el exchange: borrar no vende nada."""
    m = _motor()
    _bot(m, bot_id)
    try:
        m.borrar_bot(bot_id)
    except real.NoSePuedeError as error:
        raise conflicto(str(error)) from error


# -- Dinero real (docs/panel-v4-real.md §3) -------------------------------------------------------


@router.post("/bots/{bot_id}/activar-real", tags=["bots"])
def activar_real(bot_id: str, peticion: ActivarReal) -> DetalleBot:
    """Pasa a real un bot de pruebas o ficticio con exchange y límites. Exige 'ACTIVAR <nombre>',
    el exchange activo en real y, si su estrategia no lleva 7 días en ficticio, 'SIN PRUEBA EN
    FICTICIO'. 422 en llano con lo que falte; 409 si «Parar todo lo real» está puesto. Solo desde
    el panel: el conector MCP no puede."""
    m = _motor()
    bot = _bot(m, bot_id)
    d = bot.definicion
    if peticion.confirmacion != _activacion(d.nombre):
        raise invalido(
            f"Para activar el dinero real escribe exactamente «{_activacion(d.nombre)}»."
        )
    exchange = peticion.exchange or d.exchange
    if exchange is None:
        raise invalido("Elige en qué exchange opera con dinero real.")
    limites = _limites_de(peticion.limites) if peticion.limites is not None else d.limites
    if limites is None:
        raise invalido(
            "Pon sus límites antes de activarlo: capital máximo, máximo por orden, pérdida máxima "
            "y operaciones por día."
        )
    with m.cerrojo:
        dias = _dias_en_ficticio(m.bots(), m.ahora()).get((d.plantilla, d.estrategia), 0.0)
    if dias < DIAS_EN_FICTICIO and peticion.sin_ficticio != SIN_FICTICIO:
        lleva = f"{dias:.1f}".replace(".", ",")
        raise invalido(
            f"Su estrategia lleva {lleva} días en ficticio (menos de {DIAS_EN_FICTICIO}). Para "
            f"activarlo igualmente, escribe también «{SIN_FICTICIO}»."
        )
    try:
        with del_dominio():
            activado = m.activar_real(bot_id, exchange, limites)
    except real.NoSePuedeError as error:
        raise conflicto(str(error)) from error
    if d.plantilla == MEDIDA and d.estrategia:
        _marcar_estrategia(d.estrategia, "real")
    return _detalle(m, activado)


@router.put("/bots/{bot_id}/limites", tags=["bots"])
def cambiar_limites(bot_id: str, cambio: CambioLimites) -> DetalleBot:
    """Bajar límites, siempre; subirlos en un bot real exige 'ACTIVAR <nombre>'."""
    m = _motor()
    bot = _bot(m, bot_id)
    d = bot.definicion
    nuevos = _limites_de(cambio.limites)
    if (
        d.modo == "real"
        and limites_suben(d.limites, nuevos)
        and cambio.confirmacion != _activacion(d.nombre)
    ):
        raise invalido(
            "Subir los límites de un bot real pide la misma confirmación que activarlo: escribe "
            f"exactamente «{_activacion(d.nombre)}»."
        )
    with del_dominio():
        return _detalle(m, m.cambiar_limites(bot_id, nuevos))


@router.get("/bots-real", tags=["bots"])
def estado_real() -> EstadoReal:
    """El interruptor general, la pérdida de hoy de los bots reales y su límite diario."""
    m = _motor()
    with m.cerrojo:
        return _estado_real(m)


@router.post("/bots-real/parar-todo", tags=["bots"])
def parar_todo_real() -> ParadaGeneral:
    """El interruptor: para todos los bots reales y cancela sus órdenes abiertas. Sin confirmación:
    parar tiene que ser fácil."""
    parados, canceladas, avisos = _motor().parar_todo_real()
    return ParadaGeneral(parados=parados, ordenes_canceladas=canceladas, avisos=avisos)


@router.post("/bots-real/reanudar-todo", tags=["bots"])
def reanudar_todo_real() -> EstadoReal:
    """Quita el interruptor general (cada bot sigue parado hasta reanudarlo uno a uno)."""
    m = _motor()
    m.reanudar_todo_real()
    with m.cerrojo:
        return _estado_real(m)


@router.put("/bots-real/limite-diario", tags=["bots"])
def limite_diario(peticion: LimiteDiario) -> EstadoReal:
    """Bajarlo, siempre; subirlo exige 'DINERO REAL'."""
    m = _motor()
    antes = m.globales().limite_diario
    if antes is not None and peticion.limite > antes and peticion.confirmacion != DINERO_REAL:
        raise invalido(f"Subir el límite diario pide escribir exactamente «{DINERO_REAL}».")
    m.cambiar_limite_diario(peticion.limite)
    with m.cerrojo:
        return _estado_real(m)
