"""`invest-ll-portfolio`: tu cartera de verdad — qué tienes, qué retiraste, y qué pasó con ello.

Cuatro acciones: `add` (una compra o venta), `cash` (un depósito o retirada), `import` (el CSV
del bróker) y `show` (posiciones abiertas, cerradas y efectivo).

La separación que este comando cuida: en las posiciones abiertas el P&L es **no realizado** —
una valoración que cambia cada día—; en las cerradas es **realizado** — un hecho. Sumarlos en una
sola cifra contaría como ganado dinero que aún puede evaporarse, y por eso no se suman nunca.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_NO_ENCONTRADO, SALIDA_OK
from invest_ll.cli.emit import Salida, add_json_flag, salida_de
from invest_ll.errors import InvestLLError
from invest_ll.portfolio.csv_import import parse_broker_csv
from invest_ll.portfolio.derive import Portfolio, derive_portfolio
from invest_ll.portfolio.models import Activity, ActivityType, OpenPosition
from invest_ll.portfolio.store import ActivityStore

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal
RAIZ_DATOS = Path("data/market")


def _fecha(texto: str | None) -> datetime:
    if not texto:
        return datetime.now(UTC)
    return datetime.fromisoformat(texto).replace(tzinfo=UTC)


def ultimo_cierre(symbol: str, raiz: Path = RAIZ_DATOS) -> tuple[Decimal, datetime] | None:
    """El último cierre descargado de un activo, con su fecha.

    La fecha viaja SIEMPRE con el precio: una valoración sin fecha parece de hoy, y con
    históricos parados desde hace meses eso es exactamente la mentira que no podemos contar.
    """
    if not raiz.exists():
        return None
    for csv_path in sorted(raiz.glob(f"*/{symbol}/DAY_1.csv")):
        lineas = csv_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lineas) < 2:
            continue
        campos = lineas[-1].split(",")
        try:
            return D(campos[4]), datetime.fromisoformat(campos[0])
        except (InvalidOperation, ValueError, IndexError):  # pragma: no cover - csv corrupto
            continue
    return None


def _posicion_json(
    p: OpenPosition, precio: Decimal | None, fecha_precio: datetime | None
) -> dict[str, object]:
    return {
        "symbol": p.symbol,
        "quantity": p.quantity,
        "avg_cost": p.avg_cost,
        "invested": p.cost,
        "opened_at": p.opened_at,
        "last_price": precio,
        "price_date": fecha_precio,
        "value": p.value_at(precio) if precio is not None else None,
        "unrealized_pnl": p.unrealized_at(precio) if precio is not None else None,
    }


def _mostrar(store: ActivityStore, salida: Salida) -> int:
    try:
        cartera: Portfolio = derive_portfolio(store.activities())
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    abiertas_json: list[dict[str, object]] = []
    if not cartera.open_positions and not cartera.closed_trades:
        salida.linea("La cartera esta vacia: no hay ningun movimiento registrado.")
        salida.linea()
        salida.linea("Registra el primero con:")
        salida.linea("  uv run invest-ll-portfolio add buy --symbol GLD --quantity 10 \\")
        salida.linea("      --price 180.5 --fee 1.2")
        salida.linea("o importa el CSV de tu broker:")
        salida.linea("  uv run invest-ll-portfolio import movimientos.csv")
        salida.dato(open_positions=[], closed_trades=[], cash=cartera.cash)
        return salida.cerrar(SALIDA_OK)

    if cartera.open_positions:
        salida.linea("POSICIONES ABIERTAS (su P&L es una valoracion, no un hecho)")
        salida.linea(
            f"{'activo':<8}{'cantidad':>12}{'coste medio':>13}{'invertido':>12}"
            f"{'valor':>12}{'P&L no real.':>14}  datos de"
        )
        salida.linea("-" * 84)
        for p in cartera.open_positions:
            cierre = ultimo_cierre(p.symbol)
            precio, fecha = cierre if cierre else (None, None)
            abiertas_json.append(_posicion_json(p, precio, fecha))
            if precio is not None and fecha is not None:
                salida.linea(
                    f"{p.symbol:<8}{p.quantity:>12,.4f}{p.avg_cost:>13,.2f}{p.cost:>12,.0f}"
                    f"{p.value_at(precio):>12,.0f}{p.unrealized_at(precio):>14,.0f}"
                    f"  {fecha.date()}"
                )
            else:
                salida.linea(
                    f"{p.symbol:<8}{p.quantity:>12,.4f}{p.avg_cost:>13,.2f}{p.cost:>12,.0f}"
                    f"{'sin datos':>12}{'—':>14}"
                )

    if cartera.closed_trades:
        salida.linea()
        salida.linea("POSICIONES RETIRADAS (su P&L es un hecho: ya no cambia)")
        salida.linea(
            f"{'activo':<8}{'abierta':<12}{'retirada':<12}{'dias':>6}"
            f"{'invertido':>12}{'recuperado':>12}{'P&L realizado':>15}"
        )
        salida.linea("-" * 84)
        for t in cartera.closed_trades:
            salida.linea(
                f"{t.symbol:<8}{t.opened_at.date()!s:<12}{t.closed_at.date()!s:<12}"
                f"{t.holding_days:>6}{t.invested_total:>12,.0f}{t.proceeds_total:>12,.0f}"
                f"{t.realized_pnl:>15,.0f}"
            )
        salida.linea("-" * 84)
        salida.linea(f"{'P&L realizado total':>50}{cartera.realized_pnl:>15,.0f}")

    salida.linea()
    salida.linea(
        f"Efectivo derivado: {cartera.cash:,.2f}  "
        f"(depositado {cartera.total_deposited:,.0f}, retirado {cartera.total_withdrawn:,.0f})"
    )

    for aviso in cartera.warnings:
        salida.aviso("cash_incomplete", aviso, mostrar=False)
        salida.linea(f"[!] {aviso}")

    salida.dato(
        open_positions=abiertas_json,
        closed_trades=[
            {
                "symbol": t.symbol,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "holding_days": t.holding_days,
                "invested": t.invested_total,
                "proceeds": t.proceeds_total,
                "realized_pnl": t.realized_pnl,
            }
            for t in cartera.closed_trades
        ],
        realized_pnl_total=cartera.realized_pnl,
        cash=cartera.cash,
        total_deposited=cartera.total_deposited,
        total_withdrawn=cartera.total_withdrawn,
    )
    return salida.cerrar(SALIDA_OK)


def _anadir(args: argparse.Namespace, store: ActivityStore, salida: Salida) -> int:
    try:
        actividad = Activity(
            timestamp=_fecha(args.date),
            type=ActivityType(args.operacion),
            symbol=args.symbol.upper(),
            quantity=args.quantity,
            unit_price=args.price,
            fee=args.fee,
        )
        identificador = store.append(actividad)
    except (InvestLLError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    salida.dato(activity_id=identificador, type=args.operacion, symbol=actividad.symbol)
    salida.linea(f"Registrado: {args.operacion} {args.quantity} {actividad.symbol} a {args.price}")
    salida.linea(f"  id {identificador} · {actividad.timestamp.date()} · comision {args.fee}")
    return salida.cerrar(SALIDA_OK)


def _efectivo(args: argparse.Namespace, store: ActivityStore, salida: Salida) -> int:
    tipo = ActivityType.DEPOSIT if args.movimiento == "deposit" else ActivityType.WITHDRAWAL
    try:
        actividad = Activity(
            timestamp=_fecha(args.date),
            type=tipo,
            symbol=None,
            quantity=args.amount,
            unit_price=D(1),
        )
        identificador = store.append(actividad)
    except (InvestLLError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    salida.dato(activity_id=identificador, type=tipo.value, amount=args.amount)
    verbo = "Depositado" if tipo is ActivityType.DEPOSIT else "Retirado"
    salida.linea(f"{verbo}: {args.amount:,.2f}  ({actividad.timestamp.date()})")
    return salida.cerrar(SALIDA_OK)


def _importar(args: argparse.Namespace, store: ActivityStore, salida: Salida) -> int:
    try:
        resultado = parse_broker_csv(args.csv)
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    conocidos = store.known_ids()
    nuevas = [a for a in resultado.activities if a.activity_id not in conocidos]
    repetidas = len(resultado.activities) - len(nuevas)

    for actividad in nuevas:
        store.append(actividad)

    salida.dato(
        imported=len(nuevas),
        already_present=repetidas,
        skipped_by_type=resultado.skipped_types,
    )
    salida.linea(f"Importadas {len(nuevas)} actividad(es) de {args.csv}")
    if repetidas:
        salida.linea(f"  Ya estaban (identicas): {repetidas} — no se duplican")
    for aviso in resultado.warnings:
        salida.aviso("import_partial", aviso, mostrar=False)
        salida.linea(f"[!] {aviso}")
    return salida.cerrar(SALIDA_OK)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-portfolio",
        description=(
            "Tu cartera real, derivada de un registro de movimientos que solo anade. "
            "Las posiciones no se editan: se derivan."
        ),
    )
    parser.add_argument("--store", type=Path, help="Carpeta del registro (por defecto portfolio/)")
    sub = parser.add_subparsers(dest="accion", required=True)

    anadir = sub.add_parser("add", help="Registrar una compra o venta")
    anadir.add_argument("operacion", choices=["buy", "sell"])
    anadir.add_argument("--symbol", required=True)
    anadir.add_argument("--quantity", type=D, required=True)
    anadir.add_argument("--price", type=D, required=True, help="Precio unitario pagado/cobrado")
    anadir.add_argument("--fee", type=D, default=D(0), help="Comision de ESTA operacion")
    anadir.add_argument("--date", help="AAAA-MM-DD; sin ella, ahora")

    efectivo = sub.add_parser("cash", help="Registrar un deposito o una retirada de efectivo")
    efectivo.add_argument("movimiento", choices=["deposit", "withdraw"])
    efectivo.add_argument("--amount", type=D, required=True)
    efectivo.add_argument("--date", help="AAAA-MM-DD; sin ella, ahora")

    importar = sub.add_parser("import", help="Importar el CSV del broker (formato Ghostfolio)")
    importar.add_argument("csv", type=Path)

    sub.add_parser("show", help="Ver posiciones abiertas, retiradas y efectivo")

    add_json_flag(parser)
    for subparser in sub.choices.values():
        add_json_flag(subparser, hereda=True)

    args = parser.parse_args(argv)
    salida = salida_de(args, f"portfolio {args.accion}")
    store = ActivityStore(args.store) if args.store else ActivityStore()

    if args.accion == "add":
        return _anadir(args, store, salida)
    if args.accion == "cash":
        return _efectivo(args, store, salida)
    if args.accion == "import":
        return _importar(args, store, salida)
    return _mostrar(store, salida)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
