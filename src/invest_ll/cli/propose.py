"""`invest-ll-propose`: una cartera a partir de un importe y una periodicidad.

El comando más simple del proyecto a propósito. No pide elegir estrategia ni parámetros porque
ese es justo el conocimiento que el operador no tiene.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import (
    SALIDA_ERROR,
    SALIDA_NO_ENCONTRADO,
    SALIDA_OK,
    cargar_series,
)
from invest_ll.cli.emit import (
    AVISO_NO_ES_PREVISION,
    add_json_flag,
    salida_de,
)
from invest_ll.data.bar import Interval
from invest_ll.data.universe import build_universe
from invest_ll.engine.config import FrictionConfig
from invest_ll.errors import InvestLLError
from invest_ll.proposal.builder import FRECUENCIAS, propose_portfolio

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-propose",
        description="Propone una cartera y simula que habria pasado con ella.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV de cada activo candidato")
    parser.add_argument("--amount", type=D, required=True, help="Cuanto aportas cada vez")
    parser.add_argument("--frequency", default="monthly", choices=sorted(FRECUENCIAS))
    parser.add_argument("--interval", default="DAY_1")
    parser.add_argument("--commission", type=D, default=D("0.001"))
    parser.add_argument("--slippage", type=D, default=D("0.0005"))
    add_json_flag(parser)

    args = parser.parse_args(argv)
    salida = salida_de(args, "propose")

    try:
        universo = build_universe(cargar_series(args.paths, Interval[args.interval]))
        propuesta = propose_portfolio(
            universo,
            amount=args.amount,
            frequency=args.frequency,
            friction=FrictionConfig(commission_rate=args.commission, slippage_rate=args.slippage),
        )
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)
    except (InvestLLError, KeyError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    simulacion = propuesta.simulation
    salida.dato(
        contribution=propuesta.contribution,
        frequency=args.frequency,
        every_periods=propuesta.every_periods,
        holdings=[
            {
                "symbol": h.symbol,
                "weight": h.weight,
                "amount_per_contribution": h.amount_per_contribution,
                "explanation": h.explanation,
            }
            for h in propuesta.holdings
        ],
        simulation={
            "contributions": simulacion.contributions,
            "total_contributed": simulacion.total_contributed,
            "final_value": simulacion.final_value,
            "net_result": simulacion.net_result,
            "total_costs": simulacion.total_costs,
            "max_drawdown": simulacion.max_drawdown,
            "lump_sum_value": simulacion.lump_sum_value,
            "beats_lump_sum": simulacion.beats_lump_sum,
        },
    )

    salida.linea(propuesta.render())
    salida.linea()
    salida.aviso(
        AVISO_NO_ES_PREVISION,
        "Esto es una simulacion sobre el pasado, no una recomendacion ni una prevision.",
    )
    return salida.cerrar(SALIDA_OK)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
