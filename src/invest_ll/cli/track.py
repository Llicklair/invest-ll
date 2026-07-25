"""`invest-ll-track`: registrar lo que se estima y comprobarlo cuando venza.

**Es la única evidencia limpia que este proyecto puede producir sobre el LLM.** Un backtest sobre
el pasado no vale: el modelo fue entrenado con datos posteriores al periodo simulado. Comparar lo
que dice hoy con lo que ocurra después sí.

Por eso el comando hace tres cosas y ninguna más: emitir una estimación, registrar lo que pasó, y
enseñar el historial completo — con los fallos dentro.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_OK
from invest_ll.cli.emit import AVISO_VENCIDAS, Salida, add_json_flag, salida_de
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


def _emitir(args: argparse.Namespace, almacen: ForecastStore, salida: Salida) -> int:
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
        return salida.error(str(error), SALIDA_ERROR)

    salida.dato(
        forecast_id=identificador,
        expected_value=estimacion.expected_value,
        horizon_days=estimacion.horizon_days,
        issued_at=estimacion.issued_at,
        due_at=estimacion.due_at,
        basis=estimacion.basis,
        model=estimacion.model,
    )

    salida.linea(f"Estimacion registrada: {identificador}")
    salida.linea(f"  Valor esperado   {estimacion.expected_value:,.2f}")
    salida.linea(f"  Horizonte        {estimacion.horizon_days} dias")
    salida.linea(f"  Vence            {estimacion.due_at.date()}")
    salida.linea()
    salida.linea("Ya no se puede modificar. Cuando venza, registra lo que paso:")
    salida.linea(f"  uv run invest-ll-track record --id {identificador} --actual <valor real>")
    return salida.cerrar(SALIDA_OK)


def _registrar(args: argparse.Namespace, almacen: ForecastStore, salida: Salida) -> int:
    conocidas = {f.forecast_id for f in almacen.forecasts()}
    if args.id not in conocidas:
        return salida.error(
            f"no hay ninguna estimacion con id {args.id!r}; "
            "usa 'invest-ll-track list' para ver las registradas",
            SALIDA_ERROR,
        )

    almacen.record_outcome(
        Outcome(forecast_id=args.id, measured_at=datetime.now(UTC), actual_value=args.actual)
    )
    evaluacion = next(
        (e for e in build_track_record(almacen).evaluations if e.forecast.forecast_id == args.id),
        None,
    )

    salida.dato(forecast_id=args.id, actual_value=args.actual)
    salida.linea(f"Resultado registrado para {args.id}")
    if evaluacion is not None:
        signo = "por encima" if evaluacion.error > 0 else "por debajo"
        salida.dato(
            expected_value=evaluacion.forecast.expected_value,
            error=evaluacion.error,
        )
        salida.linea(f"  Estimado  {evaluacion.forecast.expected_value:,.2f}")
        salida.linea(f"  Real      {evaluacion.outcome.actual_value:,.2f}")
        salida.linea(f"  Error     {evaluacion.error:,.2f}  ({signo} de lo estimado)")
    return salida.cerrar(SALIDA_OK)


def _listar(almacen: ForecastStore, salida: Salida) -> int:
    estimaciones = almacen.forecasts()
    if not estimaciones:
        salida.dato(forecasts=[], overdue=0)
        salida.linea("No hay ninguna estimacion registrada todavia.")
        salida.linea()
        salida.linea("Emite la primera con:")
        salida.linea("  uv run invest-ll-track issue --expected 320000 --horizon 90 \\")
        salida.linea("      --basis 'aportaciones periodicas sobre GLD/TLT/XLE/XLF' \\")
        salida.linea("      --holding GLD:10 --holding TLT:8")
        salida.linea()
        salida.linea("Hasta que no venza una, no hay forma de saber si el sistema acierta.")
        return salida.cerrar(SALIDA_OK)

    sin_resultado = set(pending(almacen))
    ahora = datetime.now(UTC)

    salida.linea(f"{'id':<18}{'emitida':<13}{'vence':<13}{'ESTIMADO':>14}  estado")
    salida.linea("-" * 72)

    filas: list[dict[str, object]] = []
    for f in estimaciones:
        if f.forecast_id in sin_resultado:
            estado = "VENCIDA, sin registrar" if f.is_due(ahora) else "esperando"
        else:
            estado = "evaluada"
        salida.linea(
            f"{f.forecast_id:<18}{f.issued_at.date()!s:<13}{f.due_at.date()!s:<13}"
            f"{f.expected_value:>14,.2f}  {estado}"
        )
        filas.append(
            {
                "forecast_id": f.forecast_id,
                "issued_at": f.issued_at,
                "due_at": f.due_at,
                "expected_value": f.expected_value,
                "status": estado,
                "has_outcome": f.forecast_id not in sin_resultado,
            }
        )

    vencidas = [f for f in estimaciones if f.forecast_id in sin_resultado and f.is_due(ahora)]
    salida.dato(forecasts=filas, overdue=len(vencidas))

    if vencidas:
        salida.linea()
        salida.aviso(
            AVISO_VENCIDAS,
            f"{len(vencidas)} estimacion(es) ya vencieron y no tienen resultado. "
            "Sin ellos el historial no mide nada.",
            mostrar=False,
        )
        salida.linea(f"[!] {len(vencidas)} estimacion(es) ya vencieron y no tienen resultado.")
        salida.linea("    Registralos: sin ellos el historial no mide nada.")
    return salida.cerrar(SALIDA_OK)


def _evaluar(almacen: ForecastStore, salida: Salida) -> int:
    historial = build_track_record(almacen)
    salida.linea(historial.render())
    salida.dato(
        evaluations=[
            {
                "forecast_id": e.forecast.forecast_id,
                "expected_value": e.forecast.expected_value,
                "actual_value": e.outcome.actual_value,
                "error": e.error,
            }
            for e in historial.evaluations
        ],
        rendered=historial.render(),
    )
    return salida.cerrar(SALIDA_OK)


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

    # La bandera va en el padre Y en cada subcomando: `track --json list` y `track list --json`
    # son la misma intencion, y que solo funcionara una de las dos seria una trampa.
    add_json_flag(parser)
    for subparser in sub.choices.values():
        add_json_flag(subparser, hereda=True)

    args = parser.parse_args(argv)
    salida = salida_de(args, f"track {args.accion}")
    almacen = ForecastStore(args.store) if args.store else ForecastStore()

    if args.accion == "issue":
        return _emitir(args, almacen, salida)
    if args.accion == "record":
        return _registrar(args, almacen, salida)
    if args.accion == "list":
        return _listar(almacen, salida)
    return _evaluar(almacen, salida)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
