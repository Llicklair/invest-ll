"""The "Investigación" tab: the pre-registered portfolio today, its forward test, the last study.

Everything shown comes from `invest_ll.quant` and the files `invest-ll-quant` writes; this tab only
reads. The labels are Spanish like the rest of the panel.
"""

# Boundary with streamlit and pandas, as in dashboard/app.py.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from invest_ll.quant.panel import Panel, load_binance_universe

DATA_ROOT = Path("data/market/binance-universe")
RUNS = Path("research/runs")


@st.cache_resource(show_spinner="Cargando el universo de Binance...")
def _panel(mtime: float) -> Panel:
    del mtime  # cache key: reload when the file changes
    return load_binance_universe(DATA_ROOT)


def latest_report(runs: Path = RUNS) -> Path | None:
    reports = sorted(runs.glob("*/report.html"), key=lambda p: p.stat().st_mtime)
    return reports[-1] if reports else None


def render_research_tab() -> None:
    from invest_ll.quant.metrics import summarise
    from invest_ll.quant.paper import current_targets, read, replay, variants
    from invest_ll.quant.study import FLAGSHIP, FLAGSHIP_UNIVERSE, REBALANCE_EVERY, TRANCHES

    st.subheader("Cartera prerregistrada")
    st.caption(
        "Momentum diversificado sobre las 20 monedas más líquidas de cada día, con las que luego "
        "murieron incluidas. Peso por riesgo, máximo 35% por moneda, objetivo de volatilidad del "
        "60%, decisión semanal en 7 tramos. Fijada antes de ver resultados. Ver "
        "docs/quant-research.md."
    )
    klines = DATA_ROOT / "klines_1d.parquet"
    if not klines.exists():
        st.info(
            "Sin datos todavía. Descárgalos con `uv run invest-ll-quant download` (unos 6 minutos)."
        )
        return

    panel = _panel(klines.stat().st_mtime)
    last = panel.date_at(len(panel) - 1)
    stale = (datetime.now(UTC).date() - last).days
    if stale > 2:
        st.warning(
            f"Los datos acaban el {last} (hace {stale} días). Actualiza con `invest-ll-quant download`."
        )

    weights = current_targets(
        panel, FLAGSHIP, FLAGSHIP_UNIVERSE, rebalance_every=REBALANCE_EVERY, tranches=TRANCHES
    )
    capital = st.number_input(
        "Tamaño de la cuenta (USDT)",
        min_value=0.0,
        value=1000.0,
        step=100.0,
        key="research_capital",
    )
    rows = [
        {
            "Moneda": panel.symbols[i].removesuffix("USDT"),
            "Peso": float(w),
            "USDT": float(w) * capital,
        }
        for i, w in sorted(enumerate(weights), key=lambda x: -x[1])
        if w > 1e-6
    ]
    cash = 1.0 - float(sum(float(w) for w in weights if w > 1e-6))
    rows.append({"Moneda": "liquidez", "Peso": cash, "USDT": cash * capital})
    st.markdown(
        f"**Objetivo tras el cierre del {last}.** Esto no es una previsión de que vayan a subir."
    )
    st.dataframe(
        pd.DataFrame(rows).style.format({"Peso": "{:.1%}", "USDT": "{:,.2f}"}),
        hide_index=True,
        width="stretch",
    )
    st.caption("El panel no envía nada. Ejecutar estas cantidades sigue siendo cosa tuya.")

    st.subheader("Prueba hacia delante")
    labels = {
        "preregistered": "Prerregistrada",
        "filtered": "Segunda fase (filtro de mercado + banda)",
    }
    for variant in variants().values():
        records = read(variant.ledger)
        st.markdown(f"**{labels.get(variant.key, variant.key)}**")
        if not records:
            st.info(
                "Todavía no hay registros. `uv run invest-ll-quant paper record` guarda la cartera "
                "de hoy; `scripts/paper-daily.ps1` lo hace cada día y lo deja en un commit con fecha."
            )
            continue
        result = replay(panel, records, no_trade_band=variant.no_trade_band)
        if result is None or len(result.returns) < 1:
            st.info(
                f"Primer registro el {records[0].data_date}: aún no hay días después para medir."
            )
            continue
        s = summarise(result)
        btc = panel.close[:, panel.column("BTCUSDT")]
        btc_value = 10_000 * float(btc[-1] / btc[result.start])
        a, b, c = st.columns(3)
        a.metric("Cartera (desde 10.000)", f"{s.final_value:,.0f}")
        b.metric("Mantener BTC", f"{btc_value:,.0f}")
        c.metric("Peor caída", f"{s.max_drawdown:.1%}")
        st.caption(
            f"Desde {records[0].data_date}, {len(records)} registros, con las mismas comisiones "
            "que el backtest."
        )

    st.subheader("Último estudio")
    report = latest_report()
    if report is None:
        st.info(
            "Ningún estudio todavía. `uv run invest-ll-quant study` genera el informe completo."
        )
        return
    st.caption(
        f"{report} · generado {datetime.fromtimestamp(report.stat().st_mtime):%Y-%m-%d %H:%M}"
    )
    components.html(report.read_text(encoding="utf-8"), height=1400, scrolling=True)
