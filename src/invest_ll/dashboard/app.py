"""Panel interactivo.

Solo dibuja: toda la lógica está en `data.py` y en el motor, que sí tienen tests.

**Una decisión de diseño que atraviesa todo el panel**: las cifras se presentan en el mismo orden
y con las mismas advertencias que en el informe de texto. Un panel es más persuasivo que un texto
—las gráficas convencen— y por eso aquí es más importante, no menos, que el win rate vaya el
último y que las comparaciones contra no hacer nada estén siempre a la vista.

Nota sobre tipos: frontera con Streamlit, que no publica tipado completo. La comprobación estricta
se relaja **solo aquí**, igual que en `loader.py` o en los proveedores. El motor y el informe, que
es donde un error de tipos costaría dinero, siguen en modo estricto.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportMissingParameterType=false

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from invest_ll.dashboard.data import (
    AvailableAsset,
    discover_assets,
    equity_table,
    metrics_table,
    suggest_compatible,
    trades_table,
)
from invest_ll.data.universe import build_universe
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.dca import run_dca
from invest_ll.engine.rotation import run_rotation
from invest_ll.errors import InvestLLError
from invest_ll.report.portfolio import analyze_portfolio
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.price_vs_average import PriceVsAverage
from invest_ll.strategy.rotation import RelativeMomentum
from invest_ll.tracking.forecast import build_track_record, pending
from invest_ll.tracking.store import ForecastStore

D = Decimal


def friccion_desde_barra() -> FrictionConfig:
    """Los costes son obligatorios también aquí (Principio IV)."""
    st.sidebar.subheader("Costes")
    comision = st.sidebar.number_input(
        "Comision por operacion", value=0.001, min_value=0.0, max_value=0.05, format="%.4f"
    )
    slippage = st.sidebar.number_input(
        "Slippage", value=0.0005, min_value=0.0, max_value=0.05, format="%.4f"
    )
    return FrictionConfig(commission_rate=D(str(comision)), slippage_rate=D(str(slippage)))


def mostrar_informe(report: BacktestReport) -> None:
    """Presenta un informe con el mismo orden de lectura que la salida de texto."""
    if not report.conclusive:
        st.warning(f"NO CONCLUYENTE: {report.inconclusive_reason}")

    columnas = st.columns(4)
    columnas[0].metric("Resultado neto", f"{report.net_result:,.0f}")
    columnas[1].metric("Drawdown maximo", f"{report.max_drawdown:,.0f}")
    columnas[2].metric("Operaciones", report.trade_count)
    columnas[3].metric("Costes", f"{report.total_costs:,.0f}")

    if report.buy_and_hold is not None and not report.buy_and_hold.did_nothing:
        bh = report.buy_and_hold
        if report.beats_market:
            st.success(
                f"Bate a comprar y mantener por {report.excess_return:,.0f} "
                f"({report.net_result:,.0f} frente a {bh.net_result:,.0f})"
            )
        else:
            st.error(
                f"NO bate a comprar y mantener: {report.net_result:,.0f} frente a "
                f"{bh.net_result:,.0f} ({report.excess_return:,.0f}). "
                "Todo el riesgo asumido y las comisiones pagadas quedaron por debajo "
                "de no hacer nada."
            )
            if report.max_drawdown > bh.max_drawdown:
                st.info(
                    f"Aunque su caida maxima fue menor: {report.max_drawdown:,.0f} frente a "
                    f"{bh.max_drawdown:,.0f}. Gano menos, pero sufrio menos."
                )

    curva = equity_table(report)
    if curva:
        st.line_chart(curva, x="fecha", y="patrimonio", height=320)

    c = report.consistency
    if c is not None and c.periods:
        st.subheader("Regularidad del camino")
        cols = st.columns(4)
        cols[0].metric("Meses en verde", f"{c.positive_periods}/{c.periods}")
        cols[1].metric("Proporcion", f"{c.positive_ratio:.0%}")
        cols[2].metric("Peor mes", f"{c.worst_period:,.0f}")
        cols[3].metric("Racha en rojo", f"{c.longest_losing_streak} meses")

        if c.positive_ratio >= 0.7 and c.asymmetry > 3:
            st.warning(
                f"{c.positive_ratio:.0%} de meses en verde, pero el peor mes se come "
                f"{c.asymmetry:.1f} meses buenos. Ese perfil aguanta anos y luego lo devuelve "
                "de golpe: mira la asimetria, no el porcentaje."
            )

    with st.expander("Metricas completas"):
        st.dataframe(metrics_table(report), use_container_width=True, hide_index=True)
    with st.expander(f"Registro de operaciones ({report.trade_count})"):
        st.dataframe(trades_table(report), use_container_width=True, hide_index=True)


def pestana_backtest(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    st.header("Una estrategia sobre un activo")

    elegido = st.selectbox("Activo", activos, format_func=lambda a: f"{a.label} - {a.provider}")

    izquierda, derecha = st.columns(2)
    nombre = izquierda.selectbox(
        "Estrategia", ["Cruce de medias", "Precio vs media", "Ruptura de maximos"]
    )
    fraccion = derecha.slider("Fraccion del capital por entrada", 0.1, 1.0, 1.0, 0.1)

    if nombre == "Cruce de medias":
        corta = izquierda.number_input("Media corta", 2, 200, 10)
        larga = derecha.number_input("Media larga", 3, 400, 30)
        estrategia = MovingAverageCrossover(short=int(corta), long=int(larga))
    elif nombre == "Precio vs media":
        periodos = izquierda.number_input("Periodos", 2, 400, 50)
        margen = derecha.slider("Margen de salida", 0.0, 0.10, 0.0, 0.01)
        estrategia = PriceVsAverage(periods=int(periodos), exit_margin=float(margen))
    else:
        lookback = izquierda.number_input("Periodos de ruptura", 2, 400, 20)
        estrategia = BreakoutHighs(lookback=int(lookback))

    capital = st.number_input("Capital inicial", 100, 10_000_000, 10_000, step=1000)

    try:
        serie = elegido.load()
        report = run_backtest(
            serie,
            estrategia,
            initial_capital=D(str(capital)),
            friction=friction,
            risk=RiskConfig(position_fraction=D(str(fraccion))),
        )
    except (InvestLLError, ValueError) as error:
        st.error(f"No se pudo evaluar: {error}")
        return

    mostrar_informe(report)


def pestana_cartera(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    st.header("Una cartera de varios activos")

    # La preseleccion se calcula: escoger los primeros de la lista puede juntar un historico que
    # acaba en 2010 con otro que empieza en 2017, y el panel arrancaba con un error en la cara.
    seleccion = st.multiselect(
        "Activos", activos, format_func=lambda a: a.label, default=suggest_compatible(activos)
    )
    if len(seleccion) < 2:
        st.info("Elige al menos dos activos: una cartera de uno no es una cartera.")
        return

    try:
        universo = build_universe([a.load() for a in seleccion])
    except (InvestLLError, ValueError) as error:
        st.error(f"No se pudo formar el universo: {error}")
        return

    st.caption(
        f"{len(universo)} fechas comunes "
        f"({universo.timestamps[0].date()} a {universo.timestamps[-1].date()})"
    )

    try:
        analisis = analyze_portfolio(universo)
    except ValueError as error:
        st.error(str(error))
        return

    cols = st.columns(3)
    cols[0].metric("Activos", len(analisis.symbols))
    cols[1].metric("Activos efectivos", f"{analisis.effective_assets:.1f}")
    cols[2].metric("Correlacion media", f"{analisis.average_correlation:.2f}")

    if not analisis.is_diversified:
        st.warning(
            f"Tus {len(analisis.symbols)} activos equivalen a "
            f"{analisis.effective_assets:.1f} independientes. Con una correlacion media de "
            f"{analisis.average_correlation:.2f} se mueven casi a la vez: tener varios no te "
            "protege de una caida general."
        )

    with st.expander("Correlacion por pares"):
        st.dataframe(
            [{"par": f"{p.a} / {p.b}", "correlacion": round(p.value, 2)} for p in analisis.pairs],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    modo = st.radio("Que quieres medir", ["Aportaciones periodicas", "Rotacion entre activos"])

    if modo == "Aportaciones periodicas":
        izquierda, derecha = st.columns(2)
        aportacion = izquierda.number_input("Aportacion", 10, 100_000, 500, step=50)
        cada = derecha.number_input("Cada cuantos periodos", 1, 250, 21)
        try:
            informe = run_dca(
                universo,
                contribution=D(str(aportacion)),
                friction=friction,
                every_periods=int(cada),
            )
        except ValueError as error:
            st.error(str(error))
            return

        cols = st.columns(4)
        cols[0].metric("Aportado", f"{informe.total_contributed:,.0f}")
        cols[1].metric("Valor final", f"{informe.final_value:,.0f}")
        cols[2].metric(
            "Ganancia",
            f"{informe.net_result:,.0f}",
            delta=f"{informe.return_on_contributions:+.0%}",
        )
        cols[3].metric("Costes", f"{informe.total_costs:,.0f}")

        if informe.beats_lump_sum:
            st.success("Aportar poco a poco salio mejor que invertirlo todo de golpe.")
        else:
            st.info(
                f"Invertir los {informe.total_contributed:,.0f} de golpe al principio habria "
                f"dado {informe.lump_sum_value:,.0f}. Aportar poco a poco no busca ganar mas: "
                "busca que la fecha de entrada deje de decidir el resultado."
            )
        st.text(informe.render())
    else:
        lookback = st.number_input("Periodos para medir el impulso", 5, 400, 60)
        capital = st.number_input("Capital inicial", 100, 10_000_000, 10_000, step=1000)
        try:
            informe = run_rotation(
                universo,
                RelativeMomentum(lookback=int(lookback)),
                initial_capital=D(str(capital)),
                friction=friction,
                risk=RiskConfig(position_fraction=D(1)),
            )
        except (InvestLLError, ValueError) as error:
            st.error(str(error))
            return
        mostrar_informe(informe)


def pestana_seguimiento() -> None:
    """Lo estimado frente a lo que paso.

    Es la unica evidencia sobre el LLM que no esta contaminada: un backtest sobre el pasado no
    vale porque el modelo sabe lo que ocurrio despues.
    """
    st.header("Lo estimado frente a lo que paso")
    st.caption(
        "Un backtest del LLM sobre el pasado no demuestra nada: el modelo fue entrenado con "
        "datos posteriores al periodo simulado. Esto si."
    )

    almacen = ForecastStore()
    historial = build_track_record(almacen)
    sin_evaluar = pending(almacen)

    if historial.count == 0 and not sin_evaluar:
        st.info(
            "Todavia no hay ninguna estimacion registrada. Es lo normal al principio: "
            "hay que emitir una y esperar a que venza su horizonte."
        )
        return

    cols = st.columns(3)
    cols[0].metric("Evaluadas", historial.count)
    cols[1].metric("Pendientes", len(sin_evaluar))
    cols[2].metric("Sobreestimaciones", f"{historial.overestimates}/{historial.count}")

    if historial.count:
        st.warning(f"Veredicto: el sistema {historial.tendency}.")
        st.dataframe(
            [
                {
                    "emitida": e.forecast.issued_at.date(),
                    "estimado": float(e.forecast.expected_value),
                    "real": float(e.outcome.actual_value),
                    "error": float(e.error),
                }
                for e in historial.evaluations
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Los fallos siguen en la tabla a proposito. Un historial que solo guarda los "
            "aciertos no mide nada."
        )


def pestana_en_vivo(activos: list[AvailableAsset]) -> None:
    st.header("Estado actual")
    st.caption(
        "Ultimo cierre de cada historico descargado. Para actualizarlo hay que volver a "
        "descargar con invest-ll-fetch: el motor no toca la red por diseno."
    )

    filas: list[dict[str, object]] = []
    for activo in activos:
        try:
            serie = activo.load()
        except (InvestLLError, ValueError):  # pragma: no cover - fichero corrupto
            continue
        ultimo = serie.bars[-1]
        previo = serie.bars[-2] if len(serie) > 1 else ultimo
        variacion = (ultimo.close / previo.close - 1) if previo.close else 0.0
        filas.append(
            {
                "activo": activo.symbol,
                "ultimo cierre": round(ultimo.close, 2),
                "variacion": f"{variacion:+.2%}",
                "fecha": ultimo.timestamp.date(),
                "velas": len(serie),
                "descargado": activo.provenance.downloaded_at.date() if activo.provenance else None,
            }
        )

    if not filas:
        st.info("No hay historicos que mostrar.")
        return

    st.dataframe(filas, use_container_width=True, hide_index=True)

    desfasados = [
        f["activo"] for f in filas if f["fecha"] is not None and str(f["fecha"]) < "2025-12-01"
    ]
    if desfasados:
        st.warning(
            f"Estos historicos acaban antes de diciembre de 2025: {', '.join(map(str, desfasados))}. "
            "Los datos que ves no son actuales."
        )


def main() -> None:
    st.set_page_config(page_title="INVEST LL", layout="wide")
    st.title("INVEST LL")
    st.caption(
        "Simulacion sobre datos historicos. No ejecuta ninguna orden real. "
        "Recuerda: el win rate no es criterio de exito."
    )

    activos = discover_assets()
    if not activos:
        st.error(
            "No hay ningun historico descargado todavia. Descarga alguno con:\n\n"
            "```\nuv run invest-ll-fetch AAPL --market equity --interval DAY_1 "
            "--start 2020-01-01 --end 2026-01-01\n```"
        )
        return

    friction = friccion_desde_barra()
    st.sidebar.caption(
        "Los costes son obligatorios a proposito: una simulacion sin friccion es una mentira "
        "optimista."
    )

    backtest, cartera, vivo = st.tabs(["Un activo", "Una cartera", "Estado actual"])
    with backtest:
        pestana_backtest(activos, friction)
    with cartera:
        pestana_cartera(activos, friction)
    with vivo:
        pestana_en_vivo(activos)


if __name__ == "__main__":  # pragma: no cover
    main()
