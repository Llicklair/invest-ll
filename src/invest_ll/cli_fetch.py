"""Línea de comandos para descargar histórico (T031, T054).

Códigos de salida pensados para encadenarla en un script:

- `0` correcto
- `1` error de configuración o de datos
- `2` activo desconocido o rango sin datos
- `3` descarga correcta **pero con discrepancias detectadas** — para que un script no se trague
  en silencio que el proveedor revisó datos que ya tenías
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.errors import InvestLLError
from invest_ll.fetch.errors import NoDataError, UnknownSymbolError
from invest_ll.fetch.protocol import MarketDataProvider
from invest_ll.fetch.providers.crypto import CcxtProvider
from invest_ll.fetch.providers.equity import YFinanceProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import fetch_history, verify_history
from invest_ll.fetch.store import HistoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invest-ll-fetch",
        description="Descarga historico real de mercado para backtestear. Solo lectura.",
        epilog=(
            "Aviso: los precios de bolsa se guardan AJUSTADOS por splits y dividendos. "
            "Los proveedores gratuitos no incluyen empresas que dejaron de cotizar, asi que "
            "cualquier backtest de bolsa sale mejor de lo que la realidad fue."
        ),
    )
    parser.add_argument("symbol", help="activo, por ejemplo BTC/USDT o AAPL")
    parser.add_argument(
        "--market", required=True, choices=[m.value for m in Market], help="cripto o bolsa"
    )
    parser.add_argument(
        "--interval", default="DAY_1", choices=[i.name for i in Interval], help="granularidad"
    )
    parser.add_argument("--start", help="fecha inicial, formato AAAA-MM-DD")
    parser.add_argument("--end", help="fecha final, formato AAAA-MM-DD")
    parser.add_argument("--exchange", default="binance", help="exchange de cripto (ccxt)")
    parser.add_argument("--data-dir", type=Path, default=None, help="raiz de almacenamiento")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="reexamina un historico ya descargado contra el proveedor; no modifica nada",
    )
    return parser


def _fecha(texto: str | None, campo: str) -> datetime:
    if not texto:
        raise ValueError(f"falta --{campo}")
    return datetime.fromisoformat(texto).replace(tzinfo=UTC)


def _provider(args: argparse.Namespace) -> MarketDataProvider:
    if args.market == Market.CRYPTO.value:
        return CcxtProvider(args.exchange)
    return YFinanceProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        request = FetchRequest(
            symbol=args.symbol,
            interval=Interval[args.interval],
            start=_fecha(args.start, "start"),
            end=_fecha(args.end, "end"),
            market=Market(args.market),
        )
        provider = _provider(args)
        store = HistoryStore(args.data_dir)

        if args.verify:
            discrepancias = verify_history(request, provider, store)
            if not discrepancias:
                print("Sin discrepancias: el historico coincide con el proveedor.")
                return 0
            print(f"[!] {len(discrepancias)} discrepancia(s). NO se ha modificado nada:")
            for d in discrepancias[:20]:
                print(f"    {d.describe()}")
            return 3

        resultado = fetch_history(request, provider, store, now=datetime.now(UTC))

    except UnknownSymbolError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except NoDataError as error:
        print(f"sin datos: {error}", file=sys.stderr)
        return 2
    except (InvestLLError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Historico guardado en {resultado.path}")
    print(f"  Velas nuevas  {resultado.added_count}")
    print(f"  Peticiones    {resultado.requests_made}")
    print(resultado.provenance.describe())

    if resultado.warnings:
        # Solo ASCII: en la consola de Windows (cp1252) un guion largo sale como un rombo negro.
        print("\n[!] Avisos de calidad - leelos antes de creerte un backtest:")
        for aviso in resultado.warnings:
            print(f"    - {aviso.message}")

    if resultado.discrepancies:
        print(
            f"\n[!] {len(resultado.discrepancies)} discrepancia(s): el proveedor devolvio valores "
            "distintos para fechas que ya tenias."
        )
        print("    Tu historico local NO se ha modificado.")
        if resultado.discrepancy_path:
            print(f"    La version del proveedor esta en {resultado.discrepancy_path}")
        for d in resultado.discrepancies[:10]:
            print(f"    - {d.describe()}")
        return 3

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
