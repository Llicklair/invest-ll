"""`invest-ll-generate`: genera las decisiones del LLM y las guarda.

Está separado de `invest-ll-compare` a propósito. Generar cuesta tiempo y cuota; comparar es
gratis y se puede repetir. Mezclarlos haría que cada comparación volviera a preguntar.

Lo que se guarda aquí es lo que después hace reproducible el experimento: `invest-ll-compare
--recorded` lee estas decisiones y no consulta a nadie.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.cli.compare import SALIDA_ERROR, SALIDA_NO_ENCONTRADO, SALIDA_OK, cargar_series
from invest_ll.cli.emit import AVISO_FALLOS_GENERACION, add_json_flag, salida_de
from invest_ll.data.bar import Interval
from invest_ll.data.universe import build_universe
from invest_ll.decision.cache import DecisionStore
from invest_ll.decision.cli_provider import ClaudeCliProvider
from invest_ll.decision.models import DecisionRequest
from invest_ll.decision.prompt import INSTRUCCIONES_VERSION, render_context, symbol_map
from invest_ll.decision.schema import DecisionParseError, DecisionUnavailableError
from invest_ll.engine.universe_view import UniverseView
from invest_ll.errors import InvestLLError
from invest_ll.strategy.llm import CADA_MES

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

SALIDA_CANCELADO = 4
SEGUNDOS_POR_DECISION = 7


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-ll-generate",
        description="Genera decisiones del LLM y las guarda para poder repetir el experimento.",
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="Donde guardar las decisiones")
    parser.add_argument("--interval", default="DAY_1")
    parser.add_argument("--every", type=int, default=CADA_MES)
    parser.add_argument("--model", default="claude-opus-4-6")
    parser.add_argument("--limit", type=int, help="Genera solo las N primeras (para probar)")
    parser.add_argument("--yes", action="store_true", help="No preguntar antes de empezar")
    add_json_flag(parser)

    args = parser.parse_args(argv)
    salida = salida_de(args, "generate")

    try:
        universo = build_universe(cargar_series(args.paths, Interval[args.interval]))
    except FileNotFoundError as error:
        return salida.error(str(error), SALIDA_NO_ENCONTRADO)
    except (InvestLLError, KeyError, ValueError) as error:
        return salida.error(str(error), SALIDA_ERROR)

    almacen = DecisionStore(args.out)
    proveedor = ClaudeCliProvider(model=args.model)

    # Los puntos de decision, calculados igual que los recorre LLMStrategy.
    cursores = list(range(0, len(universo), args.every))
    if args.limit:
        cursores = cursores[: args.limit]

    peticiones: list[DecisionRequest] = []
    for cursor in cursores:
        vista = UniverseView(universe=universo, cursor=cursor)
        peticiones.append(
            DecisionRequest(
                timestamp=vista.current_timestamp,
                symbols=tuple(vista.symbols),
                market_context=render_context(vista),
                instructions_version=INSTRUCCIONES_VERSION,
                model=args.model,
                symbol_map=tuple(symbol_map(vista).items()),
            )
        )

    pendientes = [p for p in peticiones if not almacen.has(p.cache_key)]
    ya_estan = len(peticiones) - len(pendientes)

    salida.dato(
        universe={"periods": len(universo), "symbols": list(universo.symbols)},
        decision_points=len(peticiones),
        already_cached=ya_estan,
        pending=len(pendientes),
        model=args.model,
        out=args.out,
    )

    salida.linea(f"Universo: {len(universo)} periodos, {len(universo.symbols)} activos")
    salida.linea(f"Puntos de decision: {len(peticiones)} (cada {args.every} periodos)")
    if ya_estan:
        salida.linea(f"  Ya generadas: {ya_estan} — no se vuelven a pedir")

    if not pendientes:
        salida.linea("\nNo hay nada que generar. Todas las decisiones estan ya guardadas.")
        salida.dato(generated=0)
        return salida.cerrar(SALIDA_OK)

    minutos = len(pendientes) * SEGUNDOS_POR_DECISION / 60
    salida.linea(f"  Por generar: {len(pendientes)} (~{minutos:.0f} min, secuencial)")
    salida.linea(f"  Modelo: {args.model} · via CLI, con tu suscripcion")

    if not args.yes:
        # `--json` NO exime de confirmar: gastar cuota es una accion, no un formato de salida.
        try:
            respuesta = salida.pregunta("\nContinuar? [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            respuesta = ""
        if respuesta != "s":
            salida.linea("Cancelado. No se ha gastado nada.")
            salida.dato(cancelled=True)
            return salida.cerrar(SALIDA_CANCELADO)

    salida.linea()
    fallos: list[str] = []
    inicio = time.monotonic()

    for i, peticion in enumerate(pendientes, start=1):
        etiqueta = peticion.timestamp.date()
        try:
            decision = proveedor.decide(peticion)
        except (DecisionParseError, DecisionUnavailableError) as error:
            # Un fallo no detiene la generacion: se anota y se sigue. Es distinto de un fallo
            # durante un backtest, donde si detiene -- aqui todavia no hay ningun resultado que
            # pudiera quedar falseado.
            fallos.append(f"{etiqueta}: {error}")
            salida.linea(f"  [{i}/{len(pendientes)}] {etiqueta}  FALLO: {str(error)[:60]}")
            continue

        almacen.put(peticion.cache_key, decision)
        elegido = decision.chosen or "fuera del mercado"
        salida.linea(f"  [{i}/{len(pendientes)}] {etiqueta}  -> {elegido}")

    transcurrido = (time.monotonic() - inicio) / 60
    generadas = len(pendientes) - len(fallos)

    salida.dato(generated=generadas, failed=len(fallos), failures=fallos, minutes=transcurrido)

    salida.linea()
    salida.linea(f"Generadas {generadas} de {len(pendientes)} en {transcurrido:.1f} min")
    salida.linea(f"Guardadas en {args.out}")

    if fallos:
        salida.aviso(
            AVISO_FALLOS_GENERACION,
            f"{len(fallos)} decision(es) fallaron y NO se guardaron. Mientras falte alguna, "
            "invest-ll-compare se negara a evaluar el LLM en vez de rellenar el hueco con "
            "una suposicion.",
            mostrar=False,
        )
        salida.linea()
        salida.linea(f"[!] {len(fallos)} decision(es) fallaron y NO se guardaron:")
        for fallo in fallos[:5]:
            salida.linea(f"    {fallo}")
        salida.linea()
        salida.linea("    Vuelve a lanzar el comando: las que ya estan no se repiten.")
        salida.linea("    Mientras falte alguna, invest-ll-compare se negara a evaluar el LLM")
        salida.linea("    en vez de rellenar el hueco con una suposicion.")

    salida.linea()
    salida.linea("Ahora puedes comparar sin gastar nada mas:")
    salida.linea(f"  uv run invest-ll-compare {' '.join(str(p) for p in args.paths)} \\")
    salida.linea("      --strategies llm,momentum --commission 0.001 --slippage 0.0005 \\")
    salida.linea(f"      --recorded {args.out} --model {args.model} --every {args.every}")

    return salida.cerrar(SALIDA_OK if not fallos else SALIDA_ERROR)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
