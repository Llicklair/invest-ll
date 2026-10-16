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

import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from invest_ll.alerts.engine import NADA_QUE_CONTAR, evaluate
from invest_ll.alerts.models import Nivel, Umbrales
from invest_ll.chat.context import build_context
from invest_ll.chat.session import ChatSession, ChatUnavailableError
from invest_ll.cli.compare import ADVERTENCIA_CONTAMINACION
from invest_ll.dashboard.data import (
    VENTANAS,
    AvailableAsset,
    aviso_de_reserva,
    discover_assets,
    equity_table,
    fetch_args,
    market_overview,
    metrics_table,
    normalised_series,
    suggest_compatible,
    trades_table,
)
from invest_ll.dashboard.ordenes import enviar_orden, motivo_para_no_enviar
from invest_ll.data.universe import build_universe
from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.provider import RecordedProvider
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.dca import run_dca
from invest_ll.engine.rotation import run_rotation
from invest_ll.errors import InvestLLError
from invest_ll.fetch.catalog import EQUITY_CATALOG
from invest_ll.fetch.live import LiveDataError, crypto_tickers, equity_quotes
from invest_ll.live.broker import OrderStatus, Side
from invest_ll.live.factory import construir_broker
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import Real, resolve_mode
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.quotes import ultimo_cierre
from invest_ll.portfolio.store import ActivityStore
from invest_ll.portfolio.triggers import Trigger, TriggerRule, TriggerStore
from invest_ll.proposal.builder import FRECUENCIAS, propose_portfolio
from invest_ll.report.portfolio import analyze_portfolio
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.llm import LLMStrategy
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


def _tabla_viva(filas: list[dict[str, object]], clave: str) -> str | None:
    """La mesa de cotizaciones: color solo en el 24h, seleccion de fila."""
    df = pd.DataFrame(filas)

    def _tinta(valor: object) -> str:
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return ""
        numero = float(valor)  # type: ignore[arg-type]
        if numero > 0:
            return "color: #1a873b"
        return "color: #c92a2a" if numero < 0 else ""

    estilo = (
        df.style.map(_tinta, subset=["24h %"])
        .format("{:+.2f}%", subset=["24h %"], na_rep="—")
        .format("{:,.4g}", subset=["precio"])
        .format("{:,.1f}", subset=["volumen 24h (M)"], na_rep="—")
    )
    evento = st.dataframe(
        estilo,
        use_container_width=True,
        hide_index=True,
        height=360,
        key=clave,
        on_select="rerun",
        selection_mode="single-row",
    )
    seleccionadas = evento.get("selection", {}).get("rows", [])
    if seleccionadas:
        return str(df.iloc[seleccionadas[0]]["activo"])
    return None


