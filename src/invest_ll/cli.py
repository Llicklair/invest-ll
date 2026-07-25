"""Interfaz de línea de comandos para inspeccionar un backtest (T055).

Es una herramienta de inspección, no la vía de validación: lo que decide si el motor funciona son
los tests. Aquí se viene a mirar un resultado concreto sobre datos propios.

Los costes son argumentos **obligatorios**: igual que en la API, no se puede lanzar un backtest
sin declarar la fricción (Principio IV).
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter, MarketCalendar
from invest_ll.data.loader import load_series
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.errors import InvestLLError
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.protocol import Strategy

ESTRATEGIAS = ("ma-cross", "breakout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invest-ll",
        description="Evalua una estrategia sobre una serie historica. Solo simulacion.",
        epilog=(
            "Recordatorio: el win rate no es criterio de exito. Mira la expectancy y el "
            "drawdown antes de creerte un resultado."
        ),
    )
    parser.add_argument("serie", type=Path, help="fichero CSV o Parquet con la serie historica")
    parser.add_argument("--symbol", default="ACTIVO", help="nombre del activo")
    parser.add_argument(
        "--interval",
        default="DAY_1",
        choices=[i.name for i in Interval],
        help="intervalo temporal de las velas",
    )
    parser.add_argument(
        "--calendar",
        default="24x7",
        help="'24x7' para cripto, o el codigo de un mercado (por ejemplo XNYS) para bolsa",
    )
    parser.add_argument("--strategy", default="ma-cross", choices=ESTRATEGIAS)
    parser.add_argument("--short", type=int, default=10, help="periodos de la media corta")
    parser.add_argument("--long", type=int, default=30, help="periodos de la media larga")
    parser.add_argument("--lookback", type=int, default=20, help="periodos para la ruptura")
    parser.add_argument("--capital", default="10000", help="capital inicial simulado")
    parser.add_argument(
        "--commission", required=True, help="comision por operacion, p.ej. 0.001 para 0,1%%"
    )
    parser.add_argument("--slippage", required=True, help="slippage aplicado, p.ej. 0.0005")
    parser.add_argument(
        "--fraction", default="0.5", help="fraccion del capital por entrada, en (0, 1]"
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=30,
        help="operaciones minimas para considerar concluyente el resultado",
    )
    return parser


def _calendar(nombre: str) -> MarketCalendar:
    if nombre == "24x7":
        return Continuous24x7()
    return ExchangeCalendarAdapter(nombre)


def _strategy(args: argparse.Namespace) -> Strategy:
    if args.strategy == "breakout":
        return BreakoutHighs(lookback=args.lookback)
    return MovingAverageCrossover(short=args.short, long=args.long)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        serie, avisos = load_series(
            args.serie,
            symbol=args.symbol,
            interval=Interval[args.interval],
            calendar=_calendar(args.calendar),
        )
        report = run_backtest(
            serie,
            _strategy(args),
            initial_capital=Decimal(args.capital),
            friction=FrictionConfig(
                commission_rate=Decimal(args.commission),
                slippage_rate=Decimal(args.slippage),
            ),
            risk=RiskConfig(position_fraction=Decimal(args.fraction)),
            min_trades=args.min_trades,
            data_warnings=avisos,
        )
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (InvestLLError, ValueError, InvalidOperation) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(report.render())

    # Codigo de salida distinto cuando el resultado no concluye: permite encadenar la CLI en un
    # script sin tomar por bueno un resultado que no lo es.
    return 0 if report.conclusive else 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
