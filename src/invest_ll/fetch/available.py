"""Los históricos ya descargados: descubrirlos y resumir cómo va cada uno.

Vive en la capa de descarga, junto a `fetch.store` que decide el formato en disco
(`<raiz>/<proveedor>/<activo>/<intervalo>.csv` + `.meta.json`), para que lo consuman tanto el
panel como el chat sin que uno dependa del otro. `invest_ll.dashboard.data` lo re-exporta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter, MarketCalendar
from invest_ll.data.loader import load_series
from invest_ll.fetch.provenance import Provenance

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.data.bar import Bar
    from invest_ll.data.loader import DataWarning
    from invest_ll.data.series import PriceSeries

RAIZ_DATOS = Path("data/market")
PROVEEDORES_CRIPTO = ("ccxt",)


@dataclass(frozen=True, slots=True)
class AvailableAsset:
    """Un histórico ya descargado, listo para usar."""

    symbol: str
    provider: str
    interval: Interval
    path: Path
    provenance: Provenance | None

    @property
    def is_crypto(self) -> bool:
        return self.provider.startswith(PROVEEDORES_CRIPTO)

    @property
    def label(self) -> str:
        return f"{self.symbol} ({self.interval.name})"

    def calendar(self) -> MarketCalendar:
        return Continuous24x7() if self.is_crypto else ExchangeCalendarAdapter("XNYS")

    def load(self) -> PriceSeries:
        """Para **medir**: respeta la reserva de datos, igual que la linea de comandos."""
        serie, _ = self.load_con_avisos()
        return serie

    def load_con_avisos(self) -> tuple[PriceSeries, tuple[DataWarning, ...]]:
        """Lo mismo, con los avisos que el panel debe poder enseñar (recorte incluido)."""
        return load_series(
            self.path,
            symbol=self.symbol,
            interval=self.interval,
            calendar=self.calendar(),
        )

    def load_completa(self) -> PriceSeries:
        """Para **mirar el mercado**: todo el histórico, sin recortar.

        Ver el precio de ayer no contamina ninguna decisión de estrategia, y ocultarlo sí hace
        daño: al fijar una reserva, el panel pasó a mostrar precios de año y medio antes sin
        decirlo. La reserva protege lo que se **mide**, no lo que se **mira**.
        """
        serie, _ = load_series(
            self.path,
            symbol=self.symbol,
            interval=self.interval,
            calendar=self.calendar(),
            use_reserved=True,
        )
        return serie


def discover_assets(root: Path = RAIZ_DATOS) -> list[AvailableAsset]:
    """Encuentra los históricos descargados.

    Devuelve lista vacía si no hay nada, en vez de fallar: es el estado normal antes de la
    primera descarga y el panel debe poder decirlo con claridad.
    """
    if not root.exists():
        return []

    encontrados: list[AvailableAsset] = []
    for csv in sorted(root.rglob("*.csv")):
        # <raiz>/<proveedor>/<activo>/<intervalo>.csv — las discrepancias viven aparte.
        if "discrepancias" in csv.parts:
            continue
        try:
            interval = Interval[csv.stem]
        except KeyError:
            continue

        activo = csv.parent.name
        proveedor = csv.parent.parent.name

        meta = csv.with_suffix(".meta.json")
        provenance: Provenance | None = None
        if meta.exists():
            try:
                provenance = Provenance.from_json(meta.read_text(encoding="utf-8"))
            except (ValueError, KeyError):  # pragma: no cover - metadatos corruptos
                provenance = None

        encontrados.append(
            AvailableAsset(
                symbol=provenance.symbol if provenance else activo,
                provider=proveedor,
                interval=interval,
                path=csv,
                provenance=provenance,
            )
        )
    return encontrados


# Ventanas para la tabla de rendimiento, en sesiones bursátiles.
VENTANAS: tuple[tuple[str, int], ...] = (
    ("1 mes", 21),
    ("3 meses", 63),
    ("1 año", 252),
    ("5 años", 1260),
)

NOMBRES = {
    "GLD": "Oro",
    "TLT": "Bonos EE.UU. largo plazo",
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "XLK": "Tecnologia",
    "XLF": "Finanzas",
    "XLE": "Energia",
    "XLV": "Salud",
    "XLP": "Consumo basico",
    "XLU": "Servicios publicos",
    "AAPL": "Apple",
    "BTC/USDT": "Bitcoin",
}


def _rendimiento(cierres: list[float], periodos: int) -> float | None:
    """Variación sobre los últimos N periodos. `None` si no hay histórico suficiente.

    Devolver `None` y no 0 es deliberado: un activo sin datos suficientes no ha rendido un 0%,
    simplemente no se sabe. Confundir ambas cosas mete un activo inexistente en una comparación.
    """
    if len(cierres) <= periodos:
        return None
    anterior = cierres[-periodos - 1]
    if anterior == 0:
        return None
    return cierres[-1] / anterior - 1


# Sesiones que cubre la sparkline de cada fila (~3 meses). Una sola imagen por fila, sin ejes:
# es la única redundancia visual que la tabla se permite, igual que hace CoinMarketCap.
SPARKLINE_SESIONES = 63


def _ytd(bars: Sequence[Bar]) -> float | None:
    """Variación desde el último cierre del año anterior. `None` si el histórico no llega."""
    if not bars:
        return None
    anho_actual = bars[-1].timestamp.year
    for barra in reversed(bars):
        if barra.timestamp.year < anho_actual:
            return bars[-1].close / barra.close - 1 if barra.close else None
    return None


def market_overview(assets: Sequence[AvailableAsset]) -> list[dict[str, object]]:
    """Una fila por activo, al estilo de la tabla principal de CoinMarketCap — sin sus anzuelos.

    Lo copiado: densidad, variaciones por ventana, una sparkline por fila, ordenación por
    columna. Lo descartado a propósito: el 1h%% (ninguna decisión de aportación cambia por la
    última hora) y todo el catálogo de enganche (tendencias, ganadores del día, sentimiento).

    **La distancia al máximo es la columna que menos se mira y más importa.** Un activo que subió
    un 40%% en el año pero está un 30%% por debajo de su pico no está "yendo bien": está
    recuperándose de una caída que alguien sufrió. CoinMarketCap la esconde en la página de
    detalle; CoinGecko la trata como dato de primera clase. Aquí es una columna.
    """
    filas: list[dict[str, object]] = []

    for activo in assets:
        try:
            serie = activo.load_completa()
        except Exception:
            continue

        cierres = [b.close for b in serie.bars]
        if not cierres:
            continue

        maximo = max(cierres)
        fila: dict[str, object] = {
            "activo": activo.symbol,
            "que es": NOMBRES.get(activo.symbol, "—"),
            "ultimo": round(cierres[-1], 2),
        }

        dia = _rendimiento(cierres, 1)
        semana = _rendimiento(cierres, 5)
        fila["1 dia"] = None if dia is None else round(dia * 100, 1)
        fila["1 semana"] = None if semana is None else round(semana * 100, 1)

        for etiqueta, periodos in VENTANAS:
            rendimiento = _rendimiento(cierres, periodos)
            fila[etiqueta] = None if rendimiento is None else round(rendimiento * 100, 1)

        ytd = _ytd(serie.bars)
        fila["YTD"] = None if ytd is None else round(ytd * 100, 1)

        fila["desde maximo"] = round((cierres[-1] / maximo - 1) * 100, 1) if maximo else None
        fila["sparkline"] = [round(c, 4) for c in cierres[-SPARKLINE_SESIONES:]]
        fila["desde"] = serie.bars[0].timestamp.date()
        fila["datos hasta"] = serie.bars[-1].timestamp.date()
        filas.append(fila)

    return filas