def seccion_cotizaciones(activos: list[AvailableAsset]) -> None:
    """Cotizaciones al pulsar: cientos de activos, con su hora en la cara.

    Una foto fechada, no un chorro continuo — un panel que se refresca solo es una notificacion
    con otro nombre. Y nada de esto entra en un backtest: el historico reproducible sigue
    viniendo de invest-ll-fetch con su procedencia.
    """
    st.subheader("Cotizaciones")
    st.caption(
        f"Bolsa: {len(EQUITY_CATALOG)} valores del catalogo (ampliable en fetch/catalog.py) · "
        "Cripto: TODOS los pares USDT al contado de Binance. Se piden al pulsar; cada foto "
        "lleva su hora."
    )

    if st.button("Traer cotizaciones (bolsa + cripto)"):
        capturas: dict[str, object] = {"at": datetime.now(UTC).strftime("%H:%M:%S")}
        with st.spinner("Pidiendo a Binance todos los pares USDT..."):
            try:
                capturas["cripto"] = [q.as_row() for q in crypto_tickers()]
            except LiveDataError as error:
                capturas["cripto"] = []
                st.error(f"Cripto: {error}")
        with st.spinner(f"Pidiendo {len(EQUITY_CATALOG)} valores de bolsa a yfinance..."):
            try:
                capturas["bolsa"] = [q.as_row() for q in equity_quotes(EQUITY_CATALOG)]
            except LiveDataError as error:
                capturas["bolsa"] = []
                st.error(f"Bolsa: {error}")
        st.session_state["cotizaciones"] = capturas

    datos = st.session_state.get("cotizaciones")
    if not datos:
        st.info("Pulsa el boton para traer la primera foto del mercado.")
        return

    st.caption(f"Foto de las {datos['at']} UTC. Vuelve a pulsar para refrescarla.")
    filtro = (
        st.text_input("Filtrar por simbolo (p.ej. BTC, AAPL, .MC)", key="filtro_cotizaciones")
        .strip()
        .upper()
    )

    descargados = {a.symbol for a in activos}
    elegido: str | None = None
    mercado_elegido = ""
    for titulo, clave_datos, clave_tabla, mercado in (
        ("Bolsa", "bolsa", "viva_bolsa", "equity"),
        ("Cripto", "cripto", "viva_cripto", "crypto"),
    ):
        filas = list(datos.get(clave_datos, []))
        visibles = [f for f in filas if filtro in str(f["activo"]).upper()] if filtro else filas
        st.markdown(f"**{titulo}** — {len(visibles)} de {len(filas)} (ordenados por volumen)")
        if not visibles:
            continue
        pinchado = _tabla_viva(visibles, clave_tabla)
        if pinchado:
            elegido, mercado_elegido = pinchado, mercado

    if elegido is None:
        st.caption("Pincha una fila para poder descargar su historico completo.")
        return

    if elegido in descargados:
        st.info(f"{elegido} ya tiene historico descargado: lo tienes abajo, con su grafica.")
        return

    st.markdown(f"Seleccionado: **{elegido}**")
    if st.button(f"Descargar historico completo de {elegido}", key="descargar_vivo"):
        argumentos = [
            "uv",
            "run",
            "invest-ll-fetch",
            elegido,
            "--market",
            mercado_elegido,
            "--interval",
            "DAY_1",
            "--start",
            "2015-01-01",
            "--end",
            datetime.now(UTC).date().isoformat(),
        ]
        if mercado_elegido == "crypto":
            argumentos += ["--exchange", "binance"]
        with st.spinner(f"Descargando {elegido} desde 2015..."):
            proceso = subprocess.run(
                argumentos, capture_output=True, text=True, timeout=600, check=False
            )
        if proceso.returncode == 0:
            st.success(f"{elegido} descargado: ya aparece en las mesas de rendimiento.")
            st.rerun()
        else:
            detalle = (proceso.stderr or proceso.stdout or "sin mensaje").strip()[-300:]
            st.error(f"No se pudo descargar {elegido}: {detalle}")


