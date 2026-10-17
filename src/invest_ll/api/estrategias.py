"""Estrategias: el catálogo en llano, tus números y la recomendación (docs/panel-v2.md, 4.2, 5, 6).

Las rutas solo traducen: qué es cada estrategia vive en `estrategias.catalogo`, sus cifras salen
de ejecutar el motor sobre los datos (`estrategias.historico`, en memoria por la huella del
fichero), la simulación con tus aportaciones en `estrategias.simulacion` y las reglas de la
recomendación en `estrategias.recomendacion`.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter

from invest_ll import llano
from invest_ll.api.errores import invalido, no_encontrado
from invest_ll.api.schemas_v2 import (
    Catalogo,
    Estrategia,
    Evidencia,
    Historico,
    Parte,
    Perfil,
    PeticionSimulacion,
    PuntoSimulado,
    Recomendacion,
    ResultadoSimulado,
    Simulacion,
)
from invest_ll.estrategias import historico, recomendacion, simulacion
from invest_ll.estrategias.catalogo import FICHAS, Ficha, ficha, principales
from invest_ll.estrategias.recomendacion import CaidasDelCatalogo, Respuestas
from invest_ll.estrategias.simulacion import SinDatosDesdeError

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.estrategias.historico import Cifras

router = APIRouter()

NOTA_CATALOGO: Final = (
    "Las cifras salen de probar cada estrategia sobre el pasado, con sus comisiones y costes, "
    "empezando con 10.000. El pasado no es una promesa: si hubieras empezado en otra fecha, el "
    "resultado sería distinto."
)
NOTA_SIMULACION: Final = (
    "Es una aproximación: a tu dinero se le aplica lo que hizo cada estrategia día a día (con sus "
    "comisiones), y tus aportaciones entran el primer día con datos de cada mes sin pagar comisión "
    "propia. El pasado no es una promesa: prueba a cambiar el año de inicio."
)
TEXTO_PASADO: Final = "Probada sobre el pasado"


def _evidencia(f: Ficha) -> Evidencia:
    """'En prueba real desde…' si hay registros de la prueba hacia delante; si no, el pasado."""
    if f.prueba_real is not None:
        from invest_ll.quant.paper import read, variants

        variante = variants().get(f.prueba_real)
        registros = read(variante.ledger) if variante is not None else []
        if registros:
            desde = date.fromisoformat(registros[0].data_date)
            return Evidencia(
                tipo="prueba_real",
                desde=desde,
                texto=f"En prueba real desde el {llano.fecha_corta(desde)}",
            )
    return Evidencia(tipo="pasado", desde=None, texto=TEXTO_PASADO)


def _historico(c: Cifras) -> Historico:
    return Historico(
        desde=c.desde,
        hasta=c.hasta,
        valor_final=c.valor_final,
        crecimiento_anual=c.crecimiento_anual,
        peor_caida=c.peor_caida,
        peor_caida_fecha=c.peor_caida_fecha,
        peor_racha_anios=c.peor_racha_anios,
        tiempo_invertido=c.tiempo_invertido,
        operaciones_al_anio=c.operaciones_al_anio,
    )


def _estrategia(f: Ficha) -> Estrategia:
    ejecucion = historico.ejecucion(f)
    recorrido = ejecucion.recorrido
    return Estrategia(
        clave=f.clave,
        nombre=f.nombre,
        frase=f.frase,
        para_quien=f.para_quien,
        mercado=f.mercado,
        ejecucion=f.ejecucion,
        riesgo=f.riesgo,
        riesgo_texto=f.riesgo_texto,
        como_funciona=list(f.como_funciona),
        avisos=list(f.avisos),
        evidencia=_evidencia(f),
        activos=list(f.activos),
        laboratorio=f.laboratorio,
        retirada=f.retirada,
        disponible=recorrido is not None,
        motivo=ejecucion.motivo,
        historico=None if recorrido is None else _historico(historico.cifras(recorrido)),
    )


@router.get("/estrategias", tags=["estrategias"])
def catalogo() -> Catalogo:
    """Las estrategias con su descripción llana y sus cifras calculadas sobre los datos."""
    return Catalogo(estrategias=[_estrategia(f) for f in FICHAS], nota=NOTA_CATALOGO)


@router.post("/estrategias/simular", tags=["estrategias"])
def simular(peticion: PeticionSimulacion) -> Simulacion:
    """Inicial + mensual desde un año, en 1-4 estrategias. 404 si una clave no existe."""
    fichas: list[Ficha] = []
    for clave in dict.fromkeys(peticion.estrategias):
        encontrada = ficha(clave)
        if encontrada is None:
            raise no_encontrado(f"no hay ninguna estrategia {clave!r}")
        fichas.append(encontrada)
    if peticion.inicial == 0 and peticion.mensual == 0:
        raise invalido("Pon una cantidad inicial o una aportación mensual: con cero no hay nada.")

    desde = date(peticion.desde_anio, 1, 1)
    resultados: list[ResultadoSimulado] = []
    for f in fichas:
        ejecucion = historico.ejecucion(f)
        if ejecucion.recorrido is None:
            raise invalido(f"{f.nombre}: {ejecucion.motivo}")
        r = ejecucion.recorrido
        try:
            hecha = simulacion.simular(
                [int(d) for d in r.dias],
                [float(v) for v in r.valor],
                inicial=float(peticion.inicial),
                mensual=float(peticion.mensual),
                desde=desde,
                fecha_texto=llano.fecha_corta(r.desde),
            )
        except SinDatosDesdeError:
            raise invalido(
                f"{f.nombre}: no hay datos desde {peticion.desde_anio}; sus datos llegan hasta el "
                f"{llano.fecha_corta(r.hasta)}."
            ) from None
        except ValueError as error:
            raise invalido(f"{f.nombre}: {error}") from None
        resultados.append(
            ResultadoSimulado(
                clave=f.clave,
                nombre=f.nombre,
                desde=hecha.desde,
                hasta=hecha.hasta,
                puntos=[
                    PuntoSimulado(fecha=p.fecha, valor=p.valor, aportado=p.aportado)
                    for p in hecha.puntos
                ],
                aportado=hecha.aportado,
                valor_final=hecha.valor_final,
                ganancia=hecha.ganancia,
                peor_momento_fecha=hecha.peor_momento_fecha,
                peor_momento_valor=hecha.peor_momento_valor,
                peor_momento_aportado=hecha.peor_momento_aportado,
                peor_caida=hecha.peor_caida,
                meses_por_debajo=hecha.meses_por_debajo,
                aviso=hecha.aviso,
            )
        )
    return Simulacion(resultados=resultados, nota=NOTA_SIMULACION)


def caidas_del_catalogo() -> CaidasDelCatalogo:
    """Las peores caídas que citan los textos de la recomendación, calculadas si hay datos."""
    calculadas: dict[str, float] = {}
    for f in principales():
        recorrido = historico.ejecucion(f).recorrido
        if recorrido is not None:
            calculadas[f.clave] = historico.cifras(recorrido).peor_caida
    por_defecto = CaidasDelCatalogo()
    return CaidasDelCatalogo(
        menor=max(calculadas.values(), default=por_defecto.menor),
        mayor=min(calculadas.values(), default=por_defecto.mayor),
        cripto=calculadas.get("btc-freno", por_defecto.cripto),
    )


@router.post("/estrategias/recomendar", tags=["estrategias"])
def recomendar(perfil: Perfil) -> Recomendacion:
    """Reglas fijas y explicables (docs/panel-v2.md, sección 6)."""
    reparto = recomendacion.recomendar(
        Respuestas(
            inicial=perfil.inicial,
            mensual=perfil.mensual,
            horizonte=perfil.horizonte,
            ante_caida=perfil.ante_caida,
            cripto=perfil.cripto,
        ),
        caidas_del_catalogo(),
    )
    return Recomendacion(
        no_invertir=reparto.no_invertir,
        partes=[
            Parte(
                estrategia=p.estrategia,
                nombre=p.nombre,
                porcentaje=p.porcentaje,
                inicial=p.inicial,
                mensual=p.mensual,
            )
            for p in reparto.partes
        ],
        por_que=list(reparto.por_que),
        avisos=list(reparto.avisos),
        alternativas=list(reparto.alternativas),
    )
