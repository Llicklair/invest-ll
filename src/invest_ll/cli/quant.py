"""`invest-ll-quant`: point-in-time crypto data, the portfolio study, and the forward test.

    invest-ll-quant download            # every Binance USDT pair, delisted ones included
    invest-ll-quant study               # backtest + luck tests -> research/runs/<date>/report.html
    invest-ll-quant paper record        # append today's target portfolio to paper/momentum.jsonl
    invest-ll-quant paper status        # how the recorded portfolio has done since the first record
    invest-ll-quant paper targets --capital 2500   # what to hold now, in USDT

Every subcommand accepts `--json`. Nothing here sends orders: `paper targets` prints amounts and
executing them stays with you.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.emit import (
    AVISO_NO_ES_PREVISION,
    AVISO_SIN_VENTAJA,
    AVISO_SOBREAJUSTE,
    AVISO_SOLO_SIMULACION,
    Salida,
    add_json_flag,
    salida_de,
)

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.quant.metrics import Summary
    from invest_ll.quant.panel import Panel

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_NO_ENCONTRADO = 2
SALIDA_NO_CONCLUYENTE = 3

DATA_ROOT = Path("data/market/binance-universe")
ETF_ROOT = Path("data/market/etf-universe")
RESULTS_FILE = "results.pkl"
RUNS_ROOT = Path("research/runs")
AVISO_DATOS_VIEJOS = "stale_data"


def _panel(root: Path) -> Panel:
    from invest_ll.quant.panel import load_binance_universe

    klines = root / "klines_1d.parquet"
    if not klines.exists():
        raise FileNotFoundError(f"no data at {klines}; run `invest-ll-quant download` first")
    return load_binance_universe(root)


def _summary_dict(s: Summary) -> dict[str, object]:
    return {k: (float(v) if isinstance(v, float) else v) for k, v in s.as_dict().items()}


def cmd_download(args: argparse.Namespace, salida: Salida) -> int:
    from invest_ll.fetch.binance_universe import default_client, download

    if args.etf:
        from invest_ll.fetch import etf_universe

        path = etf_universe.download(ETF_ROOT)
        salida.dato(path=path)
        salida.linea(f"Saved {path}")
        return salida.cerrar(SALIDA_OK)

    def progress(n: int, total: int, symbol: str) -> None:
        if n % 50 == 0 or n == total:
            salida.linea(f"  {n}/{total} pairs ({symbol})")

    path = download(default_client(), args.root, progress=progress)
    salida.dato(path=path)
    salida.linea(f"Saved {path}")
    return salida.cerrar(SALIDA_OK)


def cmd_study(args: argparse.Namespace, salida: Salida) -> int:
    from invest_ll.quant.study import FLAG_KEY, run_study
    from invest_ll.quant.tearsheet import render

    panel = _panel(args.root)
    salida.linea(
        f"Panel: {len(panel.symbols)} instruments, "
        f"{panel.date_at(0)} to {panel.date_at(len(panel) - 1)}"
    )
    result = run_study(panel, progress=lambda m: salida.linea(f"  {m}"))
    etf = None
    etf_file = ETF_ROOT / "etf_1d.parquet"
    if etf_file.exists():
        from invest_ll.quant.etf_study import load_etf_panel, run_etf_study

        salida.linea("  running the ETF study")
        etf = run_etf_study(load_etf_panel(str(etf_file)))
    else:
        salida.linea("  no ETF data (`invest-ll-quant download --etf`): equities section skipped")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    out: Path = args.out or RUNS_ROOT / f"{stamp}-crypto-study"
    out.mkdir(parents=True, exist_ok=True)
    # Results are kept so the report can be re-rendered without re-running (`quant render`).
    # Pickle is only ever read back from this tool's own output folder.
    (out / RESULTS_FILE).write_bytes(pickle.dumps((result, etf)))
    report = out / "report.html"
    report.write_text(render(result, etf=etf), encoding="utf-8")

    salida.dato(
        report=report,
        start=result.start,
        end=result.end,
        summaries={k: _summary_dict(v) for k, v in result.summaries.items()},
        holdout={k: _summary_dict(v) for k, v in result.holdout.items()},
        grid=[
            {"label": lab, **_summary_dict(s)}
            for lab, s in zip(result.grid_labels, result.grid_summaries, strict=True)
        ],
        pbo=None
        if result.pbo is None
        else {
            "probability": result.pbo.probability,
            "splits": result.pbo.splits,
            "oos_loss_rate": result.pbo.oos_loss_rate,
        },
        deflated_sharpe=result.deflated,
        weekday_spread=result.weekday_spread,
        walk_forward=[]
        if result.walk is None
        else [
            {"year": s.year, "chosen": s.chosen, "test_return": s.test_return}
            for s in result.walk.steps
        ],
        universe_samples=result.universe_samples,
        stage_two={k: _summary_dict(v) for k, v in result.stage_two.items()},
        stage_two_deflated=result.stage_two_deflated,
        trials=result.trials,
        equities=None if etf is None else {k: _summary_dict(v) for k, v in etf.summaries.items()},
    )
    flag = result.summaries[FLAG_KEY]
    btc = result.summaries["Hold BTC"]
    if flag.sharpe <= btc.sharpe:
        salida.aviso(
            AVISO_SIN_VENTAJA,
            f"The pre-registered portfolio's Sharpe ({flag.sharpe:.2f}) does not beat holding "
            f"BTC ({btc.sharpe:.2f}).",
        )
    if result.deflated == result.deflated and result.deflated < 0.95:
        salida.aviso(
            AVISO_SOBREAJUSTE,
            f"Deflated Sharpe {result.deflated:.0%}: after {len(result.grid_labels)} trials the "
            "result is compatible with luck.",
        )
    salida.linea(f"Report: {report}")
    return salida.cerrar(SALIDA_OK)


def cmd_render(args: argparse.Namespace, salida: Salida) -> int:
    from invest_ll.quant.tearsheet import render

    folder: Path = args.run
    results = folder / RESULTS_FILE
    if not results.exists():
        raise FileNotFoundError(f"no saved results at {results}; run `invest-ll-quant study` first")
    result, etf = pickle.loads(results.read_bytes())
    report = folder / "report.html"
    report.write_text(render(result, etf=etf), encoding="utf-8")
    salida.dato(report=report)
    salida.linea(f"Report: {report}")
    return salida.cerrar(SALIDA_OK)


def cmd_paper(args: argparse.Namespace, salida: Salida) -> int:
    from invest_ll.quant.metrics import summarise
    from invest_ll.quant.paper import current_targets, read, record, replay, variants
    from invest_ll.quant.study import FLAGSHIP_UNIVERSE, REBALANCE_EVERY, TRANCHES

    salida.aviso(
        AVISO_SOLO_SIMULACION, "Paper portfolio: nothing here sends orders.", mostrar=False
    )
    chosen = list(variants().values())
    if args.variant != "all":
        chosen = [v for v in chosen if v.key == args.variant]
    panel = _panel(args.root)
    last = panel.date_at(len(panel) - 1)
    stale = (datetime.now(UTC).date() - last).days
    if args.action in {"record", "targets"} and stale > 2:
        salida.aviso(
            AVISO_DATOS_VIEJOS,
            f"Data ends on {last} ({stale} days ago). Run `invest-ll-quant download` first.",
        )

    report: dict[str, object] = {}
    code = SALIDA_OK
    for variant in chosen:
        if args.action in {"record", "targets"}:
            weights = current_targets(
                panel,
                variant.strategy,
                FLAGSHIP_UNIVERSE,
                rebalance_every=REBALANCE_EVERY,
                tranches=TRANCHES,
            )
            held = sorted(
                ((float(w), panel.symbols[i]) for i, w in enumerate(weights) if w > 1e-6),
                reverse=True,
            )
            cash = 1.0 - sum(w for w, _ in held)
            entry: dict[str, object] = {
                "strategy": variant.strategy.name,
                "data_date": last,
                "weights": {sym: w for w, sym in held},
                "cash": cash,
            }
            if args.capital:
                entry["amounts"] = {sym: w * args.capital for w, sym in held}
            salida.linea(
                f"[{variant.key}] targets after the close of {last} ({variant.strategy.name}):"
            )
            for w, sym in held:
                line = f"  {sym.removesuffix('USDT'):<10} {w:6.1%}"
                if args.capital:
                    line += f"   {w * args.capital:12,.2f} USDT"
                salida.linea(line)
            tail = f"   {cash * args.capital:12,.2f} USDT" if args.capital else ""
            salida.linea(f"  {'cash':<10} {cash:6.1%}{tail}")
            if args.action == "record":
                try:
                    saved = record(panel, weights, variant.strategy.name, variant.ledger)
                except ValueError as error:
                    # Append-only: the existing record stands and is not rewritten.
                    salida.aviso("already_recorded", f"  {error}")
                else:
                    entry["recorded_in"] = variant.ledger
                    salida.linea(f"  recorded {saved.data_date} in {variant.ledger}")
            report[variant.key] = entry
            continue

        records = read(variant.ledger)
        if not records:
            salida.linea(f"[{variant.key}] no records in {variant.ledger} yet.")
            report[variant.key] = None
            code = SALIDA_NO_CONCLUYENTE
            continue
        result = replay(panel, records, no_trade_band=variant.no_trade_band)
        if result is None or len(result.returns) < 1:
            salida.linea(
                f"[{variant.key}] first record {records[0].data_date}: no days after it yet."
            )
            report[variant.key] = {"since": records[0].data_date, "records": len(records)}
            code = SALIDA_NO_CONCLUYENTE
            continue
        s = summarise(result)
        btc = panel.close[:, panel.column("BTCUSDT")]
        btc_value = float(10_000 * btc[-1] / btc[result.start])
        report[variant.key] = {
            "since": records[0].data_date,
            "records": len(records),
            "summary": _summary_dict(s),
            "btc": btc_value,
        }
        salida.linea(
            f"[{variant.key}] forward test since {records[0].data_date} ({len(records)} records):"
        )
        salida.linea(
            f"  value {s.final_value:,.0f} from 10,000   max drawdown {s.max_drawdown:.1%}"
            f"   trades {s.trades}   holding BTC: {btc_value:,.0f}"
        )

    if args.action in {"record", "targets"}:
        salida.aviso(
            AVISO_NO_ES_PREVISION,
            "These are the rule's targets, not a forecast that they will rise.",
            mostrar=False,
        )
    salida.dato(variants=report)
    return salida.cerrar(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invest-ll-quant",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_json_flag(parser)
    parser.add_argument(
        "--root", type=Path, default=DATA_ROOT, help="data folder (default: %(default)s)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    download = sub.add_parser("download", help="download or extend the Binance universe")
    add_json_flag(download, hereda=True)
    download.add_argument("--etf", action="store_true", help="download the ETF universe instead")
    download.set_defaults(func=cmd_download)

    study = sub.add_parser("study", help="run the crypto study and write the report")
    add_json_flag(study, hereda=True)
    study.add_argument("--out", type=Path, default=None)
    study.set_defaults(func=cmd_study)

    again = sub.add_parser("render", help="re-render a study's report from its saved results")
    add_json_flag(again, hereda=True)
    again.add_argument("run", type=Path, help="the study's output folder")
    again.set_defaults(func=cmd_render)

    paper = sub.add_parser("paper", help="forward test of the pre-registered portfolio")
    add_json_flag(paper, hereda=True)
    paper.add_argument("action", choices=["record", "status", "targets"])
    paper.add_argument(
        "--variant",
        choices=["all", "preregistered", "filtered"],
        default="all",
        help="which forward test (default: both)",
    )
    paper.add_argument(
        "--capital", type=float, default=None, help="show amounts in USDT for this account size"
    )
    paper.set_defaults(func=cmd_paper)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    salida = salida_de(args, f"quant {args.command}")
    try:
        return int(args.func(args, salida))
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
