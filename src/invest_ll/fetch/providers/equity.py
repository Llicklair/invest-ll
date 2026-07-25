"""Proveedor de histórico de bolsa sobre `yfinance` (T029).

`auto_adjust=True` es lo que hace útil este proveedor: devuelve precios ya corregidos por splits y
dividendos. Sin eso, cada división de acciones aparecería como un desplome que nunca ocurrió.

**Fragilidad conocida y aceptada**: `yfinance` no es una API oficial. Raspa Yahoo Finance y se
rompe cuando Yahoo cambia el formato. No es una posibilidad remota, ocurre cada cierto tiempo.
Está aquí porque es la única fuente gratuita con precios ajustados; vive tras el protocolo para que
el recambio cueste un fichero.

Nota sobre tipos: frontera con una librería sin tipado completo, igual que `crypto.py`.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from invest_ll.data.bar import Bar, Interval
from invest_ll.fetch.errors import ProviderUnavailableError, UnknownSymbolError
from invest_ll.fetch.protocol import ProviderCapabilities

INTERVALOS: dict[Interval, str] = {
    Interval.MINUTE_1: "1m",
    Interval.MINUTE_5: "5m",
    Interval.MINUTE_15: "15m",
    Interval.HOUR_1: "1h",
    Interval.DAY_1: "1d",
}

UN_DIA = Interval.DAY_1.duration


def normalize_daily(momento: datetime, interval: Interval) -> datetime:
    """Lleva las marcas diarias a medianoche UTC.

    Yahoo devuelve las velas diarias con la hora local del mercado: 05:00 UTC en invierno y 04:00
    en verano, porque Nueva York cambia de horario. El fin de semana del cambio, el salto entre
    dos velas es de 71 horas en vez de 72 y deja de ser múltiplo del intervalo.

    Una vela diaria representa una sesión entera, no un instante, así que esa hora es ruido del
    proveedor. Se limpia aquí, en el borde, para que no se propague al resto del sistema.

    En intradía **no se toca**: ahí la hora es el dato.
    """
    if interval.duration < UN_DIA:
        return momento
    return momento.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class YFinanceProvider:
    """Histórico de bolsa con precios ajustados por splits y dividendos."""

    __slots__ = ("_capabilities",)

    def __init__(self) -> None:
        self._capabilities = ProviderCapabilities(
            name="yfinance",
            supported_intervals=frozenset(INTERVALOS),
            adjusts_prices=True,
            # Yahoo no sirve el histórico de empresas que dejaron de cotizar. De ahí el aviso de
            # sesgo de supervivencia: se advierte, no se corrige.
            includes_delisted=False,
            max_bars_per_request=10_000,
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def fetch(
        self,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        import yfinance

        try:
            frame = yfinance.Ticker(symbol).history(
                start=start,
                end=end,
                interval=INTERVALOS[interval],
                auto_adjust=True,  # precios ajustados: la razón de usar este proveedor
                actions=False,
                raise_errors=True,
            )
        except Exception as error:
            mensaje = str(error).lower()
            if "no data found" in mensaje or "delisted" in mensaje or "not found" in mensaje:
                raise UnknownSymbolError(
                    f"Yahoo no tiene datos para el activo {symbol!r}"
                ) from error
            raise ProviderUnavailableError(f"yfinance: {error}") from error

        if frame.empty:
            return []

        bars: list[Bar] = []
        for marca, fila in frame.iterrows():
            momento = marca.to_pydatetime()
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=UTC)
            else:
                momento = momento.astimezone(UTC)

            momento = normalize_daily(momento, interval)

            volumen = float(fila["Volume"])
            bars.append(
                Bar(
                    timestamp=momento,
                    open=float(fila["Open"]),
                    high=float(fila["High"]),
                    low=float(fila["Low"]),
                    close=float(fila["Close"]),
                    volume=max(volumen, 0.0),
                )
            )

        return bars

    def __repr__(self) -> str:
        return "YFinanceProvider()"
