"""Los históricos ya descargados: descubrirlos y resumir cómo va cada uno.

Vive en la capa de descarga, junto a `fetch.store` que decide el formato en disco
(`<raiz>/<proveedor>/<activo>/<intervalo>.csv` + `.meta.json`), para que lo consuman tanto el
panel como el chat sin que uno dependa del otro. `invest_ll.dashboard.data` lo re-exporta.
"""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll import nombres
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
        return _calendario(cripto=self.is_crypto)

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

        Se guarda en memoria por el CONTENIDO del fichero: el panel pide la misma serie en cada
        pantalla y validarla cuesta casi un segundo para trece historicos. La clave es la huella
        de los bytes y no la fecha de modificacion, que en Windows puede no cambiar entre dos
        escrituras seguidas: una descarga nueva cambia la huella y se vuelve a leer, nunca se
        sirve una serie vieja.
        """
        huella = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return _completa(
            self.path.resolve(), huella, self.path, self.symbol, self.interval, self.is_crypto
        )


def _calendario(*, cripto: bool) -> MarketCalendar:
    return Continuous24x7() if cripto else ExchangeCalendarAdapter("XNYS")


@lru_cache(maxsize=128)
def _completa(
    clave: Path, huella: str, ruta: Path, symbol: str, interval: Interval, cripto: bool
) -> PriceSeries:
    """La serie completa de un fichero con esa huella. `clave` y `huella` solo indexan la cache."""
    del clave, huella
    serie, _ = load_series(
        ruta,
        symbol=symbol,
        interval=interval,
        calendar=_calendario(cripto=cripto),
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


# Ventanas en sesiones bursátiles: las usa la comparación normalizada (`normalised_series`).
VENTANAS: tuple[tuple[str, int], ...] = (
    ("1 mes", 21),
    ("3 meses", 63),
    ("1 año", 252),
    ("5 años", 1260),
)

# Ventanas de la tabla de rendimiento, en DÍAS NATURALES. Contarlas en velas daba a cada mercado
# su propio reloj: 252 velas son un año de bolsa, pero ocho meses y medio de cripto, que cotiza
# los fines de semana. El "1 año" de Bitcoin era mentira y su "1 mes" no casaba con el de Inicio.
VENTANAS_DIAS: tuple[tuple[str, int], ...] = (
    ("1 mes", 30),
    ("3 meses", 91),
    ("1 año", 365),
    ("5 años", 1826),
)
SEMANA_DIAS = 7

# Los nombres llanos viven en un solo sitio (`invest_ll.nombres`); se re-exportan con el nombre de
# antes para quien ya los importaba de aquí.
NOMBRES = nombres.NOMBRES


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


# Sesiones que cubría la sparkline cuando se contaba en velas; se conserva el nombre para quien
# lo importaba. La de la tabla cubre `SPARKLINE_DIAS`.
SPARKLINE_SESIONES = 63

# Días naturales que cubre la sparkline de cada fila (3 meses), desde el mismo cierre con el que se
# mide "3 meses". Una sola imagen por fila, sin ejes: es la única redundancia visual que la tabla
# se permite, igual que hace CoinMarketCap.
SPARKLINE_DIAS = 91


def desde_hace(bars: Sequence[Bar], dias: int) -> int | None:
    """Posición del último cierre de hace `dias` días naturales (o de antes), contando desde el
    último. `None` si el histórico no llega tan atrás: no se sabe, no es un 0%."""
    if not bars:
        return None
    limite = bars[-1].timestamp - timedelta(days=dias)
    posicion = bisect_right([b.timestamp for b in bars], limite) - 1
    return posicion if posicion >= 0 else None


def _rendimiento_en_dias(bars: Sequence[Bar], dias: int) -> float | None:
    """Variación desde el cierre de hace `dias` días naturales. `None` si no hay histórico."""
    posicion = desde_hace(bars, dias)
    if posicion is None or bars[posicion].close == 0:
        return None
    return bars[-1].close / bars[posicion].close - 1


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
            "que es": nombres.nombre_conocido(activo.symbol) or "—",
            "ultimo": round(cierres[-1], 2),
        }

        dia = _rendimiento(cierres, 1)
        semana = _rendimiento_en_dias(serie.bars, SEMANA_DIAS)
        fila["1 dia"] = None if dia is None else round(dia * 100, 1)
        fila["1 semana"] = None if semana is None else round(semana * 100, 1)

        for etiqueta, dias in VENTANAS_DIAS:
            rendimiento = _rendimiento_en_dias(serie.bars, dias)
            fila[etiqueta] = None if rendimiento is None else round(rendimiento * 100, 1)

        ytd = _ytd(serie.bars)
        fila["YTD"] = None if ytd is None else round(ytd * 100, 1)

        fila["desde maximo"] = round((cierres[-1] / maximo - 1) * 100, 1) if maximo else None
        inicio_chispa = desde_hace(serie.bars, SPARKLINE_DIAS) or 0
        fila["sparkline"] = [round(c, 4) for c in cierres[inicio_chispa:]]
        fila["desde"] = serie.bars[0].timestamp.date()
        fila["datos hasta"] = serie.bars[-1].timestamp.date()
        filas.append(fila)

    return filas
