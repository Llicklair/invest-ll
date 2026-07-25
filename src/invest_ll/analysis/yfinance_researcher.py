"""Datos fundamentales de yfinance.

**Toca la red.** Por eso vive aquí y no dentro del motor, y por eso los tests lo sustituyen por un
doble en lugar de llamarlo.

Lo que devuelve son datos de **hoy**. Sirven para decidir hacia adelante; usarlos para juzgar una
decisión de 2018 sería look-ahead — la empresa de entonces no es esta (FR-051).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, cast

from invest_ll.analysis.models import AssetAnalysis, Fact

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

FUENTE = "yfinance"

# Cómo se traduce cada campo del proveedor a algo legible. El orden importa: es el orden en que
# el operador los va a leer, y lo primero debe ser a qué se dedica, no cuánto vale.
CAMPOS: tuple[tuple[str, str, str], ...] = (
    ("sector", "Sector", "texto"),
    ("industry", "Actividad", "texto"),
    ("country", "Pais", "texto"),
    ("fullTimeEmployees", "Empleados", "entero"),
    ("marketCap", "Valor de mercado", "dinero"),
    ("trailingPE", "Veces beneficio (PER)", "ratio"),
    ("profitMargins", "Margen de beneficio", "porcentaje"),
    ("debtToEquity", "Deuda sobre fondos propios", "ratio"),
    ("dividendYield", "Dividendo anual", "porcentaje"),
)

# Tipos de activo que no tienen empresa detrás (FR-019).
SIN_EMPRESA = {
    "GLD": ("materia prima", "Oro fisico en custodia. No hay empresa detras: es metal."),
    "SLV": ("materia prima", "Plata fisica en custodia."),
    "TLT": ("bonos", "Deuda del Estado de EE.UU. a mas de 20 anhos."),
    "SPY": ("indice", "Las 500 empresas mas grandes de EE.UU., en una sola cesta."),
    "QQQ": ("indice", "Las 100 mayores empresas no financieras del Nasdaq."),
}


def _formatear(valor: object, tipo: str) -> str | None:
    """Convierte un valor crudo del proveedor en algo legible, o `None` si no vale."""
    if valor is None or valor == "":
        return None
    try:
        if tipo == "texto":
            return str(valor)
        numero = float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    if tipo == "dinero":
        for umbral, sufijo in ((1e12, "billones"), (1e9, "mil millones"), (1e6, "millones")):
            if abs(numero) >= umbral:
                return f"{numero / umbral:,.1f} {sufijo}"
        return f"{numero:,.0f}"
    if tipo == "porcentaje":
        return f"{numero:.2%}"
    if tipo == "entero":
        return f"{numero:,.0f}"
    return f"{numero:,.2f}"


class YFinanceResearcher:
    """Trae lo que yfinance sepa de un activo.

    El lector de datos se inyecta para poder sustituirlo en los tests sin monkeypatching y sin
    que la suite salga a la red.
    """

    __slots__ = ("_fetch",)

    def __init__(self, fetch: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._fetch = fetch or _traer_de_yfinance

    def analyze(self, symbol: str) -> AssetAnalysis:
        conocido = SIN_EMPRESA.get(symbol)
        if conocido is not None:
            tipo, descripcion = conocido
            return AssetAnalysis(
                symbol=symbol,
                kind=tipo,
                facts=(),
                narrative=descripcion,
                scenarios=(),
                retrieved_at=datetime.now(UTC),
            )

        try:
            crudo = self._fetch(symbol)
        except Exception as error:
            return AssetAnalysis(
                symbol=symbol,
                kind="desconocido",
                facts=(),
                narrative=f"No se pudieron obtener datos: {error}",
                scenarios=(),
                retrieved_at=datetime.now(UTC),
            )

        hoy = date.today()
        hechos = tuple(
            Fact(label=etiqueta, value=texto, source=FUENTE, as_of=hoy)
            for clave, etiqueta, tipo in CAMPOS
            if (texto := _formatear(crudo.get(clave), tipo)) is not None
        )

        return AssetAnalysis(
            symbol=symbol,
            kind="empresa" if hechos else "desconocido",
            facts=hechos,
            narrative=str(crudo.get("longBusinessSummary") or "").strip(),
            scenarios=(),
            retrieved_at=datetime.now(UTC),
        )


def _traer_de_yfinance(symbol: str) -> dict[str, Any]:  # pragma: no cover - toca la red
    """Frontera con yfinance, que no publica tipos.

    El cast es explicito: aqui acaba la garantia del comprobador de tipos y empieza la confianza
    en un proveedor externo. Todo lo que venga de aqui se valida en `_formatear` antes de
    presentarse como dato.
    """
    import yfinance

    info = cast("dict[str, Any] | None", yfinance.Ticker(symbol).info)  # pyright: ignore[reportUnknownMemberType]
    return dict(info) if info else {}
