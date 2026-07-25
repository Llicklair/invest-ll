"""`invest-ll-alerts`: qué está pasando con tus activos, cuando tú preguntas.

**No hay envío.** Ni push, ni correo, ni un proceso que vigile en segundo plano. Este comando se
ejecuta cuando alguien lo escribe, y ese es el diseño, no una limitación pendiente de completar:
la FCA midió que las notificaciones aumentan un 11% las operaciones y un 8% las inversiones
arriesgadas, con más efecto en quien menos sabe de inversión.

Ver `src/invest_ll/alerts/models.py` para las tres reglas que gobiernan qué puede ser una alerta.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.alerts.engine import evaluate, render
from invest_ll.alerts.models import Nivel, Position, Umbrales
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_NO_ENCONTRADO, SALIDA_OK, cargar_series
from invest_ll.cli.emit import add_json_flag, salida_de
from invest_ll.data.bar import Interval
from invest_ll.errors import InvestLLError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.alerts.models import Alert

D = Decimal

# Codigo propio cuando algo pide revision: permite encadenarlo en un script sin leer el texto.
SALIDA_HAY_QUE_REVISAR = 6


def leer_posicion(texto: str) -> Position:
    """`SIMBOLO:CANTIDAD:PRECIO_DE_ENTRADA`.

    El precio de entrada es obligatorio y no opcional a propósito: sin él no se puede decir nada
    honesto sobre tu pérdida. Lo que ha caído el activo desde su máximo no es lo que has perdido
    tú si entraste después, y confundirlo es la forma más fácil de asustar a alguien sin motivo.
    """
    partes = texto.split(":")
    if len(partes) != 3:
        raise ValueError(
            f"formato invalido {texto!r}; se espera SIMBOLO:CANTIDAD:PRECIO_DE_ENTRADA "
            "(el precio de entrada hace falta para saber lo que has perdido TU)"
        )
    simbolo, cantidad, entrada = (p.strip() for p in partes)
    try:
        return Position(symbol=simbolo, quantity=D(cantidad), entry_price=D(entrada))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"posicion invalida en {texto!r}: {error}") from error


def leer_objetivo(textos: Sequence[str]) -> dict[str, Decimal]:
    """`SIMBOLO:PESO`, con el peso en tanto por uno."""
    objetivo: dict[str, Decimal] = {}
    for texto in textos:
        simbolo, _, peso = texto.partition(":")
        if not peso:
            raise ValueError(f"formato invalido {texto!r}; se espera SIMBOLO:PESO (0.25 = 25%)")
        try:
            objetivo[simbolo.strip()] = D(peso.strip())
        except InvalidOperation as error:
            raise ValueError(f"peso invalido en {texto!r}: {error}") from error
    return objetivo


def _alerta_json(alerta: Alert) -> dict[str, object]:
    return {
        "code": alerta.code,
        "symbol": alerta.symbol,
        "level": alerta.level.value,
        "message": alerta.message,
        "measured": alerta.measured,
        "threshold": alerta.threshold,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invest-ll-alerts",
        description=(
            "Que esta pasando con tus activos. Se consulta; no persigue: no hay notificaciones."
        ),
        epilog=(
            "Ninguna alerta dice que hacer. Informan de un estado, y solo saltan por riesgo -- "
            "nunca porque algo haya subido."
        ),
    )
    parser.add_argument("paths", nargs="+", type=Path, help="CSV de cada activo")
    parser.add_argument("--interval", default="DAY_1")
    parser.add_argument(
        "--holding",
        action="append",
        metavar="SIMBOLO:CANTIDAD:ENTRADA",
        help="Lo que tienes y a que precio entraste. Repetible.",
    )
    parser.add_argument(
        "--target",
        action="append",
        metavar="SIMBOLO:PESO",
        help="El peso que decidiste para ese activo (0.25 = 25%%). Repetible.",
    )
    parser.add_argument(
        "--simulated-drawdown",
        type=D,
        help="La peor caida que dio la simulacion. Con --capital, avisa si la realidad la supera.",
    )
    parser.add_argument("--capital", type=D, help="Capital sobre el que se simulo esa caida")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=Umbrales().dias_sin_datos,
        help="Dias sin actualizar a partir de los cuales los datos se consideran viejos",
    )
    add_json_flag(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    salida = salida_de(args, "alerts")

    try:
        posiciones = [leer_posicion(t) for t in (args.holding or ())]
        objetivo = leer_objetivo(args.target or ())
        umbrales = Umbrales(dias_sin_datos=args.stale_days)
        series = cargar_series(args.paths, Interval[args.interval])
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)
    except (InvestLLError, KeyError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    # Pedir una de las dos y no la otra suele ser un despiste, y el resultado seria que la regla
    # mas util del modulo no se evalua en silencio.
    if (args.simulated_drawdown is None) != (args.capital is None):
        return salida.error(
            "--simulated-drawdown y --capital van juntos: sin los dos no se puede comparar "
            "la caida real con la que dijo la simulacion",
            SALIDA_ERROR,
        )

    alertas = evaluate(
        series,
        ahora=datetime.now(UTC),
        posiciones=posiciones,
        objetivo=objetivo,
        drawdown_simulado=args.simulated_drawdown,
        capital=args.capital,
        umbrales=umbrales,
    )

    salida.linea(render(alertas))
    salida.dato(
        symbols=[s.symbol for s in series],
        alerts=[_alerta_json(a) for a in alertas],
        needs_review=[a.code for a in alertas if a.level is Nivel.REVISAR],
    )

    # Las alertas NO son avisos del sobre: un aviso dice "cuidado con como lees este resultado",
    # y esto ES el resultado. Meterlas en `warnings` las mezclaria con las advertencias del
    # sistema y dejaria `data` vacio para quien las consuma.
    if any(a.level is Nivel.REVISAR for a in alertas):
        return salida.cerrar(SALIDA_HAY_QUE_REVISAR)
    return salida.cerrar(SALIDA_OK)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
