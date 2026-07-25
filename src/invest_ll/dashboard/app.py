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

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import streamlit as st

from invest_ll.alerts.engine import NADA_QUE_CONTAR, evaluate
from invest_ll.alerts.models import Nivel, Umbrales
from invest_ll.dashboard.data import (
    VENTANAS,
    AvailableAsset,
    discover_assets,
    equity_table,
    market_overview,
    metrics_table,
    normalised_series,
    suggest_compatible,
    trades_table,
)
from invest_ll.data.universe import build_universe
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.dca import run_dca
from invest_ll.engine.rotation import run_rotation
from invest_ll.errors import InvestLLError
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.quotes import ultimo_cierre
from invest_ll.portfolio.store import ActivityStore
from invest_ll.portfolio.triggers import TriggerStore
from invest_ll.proposal.builder import FRECUENCIAS, propose_portfolio
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


def pestana_panorama(activos: list[AvailableAsset]) -> None:
    """Como va cada cosa. Sin recomendar nada.

    Es deliberadamente aburrida comparada con un panel de mercado al uso: no hay indicadores de
    "miedo y codicia" ni "temporada de altcoins". Esos indicadores existen para que operes mas, y
    todo lo medido en este proyecto dice que operar mas pierde dinero.
    """
    st.header("Panorama")
    st.caption(
        "Como ha ido cada activo. Son datos historicos hasta la ultima descarga, "
        "no precios en vivo."
    )

    filas = market_overview(activos)
    if not filas:
        st.info("No hay historicos que mostrar.")
        return

    st.subheader("Rendimiento por periodo")

    # La forma de CoinMarketCap sin sus anzuelos: color SOLO en las variaciones (la tinta
    # codifica una unica cosa: direccion), una sparkline por fila como unica imagen, y
    # ordenacion pinchando la cabecera. Ni 1h%, ni tendencias, ni ganadores del dia.
    df = pd.DataFrame(filas)
    variaciones = [
        c for c in ("1 dia", "1 semana", "1 mes", "3 meses", "YTD", "1 año", "5 años") if c in df
    ]

    def _tinta(valor: object) -> str:
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return ""
        numero = float(valor)  # type: ignore[arg-type]
        if numero > 0:
            return "color: #1a873b"
        return "color: #c92a2a" if numero < 0 else ""

    estilo = (
        df.style.map(_tinta, subset=[*variaciones, "desde maximo"])
        .format("{:+.1f}%", subset=[*variaciones, "desde maximo"], na_rep="—")
        .format("{:,.2f}", subset=["ultimo"])
    )
    st.dataframe(
        estilo,
        use_container_width=True,
        hide_index=True,
        column_order=[
            "activo",
            "que es",
            "ultimo",
            "1 dia",
            "1 semana",
            "1 mes",
            "3 meses",
            "YTD",
            "1 año",
            "5 años",
            "desde maximo",
            "sparkline",
            "datos hasta",
        ],
        column_config={
            "ultimo": st.column_config.NumberColumn("precio"),
            "sparkline": st.column_config.LineChartColumn("3 meses (grafico)", width="small"),
            "datos hasta": st.column_config.DateColumn("datos hasta"),
        },
    )
    st.caption(
        "**La columna que mas importa es 'desde maximo'**: un activo que subio un 40% este anho "
        "pero sigue un 30% por debajo de su pico no esta yendo bien, se esta recuperando de una "
        "caida que alguien sufrio. Un hueco significa que no hay historico suficiente para esa "
        "ventana, no que rindiera un 0%. Pincha una cabecera para ordenar por esa columna."
    )

    st.divider()
    st.subheader("Comparacion en base 100")

    etiquetas = ["Todo el historico", *[e for e, _ in VENTANAS]]
    elegida = st.radio("Tramo", etiquetas, horizontal=True)
    periodos = None if elegida == etiquetas[0] else dict(VENTANAS)[elegida]

    seleccion = st.multiselect(
        "Activos a comparar",
        activos,
        format_func=lambda a: a.symbol,
        default=activos[: min(5, len(activos))],
        key="panorama_activos",
    )
    if not seleccion:
        st.info("Elige al menos un activo.")
        return

    puntos = normalised_series(seleccion, periods=periodos)
    if puntos:
        st.line_chart(puntos, x="fecha", y="valor", color="activo", height=380)
        st.caption(
            "Todos empiezan en 100 al inicio del tramo. Sin normalizar, Bitcoin a 90.000 "
            "aplastaria visualmente al resto aunque el oro lo hubiera batido."
        )


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


