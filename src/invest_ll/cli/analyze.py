"""`invest-ll-analyze`: qué hay detrás de un activo."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from invest_ll.analysis.yfinance_researcher import YFinanceResearcher
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-analyze",
        description="Muestra que hay detras de un activo, separando dato de interpretacion.",
    )
    parser.add_argument("symbols", nargs="+", help="Simbolos a analizar")
    args = parser.parse_args(argv)

    investigador = YFinanceResearcher()

    for i, simbolo in enumerate(args.symbols):
        if i:
            print()
        try:
            print(investigador.analyze(simbolo).render())
        except ValueError as error:
            print(f"Error analizando {simbolo}: {error}", file=sys.stderr)
            return SALIDA_ERROR

    return SALIDA_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
