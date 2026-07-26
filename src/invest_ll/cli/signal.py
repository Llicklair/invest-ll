"""`invest-ll-signal`: en qué deberías estar ahora mismo, según tu política.

Es el comando que faltaba entre medir y operar. Los backtests dicen qué habría pasado; `execute`
manda órdenes. Esto responde a la pregunta de en medio, que es la que te haces cada semana.

**Usa los datos reservados a propósito.** La reserva existe para que un backtest no mire el tramo
guardado para validar; usarla aquí sería calcular la señal de hoy con precios del año pasado. Es la
única lectura del sistema que necesita ver hasta el último dato, y por eso lo dice en voz alta.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.cli.emit import add_json_flag, salida_de
from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.data.universe import build_universe
from invest_ll.errors import InvestLLError
from invest_ll.signal.today import senal_de_hoy

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.data.series import PriceSeries

# La politica decidida el 2026-07-26: ver docs/horizontes.md.
LOOKBACK_POR_DEFECTO = 30


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-signal",
        description=(
            "En que deberias estar ahora, segun la politica. No es un backtest: aplica la regla "
            "al ultimo dato disponible."
        ),
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV de cada activo del universo")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_POR_DEFECTO)
    parser.add_argument(
        "--sin-filtro",
        action="store_true",
        help="Elegir siempre el mejor aunque ninguno suba. Pierde la unica pieza que sobrevivio "
        "a la validacion fuera de muestra.",
    )
    parser.add_argument("--tienes", help="En que estas ahora, para que diga si hay que mover")
    add_json_flag(parser)

    args = parser.parse_args(argv)
    salida = salida_de(args, "signal")

    series: list[PriceSeries] = []
    for ruta in args.paths:
        try:
            # use_reserved: la senal de HOY necesita el ultimo dato. Ver el docstring del modulo.
            serie, _ = load_series(
                ruta,
                symbol=ruta.parent.name.replace("-", "/"),
                interval=Interval.DAY_1,
                calendar=Continuous24x7(),
                use_reserved=True,
            )
        except (InvestLLError, FileNotFoundError, ValueError) as error:
            return salida.error(f"{ruta}: {error}", SALIDA_ERROR)
        series.append(serie)

    try:
        universo = build_universe(series)
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    senal = senal_de_hoy(
        universo,
        lookback=args.lookback,
        min_return=None if args.sin_filtro else 0.0,
        tienes=args.tienes,
    )

    salida.dato(
        chosen=senal.elegido,
        holding=senal.tienes,
        must_move=senal.hay_que_mover,
        sell=senal.vender,
        buy=senal.comprar,
        data_until=senal.datos_hasta,
        days_behind=senal.dias_de_retraso,
        stale=senal.datos_viejos,
        universe=list(universo.symbols),
        lookback=args.lookback,
    )

    salida.linea(f"Universo: {', '.join(universo.symbols)}  ·  mirando {args.lookback} periodos")
    salida.linea()
    salida.linea(senal.describe())

    if senal.hay_que_mover and senal.comprar:
        salida.linea()
        salida.linea("El comando, cuando decidas la cantidad:")
        if senal.vender:
            salida.linea(
                f"  uv run invest-ll-execute --symbol {senal.vender} --side sell --quantity <?>"
            )
        salida.linea(
            f"  uv run invest-ll-execute --symbol {senal.comprar} --side buy --quantity <?>"
        )
    return salida.cerrar(SALIDA_OK)
