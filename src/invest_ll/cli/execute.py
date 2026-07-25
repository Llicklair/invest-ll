"""`invest-ll-execute`: enviar una orden. **El único comando que puede mover dinero real.**

Está escrito para que sea difícil equivocarse, no para que sea cómodo:

- Sin configurar nada, **no sale nada**. El modo por defecto es simulación y el comando lo dice.
- El modo real exige acción explícita, credenciales separadas y haber operado antes en pruebas.
  Ninguna de las tres cosas basta por sí sola.
- **Cada orden se confirma escribiendo su cantidad**, no pulsando una tecla. Un "sí" distraído no
  debería mover 0,5 BTC.
- Todo lo enviado queda en el registro, **con el modo en el que salió**.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.errors import InvestLLError
from invest_ll.live.broker import (
    Broker,
    Confirmation,
    OrderRequest,
    Side,
    SimulatedBroker,
)
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import Real, Simulation, resolve_mode

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_CANCELADO = 4
SALIDA_ATENCION = 5


def _explicar_simulacion() -> None:
    print("MODO SIMULACION — no se ha enviado nada al exterior.")
    print()
    print("Para operar de verdad hacen falta CUATRO cosas, y ninguna basta por si sola:")
    print()
    print("  1. INVEST_LL_MODE=testnet (o =real)")
    print("  2. Las credenciales de ese modo, que son distintas entre si:")
    print("       pruebas -> INVEST_LL_TESTNET_KEY / INVEST_LL_TESTNET_SECRET")
    print("       real    -> INVEST_LL_LIVE_KEY / INVEST_LL_LIVE_SECRET")
    print("  3. Para el modo real: haber operado antes en pruebas")
    print("       (INVEST_LL_TESTNET_VERIFIED=1)")
    print("  4. Confirmar ESTA orden concreta cuando el comando lo pida")
    print()
    print("Empieza por testnet. Es donde se descubren los fallos sin pagarlos.")


def _pedir_confirmacion(request: OrderRequest, *, real: bool) -> bool:
    """Pide confirmar escribiendo la cantidad.

    Escribir la cantidad y no pulsar 's' es deliberado: obliga a mirar el número que se va a
    mover. Un "sí" distraído no debería ejecutar una orden de 0,5 BTC.
    """
    print()
    print("=" * 60)
    if real:
        print("  *** DINERO REAL ***")
    else:
        print("  Red de pruebas (dinero ficticio, ordenes reales)")
    print("=" * 60)
    print(f"  {request.side.value.upper():<6} {request.quantity} {request.symbol}")
    print("  a precio de mercado, ahora mismo")
    print("=" * 60)
    print()

    try:
        escrito = input(f"Escribe la cantidad exacta ({request.quantity}) para confirmar: ")
    except (EOFError, KeyboardInterrupt):
        return False

    if escrito.strip() != str(request.quantity):
        print("La cantidad no coincide. Cancelado, no se ha enviado nada.")
        return False
    return True


def _construir_broker(modo: object, exchange_id: str) -> Broker:
    if isinstance(modo, Simulation):
        return SimulatedBroker()

    from invest_ll.live.ccxt_broker import CcxtBroker, build_exchange

    return CcxtBroker(build_exchange(modo, exchange_id=exchange_id), mode=modo)  # type: ignore[arg-type]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-execute",
        description="Envia UNA orden. En simulacion no sale nada; el modo real exige confirmar.",
    )
    parser.add_argument("--symbol", required=True, help="Par, p.ej. BTC/USDT")
    parser.add_argument("--side", required=True, choices=[s.value for s in Side])
    parser.add_argument("--quantity", type=D, required=True)
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--ledger", type=Path, help="Carpeta del registro de ordenes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra lo que se enviaria y para, sin pedir confirmacion.",
    )

    args = parser.parse_args(argv)

    try:
        modo = resolve_mode()
    except InvestLLError as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_ERROR

    try:
        peticion = OrderRequest(
            symbol=args.symbol,
            side=Side(args.side),
            quantity=args.quantity,
            requested_at=datetime.now(UTC),
        )
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return SALIDA_ERROR

    print(f"Modo: {modo.name}")

    if isinstance(modo, Simulation):
        print()
        print(
            f"Se habria enviado: {peticion.side.value.upper()} {peticion.quantity} {peticion.symbol}"
        )
        print()
        _explicar_simulacion()
        return SALIDA_OK

    if args.dry_run:
        print()
        print(f"Se enviaria: {peticion.side.value.upper()} {peticion.quantity} {peticion.symbol}")
        print("(--dry-run: no se ha enviado nada ni se ha pedido confirmacion)")
        return SALIDA_OK

    es_real = isinstance(modo, Real)
    if not _pedir_confirmacion(peticion, real=es_real):
        print("Cancelado. No se ha enviado nada.")
        return SALIDA_CANCELADO

    try:
        broker = _construir_broker(modo, args.exchange)
    except (InvestLLError, ValueError, ImportError) as error:
        print(f"Error preparando el exchange: {error}", file=sys.stderr)
        return SALIDA_ERROR

    confirmacion = Confirmation.para(peticion, at=datetime.now(UTC))

    try:
        resultado = broker.submit(peticion, confirmation=confirmacion)
    except InvestLLError as error:
        print(f"Error al enviar: {error}", file=sys.stderr)
        return SALIDA_ERROR

    libro = ExecutionLedger(args.ledger) if args.ledger else ExecutionLedger()
    libro.record(resultado, mode_name=modo.name)

    print()
    print(resultado.describe())
    print()
    print(f"Registrado en {libro.path}")

    if resultado.needs_attention:
        print()
        print("[!] La orden NO salio exactamente como se pidio. Revisala en el exchange")
        print("    antes de volver a operar.")
        return SALIDA_ATENCION

    return SALIDA_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
