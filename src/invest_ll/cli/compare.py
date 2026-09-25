"""`invest-ll-compare`: pone al LLM y a las reglas fijas uno al lado del otro.

Es el comando que responde a la pregunta que motiva la feature. Por eso su salida está diseñada
para que **no se pueda saber cuál es el LLM mirando el formato**: las mismas métricas, el mismo
orden, las mismas advertencias. Si el informe del LLM tuviera un formato propio, "el LLM elige
mejor" dejaría de ser una afirmación comprobable.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.emit import (
    AVISO_CONTAMINACION,
    AVISO_NO_CONCLUYENTE,
    AVISO_SIN_VENTAJA,
    AVISO_SOBREAJUSTE,
    AVISO_WIN_RATE,
    add_json_flag,
    salida_de,
)
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
from invest_ll.research.attempts import AttemptLog
from invest_ll.strategy.llm import ADVERTENCIA_CONTAMINACION, CADA_MES, LLMStrategy
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


def _estrategia_json(nombre: str, informe: BacktestReport) -> dict[str, object]:
    """Los mismos números de la tabla, sin el formato.

    Salen TODOS los campos para todas las estrategias, incluido `conclusive`: si el JSON omitiera
    el motivo por el que un resultado no significa nada, quien lo consuma leería solo la cifra.
    """
    return {
        "name": nombre,
        "net_result": informe.net_result,
        "max_drawdown": informe.max_drawdown,
        "trades": informe.trade_count,
        "costs": informe.total_costs,
        "excess_vs_holding": (informe.excess_return if informe.buy_and_hold is not None else None),
        "beats_holding": informe.beats_market,
        "conclusive": informe.conclusive,
        "inconclusive_reason": informe.inconclusive_reason,
    }


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
    parser.add_argument(
        "--stop-loss",
        type=D,
        help=(
            "Salir si la posicion cae esta fraccion desde la entrada (0.10 = 10%%). "
            "Sin esto no hay ninguna salida por perdida: se aguanta hasta la siguiente decision."
        ),
    )
    add_json_flag(parser)

    args = parser.parse_args(argv)
    salida = salida_de(args, "compare")
    nombres = [n.strip() for n in args.strategies.split(",") if n.strip()]

    try:
        universo = build_universe(cargar_series(args.paths, Interval[args.interval]))
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)
    except (InvestLLError, KeyError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    friccion = FrictionConfig(commission_rate=args.commission, slippage_rate=args.slippage)
    riesgo = RiskConfig(position_fraction=D(1), stop_loss_pct=args.stop_loss)

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
                return salida.error(
                    "evaluar el LLM necesita --recorded con decisiones ya generadas; "
                    "el motor no toca la red por diseno",
                    SALIDA_ERROR,
                )

            almacen = DecisionStore(args.recorded)
            estimacion = estimate_cost(
                total_decisions=len(universo) // max(1, args.every),
                cached_decisions=almacen.count(),
            )
            salida.linea(estimacion.render())
            salida.linea()

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
                return salida.error(f"evaluando el LLM: {error}", SALIDA_ERROR)
            llm_incluido = True
        else:
            return salida.error(f"estrategia desconocida {nombre!r}", SALIDA_ERROR)

    if not informes:
        return salida.error("no se indico ninguna estrategia", SALIDA_ERROR)

    # Cuenta esta evaluacion ANTES de mostrar nada: si el operador ve el resultado y decide no
    # mirar el contador, la cuenta ya esta hecha igualmente.
    intentos = AttemptLog().record(universo.symbols, interval=args.interval)
    salida.dato(
        attempts={
            "count": intentos.count,
            "expected_positive_by_chance": intentos.expected_by_chance,
            "first_at": intentos.first_at,
        }
    )

    referencia = next(iter(informes.values()))
    salida.dato(
        universe={
            "periods": len(universo),
            "symbols": list(universo.symbols),
            "interval": args.interval,
        },
        strategies=[_estrategia_json(n, i) for n, i in informes.items()],
    )

    salida.linea(f"Universo: {len(universo)} periodos, {len(universo.symbols)} activos")
    salida.linea("=" * 84)
    salida.linea(
        f"{'estrategia':<22}{'RESULTADO':>14}{'DRAWDOWN':>14}"
        f"{'ops':>7}{'COSTES':>12}{'vs NO HACER NADA':>20}"
    )
    salida.linea("-" * 84)

    for nombre, informe in informes.items():
        salida.linea(_fila(nombre, informe))

    if referencia.buy_and_hold is not None:
        bh = referencia.buy_and_hold
        # BuyAndHold no lleva trade_count: por definicion es una entrada y ninguna decision mas.
        salida.linea(
            f"{'comprar y mantener':<22}{bh.net_result:>14,.0f}"
            f"{bh.max_drawdown:>14,.0f}{1:>7}{bh.costs:>12,.0f}{'referencia':>20}"
        )
        salida.dato(
            buy_and_hold={
                "net_result": bh.net_result,
                "max_drawdown": bh.max_drawdown,
                "trades": 1,
                "costs": bh.costs,
            }
        )

    salida.linea("-" * 84)

    ganadoras = [n for n, i in informes.items() if i.beats_market]
    salida.dato(beats_holding=ganadoras)
    if ganadoras:
        salida.linea(f"  Baten a comprar y mantener: {', '.join(ganadoras)}")
        salida.linea(
            "  Eso no garantiza nada de cara al futuro. Ver la validacion fuera de muestra."
        )
    else:
        # Va como aviso y no como linea: en JSON es la diferencia entre que quien lo consuma
        # vea "ninguna bate a no hacer nada" o solo vea una lista vacia y saque sus conclusiones.
        salida.aviso(
            AVISO_SIN_VENTAJA,
            "Ninguna bate a comprar y mantener. Todo el riesgo asumido y las comisiones "
            "pagadas quedaron por debajo de no hacer nada.",
            mostrar=False,
        )
        salida.linea("  [!] Ninguna bate a comprar y mantener.")
        salida.linea("      Todo el riesgo asumido y las comisiones pagadas quedaron por debajo")
        salida.linea("      de no hacer nada.")

    salida.linea()
    salida.aviso(
        AVISO_WIN_RATE,
        "El win rate no aparece aqui a proposito: no es criterio de exito.",
        mostrar=False,
    )
    salida.linea("  El win rate no aparece aqui a proposito: no es criterio de exito.")

    if intentos.count > 1:
        # Tras el separador: lo de arriba es el RESULTADO (identico al repetir, FR-044); lo de
        # abajo es cuantas veces lo has mirado, que cambia por definicion. Mezclarlos haria
        # parecer que el experimento no es reproducible cuando si lo es.
        salida.linea()
        salida.linea("--- historial de esta sesion de trabajo ---")
        salida.linea(intentos.render())
        salida.aviso(
            AVISO_SOBREAJUSTE,
            f"Llevas {intentos.count} evaluaciones sobre este universo; con esa cantidad de "
            f"pruebas sin ventaja real esperarias ~{intentos.expected_by_chance:.0f} positivas "
            "por azar.",
            mostrar=False,
        )

    if llm_incluido:
        salida.linea()
        salida.linea(ADVERTENCIA_CONTAMINACION)
        salida.aviso(AVISO_CONTAMINACION, ADVERTENCIA_CONTAMINACION.strip(), mostrar=False)

    # El veredicto mira TODAS las estrategias, no solo la primera: si una de ellas opero tan
    # poco que su resultado no significa nada, la comparacion tampoco lo hace.
    dudosas = {n: i.inconclusive_reason for n, i in informes.items() if not i.conclusive}
    if dudosas:
        salida.linea()
        for nombre, motivo in dudosas.items():
            salida.aviso(AVISO_NO_CONCLUYENTE, f"NO CONCLUYENTE ({nombre}): {motivo}")
        return salida.cerrar(SALIDA_NO_CONCLUYENTE)

    return salida.cerrar(SALIDA_OK)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
