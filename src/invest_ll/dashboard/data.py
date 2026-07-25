"""Lógica del panel, separada de la presentación.

Aquí vive todo lo que se puede probar: descubrir qué hay descargado, cargarlo y convertir los
informes en tablas. La interfaz de Streamlit solo dibuja lo que esto devuelve.

La separación no es estética. Un panel donde la lógica vive dentro de los widgets no se puede
testear, y un panel que muestra cifras de dinero sin tests es justo lo que este proyecto lleva
toda la sesión evitando.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter, MarketCalendar
from invest_ll.data.loader import load_series
from invest_ll.fetch.provenance import Provenance

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.data.series import PriceSeries
    from invest_ll.report.report import BacktestReport

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
        serie, _ = load_series(
            self.path,
            symbol=self.symbol,
            interval=self.interval,
            calendar=self.calendar(),
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


def equity_table(report: BacktestReport) -> list[dict[str, object]]:
    """Curva de patrimonio en formato tabla, lista para graficar."""
    return [
        {"fecha": momento, "patrimonio": float(valor)}
        for momento, valor in zip(report.equity_timestamps, report.equity_curve, strict=False)
    ]


def metrics_table(report: BacktestReport) -> list[dict[str, object]]:
    """Las métricas obligatorias como filas.

    El win rate va el último y con su coletilla, igual que en el informe de texto: leído primero
    engaña, y un panel bonito engaña más que un texto.
    """
    filas: list[dict[str, object]] = [
        {"metrica": "Resultado neto", "valor": float(report.net_result)},
        {"metrica": "Expectancy por operacion", "valor": float(report.expectancy)},
        {"metrica": "Drawdown maximo", "valor": float(report.max_drawdown)},
        {"metrica": "Operaciones", "valor": report.trade_count},
        {"metrica": "Costes totales", "valor": float(report.total_costs)},
    ]
    if report.buy_and_hold is not None:
        filas.append(
            {
                "metrica": "Diferencia vs comprar y mantener",
                "valor": float(report.excess_return),
            }
        )
    filas.append(
        {"metrica": "Win rate (no es criterio de exito)", "valor": round(report.win_rate, 3)}
    )
    return filas


def trades_table(report: BacktestReport) -> list[dict[str, object]]:
    """Registro de operaciones, para poder auditar cualquier cifra (FR-014)."""
    return [
        {
            "entrada": trade.entry_order.execution_timestamp,
            "precio entrada": float(trade.entry_order.fill_price),
            "salida": trade.exit_order.execution_timestamp if trade.exit_order else None,
            "precio salida": float(trade.exit_order.fill_price) if trade.exit_order else None,
            "motivo": trade.exit_reason.value,
            "resultado": float(trade.net_pnl),
        }
        for trade in report.trades
    ]


def parse_amount(texto: str, *, campo: str) -> Decimal:
    """Convierte texto a `Decimal` con un mensaje útil si no se puede.

    Se usa `Decimal` y no `float` por lo mismo que en el motor: son cifras de dinero.
    """
    try:
        valor = Decimal(texto)
    except (ArithmeticError, ValueError) as error:
        raise ValueError(f"{campo} no es un numero valido: {texto!r}") from error
    if valor <= 0:
        raise ValueError(f"{campo} debe ser positivo, recibido {valor}")
    return valor


def suggest_compatible(
    assets: Sequence[AvailableAsset], *, maximo: int = 4
) -> list[AvailableAsset]:
    """Preseleccion de activos que de verdad se solapan en el tiempo.

    Elegir los primeros de la lista sin mirar produce combinaciones imposibles -- por ejemplo un
    historico que acaba en 2010 junto a otro que empieza en 2017. El panel arrancaba con un error
    en la cara antes de que el operador tocara nada.

    Se parte del activo con mas historia y se van anadiendo los que mantengan un solape util.
    """
    if not assets:
        return []

    cargados: list[tuple[AvailableAsset, datetime, datetime]] = []
    for activo in assets:
        try:
            serie = activo.load()
        except Exception:
            continue
        cargados.append((activo, serie.bars[0].timestamp, serie.bars[-1].timestamp))

    if not cargados:
        return []

    # El de mayor recorrido manda: es el que mas probabilidades tiene de solapar con el resto.
    cargados.sort(key=lambda c: c[2] - c[1], reverse=True)
    elegidos = [cargados[0]]
    inicio, fin = cargados[0][1], cargados[0][2]

    for activo, desde, hasta in cargados[1:]:
        if len(elegidos) >= maximo:
            break
        nuevo_inicio = max(inicio, desde)
        nuevo_fin = min(fin, hasta)
        if nuevo_inicio < nuevo_fin:
            elegidos.append((activo, desde, hasta))
            inicio, fin = nuevo_inicio, nuevo_fin

    # Se devuelven en el orden original de la lista, que es el que el operador ve.
    seleccionados = {id(a) for a, _, _ in elegidos}
    return [a for a in assets if id(a) in seleccionados]


def common_intervals(assets: Sequence[AvailableAsset]) -> list[Interval]:
    """Intervalos disponibles en todos los activos indicados.

    Un universo exige el mismo intervalo en todos, así que el panel solo debe ofrecer los que
    valgan para la selección actual.
    """
    if not assets:
        return []
    comunes = {a.interval for a in assets}
    for activo in assets[1:]:
        comunes &= {activo.interval}
    return sorted(comunes, key=lambda i: i.duration)


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
            serie = activo.load()
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


def normalised_series(
    assets: Sequence[AvailableAsset], *, periods: int | None = None
) -> list[dict[str, object]]:
    """Todos los activos en base 100 al inicio del tramo, para poder compararlos.

    Sin normalizar, una gráfica conjunta no dice nada: Bitcoin a 90.000 aplasta visualmente a
    todo lo demás aunque el oro lo haya batido en el periodo.
    """
    puntos: list[dict[str, object]] = []

    for activo in assets:
        try:
            serie = activo.load()
        except Exception:
            continue

        barras = serie.bars[-periods:] if periods else serie.bars
        if not barras or barras[0].close == 0:
            continue

        base = barras[0].close
        puntos.extend(
            {
                "fecha": b.timestamp,
                "activo": activo.symbol,
                "valor": round(b.close / base * 100, 2),
            }
            for b in barras
        )

    return puntos


def fetch_args(asset: AvailableAsset, *, hasta: datetime) -> list[str] | None:
    """El comando para re-descargar un histórico hasta `hasta`, o `None` sin procedencia.

    Se reconstruye desde los metadatos de la descarga original (mismo proveedor, mismo inicio):
    así actualizar no cambia la forma de la serie, solo la alarga. Sin procedencia no se
    adivina — descargar con parámetros supuestos produciría una serie distinta en silencio.
    """
    p = asset.provenance
    if p is None:
        return None

    args = [
        "uv",
        "run",
        "invest-ll-fetch",
        p.symbol,
        "--market",
        p.market,
        "--interval",
        p.interval,
        "--start",
        p.range_start.date().isoformat(),
        "--end",
        hasta.date().isoformat(),
    ]
    if p.market == "crypto" and "-" in p.provider:
        args += ["--exchange", p.provider.split("-", 1)[1]]
    return args
