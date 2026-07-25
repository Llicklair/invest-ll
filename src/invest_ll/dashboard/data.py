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

from invest_ll.data.bar import Interval
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
