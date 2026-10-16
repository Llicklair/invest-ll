"""Render a study as one self-contained HTML page (no network, no external files).

Charts are inline SVG drawn here; a few lines of script add the hover readout. The page follows the
light/dark tokens pattern so it reads in either theme, and every number shown in a chart is also in
a table.
"""

# Rendered text uses typographic minus signs and en dashes on purpose.
# ruff: noqa: RUF001

from __future__ import annotations

import html
import json
import math
from datetime import UTC, datetime

import numpy as np

from invest_ll.quant.metrics import Summary, drawdown
from invest_ll.quant.panel import FloatArray
from invest_ll.quant.study import (
    CAPITAL,
    FLAG_KEY,
    FLAGSHIP,
    FLAGSHIP_UNIVERSE,
    REBALANCE_EVERY,
    TRANCHES,
    StudyResult,
)

SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"]

FLAG = FLAG_KEY
CHART_KEYS = [
    FLAG,
    "Hold BTC",
    "Hold the top 20 (equal weight, monthly)",
    "INVEST LL policy on the top 20 (top-1, 30d, weekly)",
    "BTC 30-day trend (weekly)",
]
SHORT = {
    FLAG: "Momentum portfolio",
    "Hold BTC": "Hold BTC",
    "Hold the top 20 (equal weight, monthly)": "Hold top 20",
    "INVEST LL policy on the top 20 (top-1, 30d, weekly)": "Current policy",
    "BTC 30-day trend (weekly)": "BTC trend",
    "Momentum portfolio, Spanish tax paid yearly": "Momentum, after tax",
}


def _iso(day: int) -> str:
    return datetime.fromtimestamp(int(day) * 86_400, UTC).date().isoformat()


def _pct(x: float | None, digits: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x * 100:+.{digits}f}%".replace("+-", "−").replace("-", "−")


def _pct_plain(x: float | None, digits: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x * 100:.{digits}f}%".replace("-", "−")


def _num(x: float, digits: int = 2) -> str:
    if math.isnan(x):
        return "–"
    return f"{x:.{digits}f}".replace("-", "−")


def _money(x: float) -> str:
    return f"{x:,.0f}".replace("-", "−")


def _weekly(days: np.ndarray, values: FloatArray, start: int) -> tuple[list[str], list[float]]:
    idx = list(range(start, len(days), 7))
    if idx[-1] != len(days) - 1:
        idx.append(len(days) - 1)
    return [_iso(int(days[i])) for i in idx], [float(values[i]) for i in idx]


def _summary_rows(summaries: dict[str, Summary], keys: list[str]) -> str:
    rows: list[str] = []
    for k in keys:
        if k not in summaries:
            continue
        s = summaries[k]
        beta = "–" if s.beta is None else _num(s.beta)
        rows.append(
            "<tr>"
            f"<td>{html.escape(SHORT.get(k, k))}</td>"
            f"<td>{_money(s.final_value)}</td>"
            f"<td>{_pct(s.cagr)}</td>"
            f"<td>{_pct_plain(s.volatility)}</td>"
            f"<td>{_num(s.sharpe)}</td>"
            f"<td>{_pct(s.max_drawdown)}</td>"
            f"<td>{_num(s.calmar)}</td>"
            f"<td>{s.longest_drawdown_days}</td>"
            f"<td>{_pct_plain(s.exposure)}</td>"
            f"<td>{beta}</td>"
            f"<td>{_pct_plain(s.cost_drag, 1)}</td>"
            f"<td>{_money(s.final_after_tax)}</td>"
            "</tr>"
        )
    head = (
        "<tr><th>Strategy</th><th>End value</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th>"
        "<th>Max drawdown</th><th>Calmar</th><th>Longest drawdown (days)</th><th>Avg exposure</th>"
        "<th>Beta to BTC</th><th>Cost drag / yr</th><th>After liquidation tax</th></tr>"
    )
    return f'<div class="table-wrap"><table class="data"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def _yearly_table(result: StudyResult) -> str:
    keys = [k for k in CHART_KEYS if k in result.runs]
    years: list[int] = []
    per: dict[str, dict[int, float]] = {}
    for k in keys:
        r = result.runs[k]
        eq = r.equity[r.start :]
        days = r.days[r.start :]
        ys = np.array([datetime.fromtimestamp(int(d) * 86_400, UTC).year for d in days])
        per[k] = {}
        for y in sorted(set(ys.tolist())):
            sel = np.nonzero(ys == y)[0]
            begin = eq[sel[0] - 1] if sel[0] > 0 else eq[sel[0]]
            per[k][int(y)] = float(eq[sel[-1]] / begin - 1)
        years = sorted(set(years) | set(per[k]))
    head = "<tr><th>Strategy</th>" + "".join(f"<th>{y}</th>" for y in years) + "</tr>"
    rows: list[str] = []
    for k in keys:
        cells: list[str] = []
        for y in years:
            v = per[k].get(y)
            if v is None:
                cells.append("<td>–</td>")
                continue
            cls = _div_class(v)
            cells.append(f'<td class="{cls}">{_pct(v)}</td>')
        rows.append(f"<tr><td>{html.escape(SHORT.get(k, k))}</td>{''.join(cells)}</tr>")
    note = ""
    if years:
        note = f'<p class="caption">{years[-1]} is partial, to {html.escape(result.end)}.</p>'
    return f'<div class="table-wrap"><table class="data heat"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>{note}'


