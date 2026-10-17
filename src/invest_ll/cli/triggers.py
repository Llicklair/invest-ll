"""`invest-ll-triggers`: reglas de retirada que proponen. La ejecución sigue siendo tuya.

Seis acciones: `arm` (armar una regla), `list`, `disarm`, `check` (evaluarlas contra tu cartera
real), `halt`/`resume` (pausar/reanudar las propuestas de entrada) y `liquidate` (los comandos
para salir de todo, uno a uno).

El kill switch copia la distinción universal de los bots reales —"dejar de entrar" es distinto de
"liquidarlo todo"— y les quita lo peligroso: aquí ningún nivel ejecuta nada solo.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.alerts import SALIDA_HAY_QUE_REVISAR
from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.cli.emit import Salida, add_json_flag, salida_de
from invest_ll.errors import InvestLLError
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.store import ActivityStore
from invest_ll.portfolio.triggers import (
    FiredTrigger,
    Trigger,
    TriggerRule,
    TriggerStore,
    check_triggers,
    liquidation_commands,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal


def _armar(args: argparse.Namespace, store: TriggerStore, salida: Salida) -> int:
    try:
        trigger = Trigger(
            trigger_id=store.next_id(),
            symbol=args.symbol.upper(),
            rule=TriggerRule(args.rule),
            threshold=args.threshold,
            armed_at=datetime.now(UTC),
        )
        store.arm(trigger)
    except (InvestLLError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    salida.dato(trigger_id=trigger.trigger_id, rule=trigger.rule.value, symbol=trigger.symbol)
    salida.linea(f"Armado {trigger.trigger_id}: {trigger.describe()}")
    salida.linea("Cuando salte, PROPONDRA la venta; ejecutarla seguira siendo cosa tuya.")
    return salida.cerrar(SALIDA_OK)


def _listar(store: TriggerStore, salida: Salida) -> int:
    triggers = store.triggers()
    pausa = store.halted()

    salida.dato(
        triggers=[
            {
                "trigger_id": t.trigger_id,
                "symbol": t.symbol,
                "rule": t.rule.value,
                "threshold": t.threshold,
                "armed_at": t.armed_at,
            }
            for t in triggers
        ],
        halted=pausa,
    )

    if pausa:
        salida.linea(f"[PAUSA ACTIVA] no se proponen entradas nuevas: {pausa}")
        salida.linea()
    if not triggers:
        salida.linea("No hay ningun trigger armado.")
        salida.linea("  uv run invest-ll-triggers arm --symbol GLD --rule loss-from-entry \\")
        salida.linea("      --threshold 0.15")
        return salida.cerrar(SALIDA_OK)

    for t in triggers:
        salida.linea(f"{t.trigger_id:<8} {t.describe()}  (armado {t.armed_at.date()})")
    return salida.cerrar(SALIDA_OK)


def _desarmar(args: argparse.Namespace, store: TriggerStore, salida: Salida) -> int:
    if not store.disarm(args.id):
        return salida.error(f"no hay ningun trigger con id {args.id!r}", SALIDA_ERROR)
    salida.dato(disarmed=args.id)
    salida.linea(f"Desarmado {args.id}.")
    return salida.cerrar(SALIDA_OK)


def _comprobar(store: TriggerStore, actividades: ActivityStore, salida: Salida) -> int:
    try:
        cartera = derive_portfolio(actividades.activities())
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    comprobacion = check_triggers(store.triggers(), cartera.open_positions)
    disparados: list[FiredTrigger] = []
    sin_evaluar = list(comprobacion.not_evaluated)

    for resultado, fecha in comprobacion.fired:
        disparados.append(resultado)
        salida.linea(resultado.render())
        salida.linea(f"    (precio del {fecha.date()})")
        salida.linea()

    salida.dato(
        fired=[
            {
                "trigger_id": f.trigger.trigger_id,
                "symbol": f.trigger.symbol,
                "rule": f.trigger.rule.value,
                "measured": f.measured,
                "threshold": f.trigger.threshold,
                "proposed_quantity": f.quantity,
            }
            for f in disparados
        ],
        not_evaluated=sin_evaluar,
        armed=comprobacion.armed,
    )

    for pendiente in sin_evaluar:
        # No poder evaluar NO es "todo en orden", y se dice en los dos formatos.
        salida.aviso("trigger_not_evaluated", pendiente)

    if not disparados:
        if not sin_evaluar:
            salida.linea("Ningun trigger ha saltado. Eso no valora la cartera: solo dice que")
            salida.linea("ninguna de TUS reglas armadas se ha cruzado.")
        return salida.cerrar(SALIDA_OK)

    salida.linea(f"{len(disparados)} trigger(s) saltados. Nada se ha enviado a ningun sitio.")
    return salida.cerrar(SALIDA_HAY_QUE_REVISAR)


def _pausar(args: argparse.Namespace, store: TriggerStore, salida: Salida) -> int:
    try:
        store.halt(reason=args.reason, at=datetime.now(UTC))
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)
    salida.dato(halted=args.reason)
    salida.linea(f"Pausa activada: {args.reason}")
    salida.linea("invest-ll-propose y la pestana Invertir dejaran de proponer entradas nuevas.")
    salida.linea("Las posiciones abiertas NO se tocan. Reanuda con: invest-ll-triggers resume")
    return salida.cerrar(SALIDA_OK)


def _reanudar(store: TriggerStore, salida: Salida) -> int:
    habia = store.resume()
    salida.dato(resumed=habia)
    salida.linea("Pausa retirada." if habia else "No habia ninguna pausa activa.")
    return salida.cerrar(SALIDA_OK)


def _liquidar(actividades: ActivityStore, salida: Salida) -> int:
    try:
        cartera = derive_portfolio(actividades.activities())
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    comandos = liquidation_commands(cartera.open_positions)
    salida.dato(
        positions=len(cartera.open_positions),
        commands=comandos,
    )
    if not comandos:
        salida.linea("No hay posiciones abiertas que liquidar.")
        return salida.cerrar(SALIDA_OK)

    salida.linea(f"Salir de TODO son {len(comandos)} orden(es). Ninguna se ha enviado:")
    salida.linea()
    for comando in comandos:
        salida.linea(f"  {comando}")
    salida.linea()
    salida.linea("Cada una pedira confirmar escribiendo su cantidad. Es deliberado: liquidarlo")
    salida.linea("todo con un solo enter seria la clase de accion irreversible que el")
    salida.linea("Principio I prohibe.")
    return salida.cerrar(SALIDA_OK)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-triggers",
        description=(
            "Reglas de retirada que PROPONEN la salida cuando se cruzan. Nunca la ejecutan: "
            "cada orden pasa por invest-ll-execute y su confirmacion."
        ),
    )
    parser.add_argument("--store", type=Path, help="Carpeta del registro (por defecto portfolio/)")
    sub = parser.add_subparsers(dest="accion", required=True)

    armar = sub.add_parser("arm", help="Armar una regla sobre un activo")
    armar.add_argument("--symbol", required=True)
    armar.add_argument("--rule", required=True, choices=[r.value for r in TriggerRule])
    armar.add_argument("--threshold", type=D, required=True, help="Fraccion: 0.15 = 15%%")

    sub.add_parser("list", help="Ver triggers armados y si hay pausa")

    desarmar = sub.add_parser("disarm", help="Desarmar por id")
    desarmar.add_argument("--id", required=True)

    sub.add_parser("check", help="Evaluar los triggers contra tu cartera real")

    pausar = sub.add_parser("halt", help="Nivel 1: dejar de proponer entradas nuevas")
    pausar.add_argument("--reason", required=True, help="Por que pausas (obligatorio)")

    sub.add_parser("resume", help="Retirar la pausa")
    sub.add_parser("liquidate", help="Nivel 2: los comandos para salir de todo, uno a uno")

    add_json_flag(parser)
    for subparser in sub.choices.values():
        add_json_flag(subparser, hereda=True)

    args = parser.parse_args(argv)
    salida = salida_de(args, f"triggers {args.accion}")
    raiz = args.store if args.store else None
    store = TriggerStore(raiz) if raiz else TriggerStore()
    actividades = ActivityStore(raiz) if raiz else ActivityStore()

    if args.accion == "arm":
        return _armar(args, store, salida)
    if args.accion == "list":
        return _listar(store, salida)
    if args.accion == "disarm":
        return _desarmar(args, store, salida)
    if args.accion == "check":
        return _comprobar(store, actividades, salida)
    if args.accion == "halt":
        return _pausar(args, store, salida)
    if args.accion == "resume":
        return _reanudar(store, salida)
    return _liquidar(actividades, salida)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
