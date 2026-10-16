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
    from invest_ll.quant.panel import FloatArray, Panel

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_NO_ENCONTRADO = 2
SALIDA_NO_CONCLUYENTE = 3

DATA_ROOT = Path("data/market/binance-universe")
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
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    out: Path = args.out or RUNS_ROOT / f"{stamp}-crypto-study"
    out.mkdir(parents=True, exist_ok=True)
    report = out / "report.html"
    report.write_text(render(result), encoding="utf-8")

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


def _targets(args: argparse.Namespace) -> tuple[Panel, FloatArray, str]:
    from invest_ll.quant.paper import current_targets
    from invest_ll.quant.study import FLAGSHIP, FLAGSHIP_UNIVERSE, REBALANCE_EVERY, TRANCHES

    panel = _panel(args.root)
    weights = current_targets(
        panel,
        FLAGSHIP,
        FLAGSHIP_UNIVERSE,
        rebalance_every=REBALANCE_EVERY,
        tranches=TRANCHES,
    )
    return panel, weights, FLAGSHIP.name


def cmd_paper(args: argparse.Namespace, salida: Salida) -> int:
    from invest_ll.quant.metrics import summarise
    from invest_ll.quant.paper import read, record, replay

    salida.aviso(
        AVISO_SOLO_SIMULACION,
        "Paper portfolio: nothing here sends orders.",
        mostrar=False,
    )
    if args.action in {"record", "targets"}:
        panel, weights, name = _targets(args)
        last = panel.date_at(len(panel) - 1)
        stale = (datetime.now(UTC).date() - last).days
        if stale > 2:
            salida.aviso(
                AVISO_DATOS_VIEJOS,
                f"Data ends on {last} ({stale} days ago). Run `invest-ll-quant download` first.",
            )
        held = sorted(
            ((float(w), panel.symbols[i]) for i, w in enumerate(weights) if w > 1e-6),
            reverse=True,
        )
        cash = 1.0 - sum(w for w, _ in held)
        salida.dato(
            data_date=last,
            strategy=name,
            weights={sym: w for w, sym in held},
            cash=cash,
            amounts=None if not args.capital else {sym: w * args.capital for w, sym in held},
        )
        salida.linea(f"Targets after the close of {last} ({name}):")
        for w, sym in held:
            line = f"  {sym.removesuffix('USDT'):<10} {w:6.1%}"
            if args.capital:
                line += f"   {w * args.capital:12,.2f} USDT"
            salida.linea(line)
        tail = f"   {cash * args.capital:12,.2f} USDT" if args.capital else ""
        salida.linea(f"  {'cash':<10} {cash:6.1%}{tail}")
        salida.aviso(
            AVISO_NO_ES_PREVISION,
            "These are the rule's targets, not a forecast that they will rise.",
            mostrar=False,
        )
        if args.action == "record":
            try:
                entry = record(panel, weights, name, args.ledger)
            except ValueError as error:
                return salida.error(str(error), SALIDA_ERROR)
            salida.dato(recorded=entry.data_date, ledger=args.ledger)
            salida.linea(f"Recorded {entry.data_date} in {args.ledger}")
        return salida.cerrar(SALIDA_OK)

    records = read(args.ledger)
    if not records:
        salida.linea(f"No records in {args.ledger}. Start with `invest-ll-quant paper record`.")
        return salida.cerrar(SALIDA_NO_CONCLUYENTE)
    panel = _panel(args.root)
    result = replay(panel, records)
    if result is None or len(result.returns) < 1:
        salida.linea("Not enough data after the first record yet.")
        return salida.cerrar(SALIDA_NO_CONCLUYENTE)
    s = summarise(result)
    btc = panel.close[:, panel.column("BTCUSDT")]
    btc_value = float(10_000 * btc[-1] / btc[result.start])
    salida.dato(
        since=records[0].data_date, records=len(records), summary=_summary_dict(s), btc=btc_value
    )
    salida.linea(f"Forward test since {records[0].data_date} ({len(records)} records):")
    salida.linea(
        f"  value {s.final_value:,.0f} from 10,000   max drawdown {s.max_drawdown:.1%}"
        f"   trades {s.trades}"
    )
    salida.linea(f"  holding BTC over the same days: {btc_value:,.0f}")
    return salida.cerrar(SALIDA_OK)


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
    download.set_defaults(func=cmd_download)

    study = sub.add_parser("study", help="run the crypto study and write the report")
    add_json_flag(study, hereda=True)
    study.add_argument("--out", type=Path, default=None)
    study.set_defaults(func=cmd_study)

    paper = sub.add_parser("paper", help="forward test of the pre-registered portfolio")
    add_json_flag(paper, hereda=True)
    paper.add_argument("action", choices=["record", "status", "targets"])
    paper.add_argument("--ledger", type=Path, default=Path("paper/momentum.jsonl"))
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
