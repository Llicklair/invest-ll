"""Apoyo de los tests de la API: el cliente con tipos y los históricos de prueba.

Los históricos se guardan como los deja `invest-ll-fetch`, con su procedencia (`.meta.json`), en
`data/market/<proveedor>/...` relativo al directorio de trabajo del test, que es donde la API los
busca. Con procedencia el símbolo conserva su "/" (`BTC/USDT`) y actualizar sabe con qué
parámetros re-descargarlo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.series import PriceSeries
from invest_ll.fetch.provenance import Provenance
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.store import HistoryStore

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence

    import httpx
    from fastapi.testclient import TestClient

RAIZ = Path("data/market")


class Api:
    """El TestClient de FastAPI, con tipos.

    Starlette anota los parámetros del TestClient con `httpx._types.*`, que el comprobador de
    tipos no resuelve desde fuera de httpx: cada llamada sale "parcialmente desconocida" en modo
    estricto. En vez de relajar todos los ficheros de test, la frontera queda aquí, con un ignore
    puntual por método; la respuesta sí está tipada (`httpx.Response`).
    """

    __slots__ = ("_cliente",)

    def __init__(self, cliente: TestClient) -> None:
        self._cliente = cliente

    def get(
        self,
        ruta: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        respuesta = self._cliente.get(ruta, params=params, headers=headers)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return cast("httpx.Response", respuesta)

    def post(
        self, ruta: str, json: object = None, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        respuesta = self._cliente.post(ruta, json=json, headers=headers)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return cast("httpx.Response", respuesta)

    def post_crudo(self, ruta: str, contenido: str) -> httpx.Response:
        """Un cuerpo tal cual (p. ej. un JSON roto), como lo mandaría un cliente con un fallo."""
        respuesta = self._cliente.post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            ruta, content=contenido, headers={"content-type": "application/json"}
        )
        return cast("httpx.Response", respuesta)

    def put(self, ruta: str, json: object = None) -> httpx.Response:
        respuesta = self._cliente.put(ruta, json=json)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return cast("httpx.Response", respuesta)

    def delete(self, ruta: str) -> httpx.Response:
        respuesta = self._cliente.delete(ruta)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return cast("httpx.Response", respuesta)


GLD = "yfinance:GLD:DAY_1"
TLT = "yfinance:TLT:DAY_1"
BTC = "ccxt-binance:BTC/USDT:DAY_1"
COSTES = {"comision": "0.001", "slippage": "0.0005"}


def _fechas(n: int, hasta: date, *, cripto: bool) -> list[datetime]:
    """N días hasta `hasta` incluido: todos en cripto, solo laborables en bolsa."""
    fechas: list[datetime] = []
    dia = hasta
    while len(fechas) < n:
        if cripto or dia.weekday() < 5:
            fechas.append(datetime(dia.year, dia.month, dia.day, tzinfo=UTC))
        dia -= timedelta(days=1)
    return list(reversed(fechas))


def guardar(
    simbolo: str,
    cierres: Sequence[float],
    *,
    proveedor: str = "yfinance",
    hasta: date | None = None,
    procedencia: bool = True,
) -> str:
    """Escribe el histórico en `data/market` (relativo al cwd) y devuelve su id de la API."""
    cripto = proveedor.startswith("ccxt")
    fechas = _fechas(len(cierres), hasta or datetime.now(UTC).date(), cripto=cripto)
    barras = tuple(
        Bar(timestamp=f, open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000.0)
        for f, c in zip(fechas, cierres, strict=True)
    )
    serie = PriceSeries(
        symbol=simbolo, interval=Interval.DAY_1, calendar=Continuous24x7(), bars=barras
    )
    mercado = Market.CRYPTO if cripto else Market.EQUITY
    peticion = FetchRequest(
        symbol=simbolo,
        interval=Interval.DAY_1,
        start=barras[0].timestamp,
        end=barras[-1].timestamp,
        market=mercado,
    )
    meta = Provenance(
        provider=proveedor,
        symbol=simbolo,
        interval="DAY_1",
        market=mercado.value,
        downloaded_at=datetime(2026, 10, 1, tzinfo=UTC),
        range_start=barras[0].timestamp,
        range_end=barras[-1].timestamp,
        bar_count=len(barras),
        prices_adjusted=not cripto,
    )
    csv = HistoryStore(RAIZ).save(peticion, serie, meta)
    if not procedencia:
        csv.with_suffix(".meta.json").unlink()
    return f"{proveedor}:{simbolo}:DAY_1"


def subida(n: int, desde: float = 100.0, paso: float = 1.0) -> list[float]:
    return [desde + i * paso for i in range(n)]


def zigzag(n: int, desde: float = 100.0) -> list[float]:
    """Sube y baja: da operaciones a las estrategias y correlación imperfecta entre activos."""
    return [desde + (i % 20) * (1 if (i // 20) % 2 == 0 else -1) + i * 0.1 for i in range(n)]
