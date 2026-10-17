"""Bots con dinero ficticio, al estilo de los vaults de Hyperliquid (docs/panel-v3-vivo.md §3).

Las rutas solo traducen: qué es cada plantilla vive en `bots.plantillas`, lo que decide cada una en
`bots.decisiones` y el bucle que los hace correr, su cuenta y su registro en disco en `bots.motor`.
Con el panel abierto (`crear_app(en_vivo=True)`) las rutas hablan con el motor en marcha; sin él
(los tests, la generación del contrato) leen y escriben `bots/` directamente, sin hacer operar a
nadie. Nada sale al exterior.

`lista()` se pide cada ~2 s desde el stream (`GET /api/vivo/stream`, evento `bots`): sale de
memoria, sin leer el disco.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, Query

from invest_ll.api.errores import del_dominio, no_encontrado
from invest_ll.api.schemas_v3 import (
    Bots,
    DetalleBot,
    EstadoReal,
    EventoBot,
    EvidenciaBot,
    NuevoBot,
    OperacionBot,
    ParametroBot,
    PlantillaBot,
    Plantillas,
    PosicionPractica,
    PuntoBot,
    ResumenBot,
)
from invest_ll.api.schemas_v4 import ActivarReal, CambioLimites, LimiteDiario, ParadaGeneral
from invest_ll.api.schemas_v5 import Actividad, MetricasBot, MovimientoBot, PendienteBot
from invest_ll.bots import motor
from invest_ll.bots.metricas import metricas as calcular_metricas
from invest_ll.bots.motor import NOTA, ZONA, Motor
from invest_ll.bots.pendientes import pendientes as calcular_pendientes
from invest_ll.bots.plantillas import PLANTILLAS
from invest_ll.bots.registro import CARPETA, BotNoEncontradoError
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.bots.actividad import Movimiento
    from invest_ll.bots.motor import Bot
    from invest_ll.bots.plantillas import Evidencia, Plantilla
    from invest_ll.bots.registro import Punto

router = APIRouter()

CENTIMO: Final = Decimal("0.01")
SEGUNDOS_DIA: Final = 86_400


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


def _resumen(m: Motor, bot: Bot) -> ResumenBot:
    d, e = bot.definicion, bot.estado
    ahora = m.ahora()
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
        desde=d.creado,
        dias=round((ahora - d.creado).total_seconds() / SEGUNDOS_DIA, 3),
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
        # Puente hasta los bots reales (v4): hoy todos son ficticios, sin exchange ni limites.
        modo="ficticio",
        exchange=None,
        estrategia=None,
        limites=None,
        consumo=None,
        probado_en_ficticio_dias=None,
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
        desde=bot.definicion.creado,
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
        # Puente hasta los bots reales (v4): hoy todos son ficticios.
        modo="ficticio",
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
        resumen = _resumen(m, bot)
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
        resumenes = [_resumen(m, b) for b in m.bots()]
    capital = sum((r.capital for r in resumenes), Decimal(0))
    valores = [r.valor for r in resumenes]
    conocidos = [v for v in valores if v is not None]
    valor = sum(conocidos, Decimal(0)) if len(conocidos) == len(valores) else None
    ganancia = valor - capital if valor is not None else None
    return Bots(
        bots=resumenes,
        capital=capital,
        valor=_dinero(valor),
        ganancia=_dinero(ganancia),
        ganancia_pct=_fraccion(ganancia, capital),
        # Puente hasta los bots reales (v4): todavia no hay ninguno.
        real=EstadoReal(
            bots_reales=0,
            en_marcha=0,
            perdida_hoy=Decimal(0),
            limite_diario=None,
            parado_todo=False,
            aviso=None,
        ),
        at=m.ahora(),
        nota=NOTA,
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


@router.post("/bots", tags=["bots"], status_code=201)
def desplegar(nuevo: NuevoBot) -> DetalleBot:
    """Crea el bot y lo pone en marcha. 422 en llano si la plantilla, las monedas o los
    parámetros no valen."""
    m = _motor()
    with del_dominio():
        bot = m.desplegar(
            nuevo.plantilla, nuevo.nombre, nuevo.monedas, nuevo.capital, nuevo.parametros
        )
    return _detalle(m, bot)


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
    m = _motor()
    _bot(m, bot_id)
    return _detalle(m, m.reanudar_bot(bot_id))


@router.delete("/bots/{bot_id}", tags=["bots"], status_code=204)
def borrar(bot_id: str) -> None:
    """Borra el bot y su registro. 404 si no existe."""
    m = _motor()
    _bot(m, bot_id)
    m.borrar_bot(bot_id)


# -- Dinero real (docs/panel-v4-real.md §3). ESQUELETO DEL CONTRATO v4: cuerpos pendientes. --------


@router.post("/bots/{bot_id}/activar-real", tags=["bots"])
def activar_real(bot_id: str, peticion: ActivarReal) -> DetalleBot:
    """Pasa a real un bot de pruebas o ficticio con exchange y límites. Exige 'ACTIVAR <nombre>',
    el exchange activo en real y, si su estrategia no lleva 7 días en ficticio, 'SIN PRUEBA EN
    FICTICIO'. 422 en llano con lo que falte. Solo desde el panel: el conector MCP no puede."""
    raise NotImplementedError("pendiente de implementar")


@router.put("/bots/{bot_id}/limites", tags=["bots"])
def cambiar_limites(bot_id: str, cambio: CambioLimites) -> DetalleBot:
    """Bajar límites, siempre; subirlos en un bot real exige 'ACTIVAR <nombre>'."""
    raise NotImplementedError("pendiente de implementar")


@router.get("/bots-real", tags=["bots"])
def estado_real() -> EstadoReal:
    raise NotImplementedError("pendiente de implementar")


@router.post("/bots-real/parar-todo", tags=["bots"])
def parar_todo_real() -> ParadaGeneral:
    """El interruptor: para todos los bots reales y cancela sus órdenes abiertas. Sin confirmación:
    parar tiene que ser fácil."""
    raise NotImplementedError("pendiente de implementar")


@router.post("/bots-real/reanudar-todo", tags=["bots"])
def reanudar_todo_real() -> EstadoReal:
    """Quita el interruptor general (cada bot sigue parado hasta reanudarlo uno a uno)."""
    raise NotImplementedError("pendiente de implementar")


@router.put("/bots-real/limite-diario", tags=["bots"])
def limite_diario(peticion: LimiteDiario) -> EstadoReal:
    """Bajarlo, siempre; subirlo exige 'DINERO REAL'."""
    raise NotImplementedError("pendiente de implementar")
