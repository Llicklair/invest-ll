"""`invest-ll-track`: registrar lo que se estima y comprobarlo cuando venza.

**Es la única evidencia limpia que este proyecto puede producir sobre el LLM.** Un backtest sobre
el pasado no vale: el modelo fue entrenado con datos posteriores al periodo simulado. Comparar lo
que dice hoy con lo que ocurra después sí.

Por eso el comando hace tres cosas y ninguna más: emitir una estimación, registrar lo que pasó, y
enseñar el historial completo — con los fallos dentro.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.errors import InvestLLError
from invest_ll.tracking.forecast import build_track_record, pending
from invest_ll.tracking.models import Forecast, Holding, Outcome
from invest_ll.tracking.store import ForecastStore

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal
HORIZONTE_POR_DEFECTO = 90


def _leer_cartera(textos: Sequence[str]) -> tuple[Holding, ...]:
    """Convierte `SIMBOLO:CANTIDAD` en posiciones."""
    holdings: list[Holding] = []
    for texto in textos:
        if ":" not in texto:
            raise ValueError(f"formato invalido {texto!r}; se espera SIMBOLO:CANTIDAD")
        simbolo, _, cantidad = texto.partition(":")
        try:
            holdings.append(Holding(symbol=simbolo.strip(), quantity=D(cantidad.strip())))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"cantidad invalida en {texto!r}: {error}") from error
    return tuple(holdings)


def _emitir(args: argparse.Namespace, almacen: ForecastStore) -> int:
    try:
        estimacion = Forecast(
            issued_at=datetime.now(UTC),
            horizon_days=args.horizon,
            portfolio=_leer_cartera(args.holding or ()),
            expected_value=args.expected,
            basis=args.basis,
            model=args.model or "",
        )
        identificador = almacen.append(estimacion)
    except (InvestLLError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_ERROR

    print(f"Estimacion registrada: {identificador}")
    print(f"  Valor esperado   {estimacion.expected_value:,.2f}")
    print(f"  Horizonte        {estimacion.horizon_days} dias")
    print(f"  Vence            {estimacion.due_at.date()}")
    print()
    print("Ya no se puede modificar. Cuando venza, registra lo que paso:")
    print(f"  uv run invest-ll-track record --id {identificador} --actual <valor real>")
    return SALIDA_OK


def _registrar(args: argparse.Namespace, almacen: ForecastStore) -> int:
    conocidas = {f.forecast_id for f in almacen.forecasts()}
    if args.id not in conocidas:
        print(
            f"Error: no hay ninguna estimacion con id {args.id!r}.\n"
            "       Usa 'invest-ll-track list' para ver las registradas.",
            file=sys.stderr,
        )
        return SALIDA_ERROR

    almacen.record_outcome(
        Outcome(forecast_id=args.id, measured_at=datetime.now(UTC), actual_value=args.actual)
    )
    evaluacion = next(
        (e for e in build_track_record(almacen).evaluations if e.forecast.forecast_id == args.id),
        None,
    )

    print(f"Resultado registrado para {args.id}")
    if evaluacion is not None:
        signo = "por encima" if evaluacion.error > 0 else "por debajo"
        print(f"  Estimado  {evaluacion.forecast.expected_value:,.2f}")
        print(f"  Real      {evaluacion.outcome.actual_value:,.2f}")
        print(f"  Error     {evaluacion.error:,.2f}  ({signo} de lo estimado)")
    return SALIDA_OK


def _listar(almacen: ForecastStore) -> int:
    estimaciones = almacen.forecasts()
    if not estimaciones:
        print("No hay ninguna estimacion registrada todavia.")
        print()
        print("Emite la primera con:")
        print("  uv run invest-ll-track issue --expected 320000 --horizon 90 \\")
        print("      --basis 'aportaciones periodicas sobre GLD/TLT/XLE/XLF' \\")
        print("      --holding GLD:10 --holding TLT:8")
        print()
        print("Hasta que no venza una, no hay forma de saber si el sistema acierta.")
        return SALIDA_OK

    sin_resultado = set(pending(almacen))
    ahora = datetime.now(UTC)

    print(f"{'id':<18}{'emitida':<13}{'vence':<13}{'ESTIMADO':>14}  estado")
    print("-" * 72)
    for f in estimaciones:
        if f.forecast_id in sin_resultado:
            estado = "VENCIDA, sin registrar" if f.is_due(ahora) else "esperando"
        else:
            estado = "evaluada"
        print(
            f"{f.forecast_id:<18}{f.issued_at.date()!s:<13}{f.due_at.date()!s:<13}"
            f"{f.expected_value:>14,.2f}  {estado}"
        )

    vencidas = [f for f in estimaciones if f.forecast_id in sin_resultado and f.is_due(ahora)]
    if vencidas:
        print()
        print(f"[!] {len(vencidas)} estimacion(es) ya vencieron y no tienen resultado.")
        print("    Registralos: sin ellos el historial no mide nada.")
    return SALIDA_OK


def _evaluar(almacen: ForecastStore) -> int:
    print(build_track_record(almacen).render())
    return SALIDA_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-track",
        description=(
            "Registra lo que el sistema estima y compruebalo cuando venza. "
            "Es la unica evidencia sobre el LLM que no esta contaminada."
        ),
    )
    parser.add_argument("--store", type=Path, help="Carpeta del historial")
    sub = parser.add_subparsers(dest="accion", required=True)

    emitir = sub.add_parser("issue", help="Emitir una estimacion (queda congelada)")
    emitir.add_argument("--expected", type=D, required=True, help="Valor esperado al vencimiento")
    emitir.add_argument("--horizon", type=int, default=HORIZONTE_POR_DEFECTO, help="Dias")
    emitir.add_argument("--basis", required=True, help="En que se basa (obligatorio)")
    emitir.add_argument("--holding", action="append", help="SIMBOLO:CANTIDAD, repetible")
    emitir.add_argument("--model", help="Que modelo la produjo, si fue un LLM")

    registrar = sub.add_parser("record", help="Registrar lo que paso de verdad")
    registrar.add_argument("--id", required=True)
    registrar.add_argument("--actual", type=D, required=True, help="Valor real medido")

    sub.add_parser("list", help="Ver las estimaciones y su estado")
    sub.add_parser("evaluate", help="Ver el historial: aciertos, fallos y sesgo")

    args = parser.parse_args(argv)
    almacen = ForecastStore(args.store) if args.store else ForecastStore()

    if args.accion == "issue":
        return _emitir(args, almacen)
    if args.accion == "record":
        return _registrar(args, almacen)
    if args.accion == "list":
        return _listar(almacen)
    return _evaluar(almacen)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
