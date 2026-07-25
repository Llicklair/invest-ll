"""`invest-ll-analyze`: qué hay detrás de un activo."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from invest_ll.analysis.yfinance_researcher import YFinanceResearcher
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.cli.emit import AVISO_NO_ES_PREVISION, add_json_flag, salida_de

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-analyze",
        description="Muestra que hay detras de un activo, separando dato de interpretacion.",
    )
    parser.add_argument("symbols", nargs="+", help="Simbolos a analizar")
    add_json_flag(parser)
    args = parser.parse_args(argv)
    salida = salida_de(args, "analyze")

    investigador = YFinanceResearcher()
    informes: list[dict[str, object]] = []

    for i, simbolo in enumerate(args.symbols):
        if i:
            salida.linea()
        try:
            informe = investigador.analyze(simbolo)
        except ValueError as error:
            return salida.error(f"analizando {simbolo}: {error}", SALIDA_ERROR)

        salida.linea(informe.render())
        informes.append({"symbol": simbolo, "rendered": informe.render()})

    salida.dato(assets=informes)
    # El comando existe para explicar que hay detras de un activo. Que eso no se lea como una
    # prevision es parte del contenido, no un adorno del formato de texto.
    salida.aviso(
        AVISO_NO_ES_PREVISION,
        "Esto describe lo que hay detras del activo. Los escenarios no son predicciones.",
        mostrar=False,
    )
    return salida.cerrar(SALIDA_OK)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
