"""Paneles de precios sintéticos para el panel v2: pequeños, deterministas y con el formato real.

Se escriben como los deja `invest-ll-quant download` (`data/market/binance-universe/
klines_1d.parquet` y `data/market/etf-universe/etf_1d.parquet`, en formato largo), relativos al
directorio de trabajo del test. Así la API los lee por el mismo camino que los de verdad, pero con
unos pocos activos y unos pocos años: el catálogo entero se calcula en un momento.
"""

# Frontera con pandas, sin tipos en el proyecto (como en quant/panel.py).
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, Literal

import pandas as pd

from invest_ll.quant.etf_study import ASSETS, CASH

CRIPTO: Final = Path("data/market/binance-universe/klines_1d.parquet")
BOLSA: Final = Path("data/market/etf-universe/etf_1d.parquet")
DESDE: Final = date(2024, 1, 1)
HASTA: Final = date(2026, 10, 16)
MONEDAS: Final = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "USDCUSDT")


def dia(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()) // 86_400


def _precio(t: int, base: float, tendencia: float, fase: float) -> float:
    return base * (1 + tendencia) ** t * (1 + 0.08 * math.sin(t / 11 + fase))


def _btc(t: int, total: int, final: Literal["sube", "baja"]) -> float:
    """Sube siempre; con `baja`, los últimos 60 días caen un 30 %."""
    precio = 20_000.0 * 1.002**t
    if final == "baja" and t > total - 60:
        tope = 20_000.0 * 1.002 ** (total - 60)
        precio = tope * (1 - 0.3 * (t - (total - 60)) / 60)
    return precio


def filas_cripto(
    desde: date = DESDE, hasta: date = HASTA, *, btc: Literal["sube", "baja"] = "sube"
) -> pd.DataFrame:
    total = (hasta - desde).days + 1
    filas: list[dict[str, object]] = []
    for j, simbolo in enumerate(MONEDAS):
        for t in range(total):
            if simbolo == "BTCUSDT":
                cierre = _btc(t, total, btc)
            elif simbolo == "USDCUSDT":
                cierre = 1.0
            else:
                cierre = _precio(t, 10.0 * (j + 1), 0.001 * (j - 2), j)
            filas.append(
                {
                    "symbol": simbolo,
                    "day": dia(desde) + t,
                    "open": cierre,
                    "high": cierre * 1.01,
                    "low": cierre * 0.99,
                    "close": cierre,
                    "volume": 1_000.0,
                    "quote_volume": 50_000_000.0 * (len(MONEDAS) - j),
                    "trades": 100,
                }
            )
    return pd.DataFrame(filas)


SESIONES_DE_CAIDA: Final = 280


def filas_bolsa(
    desde: date = DESDE, hasta: date = HASTA, *, cae: str | None = None
) -> pd.DataFrame:
    """Los ocho fondos y SHY; con `cae`, ese fondo lleva sus últimas 280 sesiones bajando."""
    filas: list[dict[str, object]] = []
    sesiones: list[date] = []
    d = desde
    while d <= hasta:
        if d.weekday() < 5:
            sesiones.append(d)
        d += timedelta(days=1)
    desde_la_caida = len(sesiones) - SESIONES_DE_CAIDA
    for j, simbolo in enumerate((*ASSETS, CASH)):
        for t, sesion in enumerate(sesiones):
            # SHY, la liquidez de los fondos, sube despacio y sin vaivenes.
            cierre = 80.0 * 1.0001**t if simbolo == CASH else _precio(t, 50.0 + 10 * j, 0.0004, j)
            if simbolo == cae and t > desde_la_caida:
                # Un año largo bajando sin respiro: el freno de tendencia lo deja fuera.
                cierre = _precio(desde_la_caida, 50.0 + 10 * j, 0.0004, j) * 0.997 ** (
                    t - desde_la_caida
                )
            filas.append(
                {
                    "symbol": simbolo,
                    "day": dia(sesion),
                    "open": cierre,
                    "high": cierre * 1.005,
                    "low": cierre * 0.995,
                    "close": cierre,
                    "quote_volume": 1e9,
                }
            )
    return pd.DataFrame(filas)


def escribir_paneles(
    raiz: Path = Path(),
    *,
    cripto: bool = True,
    bolsa: bool = True,
    btc: Literal["sube", "baja"] = "sube",
    hasta: date = HASTA,
    cae: str | None = None,
) -> None:
    """Escribe los paneles sintéticos bajo `raiz` (por defecto, el directorio de trabajo)."""
    if cripto:
        (raiz / CRIPTO).parent.mkdir(parents=True, exist_ok=True)
        filas_cripto(btc=btc, hasta=hasta).to_parquet(raiz / CRIPTO)
    if bolsa:
        (raiz / BOLSA).parent.mkdir(parents=True, exist_ok=True)
        filas_bolsa(hasta=hasta, cae=cae).to_parquet(raiz / BOLSA)
