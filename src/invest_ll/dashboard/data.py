"""Lógica del panel, separada de la presentación.

Aquí vive todo lo que se puede probar: descubrir qué hay descargado, cargarlo y convertir los
informes en tablas. La API del panel (`invest_ll.api`) solo traduce a HTTP lo que esto devuelve,
y el frontend solo lo dibuja.

La separación no es estética. Un panel donde la lógica vive dentro de los widgets no se puede
testear, y un panel que muestra cifras de dinero sin tests es justo lo que este proyecto lleva
toda la sesión evitando. Sobrevivió al cambio de Streamlit a FastAPI sin tocarse por eso mismo.
"""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.data.reserved import load_reservation

# Descubrir y resumir lo descargado vive ahora en `fetch.available`, para que el chat no tenga que
# importar el panel. Se re-exporta aquí para no romper a quien ya lo importaba de este módulo.
from invest_ll.fetch.available import (
    NOMBRES,
    PROVEEDORES_CRIPTO,
    RAIZ_DATOS,
    SPARKLINE_SESIONES,
    VENTANAS,
    AvailableAsset,
    discover_assets,
    market_overview,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.report.report import BacktestReport


__all__ = [
    "EXCHANGE_CRIPTO",
    "INICIO_HISTORICO_COMPLETO",
    "NOMBRES",
    "PROVEEDORES_CRIPTO",
    "RAIZ_DATOS",
    "SPARKLINE_SESIONES",
    "VENTANAS",
    "AvailableAsset",
    "aviso_de_reserva",
    "discover_assets",
    "equity_table",
    "fetch_args",
    "full_history_args",
    "lanzador_fetch",
    "market_overview",
    "metrics_table",
    "normalised_series",
    "parse_amount",
    "suggest_compatible",
    "trades_table",
]


def aviso_de_reserva() -> str | None:
    """Qué contarle al operador sobre la reserva vigente. `None` si no hay ninguna."""
    reserva = load_reservation()
    if reserva is None:
        return None
    return (
        f"Hay datos reservados desde {reserva.cutoff}: los backtests se recortan ahi para que ese "
        "tramo siga sirviendo como validacion. Las cotizaciones y el rendimiento por periodo si "
        f"usan el historico completo. Motivo: {reserva.reason}"
    )


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
            serie = activo.load_completa()
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
            serie = activo.load_completa()
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


INICIO_HISTORICO_COMPLETO = "2015-01-01"
"""Desde donde se descarga un activo nuevo: lo bastante atras para cubrir varios ciclos."""

EXCHANGE_CRIPTO = "binance"


def lanzador_fetch() -> list[str]:
    """Cómo se invoca `invest-ll-fetch` desde el panel: con el Python que ya está corriendo.

    No con `uv run`: el panel es un proceso del entorno virtual en marcha, y `uv run` intenta
    sincronizar ese mismo entorno antes de ejecutar nada. En Windows eso choca con los ejecutables
    abiertos ("os error 32") y la descarga muere antes de empezar.
    """
    return [sys.executable, "-m", "invest_ll.cli_fetch"]


def full_history_args(symbol: str, *, market: str, hasta: datetime) -> list[str]:
    """El comando para descargar un activo nuevo entero, desde 2015 hasta `hasta`.

    Es la descarga del botón de las cotizaciones: un activo que se ve al momento y aún no tiene
    histórico. En cripto se fija Binance, que es de donde salen esas cotizaciones.
    """
    args = [
        *lanzador_fetch(),
        symbol,
        "--market",
        market,
        "--interval",
        "DAY_1",
        "--start",
        INICIO_HISTORICO_COMPLETO,
        "--end",
        hasta.date().isoformat(),
    ]
    if market == "crypto":
        args += ["--exchange", EXCHANGE_CRIPTO]
    return args


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
        *lanzador_fetch(),
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