def _div_class(v: float) -> str:
    mag = abs(v)
    step = 0 if mag < 0.05 else 1 if mag < 0.25 else 2 if mag < 0.75 else 3 if mag < 2 else 4
    if step == 0:
        return "d0"
    return f"{'p' if v > 0 else 'n'}{step}"


def _line_chart_data(result: StudyResult) -> dict[str, object]:
    keys = [k for k in CHART_KEYS if k in result.runs]
    series: list[dict[str, object]] = []
    dates: list[str] = []
    for k in keys:
        r = result.runs[k]
        eq = r.equity / r.equity[r.start] * CAPITAL
        dates, vals = _weekly(r.days, eq, r.start)
        series.append({"name": SHORT.get(k, k), "values": vals})
    flag = result.runs[FLAG]
    btc = result.runs["Hold BTC"]
    _, dd_flag = _weekly(
        flag.days,
        np.concatenate([np.zeros(flag.start), drawdown(flag.equity[flag.start :])]),
        flag.start,
    )
    _, dd_btc = _weekly(
        btc.days,
        np.concatenate([np.zeros(btc.start), drawdown(btc.equity[btc.start :])]),
        btc.start,
    )
    return {
        "dates": dates,
        "series": series,
        "drawdown": [
            {"name": "Momentum portfolio", "values": dd_flag},
            {"name": "Hold BTC", "values": dd_btc},
        ],
    }


def _grid_section(result: StudyResult) -> str:
    if not result.grid_summaries:
        return ""
    sharpes = [s.sharpe for s in result.grid_summaries]
    cagrs = [s.cagr for s in result.grid_summaries]
    flag = result.summaries[FLAG]
    positive = sum(1 for c in cagrs if c > 0)
    beat_btc = sum(
        1 for s in result.grid_summaries if s.sharpe > result.summaries["Hold BTC"].sharpe
    )
    best = max(range(len(sharpes)), key=lambda i: sharpes[i])
    worst = min(range(len(sharpes)), key=lambda i: sharpes[i])
    data = json.dumps(
        {
            "sharpes": sharpes,
            "labels": result.grid_labels,
            "flag": flag.sharpe,
            "btc": result.summaries["Hold BTC"].sharpe,
        }
    )
    rows = "".join(
        f"<tr><td>{html.escape(result.grid_labels[i])}</td><td>{_num(result.grid_summaries[i].sharpe)}</td>"
        f"<td>{_pct(result.grid_summaries[i].cagr)}</td><td>{_pct(result.grid_summaries[i].max_drawdown)}</td></tr>"
        for i in sorted(range(len(sharpes)), key=lambda i: -sharpes[i])
    )
    return f"""
<section aria-labelledby="grid">
  <div class="section-head"><div class="eyebrow">Fragility</div><h2 id="grid">How much the settings matter</h2></div>
  <p class="col">The pre-registered portfolio has {len(sharpes)} neighbours: three trend horizons, three portfolio sizes,
  three volatility targets and three universe sizes. {positive} of {len(sharpes)} grow the account and {beat_btc}
  have a better Sharpe ratio than holding Bitcoin. The best cell ({html.escape(result.grid_labels[best])}) and the worst
  ({html.escape(result.grid_labels[worst])}) bracket what a different reasonable choice would have given.</p>
  <figure>
    <div class="fig-head"><div class="fig-title">Sharpe ratio of every configuration</div>
    <div class="fig-sub">Each dot is one configuration. The vertical lines mark the pre-registered portfolio and holding Bitcoin.</div></div>
    <div class="fig-body"><div id="strip" class="chart"></div><div class="tt" id="tt-strip" hidden></div></div>
    <details><summary>Show all {len(sharpes)} configurations</summary>
      <div class="table-wrap"><table class="data"><thead><tr><th>Configuration</th><th>Sharpe</th><th>CAGR</th><th>Max drawdown</th></tr></thead><tbody>{rows}</tbody></table></div>
    </details>
  </figure>
  <script type="application/json" id="strip-data">{data}</script>
</section>"""


