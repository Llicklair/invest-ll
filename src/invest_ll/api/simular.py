"""Pestaña Simular: ¿qué pasaría si...? Todo lo que es ensayo vive junto, y nada de esto mueve dinero.

Las cifras salen en el mismo orden de lectura que el informe de texto, con el win rate al final y
la comparación contra no hacer nada siempre a la vista: un panel es más persuasivo que un texto
—las gráficas convencen— y por eso aquí importa más, no menos.

Registrar la propuesta es contabilidad: anota las compras en Mi cartera al último cierre
descargado. No compra nada en ningún mercado.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter

from invest_ll.api.activos import (
    costes,
    descargados,
    id_de,
    resolver,
    resolver_varios,
    series_para_medir,
)
from invest_ll.api.errores import ERRORES_DEL_DOMINIO, del_dominio, en_pausa
from invest_ll.api.schemas import (
    AnalisisCartera,
    Celda,
    ComparacionLLM,
    CompraPropuesta,
    ComprarYMantener,
    Consistencia,
    FilaLLM,
    Friccion,
    Informe,
    InformeAportaciones,
    OpcionesSimular,
    Par,
    PeticionAportaciones,
    PeticionPropuesta,
    PeticionRegistrarPropuesta,
    PeticionRotacion,
    PeticionUnActivo,
    PeticionUniverso,
    Propuesta,
    Punto,
    RegistroPropuesta,
    Tabla,
)
from invest_ll.dashboard.data import (
    equity_table,
    metrics_table,
    suggest_compatible,
    trades_table,
)
from invest_ll.data.universe import build_universe
from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.provider import RecordedProvider
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import RiskConfig
from invest_ll.engine.dca import run_dca
from invest_ll.engine.rotation import run_rotation
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.quotes import ultimo_cierre
from invest_ll.portfolio.store import ActivityStore
from invest_ll.portfolio.triggers import TriggerStore
from invest_ll.proposal.builder import FRECUENCIAS, propose_portfolio
from invest_ll.report.portfolio import analyze_portfolio
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.llm import ADVERTENCIA_CONTAMINACION, LLMStrategy
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.price_vs_average import PriceVsAverage
from invest_ll.strategy.rotation import RelativeMomentum

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.dashboard.data import AvailableAsset
    from invest_ll.data.universe import Universe
    from invest_ll.report.report import BacktestReport
    from invest_ll.strategy.protocol import Strategy

router = APIRouter()

D = Decimal
CUATRO_DECIMALES = D("0.0001")
ESTRATEGIAS = ("cruce-medias", "precio-vs-media", "ruptura-maximos")
COLUMNAS_METRICAS = ["metrica", "valor"]
COLUMNAS_OPERACIONES = [
    "entrada",
    "precio entrada",
    "salida",
    "precio salida",
    "motivo",
    "resultado",
]

DECISIONES_LLM = Path("decisions/llm-trimestral")
SIMBOLOS_EXPERIMENTO_LLM = ("GLD", "TLT", "XLE", "XLF")
MODELO_EXPERIMENTO_LLM = "claude-opus-4-6"


def _pausa_activa() -> None:
    """Nivel 1 del kill switch: con pausa no se propone ni se anota ninguna entrada nueva."""
    pausa = TriggerStore().halted()
    if pausa:
        raise en_pausa(
            f"Pausa activa: {pausa}. No se proponen entradas nuevas; las posiciones abiertas "
            "no se tocan. Retirala con `invest-ll-triggers resume`."
        )


# -- Del informe del motor al contrato ---------------------------------------------------------


def _celda(valor: object) -> Celda:
    if valor is None or isinstance(valor, str | bool | int | float):
        return valor
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    return str(valor)


def _tabla(columnas: list[str], filas: Sequence[dict[str, object]]) -> Tabla:
    return Tabla(
        columnas=columnas, filas=[[_celda(fila.get(c)) for c in columnas] for fila in filas]
    )


def _consistencia(report: BacktestReport) -> Consistencia | None:
    c = report.consistency
    if c is None or not c.periods:
        return None
    aviso = None
    if c.positive_ratio >= 0.7 and c.asymmetry > 3:
        aviso = (
            f"{c.positive_ratio:.0%} de meses en verde, pero el peor mes se come "
            f"{c.asymmetry:.1f} meses buenos. Ese perfil aguanta anos y luego lo devuelve "
            "de golpe: mira la asimetria, no el porcentaje."
        )
    return Consistencia(
        periodos=c.periods,
        positivos=c.positive_periods,
        proporcion=c.positive_ratio,
        peor_periodo=c.worst_period,
        racha_en_rojo=c.longest_losing_streak,
        asimetria=float(c.asymmetry),
        aviso=aviso,
    )


def informe_de(report: BacktestReport) -> Informe:
    """Un backtest en el orden del informe de texto. La comparación solo si hubo con qué."""
    bh = report.buy_and_hold
    comparable = bh is not None and not bh.did_nothing
    return Informe(
        concluyente=report.conclusive,
        motivo_no_concluyente=report.inconclusive_reason,
        resultado_neto=report.net_result,
        drawdown_maximo=report.max_drawdown,
        operaciones=report.trade_count,
        costes=report.total_costs,
        comprar_y_mantener=(
            ComprarYMantener(
                resultado=bh.net_result, drawdown=bh.max_drawdown, no_hizo_nada=bh.did_nothing
            )
            if bh is not None
            else None
        ),
        bate_al_mercado=report.beats_market if comparable else None,
        diferencia=report.excess_return if comparable else None,
        curva=[Punto.model_validate(p) for p in _curva(report)],
        consistencia=_consistencia(report),
        metricas=_tabla(COLUMNAS_METRICAS, metrics_table(report)),
        registro=_tabla(COLUMNAS_OPERACIONES, trades_table(report)),
    )


def _curva(report: BacktestReport) -> list[dict[str, object]]:
    return [{"fecha": p["fecha"], "valor": p["patrimonio"]} for p in equity_table(report)]


def _universo(activos: Sequence[AvailableAsset]) -> Universe:
    with del_dominio("No se pudo formar el universo: "):
        return build_universe(series_para_medir(activos))


# -- Rutas -------------------------------------------------------------------------------------


@router.get("/simular/opciones", tags=["simular"])
def opciones_simular() -> OpcionesSimular:
    """Frecuencias, activos compatibles sugeridos, estrategias y si hay pausa."""
    return OpcionesSimular(
        frecuencias=sorted(FRECUENCIAS),
        sugeridos=[id_de(a) for a in suggest_compatible(descargados())],
        estrategias=list(ESTRATEGIAS),
        pausa=TriggerStore().halted(),
    )


@router.post("/simular/propuesta", tags=["simular"])
def propuesta(peticion: PeticionPropuesta) -> Propuesta:
    """Propuesta simple (`propose_portfolio`). 409 si hay pausa de entradas."""
    _pausa_activa()
    seleccion = resolver_varios(peticion.activos)
    with del_dominio("No se pudo proponer: "):
        universo = build_universe(series_para_medir(seleccion))
        propuesta_ = propose_portfolio(
            universo,
            amount=peticion.importe,
            frequency=peticion.frecuencia,
            friction=costes(peticion),
        )

    compras: list[CompraPropuesta] = []
    comandos: list[str] = []
    for h in propuesta_.holdings:
        cierre = ultimo_cierre(h.symbol)
        precio, fecha = cierre if cierre is not None else (None, None)
        cantidad = (
            (h.amount_per_contribution / precio).quantize(CUATRO_DECIMALES) if precio else None
        )
        compras.append(
            CompraPropuesta(
                symbol=h.symbol,
                importe=h.amount_per_contribution,
                precio=precio,
                fecha=fecha.date() if fecha is not None else None,
                cantidad=cantidad,
            )
        )
        comandos.append(
            f"uv run invest-ll-execute --symbol {h.symbol} --side buy --quantity {cantidad}"
            if cantidad
            else f"# {h.symbol}: sin precio descargado, calcula la cantidad a mano"
        )
    return Propuesta(texto=propuesta_.render(), compras=compras, comandos=comandos)


@router.post("/simular/propuesta/registrar", tags=["simular"])
def registrar_propuesta(peticion: PeticionRegistrarPropuesta) -> RegistroPropuesta:
    """Anota las compras de la propuesta en el ledger (fuente 'propuesta'). No compra nada."""
    _pausa_activa()
    registradas = 0
    problemas: list[str] = []
    almacen = ActivityStore()
    for compra in peticion.compras:
        if not compra.cantidad or compra.precio is None:
            problemas.append(f"{compra.symbol}: sin precio descargado, registralo a mano")
            continue
        try:
            almacen.append(
                Activity(
                    timestamp=datetime.now(UTC),
                    type=ActivityType.BUY,
                    symbol=compra.symbol,
                    quantity=compra.cantidad,
                    unit_price=compra.precio,
                    source="propuesta",
                )
            )
        except ERRORES_DEL_DOMINIO as error:
            problemas.append(f"{compra.symbol}: {error}")
        else:
            registradas += 1
    return RegistroPropuesta(registradas=registradas, problemas=problemas)


def _estrategia(peticion: PeticionUnActivo) -> Strategy:
    if peticion.estrategia == "cruce-medias":
        return MovingAverageCrossover(short=peticion.corta, long=peticion.larga)
    if peticion.estrategia == "precio-vs-media":
        return PriceVsAverage(periods=peticion.periodos, exit_margin=peticion.margen)
    return BreakoutHighs(lookback=peticion.lookback)


@router.post("/simular/activo", tags=["simular"])
def un_activo(peticion: PeticionUnActivo) -> Informe:
    """Una estrategia sobre un activo (`run_backtest`)."""
    activo = resolver(peticion.activo)
    with del_dominio("No se pudo evaluar: "):
        report = run_backtest(
            activo.load(),
            _estrategia(peticion),
            initial_capital=peticion.capital,
            friction=costes(peticion),
            risk=RiskConfig(position_fraction=peticion.fraccion),
        )
    return informe_de(report)


@router.post("/simular/cartera/analisis", tags=["simular"])
def analisis_cartera(peticion: PeticionUniverso) -> AnalisisCartera:
    """Diversificación real del universo (`analyze_portfolio`)."""
    universo = _universo(resolver_varios(peticion.activos))
    with del_dominio():
        analisis = analyze_portfolio(universo)

    aviso = None
    if not analisis.is_diversified:
        aviso = (
            f"Tus {len(analisis.symbols)} activos equivalen a "
            f"{analisis.effective_assets:.1f} independientes. Con una correlacion media de "
            f"{analisis.average_correlation:.2f} se mueven casi a la vez: tener varios no te "
            "protege de una caida general."
        )
    return AnalisisCartera(
        fechas_comunes=len(universo),
        desde=universo.timestamps[0].date(),
        hasta=universo.timestamps[-1].date(),
        activos=len(analisis.symbols),
        activos_efectivos=analisis.effective_assets,
        correlacion_media=analisis.average_correlation,
        diversificada=analisis.is_diversified,
        aviso=aviso,
        pares=[Par(par=f"{p.a} / {p.b}", correlacion=p.value) for p in analisis.pairs],
    )


@router.post("/simular/cartera/aportaciones", tags=["simular"])
def aportaciones(peticion: PeticionAportaciones) -> InformeAportaciones:
    """Aportaciones periódicas (`run_dca`)."""
    universo = _universo(resolver_varios(peticion.activos))
    with del_dominio():
        informe = run_dca(
            universo,
            contribution=peticion.aportacion,
            friction=costes(peticion),
            every_periods=peticion.cada,
        )
    return InformeAportaciones(
        aportado=informe.total_contributed,
        valor_final=informe.final_value,
        ganancia=informe.net_result,
        rentabilidad=informe.return_on_contributions,
        costes=informe.total_costs,
        bate_a_todo_de_golpe=informe.beats_lump_sum,
        valor_todo_de_golpe=informe.lump_sum_value,
        texto=informe.render(),
    )


@router.post("/simular/cartera/rotacion", tags=["simular"])
def rotacion(peticion: PeticionRotacion) -> Informe:
    """Rotación por momentum relativo (`run_rotation`)."""
    universo = _universo(resolver_varios(peticion.activos))
    with del_dominio():
        report = run_rotation(
            universo,
            RelativeMomentum(lookback=peticion.lookback),
            initial_capital=peticion.capital,
            friction=costes(peticion),
            risk=RiskConfig(position_fraction=D(1)),
        )
    return informe_de(report)


def _no_disponible(motivo: str) -> ComparacionLLM:
    return ComparacionLLM(
        disponible=False,
        motivo=motivo,
        filas=[],
        ninguna_bate=False,
        advertencia=ADVERTENCIA_CONTAMINACION,
    )


def _fila_llm(estrategia: str, report: BacktestReport) -> FilaLLM:
    return FilaLLM(
        estrategia=estrategia,
        resultado=report.net_result,
        drawdown=report.max_drawdown,
        operaciones=report.trade_count,
        costes=report.total_costs,
    )


@router.post("/simular/llm", tags=["simular"])
def llm(friccion: Friccion) -> ComparacionLLM:
    """El experimento del LLM con decisiones grabadas, contra momentum y no hacer nada."""
    # Generar decisiones NUEVAS gasta cuota y sigue en invest-ll-generate; repetir el experimento
    # con lo grabado es gratis, que es justo lo que lo hace repetible.
    if not DECISIONES_LLM.exists():
        return _no_disponible(
            f"No hay decisiones grabadas en {DECISIONES_LLM.as_posix()}. "
            "Generalas con invest-ll-generate (gasta cuota; se hace una sola vez)."
        )

    unicos = {
        a.symbol: a
        for a in descargados()
        if a.symbol in SIMBOLOS_EXPERIMENTO_LLM and not a.is_crypto
    }
    if len(unicos) < len(SIMBOLOS_EXPERIMENTO_LLM):
        return _no_disponible(
            "Faltan historicos de GLD/TLT/XLE/XLF para reproducir el experimento."
        )

    friction = costes(friccion)
    riesgo = RiskConfig(position_fraction=D(1))
    with del_dominio("No se pudo reproducir: "):
        universo = build_universe(series_para_medir([unicos[s] for s in SIMBOLOS_EXPERIMENTO_LLM]))
        proveedor = RecordedProvider(DecisionStore(DECISIONES_LLM), model=MODELO_EXPERIMENTO_LLM)
        informe_llm = run_rotation(
            universo,
            LLMStrategy(proveedor, every_periods=63),
            initial_capital=D(10000),
            friction=friction,
            risk=riesgo,
        )
        informe_mom = run_rotation(
            universo,
            RelativeMomentum(lookback=60),
            initial_capital=D(10000),
            friction=friction,
            risk=riesgo,
        )

    filas = [_fila_llm("LLM (grabado)", informe_llm), _fila_llm("momentum", informe_mom)]
    bh = informe_llm.buy_and_hold
    if bh is not None:
        filas.append(
            FilaLLM(
                estrategia="comprar y mantener",
                resultado=bh.net_result,
                drawdown=bh.max_drawdown,
                operaciones=1,
                costes=bh.costs,
            )
        )
    return ComparacionLLM(
        disponible=True,
        motivo=None,
        filas=filas,
        ninguna_bate=not (informe_llm.beats_market or informe_mom.beats_market),
        advertencia=ADVERTENCIA_CONTAMINACION,
    )