def _tabla_mercado(filas: list[dict[str, object]], clave: str) -> str | None:
    """Una mesa densa con seleccion de fila: devuelve el activo pinchado, o `None`."""
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
    evento = st.dataframe(
        estilo,
        use_container_width=True,
        hide_index=True,
        key=clave,
        on_select="rerun",
        selection_mode="single-row",
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
    seleccionadas = evento.get("selection", {}).get("rows", [])
    if seleccionadas:
        return str(df.iloc[seleccionadas[0]]["activo"])
    return None


def _grafica_activo(simbolo: str, activos: list[AvailableAsset]) -> None:
    """La grafica del activo pinchado, con su tramo y la fecha de los datos a la vista."""
    activo = next((a for a in activos if a.symbol == simbolo), None)
    if activo is None:
        return
    try:
        serie = activo.load_completa()
    except (InvestLLError, ValueError) as error:
        st.error(f"No se pudo cargar {simbolo}: {error}")
        return

    st.subheader(f"Grafica: {simbolo}")
    tramo = st.radio(
        "Tramo",
        ["3 meses", "1 año", "5 años", "Todo"],
        horizontal=True,
        key=f"tramo_{simbolo}",
    )
    sesiones = {"3 meses": 63, "1 año": 252, "5 años": 1260}.get(str(tramo))
    barras = serie.bars[-sesiones:] if sesiones else serie.bars
    st.line_chart(
        [{"fecha": b.timestamp, "precio": b.close} for b in barras],
        x="fecha",
        y="precio",
        height=340,
    )
    st.caption(
        f"{len(barras)} sesiones, hasta el {serie.bars[-1].timestamp.date()}. "
        "Datos historicos descargados, no precios en vivo."
    )


def seccion_panorama(activos: list[AvailableAsset]) -> None:
    """Como va cada cosa. Sin recomendar nada.

    Es deliberadamente aburrida comparada con un panel de mercado al uso: no hay indicadores de
    "miedo y codicia" ni "temporada de altcoins". Esos indicadores existen para que operes mas, y
    todo lo medido en este proyecto dice que operar mas pierde dinero.
    """
    st.caption(
        "Rendimiento sobre el HISTORICO descargado (las cotizaciones al momento estan arriba). "
        "Aqui solo aparece lo que tiene serie completa: graficas, backtests y alertas salen "
        "de estos datos."
    )

    filas = market_overview(activos)
    if not filas:
        st.info("No hay historicos que mostrar.")
        return

    st.subheader("Rendimiento por periodo")

    # La forma de CoinMarketCap sin sus anzuelos, en dos mesas: bolsa y cripto. Color solo en
    # las variaciones, una sparkline por fila, ordenacion pinchando la cabecera -- y al pinchar
    # una FILA, la grafica del activo. Ni 1h%, ni tendencias, ni ganadores del dia.
    es_cripto = {a.symbol: a.is_crypto for a in activos}
    bolsa = [f for f in filas if not es_cripto.get(str(f["activo"]), False)]
    cripto = [f for f in filas if es_cripto.get(str(f["activo"]), False)]

    elegido: str | None = None
    if bolsa:
        st.markdown(f"**Bolsa** — {len(bolsa)} activo(s)")
        elegido = _tabla_mercado(bolsa, "tabla_bolsa") or elegido
    if cripto:
        st.markdown(f"**Cripto** — {len(cripto)} activo(s)")
        elegido = _tabla_mercado(cripto, "tabla_cripto") or elegido

    st.caption(
        "**La columna que mas importa es 'desde maximo'**: un activo que subio un 40% este anho "
        "pero sigue un 30% por debajo de su pico no esta yendo bien, se esta recuperando de una "
        "caida que alguien sufrio. Un hueco significa que no hay historico suficiente para esa "
        "ventana, no que rindiera un 0%. Pincha una cabecera para ordenar, y una fila para ver "
        "su grafica."
    )

    if elegido is not None:
        st.divider()
        _grafica_activo(elegido, activos)

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


def seccion_un_activo(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    st.subheader("Una estrategia sobre un activo")

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


def seccion_una_cartera(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    st.subheader("Aportaciones periodicas a una cartera")

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


def seccion_propuesta(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    """Simula y, si quieres, REGISTRA la decision en tu ledger con un boton.

    Registrar es contabilidad: anota las compras en Mi cartera al ultimo cierre descargado. No
    compra nada en ningun mercado — la unica puerta al dinero real sigue siendo
    `invest-ll-execute`, con su confirmacion escribiendo la cantidad.
    """
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

        compras: list[dict[str, object]] = []
        for h in propuesta.holdings:
            cierre = ultimo_cierre(h.symbol)
            precio, fecha = cierre if cierre is not None else (None, None)
            compras.append(
                {
                    "symbol": h.symbol,
                    "importe": str(h.amount_per_contribution),
                    "precio": str(precio) if precio is not None else None,
                    "fecha": fecha.date().isoformat() if fecha is not None else None,
                    "cantidad": (
                        str((h.amount_per_contribution / precio).quantize(D("0.0001")))
                        if precio
                        else None
                    ),
                }
            )
        st.session_state["propuesta_actual"] = {"texto": propuesta.render(), "compras": compras}

    guardada = st.session_state.get("propuesta_actual")
    if not guardada:
        return

    st.text(guardada["texto"])
    st.caption("Esto es una simulacion sobre el pasado, no una recomendacion ni una prevision.")

    st.subheader("Llevarla a tu cartera")
    st.dataframe(
        [
            {
                "activo": c["symbol"],
                "importe": c["importe"],
                "cantidad": c["cantidad"] or "sin precio",
                "precio de referencia": c["precio"] or "—",
                "cierre del": c["fecha"] or "—",
            }
            for c in guardada["compras"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if st.button("Registrar estas compras en Mi cartera"):
        registradas = 0
        problemas: list[str] = []
        for c in guardada["compras"]:
            if not c["cantidad"]:
                problemas.append(f"{c['symbol']}: sin precio descargado, registralo a mano")
                continue
            try:
                ActivityStore().append(
                    Activity(
                        timestamp=datetime.now(UTC),
                        type=ActivityType.BUY,
                        symbol=str(c["symbol"]),
                        quantity=D(str(c["cantidad"])),
                        unit_price=D(str(c["precio"])),
                        source="propuesta",
                    )
                )
                registradas += 1
            except (InvestLLError, ValueError) as error:
                problemas.append(f"{c['symbol']}: {error}")
        for problema in problemas:
            st.error(problema)
        if registradas:
            del st.session_state["propuesta_actual"]
            st.success(
                f"Registradas {registradas} compra(s) en el ledger: ya estan en Mi cartera. "
                "Es contabilidad tuya, al ultimo cierre descargado — NO se ha comprado nada en "
                "ningun mercado. Para dinero real: invest-ll-execute."
            )

    st.caption(
        "Registrar anota la decision en tu ledger; no envia ninguna orden. Enviar de verdad exige "
        "confirmar cada orden por separado, aqui o en invest-ll-execute."
    )
    with st.expander("Los comandos equivalentes (para ejecutar de verdad, fuera del panel)"):
        lineas: list[str] = []
        for c in guardada["compras"]:
            if not c["cantidad"]:
                lineas.append(f"# {c['symbol']}: sin precio descargado, calcula la cantidad a mano")
                continue
            lineas.append(
                f"uv run invest-ll-execute --symbol {c['symbol']} --side buy "
                f"--quantity {c['cantidad']}"
            )
        st.code("\n".join(lineas), language="bash")

    seccion_enviar_orden(
        [c["symbol"] for c in guardada["compras"] if c["cantidad"]], clave="propuesta"
    )


def seccion_enviar_orden(sugeridos: list[str] | None = None, *, clave: str = "propuesta") -> None:
    """Enviar UNA orden desde el panel, con la misma confirmacion que el terminal.

    El boton no envia por si solo: se habilita al escribir la cantidad exacta, igual que
    `invest-ll-execute` pide teclearla. Un clic distraido no mueve dinero.

    La decision de si se puede enviar vive en `dashboard/ordenes.py`, comprobada por tests sin
    levantar Streamlit; aqui solo se pinta.
    """
    modo = resolve_mode()

    st.markdown("---")
    st.subheader("Enviar una orden")

    if not modo.sends_real_orders:
        st.caption(
            "Modo simulacion: el panel no puede enviar nada. Para operar en la red de pruebas, "
            "arranca el panel con INVEST_LL_MODE=testnet y sus credenciales."
        )
        return

    if isinstance(modo, Real):
        st.error(
            "MODO REAL: lo que envies desde aqui mueve DINERO DE VERDAD. "
            "Cada orden sigue pidiendo su confirmacion."
        )
    else:
        st.warning(
            "Red de pruebas: las ordenes salen de verdad al exchange, con dinero ficticio. "
            "Los precios de la red de pruebas no son los del mercado real."
        )

    opciones = sugeridos or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    col_par, col_lado, col_cant = st.columns([2, 1, 1])
    with col_par:
        par = st.selectbox("Par", opciones, key=f"envio_par_{clave}")
    with col_lado:
        lado = st.selectbox("Lado", [s.value for s in Side], key=f"envio_lado_{clave}")
    with col_cant:
        cantidad = st.number_input(
            "Cantidad",
            min_value=0.0,
            value=0.001,
            step=0.001,
            format="%.6f",
            key=f"envio_cantidad_{clave}",
        )

    cantidad_decimal = Decimal(str(cantidad))
    escrito = st.text_input(
        f"Escribe la cantidad exacta ({cantidad_decimal}) para confirmar",
        key=f"envio_confirmacion_{clave}",
        help="Se escribe el numero, no un si: obliga a mirar lo que se va a mover.",
    )

    motivo = motivo_para_no_enviar(modo, cantidad=cantidad_decimal, escrito=escrito)
    if motivo:
        st.caption(motivo)

    if st.button(
        f"Enviar {lado.upper()} {cantidad_decimal} {par}",
        disabled=motivo is not None,
        key=f"envio_boton_{clave}",
    ):
        try:
            resultado = enviar_orden(
                construir_broker(modo),
                symbol=par,
                side=Side(lado),
                cantidad=cantidad_decimal,
                escrito=escrito,
                ahora=datetime.now(UTC),
                ledger=ExecutionLedger(),
            )
        except (InvestLLError, ValueError) as error:
            st.error(str(error))
            return

        if resultado.status is OrderStatus.UNKNOWN:
            st.error(resultado.describe())
        elif resultado.needs_attention:
            st.warning(resultado.describe())
        else:
            st.info(resultado.describe())
        st.caption(
            f"Registrada en {ExecutionLedger().path} con el modo '{modo.name}' dentro. "
            "Ese campo es lo que permite demostrar despues en que modo salio."
        )


def seccion_llm(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    """Reproduce el experimento real del LLM sin gastar cuota: decisiones grabadas.

    Generar decisiones NUEVAS gasta cuota y sigue en `invest-ll-generate`; repetir el
    experimento con lo grabado es gratis, que es justo lo que lo hace repetible.
    """
    st.subheader("El LLM decide (decisiones grabadas)")
    st.caption(
        "84 decisiones reales de claude-opus-4-6 sobre 21 anhos (GLD/TLT/XLE/XLF), grabadas en "
        "decisions/llm-trimestral. Compararlas no consulta a nadie ni gasta nada."
    )

    almacen_dir = Path("decisions/llm-trimestral")
    if not almacen_dir.exists():
        st.info(
            "No hay decisiones grabadas en decisions/llm-trimestral. "
            "Generalas con invest-ll-generate (gasta cuota; se hace una sola vez)."
        )
        return

    simbolos_exp = ("GLD", "TLT", "XLE", "XLF")
    unicos = {a.symbol: a for a in activos if a.symbol in simbolos_exp and not a.is_crypto}
    if len(unicos) < len(simbolos_exp):
        st.info("Faltan historicos de GLD/TLT/XLE/XLF para reproducir el experimento.")
        return

    if st.button("Comparar LLM vs momentum vs no hacer nada"):
        with st.spinner("Reproduciendo 21 anhos de decisiones..."):
            try:
                universo = build_universe([unicos[s].load() for s in simbolos_exp])
                riesgo = RiskConfig(position_fraction=D(1))
                proveedor = RecordedProvider(DecisionStore(almacen_dir), model="claude-opus-4-6")
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
            except InvestLLError as error:
                st.error(f"No se pudo reproducir: {error}")
                return

        filas = [
            {
                "estrategia": "LLM (grabado)",
                "resultado": float(informe_llm.net_result),
                "drawdown": float(informe_llm.max_drawdown),
                "operaciones": informe_llm.trade_count,
                "costes": float(informe_llm.total_costs),
            },
            {
                "estrategia": "momentum",
                "resultado": float(informe_mom.net_result),
                "drawdown": float(informe_mom.max_drawdown),
                "operaciones": informe_mom.trade_count,
                "costes": float(informe_mom.total_costs),
            },
        ]
        bh = informe_llm.buy_and_hold
        if bh is not None:
            filas.append(
                {
                    "estrategia": "comprar y mantener",
                    "resultado": float(bh.net_result),
                    "drawdown": float(bh.max_drawdown),
                    "operaciones": 1,
                    "costes": float(bh.costs),
                }
            )
        st.dataframe(filas, use_container_width=True, hide_index=True)

        if not (informe_llm.beats_market or informe_mom.beats_market):
            st.error(
                "Ninguna bate a comprar y mantener. Todo el riesgo asumido y las comisiones "
                "pagadas quedaron por debajo de no hacer nada."
            )
        st.warning(ADVERTENCIA_CONTAMINACION)


def pestana_mercado(activos: list[AvailableAsset]) -> None:
    """¿Cómo está el mundo? Rendimiento, comparación y estado de los datos, juntos.

    Antes esto vivía repartido entre "Panorama" y "Estado actual" — la misma pregunta contada en
    dos pestañas. La reestructuración las junta: **una pestaña por pregunta**.
    """
    st.header("Mercado")
    seccion_cotizaciones(activos)
    st.divider()
    seccion_panorama(activos)
    st.divider()
    seccion_datos(activos)


def pestana_simular(activos: list[AvailableAsset], friction: FrictionConfig) -> None:
    """¿Qué pasaría si...? Todo lo que es ensayo vive junto, y nada de esto mueve dinero."""
    st.header("Simular")
    st.caption(
        "Propuestas y backtests sobre datos historicos. Nada de esta pestana envia ordenes: "
        "la unica puerta al dinero real es invest-ll-execute, con su confirmacion."
    )

    modo = st.radio(
        "Que quieres ensayar",
        [
            "Propuesta simple",
            "Aportaciones periodicas a una cartera",
            "Una estrategia sobre un activo",
            "El LLM decide (grabado)",
        ],
        horizontal=True,
    )
    st.divider()
    if modo == "Propuesta simple":
        seccion_propuesta(activos, friction)
    elif modo == "Aportaciones periodicas a una cartera":
        seccion_una_cartera(activos, friction)
    elif modo == "Una estrategia sobre un activo":
        seccion_un_activo(activos, friction)
    else:
        seccion_llm(activos, friction)

    st.divider()
    st.subheader("Las cuatro vias de invertir")
    st.markdown(
        "| Via | Donde, en esta pagina |\n"
        "|---|---|\n"
        "| **Boton simple** | Propuesta simple: simula y **registra en Mi cartera con un "
        "boton** |\n"
        "| **Bot determinista** | Rotacion momentum: Aportaciones / Un activo, aqui arriba |\n"
        "| **LLM** | 'El LLM decide (grabado)': reproduce el experimento real sin gastar "
        "cuota, y la pestana Chat para preguntarle |\n"
        "| **LLM desde fuera** | Un agente externo maneja los diez comandos con `--json`; "
        "las advertencias viajan dentro del JSON |\n"
    )
    st.caption(
        "Lo unico que no vive en el panel es el dinero real: eso es invest-ll-execute, con su "
        "confirmacion. Lo medido hasta hoy (21 anhos, 4 activos): cuanto menos se opera, mejor "
        "-- 423 operaciones dieron 2.890; una sola dio 37.773. Ver "
        "docs/experimento-llm-2026-07.md."
    )


def pestana_mi_cartera() -> None:
    """La cartera real, derivada del ledger de movimientos.

    El panel SOLO LEE. Registrar movimientos se hace con `invest-ll-portfolio` — mantener la
    escritura fuera del panel es deliberado: un formulario de compra a un clic del grafico es el
    patron que la FCA midio en +11% de operaciones.
    """
    st.header("Mi cartera")

    with (
        st.expander("Registrar un movimiento (escribe en el ledger; NO envia ordenes)"),
        st.form("registrar_movimiento", clear_on_submit=True),
    ):
        tipo = st.selectbox("Tipo", ["compra", "venta", "deposito", "retirada"])
        c1, c2 = st.columns(2)
        simbolo = c1.text_input("Activo (solo compra/venta)", placeholder="GLD")
        fecha = c2.date_input("Fecha", value=datetime.now(UTC).date())
        c3, c4, c5 = st.columns(3)
        cantidad = c3.text_input("Cantidad (o importe si es efectivo)")
        precio = c4.text_input("Precio unitario", placeholder="240.50")
        comision = c5.text_input("Comision", value="0")

        if st.form_submit_button("Registrar en el ledger"):
            try:
                momento = datetime(fecha.year, fecha.month, fecha.day, tzinfo=UTC)
                if tipo in ("compra", "venta"):
                    actividad = Activity(
                        timestamp=momento,
                        type=ActivityType.BUY if tipo == "compra" else ActivityType.SELL,
                        symbol=simbolo.strip().upper(),
                        quantity=D(cantidad.strip()),
                        unit_price=D(precio.strip()),
                        fee=D(comision.strip() or "0"),
                        source="panel",
                    )
                else:
                    actividad = Activity(
                        timestamp=momento,
                        type=(
                            ActivityType.DEPOSIT if tipo == "deposito" else ActivityType.WITHDRAWAL
                        ),
                        symbol=None,
                        quantity=D(cantidad.strip()),
                        unit_price=D(1),
                        source="panel",
                    )
                ActivityStore().append(actividad)
            except (InvestLLError, ValueError, ArithmeticError) as error:
                st.error(f"No registrado: {error}")
            else:
                st.rerun()

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
        # La cartera vacia es precisamente cuando hace falta poder mandar la primera orden. Y ver
        # lo enviado importa mas aqui que en ningun sitio: si mandaste algo y esto sigue vacio,
        # la explicacion esta en la tabla de abajo.
        seccion_enviar_orden(clave="cartera")
        seccion_ordenes_enviadas()
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
        "Los movimientos ya hechos se registran con `invest-ll-portfolio` (add / cash / import). "
        "Para enviar una orden al mercado, abajo o `invest-ll-execute`: las dos piden confirmarla."
    )

    seccion_enviar_orden(clave="cartera")
    seccion_ordenes_enviadas()


def seccion_ordenes_enviadas() -> None:
    """Lo que de verdad salio al mercado, con el modo de cada orden a la vista.

    Vive separado de la cartera a proposito: la cartera dice **que tienes**, y esto **que
    mandaste**. Una orden rechazada o de estado desconocido no cambia lo que tienes, pero es justo
    lo que hay que poder mirar cuando algo ha ido mal.
    """
    entradas = ExecutionLedger().entries()
    if not entradas:
        return

    st.markdown("---")
    st.subheader("Ordenes enviadas")

    filas = [
        {
            "cuando": e.result.executed_at or e.recorded_at,
            "modo": e.mode_name,
            "activo": e.result.request.symbol,
            "lado": e.result.request.side.value,
            "pedida": float(e.result.request.quantity),
            "ejecutada": float(e.result.filled_quantity),
            "precio": float(e.result.fill_price) if e.result.fill_price else None,
            "comision": float(e.result.commission) if e.result.commission is not None else None,
            "estado": e.result.status.value,
            "referencia": e.result.broker_reference or "",
        }
        for e in reversed(entradas)
    ]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    reales = sum(1 for e in entradas if e.was_real_money)
    atencion = [e for e in entradas if e.result.needs_attention]
    sin_comision = sum(
        1 for e in entradas if e.result.commission is None and e.result.filled_quantity > 0
    )

    st.caption(
        f"{len(entradas)} orden(es) · {reales} con dinero real · "
        f"registro en {ExecutionLedger().path}"
    )
    for e in atencion:
        st.warning(e.result.describe())
    if sin_comision:
        st.caption(
            f"{sin_comision} sin comision registrada: no pasan a la cartera, porque anotarlas "
            "con comision cero las haria parecer mas rentables de lo que fueron."
        )


def pestana_alertas(activos: list[AvailableAsset]) -> None:
    """Lo que esta pasando con tus activos. Se mira; no persigue.

    Esta pestana **no notifica**: existe aqui, y aparece cuando la abres. Es deliberado. La FCA
    midio sobre mas de 9.000 personas que las notificaciones aumentan un 11% las operaciones y un
    8% las inversiones arriesgadas, con mas efecto en quien menos sabe de inversion.

    Tampoco hay alertas de subidas. Una que dijera "GLD subio un 20%" no informa de nada que
    necesites: existe para que abras la aplicacion.
    """
    st.header("Vigilar")
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
            series.append(activo.load_completa())
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

    st.divider()
    st.subheader("Triggers de retirada")
    st.caption(
        "Cuando se cruzan, PROPONEN la venta exacta (con `invest-ll-triggers check`); "
        "ejecutarla y confirmarla sigue siendo cosa tuya."
    )

    triggers_store = TriggerStore()
    pausa = triggers_store.halted()
    if pausa:
        st.warning(f"Pausa activa (no se proponen entradas nuevas): {pausa}")

    armados = triggers_store.triggers()
    for armado in armados:
        col_desc, col_boton = st.columns([5, 1])
        col_desc.write(f"`{armado.trigger_id}` {armado.describe()}")
        if col_boton.button("Desarmar", key=f"desarmar_{armado.trigger_id}"):
            triggers_store.disarm(armado.trigger_id)
            st.rerun()
    if not armados:
        st.caption("Ninguno armado.")

    with st.form("armar_trigger"):
        col_a, col_b, col_c = st.columns(3)
        simbolo_t = col_a.text_input("Activo", placeholder="GLD")
        regla = col_b.selectbox("Regla", [r.value for r in TriggerRule])
        umbral = col_c.slider("Umbral (%)", 5, 60, 15, step=5)
        if st.form_submit_button("Armar trigger"):
            try:
                triggers_store.arm(
                    Trigger(
                        trigger_id=triggers_store.next_id(),
                        symbol=simbolo_t.strip().upper(),
                        rule=TriggerRule(regla),
                        threshold=D(umbral) / 100,
                        armed_at=datetime.now(UTC),
                    )
                )
            except (InvestLLError, ValueError) as error:
                st.error(str(error))
            else:
                st.rerun()

    col_pausa, col_reanudar = st.columns(2)
    with col_pausa, st.form("pausar_entradas"):
        motivo = st.text_input("Motivo de la pausa (obligatorio)")
        if st.form_submit_button("Pausar entradas nuevas"):
            try:
                triggers_store.halt(reason=motivo, at=datetime.now(UTC))
            except InvestLLError as error:
                st.error(str(error))
            else:
                st.rerun()
    with col_reanudar:
        if st.button("Retirar la pausa"):
            triggers_store.resume()
            st.rerun()


def pestana_chat() -> None:
    """Hablar con Claude sobre TU situacion. Lee y explica; no puede ejecutar nada.

    Usa el CLI de `claude` con la suscripcion del operador (igual que invest-ll-generate).
    El contexto (cartera, triggers, mercado con sus fechas) se reconstruye en cada mensaje.
    """
    st.header("Chat")
    st.caption(
        "Claude lee tu cartera, tus triggers y tus datos (con sus fechas). NO puede ejecutar "
        "nada: propone comandos y ejecutarlos es cosa tuya. Cada mensaje gasta cuota de tu "
        "suscripcion."
    )

    if "chat_sesion" not in st.session_state:
        st.session_state["chat_sesion"] = ChatSession()
    sesion: ChatSession = st.session_state["chat_sesion"]

    for autor, texto in sesion.history:
        with st.chat_message("user" if autor == "operador" else "assistant"):
            st.markdown(texto)

    pregunta = st.chat_input("Pregunta sobre tu cartera, tus datos o que comando usar")
    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Preguntando a Claude (tu suscripcion)..."):
                    respuesta = sesion.ask(pregunta, contexto=build_context())
            except ChatUnavailableError as error:
                st.error(str(error))
            else:
                st.markdown(respuesta)


def seccion_datos(activos: list[AvailableAsset]) -> None:
    st.subheader("Datos descargados")
    st.caption(
        "Ultimo cierre de cada historico descargado. Para actualizarlo hay que volver a "
        "descargar con invest-ll-fetch: el motor no toca la red por diseno."
    )

    filas: list[dict[str, object]] = []
    for activo in activos:
        try:
            serie = activo.load_completa()
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

    st.divider()
    if st.button("Actualizar todos los historicos (descarga de internet, tarda un rato)"):
        resultados: list[tuple[str, bool, str]] = []
        with st.status("Descargando...", expanded=True) as estado:
            for activo in activos:
                argumentos = fetch_args(activo, hasta=datetime.now(UTC))
                if argumentos is None:
                    st.write(f"{activo.symbol}: sin metadatos de procedencia, saltado")
                    continue
                st.write(f"{activo.symbol}...")
                proceso = subprocess.run(
                    argumentos, capture_output=True, text=True, timeout=600, check=False
                )
                detalle = (proceso.stderr or proceso.stdout or "").strip()[-200:]
                resultados.append((activo.symbol, proceso.returncode == 0, detalle))

            fallos = [r for r in resultados if not r[1]]
            estado.update(
                label=f"Terminado: {len(resultados) - len(fallos)} bien, {len(fallos)} con fallo",
                state="error" if fallos else "complete",
            )
        for simbolo, bien, detalle in resultados:
            if not bien:
                st.error(f"{simbolo}: {detalle}")
        if resultados and not fallos:
            st.rerun()


def pestana_investigacion() -> None:
    from invest_ll.dashboard.research import render_research_tab

    render_research_tab()


def main() -> None:
    st.set_page_config(page_title="INVEST LL", layout="wide")
    st.title("INVEST LL")

    # El modo va en la cabecera, no escondido en una pestana: es lo primero que hay que saber al
    # mirar cualquier cifra. Anunciar "no ejecuta ordenes reales" cuando si puede seria la clase
    # de mentira que este proyecto existe para no contar.
    modo_actual = resolve_mode()
    if isinstance(modo_actual, Real):
        st.error(
            "MODO REAL: este panel PUEDE enviar ordenes con dinero de verdad. "
            "Cada una sigue pidiendo su confirmacion."
        )
    elif modo_actual.sends_real_orders:
        st.warning("MODO PRUEBAS: las ordenes salen de verdad al exchange, con dinero ficticio.")
    st.caption(
        "Simulacion sobre datos historicos. "
        + (
            "Las ordenes se envian desde Mi cartera, con confirmacion. "
            if modo_actual.sends_real_orders
            else "No ejecuta ninguna orden real. "
        )
        + "Recuerda: el win rate no es criterio de exito."
    )

    # La reserva recorta los backtests. Sin decirlo, un resultado de 2024 parece de hoy.
    reservado = aviso_de_reserva()
    if reservado:
        st.caption(reservado)

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

    # Siete pestanas, una pregunta cada una, en el orden en que se usan:
    # mirar -> tener -> ensayar -> vigilar -> comprobar -> investigar -> preguntar.
    mercado, mi_cartera, simular, vigilar, seguimiento, investigacion, chat = st.tabs(
        ["Mercado", "Mi cartera", "Simular", "Vigilar", "Estimado vs real", "Investigación", "Chat"]
    )
    with mercado:
        pestana_mercado(activos)
    with mi_cartera:
        pestana_mi_cartera()
    with simular:
        pestana_simular(activos, friction)
    with vigilar:
        pestana_alertas(activos)
    with seguimiento:
        pestana_seguimiento()
    with investigacion:
        pestana_investigacion()
    with chat:
        pestana_chat()


if __name__ == "__main__":  # pragma: no cover
    main()