def _luck_section(result: StudyResult) -> str:
    parts: list[str] = []
    if result.pbo is not None:
        parts.append(
            f'<dt>Probability of backtest overfitting</dt><dd><span class="num">{_pct_plain(result.pbo.probability)}</span> '
            f"over {result.pbo.splits:,} splits of history. Picking the best of the {len(result.grid_labels)} configurations "
            f"in one half lands below the median in the other half this often. 50% would mean choosing is no better than chance. "
            f"The in-sample winner lost money out of sample in {_pct_plain(result.pbo.oos_loss_rate)} of splits.</dd>"
        )
    if not math.isnan(result.deflated):
        verdict = "clears" if result.deflated >= 0.95 else "does not clear"
        parts.append(
            f'<dt>Deflated Sharpe ratio</dt><dd><span class="num">{_pct_plain(result.deflated)}</span> probability that the '
            f"pre-registered portfolio's Sharpe beats the best of {len(result.grid_labels)} skill-less trials. It {verdict} the "
            f"usual 95% bar.</dd>"
        )
    if result.flagship_cagr is not None and result.flagship_sharpe is not None:
        c, s = result.flagship_cagr, result.flagship_sharpe
        parts.append(
            f"<dt>Bootstrap, 90% interval</dt><dd>CAGR {_pct(c.low)} to {_pct(c.high)}; Sharpe {_num(s.low)} to {_num(s.high)}. "
            "Resampling blocks of days shows how much the headline depends on this exact history.</dd>"
        )
    if result.weekday_spread:
        lo, hi = min(result.weekday_spread), max(result.weekday_spread)
        flag = result.summaries[FLAG].final_value
        parts.append(
            f"<dt>Weekday lottery</dt><dd>Without tranches, the same portfolio ends between {_money(lo)} and {_money(hi)} "
            f"depending on the decision weekday. With {TRANCHES} tranches it ends at {_money(flag)}.</dd>"
        )
    walk = ""
    if result.walk is not None and result.walk.steps:
        rows = "".join(
            f"<tr><td>{st.year}</td><td>{html.escape(st.chosen)}</td><td>{_num(st.train_sharpe * math.sqrt(365))}</td><td>{_pct(st.test_return)}</td></tr>"
            for st in result.walk.steps
        )
        stitched = float(np.prod(1 + result.walk.returns))
        years = len(result.walk.returns) / 365
        cagr = stitched ** (1 / years) - 1 if years > 0 and stitched > 0 else float("nan")
        walk = f"""
  <h3>Walk-forward: choosing each year with only the past</h3>
  <p class="col">Each January, the configuration with the best Sharpe so far is adopted for the year. Stitched together, these
  out-of-sample years compound at {_pct(cagr)} a year, using {result.walk.distinct_choices} different configurations.</p>
  <div class="table-wrap"><table class="data"><thead><tr><th>Year</th><th>Chosen on the past</th><th>Its past Sharpe</th><th>Return that year</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    return f"""
<section aria-labelledby="luck">
  <div class="section-head"><div class="eyebrow">Skill or luck</div><h2 id="luck">The tests a single backtest cannot pass</h2></div>
  <dl class="facts col">{"".join(parts)}</dl>{walk}
</section>"""


def _capacity_section(result: StudyResult) -> str:
    if not result.capacity:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{_pct(s.cagr)}</td><td>{_num(s.sharpe)}</td><td>{_pct_plain(s.cost_drag, 1)}</td></tr>"
        for k, s in result.capacity.items()
    )
    return f"""
<section aria-labelledby="capacity">
  <div class="section-head"><div class="eyebrow">Capacity</div><h2 id="capacity">What changes with a bigger account</h2></div>
  <p class="col">Orders move the price more when they are large relative to a coin's daily volume. The engine charges that as a
  square-root impact on top of fees, which is what limits how much money a strategy can run.</p>
  <div class="table-wrap"><table class="data"><thead><tr><th>Starting capital (USDT)</th><th>CAGR</th><th>Sharpe</th><th>Cost drag / yr</th></tr></thead><tbody>{rows}</tbody></table></div>
