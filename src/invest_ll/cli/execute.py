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
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.emit import (
    AVISO_DINERO_REAL,
    AVISO_ORDEN_REVISAR,
    AVISO_SOLO_SIMULACION,
    Salida,
    add_json_flag,
    salida_de,
)
from invest_ll.errors import InvestLLError
from invest_ll.live.broker import (
    Broker,
    Confirmation,
    OrderRequest,
    Side,
)
from invest_ll.live.factory import construir_broker
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import OperatingMode, Real, Simulation, resolve_mode

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

D = Decimal

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_CANCELADO = 4
SALIDA_ATENCION = 5


def _explicar_simulacion(salida: Salida) -> None:
    salida.aviso(
        AVISO_SOLO_SIMULACION,
        "MODO SIMULACION: no se ha enviado nada al exterior. Operar de verdad exige modo, "
        "credenciales propias de ese modo, haber operado antes en pruebas, y confirmar la orden.",
        mostrar=False,
    )
    salida.linea("MODO SIMULACION — no se ha enviado nada al exterior.")
    salida.linea()
    salida.linea("Para operar de verdad hacen falta CUATRO cosas, y ninguna basta por si sola:")
    salida.linea()
    salida.linea("  1. INVEST_LL_MODE=testnet (o =real)")
    salida.linea("  2. Las credenciales de ese modo, que son distintas entre si:")
    salida.linea("       pruebas -> INVEST_LL_TESTNET_KEY / INVEST_LL_TESTNET_SECRET")
    salida.linea("       real    -> INVEST_LL_LIVE_KEY / INVEST_LL_LIVE_SECRET")
    salida.linea("  3. Para el modo real: haber operado antes en pruebas")
    salida.linea("       (INVEST_LL_TESTNET_VERIFIED=1)")
    salida.linea("  4. Confirmar ESTA orden concreta cuando el comando lo pida")
    salida.linea()
    salida.linea("Empieza por testnet. Es donde se descubren los fallos sin pagarlos.")


def _pedir_confirmacion(request: OrderRequest, *, real: bool, salida: Salida) -> bool:
    """Pide confirmar escribiendo la cantidad.

    Escribir la cantidad y no pulsar 's' es deliberado: obliga a mirar el número que se va a
    mover. Un "sí" distraído no debería ejecutar una orden de 0,5 BTC.

    **El formato de salida no entra aquí.** `--json` cambia cómo se comunica el resultado, nunca
    si hay que preguntar: en modo JSON el mensaje sale por stderr y se sigue esperando respuesta.
    Que un agente pueda leer la salida no significa que pueda ocupar el lugar de la persona.
    `tests/integration/test_cli_json.py` comprueba que en este cuerpo no aparece `json_mode`.
    """
    salida.linea()
    salida.linea("=" * 60)
    salida.linea("  *** DINERO REAL ***" if real else "  Red de pruebas (dinero ficticio)")
    salida.linea("=" * 60)
    salida.linea(f"  {request.side.value.upper():<6} {request.quantity} {request.symbol}")
    salida.linea("  a precio de mercado, ahora mismo")
    salida.linea("=" * 60)
    salida.linea()

    try:
        escrito = salida.pregunta(
            f"Escribe la cantidad exacta ({request.quantity}) para confirmar: "
        )
    except (EOFError, KeyboardInterrupt):
        return False

    if escrito.strip() != str(request.quantity):
        salida.linea("La cantidad no coincide. Cancelado, no se ha enviado nada.")
        return False
    return True


def _construir_broker(modo: OperatingMode, exchange_id: str) -> Broker:
    """Delega en la fabrica compartida: el panel construye el broker con la misma regla."""
    return construir_broker(modo, exchange_id=exchange_id)


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
    add_json_flag(parser)

    args = parser.parse_args(argv)
    salida = salida_de(args, "execute")

    try:
        modo = resolve_mode()
    except InvestLLError as error:
        return salida.error(str(error), SALIDA_ERROR)

    try:
        peticion = OrderRequest(
            symbol=args.symbol,
            side=Side(args.side),
            quantity=args.quantity,
            requested_at=datetime.now(UTC),
        )
    except ValueError as error:
        return salida.error(str(error), SALIDA_ERROR)

    # El modo va SIEMPRE, y va primero. Quien lea esta salida —persona o programa— tiene que
    # saber en que mundo ocurrio antes de leer ningun numero.
    salida.dato(
        mode=modo.name,
        symbol=peticion.symbol,
        side=peticion.side.value,
        quantity=peticion.quantity,
        submitted=False,
    )
    salida.linea(f"Modo: {modo.name}")

    if isinstance(modo, Simulation):
        salida.linea()
        salida.linea(
            f"Se habria enviado: {peticion.side.value.upper()} {peticion.quantity} "
            f"{peticion.symbol}"
        )
        salida.linea()
        _explicar_simulacion(salida)
        return salida.cerrar(SALIDA_OK)

    if args.dry_run:
        salida.linea()
        salida.linea(
            f"Se enviaria: {peticion.side.value.upper()} {peticion.quantity} {peticion.symbol}"
        )
        salida.linea("(--dry-run: no se ha enviado nada ni se ha pedido confirmacion)")
        salida.dato(dry_run=True)
        return salida.cerrar(SALIDA_OK)

    es_real = isinstance(modo, Real)
    if es_real:
        salida.aviso(
            AVISO_DINERO_REAL, "Esta orden mueve DINERO REAL en el exchange.", mostrar=False
        )

    if not _pedir_confirmacion(peticion, real=es_real, salida=salida):
        salida.linea("Cancelado. No se ha enviado nada.")
        salida.dato(cancelled=True)
        return salida.cerrar(SALIDA_CANCELADO)

    try:
        broker = _construir_broker(modo, args.exchange)
    except (InvestLLError, ValueError, ImportError) as error:
        return salida.error(f"preparando el exchange: {error}", SALIDA_ERROR)

    confirmacion = Confirmation.para(peticion, at=datetime.now(UTC))

    try:
        resultado = broker.submit(peticion, confirmation=confirmacion)
    except InvestLLError as error:
        return salida.error(f"al enviar: {error}", SALIDA_ERROR)

    libro = ExecutionLedger(args.ledger) if args.ledger else ExecutionLedger()
    libro.record(resultado, mode_name=modo.name)

    salida.dato(
        submitted=True,
        ledger=libro.path,
        needs_attention=resultado.needs_attention,
    )

    salida.linea()
    salida.linea(resultado.describe())
    salida.linea()
    salida.linea(f"Registrado en {libro.path}")

    if resultado.needs_attention:
        salida.aviso(
            AVISO_ORDEN_REVISAR,
            "La orden NO salio exactamente como se pidio. Revisala en el exchange antes de "
            "volver a operar.",
            mostrar=False,
        )
        salida.linea()
        salida.linea("[!] La orden NO salio exactamente como se pidio. Revisala en el exchange")
        salida.linea("    antes de volver a operar.")
        return salida.cerrar(SALIDA_ATENCION)

    return salida.cerrar(SALIDA_OK)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
