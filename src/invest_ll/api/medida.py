"""Estrategias a medida y diseñarlas con Claude (docs/panel-v4-real.md §2).

Las rutas solo traducen: el formato y sus reglas en llano viven en `estrategias_custom.formato`, la
prueba sobre el pasado en `estrategias_custom.prueba`, la biblioteca (`medida/`) en
`estrategias_custom.biblioteca` y la conversación con Claude en `estrategias_custom.disenar`. Una
estrategia es un JSON validado que el motor interpreta; nada se ejecuta como código.

Lo que sale a la red (las velas del exchange para probar, el CLI de `claude` para diseñar) se pide
por `conector_publico` y `nuevo_disenador`, que los tests sustituyen.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter

from invest_ll.api.errores import conflicto, del_dominio, no_encontrado
from invest_ll.api.schemas_v3 import OperacionBot, PuntoBot
from invest_ll.api.schemas_v4 import (
    DetalleEstrategia,
    EsquemaEstrategia,
    Estrategias,
    MensajeDiseno,
    NuevaEstrategia,
    PeticionDiseno,
    PeticionPruebaEstrategia,
    RespuestaDiseno,
    ResultadoPrueba,
    ResumenEstrategia,
    VersionEstrategia,
)
from invest_ll.estrategias_custom import formato
from invest_ll.estrategias_custom.biblioteca import (
    CARPETA,
    Biblioteca,
    EstrategiaNoEncontradaError,
    bots_que_usan,
)
from invest_ll.estrategias_custom.disenar import Disenador, SesionNoEncontradaError
from invest_ll.estrategias_custom.prueba import probar as probar_estrategia
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.estrategias_custom.biblioteca import Ficha
    from invest_ll.estrategias_custom.disenar import Turno
    from invest_ll.estrategias_custom.prueba import Resultado
    from invest_ll.exchanges.conector import Conector

router = APIRouter()

CENTIMO: Final = Decimal("0.01")


def biblioteca() -> Biblioteca:
    """La de `medida/`, relativa al directorio de trabajo (como `bots/`)."""
    return Biblioteca(CARPETA)


def conector_publico(exchange: str) -> Conector:
    """Las velas del exchange para probar. Los tests lo sustituyen por un conector falso."""
    from invest_ll.exchanges import registro

    return registro.conector_publico(exchange)


def nuevo_disenador(b: Biblioteca) -> Disenador:
    """La conversación con el CLI de claude. Los tests la sustituyen: gasta cuota."""
    return Disenador(b)


def _ficha(b: Biblioteca, estrategia_id: str) -> Ficha:
    try:
        return b.ficha(estrategia_id)
    except EstrategiaNoEncontradaError as error:
        raise no_encontrado(str(error)) from error


def _cantidad(valor: Decimal) -> Decimal:
    return Decimal(format(valor.normalize(), "f"))


def _resultado(r: Resultado) -> ResultadoPrueba:
    return ResultadoPrueba(
        exchange=r.exchange,
        monedas=list(r.monedas),
        intervalo=r.intervalo,
        desde=r.desde,
        hasta=r.hasta,
        capital=r.capital,
        valor_final=r.valor_final.quantize(CENTIMO),
        ganancia_pct=r.ganancia_pct,
        mantener_pct=r.mantener_pct,
        peor_caida=r.peor_caida,
        mantener_peor_caida=r.mantener_peor_caida,
        operaciones=r.operaciones,
        comisiones=r.comisiones.quantize(CENTIMO),
        tiempo_dentro=r.tiempo_dentro,
        curva=[PuntoBot(at=p.at, valor=float(p.valor)) for p in r.curva],
        curva_mantener=[PuntoBot(at=p.at, valor=float(p.valor)) for p in r.curva_mantener],
        lista_operaciones=[
            OperacionBot(
                at=o.at,
                coin=o.coin,
                nombre=nombre_hyperliquid(o.coin),
                lado="compra" if o.lado == "compra" else "venta",
                cantidad=_cantidad(o.cantidad),
                precio=_cantidad(o.precio),
                importe=o.importe.quantize(CENTIMO),
                comision=_cantidad(o.comision),
                motivo=o.motivo,
            )
            for o in r.lista_operaciones
        ],
        versiones_probadas=r.versiones_probadas,
        aviso_sobreajuste=r.aviso_sobreajuste,
        avisos=list(r.avisos),
    )


def _resumen(b: Biblioteca, f: Ficha) -> ResumenEstrategia:
    e = f.estrategia
    ultima = b.ultima_prueba(f.id)
    return ResumenEstrategia(
        id=f.id,
        nombre=e.nombre,
        version=f.ultima.version,
        estado=f.estado,
        autor=f.autor,
        explicacion=e.explicacion,
        monedas=list(e.monedas),
        intervalo=e.intervalo,
        actualizada=f.actualizada,
        ultima_prueba=_resultado(ultima) if ultima is not None else None,
        bots=bots_que_usan(f.id),
    )


def _detalle(b: Biblioteca, f: Ficha) -> DetalleEstrategia:
    resumen = _resumen(b, f)
    return DetalleEstrategia(
        **resumen.model_dump(),
        definicion=f.ultima.definicion,
        reglas_en_llano=formato.reglas_en_llano(f.estrategia),
        versiones=[
            VersionEstrategia(version=v.version, at=v.at, huella=v.huella, nota=v.nota)
            for v in f.versiones
        ],
        pruebas=[_resultado(r) for r in b.pruebas(f.id)],
    )


def _respuesta(t: Turno) -> RespuestaDiseno:
    return RespuestaDiseno(
        sesion=t.sesion,
        respuesta=t.respuesta,
        estrategia=t.estrategia,
        herramientas=list(t.herramientas),
        historial=[MensajeDiseno(autor=m.autor, texto=m.texto, at=m.at) for m in t.historial],
    )


@router.get("/medida", tags=["medida"])
def lista() -> Estrategias:
    b = biblioteca()
    return Estrategias(estrategias=[_resumen(b, f) for f in b.fichas()])


@router.get("/medida/esquema", tags=["medida"])
def esquema() -> EsquemaEstrategia:
    """El formato de las estrategias (JSON Schema), con ejemplos y su explicación."""
    return EsquemaEstrategia(
        esquema=formato.esquema(), ejemplos=formato.EJEMPLOS, explicacion=formato.EXPLICACION
    )


@router.post("/medida", tags=["medida"], status_code=201)
def guardar(nueva: NuevaEstrategia) -> DetalleEstrategia:
    """Valida y guarda (nueva estrategia o nueva versión). 422 en llano si no es válida."""
    b = biblioteca()
    if nueva.id is not None:
        _ficha(b, nueva.id)
    with del_dominio():
        f = b.guardar(nueva.definicion, autor=nueva.autor, nota=nueva.nota, estrategia_id=nueva.id)
    return _detalle(b, f)


@router.get("/medida/{estrategia_id}", tags=["medida"])
def detalle(estrategia_id: str) -> DetalleEstrategia:
    b = biblioteca()
    return _detalle(b, _ficha(b, estrategia_id))


@router.delete("/medida/{estrategia_id}", tags=["medida"], status_code=204)
def borrar(estrategia_id: str) -> None:
    """409 si algún bot la usa."""
    b = biblioteca()
    f = _ficha(b, estrategia_id)
    usan = bots_que_usan(f.id)
    if usan:
        raise conflicto(
            f"La usa{'n' if len(usan) > 1 else ''} {len(usan)} bot{'s' if len(usan) > 1 else ''} "
            f"({', '.join(usan)}): bórralos antes de borrar la estrategia."
        )
    b.borrar(f.id)


@router.post("/medida/{estrategia_id}/probar", tags=["medida"])
def probar(estrategia_id: str, peticion: PeticionPruebaEstrategia) -> ResultadoPrueba:
    """La prueba sobre el pasado con velas del exchange, costes y frente a mantener."""
    b = biblioteca()
    f = _ficha(b, estrategia_id)
    with del_dominio():
        resultado = probar_estrategia(
            f.estrategia,
            peticion.exchange,
            capital=peticion.capital,
            desde=peticion.desde,
            hasta=peticion.hasta,
            conector_publico=conector_publico,
        )
        resultado = b.registrar_prueba(f.id, resultado)
    return _resultado(resultado)


@router.post("/medida/disenar", tags=["medida"])
def disenar(peticion: PeticionDiseno) -> RespuestaDiseno:
    """Un turno de la conversación con Claude (CLI `claude`, suscripción; gasta cuota). Claude usa
    el conector MCP: puede escribir, validar, probar y desplegar en ficticio; NUNCA activar real.
    Puede tardar un par de minutos. 422 si `claude` no está disponible."""
    d = nuevo_disenador(biblioteca())
    if peticion.sesion is not None:
        try:
            d.conversacion(peticion.sesion)
        except SesionNoEncontradaError as error:
            raise no_encontrado(str(error)) from error
    with del_dominio():
        turno = d.turno(peticion.mensaje, peticion.sesion)
    return _respuesta(turno)


@router.get("/medida/disenar/{sesion}", tags=["medida"])
def conversacion(sesion: str) -> RespuestaDiseno:
    """La conversación guardada (404 si no existe)."""
    try:
        return _respuesta(nuevo_disenador(biblioteca()).conversacion(sesion))
    except SesionNoEncontradaError as error:
        raise no_encontrado(str(error)) from error