def pestana_invertir(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    """Las cuatro vías de invertir, y una sola puerta al dinero real.

    El botón NO ejecuta nada: produce una propuesta simulada y el comando exacto para llevarla a
    cabo. Freqtrade u OctoBot, una vez armados, operan solos; aquí la confirmación humana por
    orden es el Principio I y el panel es de solo lectura respecto al dinero.
    """
    st.header("Invertir")
    st.caption(
        "Cualquiera de las cuatro vias termina en `invest-ll-execute`, que pide confirmar "
        "escribiendo la cantidad. Ninguna se salta ese paso."
    )

    pausa = TriggerStore().halted()
    if pausa:
        st.warning(
            f"Pausa activa: {pausa}. No se proponen entradas nuevas; las posiciones abiertas "
            "no se tocan. Retirala con `invest-ll-triggers resume`."
        )
        return

    st.subheader("Propuesta simple")
    seleccion = st.multiselect(
        "Activos candidatos",
        activos,
        format_func=lambda a: a.label,
        default=suggest_compatible(activos),
        key="invertir_activos",
    )
    columnas = st.columns(2)
    importe = columnas[0].number_input("Cuanto aportas cada vez", value=500, min_value=1)
    frecuencia = columnas[1].selectbox("Cada cuanto", sorted(FRECUENCIAS), index=None)

    if st.button("Proponer cartera (simulacion, no mueve dinero)"):
        if not seleccion or frecuencia is None:
            st.error("Elige al menos un activo y una frecuencia.")
            return
        try:
            universo = build_universe([a.load() for a in seleccion])
            propuesta = propose_portfolio(
                universo, amount=D(int(importe)), frequency=frecuencia, friction=friction
            )
        except (InvestLLError, ValueError) as error:
            st.error(f"No se pudo proponer: {error}")
            return

        st.text(propuesta.render())
        st.caption("Esto es una simulacion sobre el pasado, no una recomendacion ni una prevision.")

        st.subheader("Para ejecutarla de verdad")
        lineas: list[str] = []
        for h in propuesta.holdings:
            cierre = ultimo_cierre(h.symbol)
            if cierre is None:
                lineas.append(f"# {h.symbol}: sin precio descargado, calcula la cantidad a mano")
                continue
            precio, fecha = cierre
            cantidad = (h.amount_per_contribution / precio).quantize(D("0.0001"))
            lineas.append(
                f"# {h.symbol}: {h.amount_per_contribution:,.0f} a ~{precio:,.2f} "
                f"(cierre del {fecha.date()})"
            )
            lineas.append(
                f"uv run invest-ll-execute --symbol {h.symbol} --side buy --quantity {cantidad}"
            )
        st.code("\n".join(lineas), language="bash")
        st.caption(
            "Cada comando pide confirmar escribiendo la cantidad exacta. Sin las variables de "
            "entorno del modo real, no sale nada: lo dice el propio comando."
        )

    st.divider()
    st.subheader("Las cuatro vias")
    st.markdown(
        "| Via | Como |\n"
        "|---|---|\n"
        "| **Boton simple** | El de arriba: propuesta + comandos listos |\n"
        "| **Bot determinista** | Rotacion momentum, en la pestana *Una cartera*; "
        "se evalua con las mismas metricas |\n"
        "| **LLM dentro (CLI)** | `invest-ll-generate` decide, `invest-ll-compare` lo mide "
        "contra momentum y contra no hacer nada |\n"
        "| **LLM desde fuera** | Cualquier agente puede leer los nueve comandos con `--json`; "
        "las advertencias viajan en el JSON |\n"
    )
    st.caption(
        "Lo medido hasta hoy (21 anhos, 4 activos): cuanto menos se opera, mejor -- 423 "
        "operaciones dieron 2.890; una sola dio 37.773. Ver docs/experimento-llm-2026-07.md."
    )


def pestana_mi_cartera() -> None:
    """La cartera real, derivada del ledger de movimientos.

    El panel SOLO LEE. Registrar movimientos se hace con `invest-ll-portfolio` — mantener la
    escritura fuera del panel es deliberado: un formulario de compra a un clic del grafico es el
    patron que la FCA midio en +11% de operaciones.
    """
    st.header("Mi cartera")

    try:
        cartera = derive_portfolio(ActivityStore().activities())
    except InvestLLError as error:
        st.error(f"El ledger cuenta una historia imposible: {error}")
        return

    if not cartera.open_positions and not cartera.closed_trades:
        st.info(
            "La cartera esta vacia: no hay ningun movimiento registrado.\n\n"
            "Registra una compra o importa el CSV de tu broker:\n"
            "```\nuv run invest-ll-portfolio add buy --symbol GLD --quantity 10 "
            "--price 240.5 --fee 2\nuv run invest-ll-portfolio import movimientos.csv\n```"
        )
        return

    for aviso in cartera.warnings:
        st.warning(aviso)

    if cartera.open_positions:
        st.subheader("Posiciones abiertas")
        st.caption("Su P&L es una **valoracion con la fecha de los datos al lado**, no un hecho.")

        filas: list[dict[str, object]] = []
        valor_total = D(0)
        con_precio = True
        for p in cartera.open_positions:
            cierre = ultimo_cierre(p.symbol)
            precio, fecha = cierre if cierre else (None, None)
            if precio is not None:
                valor_total += p.value_at(precio)
            else:
                con_precio = False
            filas.append(
                {
                    "activo": p.symbol,
                    "cantidad": float(p.quantity),
                    "coste medio": round(float(p.avg_cost), 2),
                    "invertido": round(float(p.cost), 2),
                    "valor": round(float(p.value_at(precio)), 2) if precio is not None else None,
                    "P&L no realizado": (
                        round(float(p.unrealized_at(precio)), 2) if precio is not None else None
                    ),
                    "datos de": fecha.date() if fecha is not None else "sin datos",
                }
            )
        st.dataframe(filas, use_container_width=True, hide_index=True)

        columnas = st.columns(3)
        columnas[0].metric("Invertido en abiertas", f"{cartera.invested_open:,.0f}")
        columnas[1].metric(
            "Valor con ultimos datos", f"{valor_total:,.0f}" if con_precio else "incompleto"
        )
        columnas[2].metric("Efectivo derivado", f"{cartera.cash:,.2f}")

    if cartera.closed_trades:
        st.subheader("Posiciones retiradas")
        st.caption("Su P&L es **realizado**: un hecho que ya no cambia.")
        st.dataframe(
            [
                {
                    "activo": t.symbol,
                    "abierta": t.opened_at.date(),
                    "retirada": t.closed_at.date(),
                    "dias": t.holding_days,
                    "invertido": round(float(t.invested_total), 2),
                    "recuperado": round(float(t.proceeds_total), 2),
                    "P&L realizado": round(float(t.realized_pnl), 2),
                }
                for t in cartera.closed_trades
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"P&L realizado total: **{cartera.realized_pnl:,.0f}**")

    st.divider()
    st.caption(
        "El panel solo lee. Los movimientos se registran con `invest-ll-portfolio` "
        "(add / cash / import), y las ordenes reales pasan siempre por `invest-ll-execute`."
    )


def pestana_alertas(activos: list[AvailableAsset]) -> None:
    """Lo que esta pasando con tus activos. Se mira; no persigue.

    Esta pestana **no notifica**: existe aqui, y aparece cuando la abres. Es deliberado. La FCA
    midio sobre mas de 9.000 personas que las notificaciones aumentan un 11% las operaciones y un
    8% las inversiones arriesgadas, con mas efecto en quien menos sabe de inversion.

    Tampoco hay alertas de subidas. Una que dijera "GLD subio un 20%" no informa de nada que
    necesites: existe para que abras la aplicacion.
    """
    st.header("Alertas")
    st.caption(
        "Solo saltan por riesgo, nunca porque algo haya subido. Informan de un estado; "
        "ninguna dice que hacer."
    )

    dias = int(
        st.number_input(
            "Avisar si un historico lleva sin actualizarse mas de (dias)",
            min_value=1,
            max_value=365,
            value=Umbrales().dias_sin_datos,
        )
    )
    caida = st.slider("Avisar si un activo cae desde su maximo mas de (%)", 5, 60, 15, step=5) / 100

    series = []
    for activo in activos:
        try:
            series.append(activo.load())
        except (InvestLLError, ValueError):  # pragma: no cover - fichero corrupto
            continue

    alertas = evaluate(
        series,
        ahora=datetime.now(UTC),
        umbrales=Umbrales(dias_sin_datos=dias, caida_desde_maximo=Decimal(str(caida))),
    )

    if not alertas:
        # Ni "todo correcto" ni globos: solo lo que se ha mirado y lo que no.
        st.info(NADA_QUE_CONTAR)
        return

    for alerta in alertas:
        texto = f"**{alerta.symbol}** — {alerta.message}" if alerta.symbol else alerta.message
        if alerta.level is Nivel.REVISAR:
            st.warning(texto)
        else:
            st.info(texto)

    st.caption(
        "Para las alertas que dependen de lo que tengas de verdad (perdida desde tu entrada, "
        "desviacion del plan) hace falta declarar posiciones:\n\n"
        "```\nuv run invest-ll-alerts data/market/yfinance/GLD/DAY_1.csv "
        "--holding GLD:10:180\n```"
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

    panorama, mi_cartera, invertir, backtest, cartera, seguimiento, alertas, vivo = st.tabs(
        [
            "Panorama",
            "Mi cartera",
            "Invertir",
            "Un activo",
            "Una cartera",
            "Estimado vs real",
            "Alertas",
            "Estado actual",
        ]
    )
    with panorama:
        pestana_panorama(activos)
    with mi_cartera:
        pestana_mi_cartera()
    with invertir:
        pestana_invertir(activos, friction)
    with backtest:
        pestana_backtest(activos, friction)
    with cartera:
        pestana_cartera(activos, friction)
    with seguimiento:
        pestana_seguimiento()
    with alertas:
        pestana_alertas(activos)
    with vivo:
        pestana_en_vivo(activos)


if __name__ == "__main__":  # pragma: no cover
    main()
