"""`invest-ll-compare`: pone al LLM y a las reglas fijas uno al lado del otro.

Es el comando que responde a la pregunta que motiva la feature. Por eso su salida está diseñada
para que **no se pueda saber cuál es el LLM mirando el formato**: las mismas métricas, el mismo
orden, las mismas advertencias. Si el informe del LLM tuviera un formato propio, "el LLM elige
mejor" dejaría de ser una afirmación comprobable.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter
from invest_ll.data.loader import load_series
from invest_ll.data.universe import build_universe
from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.cost import estimate_cost
from invest_ll.decision.provider import RecordedProvider
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.rotation import run_rotation
from invest_ll.errors import InvestLLError
from invest_ll.strategy.llm import CADA_MES, LLMStrategy
from invest_ll.strategy.rotation import RelativeMomentum

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.data.series import PriceSeries
    from invest_ll.report.report import BacktestReport

D = Decimal

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_NO_ENCONTRADO = 2
SALIDA_NO_CONCLUYENTE = 3
SALIDA_CANCELADO = 4

ADVERTENCIA_CONTAMINACION = """\
[!] Sobre el resultado del LLM: el modelo fue entrenado con datos que incluyen lo que paso
    despues del periodo simulado. Eso no se puede eliminar, solo acotar -- aqui se le ocultan
    fechas y nombres, pero un modelo que reconozca un patron sabe en que epoca esta.
    Un buen resultado del LLM sobre el pasado NO es evidencia de que funcione hacia adelante.
    La unica prueba limpia es registrar lo que estima y comparar con lo que pase despues.
"""


def _calendario(ruta: Path):  # type: ignore[no-untyped-def]
    return Continuous24x7() if "ccxt" in ruta.parts else ExchangeCalendarAdapter("XNYS")


def cargar_series(rutas: Sequence[Path], interval: Interval) -> list[PriceSeries]:
    series: list[PriceSeries] = []
    for ruta in rutas:
        if not ruta.exists():
            raise FileNotFoundError(f"no existe {ruta}")
        serie, _ = load_series(
            ruta,
            symbol=ruta.parent.name,
            interval=interval,
            calendar=_calendario(ruta),
        )
        series.append(serie)
    return series


def _fila(nombre: str, informe: BacktestReport) -> str:
    exceso = informe.excess_return if informe.buy_and_hold is not None else D(0)
    return (
        f"{nombre:<22}{informe.net_result:>14,.0f}{informe.max_drawdown:>14,.0f}"
        f"{informe.trade_count:>7}{informe.total_costs:>12,.0f}{exceso:>20,.0f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-compare",
        description="Compara estrategias sobre el mismo universo con las mismas metricas.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV de cada activo")
    parser.add_argument(
        "--strategies",
        default="llm,momentum",
        help="Separadas por comas: llm, momentum. Comprar y mantener sale siempre.",
    )
    parser.add_argument("--interval", default="DAY_1")
    parser.add_argument("--capital", type=D, default=D(10000))
    parser.add_argument("--commission", type=D, required=True)
    parser.add_argument("--slippage", type=D, required=True)
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument(
        "--every",
        type=int,
        default=CADA_MES,
        help=f"Periodos entre decisiones del LLM (por defecto {CADA_MES}, ~un mes).",
    )
    parser.add_argument(
        "--recorded",
        type=Path,
        help="Carpeta de decisiones grabadas. Sin ella, el LLM no se puede evaluar sin red.",
    )
    parser.add_argument("--model", default="claude-opus-5")

    args = parser.parse_args(argv)
    nombres = [n.strip() for n in args.strategies.split(",") if n.strip()]

    try:
        universo = build_universe(cargar_series(args.paths, Interval[args.interval]))
    except FileNotFoundError as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_NO_ENCONTRADO
    except (InvestLLError, KeyError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_ERROR

    friccion = FrictionConfig(commission_rate=args.commission, slippage_rate=args.slippage)
    riesgo = RiskConfig(position_fraction=D(1))

    informes: dict[str, BacktestReport] = {}
    llm_incluido = False

    for nombre in nombres:
        if nombre == "momentum":
            informes["momentum"] = run_rotation(
                universo,
                RelativeMomentum(lookback=args.lookback),
                initial_capital=args.capital,
                friction=friccion,
                risk=riesgo,
            )
        elif nombre == "llm":
            if args.recorded is None:
                print(
                    "Error: evaluar el LLM necesita --recorded con decisiones ya generadas.\n"
                    "       El motor no toca la red por diseno.",
                    file=sys.stderr,
                )
                return SALIDA_ERROR

            almacen = DecisionStore(args.recorded)
            estimacion = estimate_cost(
                total_decisions=len(universo) // max(1, args.every),
                cached_decisions=almacen.count(),
            )
            print(estimacion.render())
            print()

            try:
                informes["llm"] = run_rotation(
                    universo,
                    LLMStrategy(
                        RecordedProvider(almacen, model=args.model), every_periods=args.every
                    ),
                    initial_capital=args.capital,
                    friction=friccion,
                    risk=riesgo,
                )
            except InvestLLError as error:
                print(f"Error evaluando el LLM: {error}", file=sys.stderr)
                return SALIDA_ERROR
            llm_incluido = True
        else:
            print(f"Error: estrategia desconocida {nombre!r}", file=sys.stderr)
            return SALIDA_ERROR

    if not informes:
        print("Error: no se indico ninguna estrategia", file=sys.stderr)
        return SALIDA_ERROR

    referencia = next(iter(informes.values()))
    print(f"Universo: {len(universo)} periodos, {len(universo.symbols)} activos")
    print("=" * 84)
    print(
        f"{'estrategia':<22}{'RESULTADO':>14}{'DRAWDOWN':>14}"
        f"{'ops':>7}{'COSTES':>12}{'vs NO HACER NADA':>20}"
    )
    print("-" * 84)

    for nombre, informe in informes.items():
        print(_fila(nombre, informe))

    if referencia.buy_and_hold is not None:
        bh = referencia.buy_and_hold
        # BuyAndHold no lleva trade_count: por definicion es una entrada y ninguna decision mas.
        print(
            f"{'comprar y mantener':<22}{bh.net_result:>14,.0f}"
            f"{bh.max_drawdown:>14,.0f}{1:>7}{bh.costs:>12,.0f}{'referencia':>20}"
        )

    print("-" * 84)

    ganadoras = [n for n, i in informes.items() if i.beats_market]
    if ganadoras:
        print(f"  Baten a comprar y mantener: {', '.join(ganadoras)}")
        print("  Eso no garantiza nada de cara al futuro. Ver la validacion fuera de muestra.")
    else:
        print("  [!] Ninguna bate a comprar y mantener.")
        print("      Todo el riesgo asumido y las comisiones pagadas quedaron por debajo")
        print("      de no hacer nada.")

    print()
    print("  El win rate no aparece aqui a proposito: no es criterio de exito.")

    if llm_incluido:
        print()
        print(ADVERTENCIA_CONTAMINACION)

    # El veredicto mira TODAS las estrategias, no solo la primera: si una de ellas opero tan
    # poco que su resultado no significa nada, la comparacion tampoco lo hace.
    dudosas = {n: i.inconclusive_reason for n, i in informes.items() if not i.conclusive}
    if dudosas:
        print()
        for nombre, motivo in dudosas.items():
            print(f"NO CONCLUYENTE ({nombre}): {motivo}")
        return SALIDA_NO_CONCLUYENTE

    return SALIDA_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