</section>"""


def _universe_section(result: StudyResult) -> str:
    if not result.universe_samples:
        return ""
    rows = "".join(
        f'<tr><td>{html.escape(d)}</td><td class="coins">{html.escape(", ".join(coins))}</td></tr>'
        for d, coins in result.universe_samples.items()
    )
    return f"""
<section aria-labelledby="universe">
  <div class="section-head"><div class="eyebrow">Reference data</div><h2 id="universe">The universe on a few dates</h2></div>
  <p class="col">The {FLAGSHIP_UNIVERSE.top_n} most liquid Binance USDT pairs of each day (median daily volume over {FLAGSHIP_UNIVERSE.window}
  days, at least {FLAGSHIP_UNIVERSE.min_history} days listed, no stablecoins, wrapped or leveraged tokens). Coins that later collapsed
  appear while they were liquid, as they did in front of a real investor.</p>
  <div class="table-wrap"><table class="data"><thead><tr><th>Date</th><th>Members</th></tr></thead><tbody>{rows}</tbody></table></div>
</section>"""


def render(result: StudyResult, *, title: str = "Crypto Momentum Study") -> str:
    flag = result.summaries[FLAG]
    btc = result.summaries["Hold BTC"]
    main_keys = [*CHART_KEYS, "Momentum portfolio, Spanish tax paid yearly"]
    holdout = _summary_rows(result.holdout, list(result.holdout)) if result.holdout else ""
    chart = json.dumps(_line_chart_data(result))
    config = (
        f"Trend horizons {'/'.join(str(x) for x in FLAGSHIP.lookbacks)} days, top {FLAGSHIP.top_k} of the "
        f"{FLAGSHIP_UNIVERSE.top_n} most liquid coins, inverse-volatility weights capped at {FLAGSHIP.max_weight:.0%}, "
        f"volatility target {FLAGSHIP.vol_target:.0%}, decided every {REBALANCE_EVERY} days in {TRANCHES} staggered tranches."
    )
    lead = (
        f"From {_money(CAPITAL)} USDT on {result.start}, the pre-registered portfolio ends at {_money(flag.final_value)} "
        f"({_pct(flag.cagr)} a year, Sharpe {_num(flag.sharpe)}, worst fall {_pct(flag.max_drawdown)}). Holding Bitcoin ends at "
        f"{_money(btc.final_value)} ({_pct(btc.cagr)} a year, Sharpe {_num(btc.sharpe)}, worst fall {_pct(btc.max_drawdown)})."
    )
    return _PAGE.format(
        title=html.escape(title),
        start=html.escape(result.start),
        end=html.escape(result.end),
        lead=html.escape(lead),
        config=html.escape(config),
        summary=_summary_rows(result.summaries, main_keys),
        yearly=_yearly_table(result),
        holdout=holdout,
        grid=_grid_section(result),
        luck=_luck_section(result),
        capacity=_capacity_section(result),
        universe=_universe_section(result),
        chart=chart,
        light=json.dumps(SERIES_LIGHT),
        dark=json.dumps(SERIES_DARK),
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )


_PAGE = """<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Layout: a single reading column; charts and tables use the full width of the page. */
:root {{
  --paper: #f6f7f9; --surface: #fcfcfd; --ink: #12161d; --ink-2: #434b58; --muted: #737c8b;
  --rule: #dce0e6; --grid: #e6e9ee; --accent: #0d6a64;
  --d0: #eceef1; --p1: #cfe2fa; --p2: #8ab8ef; --p3: #2f74c8; --p4: #1c5cab;
  --n1: #f8d4d3; --n2: #ef9a99; --n3: #c94342; --n4: #a8302f; --fg-lo: #12161d; --fg-hi: #ffffff;
  --sans: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --paper: #0f1216; --surface: #151a20; --ink: #e9edf2; --ink-2: #b4bcc8; --muted: #828c9b; --rule: #29313b; --grid: #222932; --accent: #52c3b9;
  --d0: #2f343b; --p1: #1c4a80; --p2: #2a6cc0; --p3: #5a9be8; --p4: #9cc5f2; --n1: #6b2524; --n2: #a83a39; --n3: #e06866; --n4: #f2a5a4;
  --fg-lo: #e9edf2; --fg-hi: #0f1216; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --paper: #0f1216; --surface: #151a20; --ink: #e9edf2; --ink-2: #b4bcc8; --muted: #828c9b; --rule: #29313b; --grid: #222932; --accent: #52c3b9;
  --d0: #2f343b; --p1: #1c4a80; --p2: #2a6cc0; --p3: #5a9be8; --p4: #9cc5f2; --n1: #6b2524; --n2: #a83a39; --n3: #e06866; --n4: #f2a5a4;
  --fg-lo: #e9edf2; --fg-hi: #0f1216; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 15.5px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 36px 60px; margin: 0; }}
.page {{ max-width: 1040px; margin: 0 auto; display: grid; gap: 48px; }}
.col {{ max-width: 70ch; }}
h1, h2, h3 {{ margin: 0; line-height: 1.12; text-wrap: balance; }}
h1 {{ font-size: clamp(2rem, 6vw, 3rem); letter-spacing: -0.01em; }}
h2 {{ font-size: clamp(1.35rem, 3vw, 1.75rem); }}
h3 {{ font-size: 1.1rem; margin-top: 8px; }}
p {{ margin: 0; }}
.eyebrow {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }}
header {{ display: grid; gap: 14px; padding-bottom: 28px; border-bottom: 1px solid var(--rule); }}
.lede {{ font-size: 1.08rem; color: var(--ink-2); }}
.meta {{ font-family: var(--mono); font-size: 12.5px; color: var(--muted); }}
section {{ display: grid; gap: 16px; }}
.section-head {{ display: grid; gap: 6px; }}
.table-wrap {{ overflow-x: auto; border: 1px solid var(--rule); border-radius: 6px; background: var(--surface); }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }}
table.data th, table.data td {{ padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
table.data th:first-child, table.data td:first-child {{ text-align: left; white-space: normal; min-width: 150px; }}
table.data thead th {{ font-weight: 500; color: var(--muted); font-size: 12px; vertical-align: bottom; }}
table.data tbody tr:last-child td {{ border-bottom: 0; }}
table.data td.coins {{ white-space: normal; text-align: left; }}
.heat td.d0 {{ background: var(--d0); }} .heat td.p1 {{ background: var(--p1); color: var(--fg-lo); }} .heat td.p2 {{ background: var(--p2); color: var(--fg-lo); }}
.heat td.p3 {{ background: var(--p3); color: var(--fg-hi); }} .heat td.p4 {{ background: var(--p4); color: var(--fg-hi); }}
.heat td.n1 {{ background: var(--n1); color: var(--fg-lo); }} .heat td.n2 {{ background: var(--n2); color: var(--fg-lo); }}
.heat td.n3 {{ background: var(--n3); color: var(--fg-hi); }} .heat td.n4 {{ background: var(--n4); color: var(--fg-hi); }}
.caption {{ font-size: 13px; color: var(--muted); }}
figure {{ margin: 0; display: grid; gap: 10px; }}
.fig-title {{ font-weight: 600; }} .fig-sub {{ color: var(--ink-2); font-size: 14px; }}
.fig-body {{ position: relative; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 14px; }}
.chart svg {{ display: block; width: 100%; height: auto; overflow: visible; }}
.chart text {{ font-family: var(--sans); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2); margin-bottom: 8px; }}
.legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend i {{ width: 16px; height: 2px; display: inline-block; border-radius: 1px; }}
.tt {{ position: absolute; pointer-events: none; z-index: 5; min-width: 190px; background: var(--surface); color: var(--ink);
  border: 1px solid var(--rule); border-radius: 6px; box-shadow: 0 6px 20px rgba(0,0,0,.14); padding: 9px 11px; font-size: 12.5px; display: grid; gap: 3px; }}
.tt .row {{ display: flex; justify-content: space-between; gap: 14px; font-variant-numeric: tabular-nums; }}
.tt .row b {{ font-weight: 600; }} .tt .k {{ display: inline-flex; align-items: center; gap: 6px; color: var(--ink-2); }}
.tt .k i {{ width: 12px; height: 2px; display: inline-block; }}
.tt .date {{ color: var(--muted); font-size: 12px; }}
dl.facts {{ margin: 0; display: grid; grid-template-columns: 13rem minmax(0, 1fr); border-top: 1px solid var(--rule); }}
dl.facts dt, dl.facts dd {{ margin: 0; padding: 11px 0; border-bottom: 1px solid var(--rule); }}
dl.facts dt {{ font-weight: 600; padding-right: 16px; }} dl.facts dd {{ color: var(--ink-2); min-width: 0; }}
dl.facts .num {{ color: var(--ink); font-weight: 600; }}
@media (max-width: 620px) {{ dl.facts {{ grid-template-columns: minmax(0, 1fr); }} dl.facts dt {{ border-bottom: 0; padding-bottom: 0; }} }}
details summary {{ cursor: pointer; color: var(--accent); font-size: 14px; width: fit-content; }}
details .table-wrap {{ margin-top: 10px; }}
footer {{ border-top: 1px solid var(--rule); padding-top: 18px; font-size: 12.5px; color: var(--muted); }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
</style>
<div class="page">
<header>
  <div class="eyebrow">INVEST LL research · {start} to {end}</div>
  <h1>{title}</h1>
  <p class="lede col">{lead}</p>
  <p class="meta">Pre-registered configuration: {config}</p>
</header>

<section aria-labelledby="growth">
  <div class="section-head"><div class="eyebrow">Results</div><h2 id="growth">Growth of 10,000 USDT</h2></div>
  <figure>
    <div class="fig-head"><div class="fig-title">Account value, log scale, after fees and slippage</div>
    <div class="fig-sub">Hover or tap the chart for the values on a given week.</div></div>
    <div class="fig-body"><div class="legend" id="legend"></div><div id="growth-chart" class="chart"></div><div class="tt" id="tt-growth" hidden></div></div>
  </figure>
  <figure>
    <div class="fig-head"><div class="fig-title">Fall from the previous peak</div>
    <div class="fig-sub">Momentum portfolio against holding Bitcoin.</div></div>
    <div class="fig-body"><div id="dd-chart" class="chart"></div></div>
  </figure>
  {summary}
  <p class="caption">Sharpe and volatility are annualised over 365 days. "After liquidation tax" sells everything on the last day
  and pays Spanish savings tax on gains not yet taxed; the row "Momentum, after tax" also paid tax every July along the way.</p>
</section>

<section aria-labelledby="years">
  <div class="section-head"><div class="eyebrow">By year</div><h2 id="years">Calendar-year returns</h2></div>
  {yearly}
</section>

<section aria-labelledby="holdout">
  <div class="section-head"><div class="eyebrow">Reserved data</div><h2 id="holdout">From 1 January 2025 only</h2></div>
  <p class="col">INVEST LL reserves everything from 2025 onward for validation. These rows measure only that stretch.</p>
  {holdout}
</section>
{grid}
{luck}
{capacity}
{universe}
<footer>Generated by invest-ll-quant on {generated}. Binance spot daily data; costs 0.1% commission and 0.05% slippage per side plus
square-root market impact. Past results say nothing certain about the future. Not investment advice.</footer>
</div>
<script type="application/json" id="chart-data">{chart}</script>
<script>
(function () {{
  var LIGHT = {light}, DARK = {dark};
  var data = JSON.parse(document.getElementById("chart-data").textContent);
  var NS = "http://www.w3.org/2000/svg";
  function isDark() {{
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }}
  function palette() {{ return isDark() ? DARK : LIGHT; }}
  function css(name) {{ return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }}
  function el(name, attrs, text) {{ var e = document.createElementNS(NS, name); for (var k in attrs) e.setAttribute(k, attrs[k]); if (text !== undefined) e.textContent = text; return e; }}
  function fmt(v) {{ return Math.round(v).toLocaleString("en-GB"); }}
  function pct(v) {{ return (v * 100).toFixed(0) + "%"; }}

  function legend() {{
    var box = document.getElementById("legend"); box.textContent = "";
    data.series.forEach(function (s, i) {{
      var span = document.createElement("span"); var key = document.createElement("i");
      key.style.background = palette()[i]; span.appendChild(key); span.appendChild(document.createTextNode(s.name)); box.appendChild(span);
    }});
  }}

  function lineChart(hostId, series, opts) {{
    var host = document.getElementById(hostId); var W = Math.max(320, host.clientWidth);
    var H = opts.height, m = {{ l: 54, r: opts.endLabels ? 118 : 16, t: 10, b: 26 }};
    if (W < 560) m.r = 16;
    var pw = W - m.l - m.r, ph = H - m.t - m.b, n = data.dates.length;
    var all = [].concat.apply([], series.map(function (s) {{ return s.values; }}));
    var lo = opts.log ? Math.log10(Math.min.apply(null, all)) : Math.min(0, Math.min.apply(null, all));
    var hi = opts.log ? Math.log10(Math.max.apply(null, all)) : 0;
    if (opts.log) {{ lo = Math.floor(lo); hi = Math.ceil(hi); }}
    var x = function (i) {{ return m.l + i / (n - 1) * pw; }};
    var y = function (v) {{ var t = opts.log ? Math.log10(Math.max(v, 1e-9)) : v; return m.t + (hi - t) / (hi - lo) * ph; }};
    var svg = el("svg", {{ viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": opts.label }});
    var grid = css("--grid"), muted = css("--muted"), ink2 = css("--ink-2");
    var ticks = [];
    if (opts.log) {{ for (var p = lo; p <= hi; p++) ticks.push(Math.pow(10, p)); }} else {{ for (var q = 0; q >= lo - 1e-9; q -= 0.25) ticks.push(q); }}
    ticks.forEach(function (v) {{
      svg.appendChild(el("line", {{ x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: grid, "stroke-width": 1 }}));
      svg.appendChild(el("text", {{ x: m.l - 8, y: y(v) + 4, "text-anchor": "end", fill: muted, "font-size": 11 }}, opts.log ? (v >= 1e6 ? (v / 1e6) + "M" : v >= 1e3 ? (v / 1e3) + "k" : v) : pct(v)));
    }});
    var lastYear = null;
    data.dates.forEach(function (d, i) {{
      var yr = d.slice(0, 4);
      if (yr !== lastYear && d.slice(5, 7) === "01") {{
        svg.appendChild(el("text", {{ x: x(i), y: H - 6, "text-anchor": "middle", fill: muted, "font-size": 11 }}, yr));
        lastYear = yr;
      }}
    }});
    series.forEach(function (s, si) {{
      var dpath = s.values.map(function (v, i) {{ return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1); }}).join(" ");
      svg.appendChild(el("path", {{ d: dpath, fill: "none", stroke: palette()[si], "stroke-width": si === 0 ? 2.5 : 1.75, "stroke-linejoin": "round", "stroke-linecap": "round", opacity: si === 0 ? 1 : 0.9 }}));
    }});
    if (opts.endLabels && W >= 560) {{
      var ends = series.map(function (s, si) {{ return {{ y: y(s.values[s.values.length - 1]), name: s.name, si: si }}; }}).sort(function (a, b) {{ return a.y - b.y; }});
      for (var k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 14) ends[k].y = ends[k - 1].y + 14;
      ends.forEach(function (e) {{
        svg.appendChild(el("circle", {{ cx: W - m.r + 6, cy: e.y, r: 3, fill: palette()[e.si] }}));
        svg.appendChild(el("text", {{ x: W - m.r + 13, y: e.y + 4, fill: ink2, "font-size": 11.5 }}, e.name));
      }});
    }}
    var cross = el("line", {{ x1: 0, x2: 0, y1: m.t, y2: m.t + ph, stroke: muted, "stroke-width": 1, visibility: "hidden" }});
    svg.appendChild(cross);
    var hit = el("rect", {{ x: m.l, y: m.t, width: pw, height: ph, fill: "transparent", tabindex: "0", "aria-label": opts.label + ". Use arrow keys to move." }});
    svg.appendChild(hit);
    host.textContent = ""; host.appendChild(svg);
    if (!opts.tooltip) return;
    var tt = document.getElementById(opts.tooltip); var idx = n - 1;
    function show(i, px, py) {{
      idx = Math.max(0, Math.min(n - 1, i)); cross.setAttribute("x1", x(idx)); cross.setAttribute("x2", x(idx)); cross.setAttribute("visibility", "visible");
      tt.textContent = ""; var dd = document.createElement("div"); dd.className = "date"; dd.textContent = data.dates[idx]; tt.appendChild(dd);
      series.map(function (s, si) {{ return {{ s: s, si: si }}; }}).sort(function (a, b) {{ return b.s.values[idx] - a.s.values[idx]; }}).forEach(function (o) {{
        var row = document.createElement("div"); row.className = "row"; var k = document.createElement("span"); k.className = "k";
        var i2 = document.createElement("i"); i2.style.background = palette()[o.si]; k.appendChild(i2); k.appendChild(document.createTextNode(o.s.name));
        var b = document.createElement("b"); b.textContent = opts.log ? fmt(o.s.values[idx]) : pct(o.s.values[idx]); row.appendChild(k); row.appendChild(b); tt.appendChild(row);
      }});
      tt.hidden = false; var hw = host.parentNode.clientWidth; var left = Math.min(Math.max(8, px + 16), hw - tt.offsetWidth - 8); tt.style.left = left + "px"; tt.style.top = Math.max(4, py - 20) + "px";
    }}
    hit.addEventListener("pointermove", function (e) {{ var r = svg.getBoundingClientRect(); var sx = (e.clientX - r.left) * W / r.width; show(Math.round((sx - m.l) / pw * (n - 1)), e.clientX - host.parentNode.getBoundingClientRect().left, e.clientY - host.parentNode.getBoundingClientRect().top); }});
    hit.addEventListener("pointerleave", function () {{ tt.hidden = true; cross.setAttribute("visibility", "hidden"); }});
    hit.addEventListener("focus", function () {{ show(idx, x(idx), 30); }});
    hit.addEventListener("blur", function () {{ tt.hidden = true; cross.setAttribute("visibility", "hidden"); }});
    hit.addEventListener("keydown", function (e) {{ if (e.key === "ArrowLeft") {{ show(idx - 1, x(idx - 1), 30); e.preventDefault(); }} if (e.key === "ArrowRight") {{ show(idx + 1, x(idx + 1), 30); e.preventDefault(); }} }});
  }}

  function strip() {{
    var node = document.getElementById("strip-data"); if (!node) return;
    var d = JSON.parse(node.textContent); var host = document.getElementById("strip"); var W = Math.max(320, host.clientWidth), H = 120;
    var m = {{ l: 16, r: 16, t: 30, b: 26 }}; var vals = d.sharpes.concat([d.flag, d.btc]);
    var lo = Math.floor(Math.min.apply(null, vals) * 4) / 4, hi = Math.ceil(Math.max.apply(null, vals) * 4) / 4;
    var x = function (v) {{ return m.l + (v - lo) / (hi - lo) * (W - m.l - m.r); }};
    var svg = el("svg", {{ viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Sharpe ratio of each configuration" }});
    var muted = css("--muted"), grid = css("--grid"), ink2 = css("--ink-2"), surface = css("--surface");
    for (var t = lo; t <= hi + 1e-9; t += 0.25) {{
      svg.appendChild(el("line", {{ x1: x(t), x2: x(t), y1: m.t - 6, y2: H - m.b, stroke: grid }}));
      svg.appendChild(el("text", {{ x: x(t), y: H - 8, "text-anchor": "middle", fill: muted, "font-size": 11 }}, t.toFixed(2)));
    }}
    [[d.btc, "Hold BTC", "end"], [d.flag, "Pre-registered", "start"]].forEach(function (r) {{
      svg.appendChild(el("line", {{ x1: x(r[0]), x2: x(r[0]), y1: 12, y2: H - m.b, stroke: ink2, "stroke-width": 1 }}));
      svg.appendChild(el("text", {{ x: x(r[0]) + (r[2] === "start" ? 5 : -5), y: 20, "text-anchor": r[2], fill: ink2, "font-size": 11.5 }}, r[1] + " " + r[0].toFixed(2)));
    }});
    var tt = document.getElementById("tt-strip");
    d.sharpes.forEach(function (v, i) {{
      var jitter = ((i * 37) % 11 - 5) * 4; var cy = (m.t + H - m.b) / 2 + jitter;
      var c = el("circle", {{ cx: x(v), cy: cy, r: 4.5, fill: palette()[0], stroke: surface, "stroke-width": 2, tabindex: "0" }});
      function show() {{ tt.textContent = ""; var a = document.createElement("div"); a.className = "row"; var b = document.createElement("b"); b.textContent = "Sharpe " + v.toFixed(2); a.appendChild(b); tt.appendChild(a); var l = document.createElement("div"); l.className = "date"; l.textContent = d.labels[i]; tt.appendChild(l); tt.hidden = false; var hw = host.parentNode.clientWidth; tt.style.left = Math.min(Math.max(8, x(v) * host.clientWidth / W + 12), hw - tt.offsetWidth - 8) + "px"; tt.style.top = "8px"; }}
      c.addEventListener("pointerenter", show); c.addEventListener("focus", show);
      c.addEventListener("pointerleave", function () {{ tt.hidden = true; }}); c.addEventListener("blur", function () {{ tt.hidden = true; }});
      svg.appendChild(c);
    }});
    host.textContent = ""; host.appendChild(svg);
  }}

  function draw() {{
    legend();
    lineChart("growth-chart", data.series, {{ height: 360, log: true, endLabels: true, tooltip: "tt-growth", label: "Growth of 10,000 USDT, log scale" }});
    lineChart("dd-chart", data.drawdown, {{ height: 200, log: false, endLabels: false, label: "Drawdown from peak" }});
    strip();
  }}
  draw();
  var last = 0; window.addEventListener("resize", function () {{ var w = document.getElementById("growth-chart").clientWidth; if (Math.abs(w - last) > 4) {{ last = w; draw(); }} }});
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
  new MutationObserver(draw).observe(document.documentElement, {{ attributes: true, attributeFilter: ["data-theme"] }});
}})();
</script>
"""
