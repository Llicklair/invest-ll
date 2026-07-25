"""Fusión de lo descargado con lo almacenado (T026, T038, T045).

**Función pura**: sin E/S, sin red, sin reloj. Recibe lo que hay y lo que llegó, devuelve el
resultado. Se aísla así a propósito, porque es donde se esconden los errores de solape y porque
esos errores son silenciosos — no rompen nada, solo dejan un histórico ligeramente mal que produce
un backtest ligeramente falso.

**La regla que gobierna todo el módulo**: ante conflicto, gana lo almacenado. Nunca se aplica sola
la versión del proveedor (FR-026).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Bar

CAMPOS_COMPARADOS = ("open", "high", "low", "close", "volume")

# Cuántas velas ya almacenadas se vuelven a pedir al ampliar un histórico. Es lo que hace que las
# revisiones del proveedor se detecten en el uso normal sin gastar peticiones de más: van dentro
# de una petición que ya se iba a hacer. Cinco cubre la frontera reciente, que es donde los
# proveedores corrigen.
SOLAPE_POR_DEFECTO = 5


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """Un dato que el proveedor devuelve distinto de como está guardado.

    En bolsa serán frecuentes y **legítimas**: cada nuevo split o dividendo recalcula la serie
    ajustada hacia atrás. Una diferencia proporcional y uniforme en toda la serie tiene la firma de
    un ajuste, no de una corrupción — por eso se guardan los dos valores y se deja interpretar al
    operador.
    """

    timestamp: datetime
    field: str
    stored_value: float
    provider_value: float

    def describe(self) -> str:
        return (
            f"{self.timestamp.isoformat()} · {self.field}: "
            f"almacenado {self.stored_value} vs proveedor {self.provider_value}"
        )


@dataclass(frozen=True, slots=True)
class MergeResult:
    bars: tuple[Bar, ...]
    added_count: int
    discrepancies: tuple[Discrepancy, ...]


def merge(stored: Sequence[Bar] | None, fetched: Sequence[Bar]) -> MergeResult:
    """Fusiona lo descargado con lo almacenado sin modificar nunca lo segundo."""
    almacenado = {bar.timestamp: bar for bar in (stored or ())}
    resultado = dict(almacenado)

    discrepancias: list[Discrepancy] = []
    anadidas = 0

    for bar in fetched:
        previa = almacenado.get(bar.timestamp)

        if previa is None:
            # Si la misma marca llega dos veces en la respuesta, la primera manda: así el
            # resultado no depende del orden en que el proveedor las envíe.
            if bar.timestamp not in resultado:
                resultado[bar.timestamp] = bar
                anadidas += 1
            continue

        discrepancias.extend(_comparar(previa, bar))

    ordenadas = tuple(resultado[marca] for marca in sorted(resultado))
    return MergeResult(bars=ordenadas, added_count=anadidas, discrepancies=tuple(discrepancias))


def _comparar(almacenada: Bar, nueva: Bar) -> list[Discrepancy]:
    """Compara campo a campo dos versiones de la misma vela."""
    diferencias: list[Discrepancy] = []
    for campo in CAMPOS_COMPARADOS:
        anterior: float = getattr(almacenada, campo)
        actual: float = getattr(nueva, campo)
        if anterior != actual:
            diferencias.append(
                Discrepancy(
                    timestamp=almacenada.timestamp,
                    field=campo,
                    stored_value=anterior,
                    provider_value=actual,
                )
            )
    return diferencias


def missing_ranges(
    stored: Sequence[Bar] | None,
    start: datetime,
    end: datetime,
    *,
    interval_duration: timedelta,
    overlap_bars: int = SOLAPE_POR_DEFECTO,
) -> list[tuple[datetime, datetime]]:
    """Qué tramos del rango pedido no están todavía en local (FR-013).

    `interval_duration` importa más de lo que parece: la cobertura de una vela llega hasta su
    **fin**, no hasta su marca. Comparar contra la marca hace que cada descarga vuelva a pedir la
    última vela que ya se tenía — una petición inútil por descarga, justo lo que SC-005 prohíbe.

    Deliberadamente simple: devuelve como mucho el tramo anterior a lo almacenado y el posterior.
    No intenta rellenar huecos interiores, y es a propósito — un hueco dentro del rango cubierto
    suele ser un cierre de mercado o un dato que el proveedor sencillamente no tiene, y volver a
    pedirlo en cada descarga gastaría peticiones para recibir lo mismo.

    **`overlap_bars` resuelve una contradicción real del diseño.** FR-013 pide no solicitar lo que
    ya se tiene, pero FR-011 exige detectar que el proveedor haya revisado datos guardados — y para
    detectarlo hay que volver a mirarlos. Sin solape, una descarga normal nunca compara nada y
    FR-011 se queda en papel mojado.

    El solape retrocede unas pocas velas al ampliar por la derecha. No cuesta ninguna petición
    extra: amplía ligeramente el rango de una petición que ya se iba a hacer. A cambio, cada
    ampliación revisa la frontera de lo ya almacenado, que es justo donde un proveedor corrige sus
    datos recientes. La reverificación completa sigue siendo explícita (FR-029).
    """
    if not stored:
        return [(start, end)]

    primera = stored[0].timestamp
    fin_cubierto = stored[-1].timestamp + interval_duration

    faltantes: list[tuple[datetime, datetime]] = []
    if start < primera:
        faltantes.append((start, min(primera, end)))
    if end > fin_cubierto:
        desde = max(fin_cubierto - interval_duration * max(overlap_bars, 0), start)
        faltantes.append((min(desde, fin_cubierto), end))
    return faltantes


def drop_unclosed(
    bars: Sequence[Bar], *, interval_duration: timedelta, now: datetime
) -> tuple[Bar, ...]:
    """Descarta el periodo que aún no ha cerrado (FR-007).

    Guardarlo como definitivo metería en el histórico un dato que todavía va a cambiar: un
    backtest de hoy y otro de mañana sobre "el mismo" fichero darían resultados distintos.
    """
    return tuple(bar for bar in bars if bar.timestamp + interval_duration <= now)
