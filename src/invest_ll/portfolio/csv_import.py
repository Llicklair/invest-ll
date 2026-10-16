"""Importar el CSV del bróker (formato Ghostfolio y parecidos).

Ghostfolio es el formato con conversores desde decenas de brókers:
`Date,Symbol,Type,Quantity,Unit Price,Fee,Currency,Account`. Se aceptan cabeceras en inglés o en
español y con sinónimos (`fecha`, `ticker`, `shares`, `precio`...), y fechas ISO o europeas
(`15/01/2026`, día primero).

**Solo entran compras y ventas.** Dividendos, intereses, comisiones sueltas o depósitos se cuentan
y se reportan, pero no se importan: un dividendo modelado a medias inflaría el P&L, y descartado
en silencio, la cartera mentiría por omisión. Contarlo es la diferencia.

**Todo o nada.** Si una fila no se entiende, el CSV entero se rechaza diciendo qué fila y por qué:
importar la mitad dejaría una cartera con aspecto de completa.
"""

from __future__ import annotations

import csv
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from invest_ll.errors import InvestLLError
from invest_ll.portfolio.models import CERO, Activity, ActivityType

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path


class CsvFormatError(InvestLLError):
    """El CSV no se puede importar tal cual. El mensaje dice qué columna o qué fila."""


@dataclass(frozen=True, slots=True)
class CsvImportResult:
    """Lo que se puede importar, y la cuenta de lo que no."""

    activities: tuple[Activity, ...]
    skipped_types: dict[str, int]
    """Filas que no son compra/venta, por tipo. Contadas, nunca calladas."""
    warnings: tuple[str, ...]


# Nombre canónico -> cabeceras aceptadas, ya normalizadas (minúsculas, sin acentos ni espacios).
SINONIMOS: dict[str, tuple[str, ...]] = {
    "date": ("date", "fecha", "tradedate", "datetime"),
    "symbol": ("symbol", "ticker", "code", "simbolo"),
    "type": ("type", "tipo", "action", "operacion"),
    "quantity": ("quantity", "shares", "cantidad", "qty", "units"),
    "unit price": ("unitprice", "price", "precio", "preciounitario", "tradeprice"),
    "fee": ("fee", "fees", "comision", "commission"),
    "currency": ("currency", "divisa", "moneda", "ccy"),
    "account": ("account", "cuenta"),
}
OBLIGATORIAS = ("date", "symbol", "type", "quantity", "unit price")

TIPOS: dict[str, ActivityType] = {
    "buy": ActivityType.BUY,
    "compra": ActivityType.BUY,
    "sell": ActivityType.SELL,
    "venta": ActivityType.SELL,
}
TIPOS_DE_EFECTIVO = frozenset({"deposit", "withdrawal", "withdraw", "deposito", "retirada"})

# Día primero: es el convenio de Ghostfolio y el europeo. Uno de mes primero (EE. UU.) falla en
# cuanto aparece un día mayor que 12, que es lo que hace que el CSV entero se rechace.
FORMATOS_EUROPEOS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
)


def parse_broker_csv(path: Path) -> CsvImportResult:
    """Lee el CSV y devuelve los movimientos importables. No escribe nada en el ledger.

    Raises:
        FileNotFoundError: si el fichero no existe.
        CsvFormatError: si faltan columnas o alguna fila no se entiende (con su número).
    """
    if not path.exists():
        raise FileNotFoundError(f"no existe el CSV {path}")
    try:
        texto = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvFormatError(
            f"{path.name} no esta en UTF-8 ({error.reason}). Guardalo como UTF-8 y vuelve a "
            "importarlo: adivinar la codificacion podria cambiar un simbolo sin que se note."
        ) from error

    lineas = texto.splitlines()
    if not lineas or not lineas[0].strip():
        raise CsvFormatError(f"{path.name} esta vacio: no hay ni cabecera")
    separador = ";" if ";" in lineas[0] and "," not in lineas[0] else ","
    lector = csv.reader(lineas, delimiter=separador)
    cabecera = next(lector)
    columnas = _columnas(cabecera)

    fuente = f"csv:{path.name}"
    actividades: list[Activity] = []
    vistas: dict[str, int] = {}
    saltadas: Counter[str] = Counter()
    divisas: set[str] = set()
    cuentas: set[str] = set()
    sin_comision = 0
    horas_sin_zona = 0

    for celdas in lector:
        fila = lector.line_num
        if not any(c.strip() for c in celdas):
            continue
        valores = {campo: _celda(celdas, indice) for campo, indice in columnas.items()}

        tipo_crudo = valores["type"].lower()
        tipo = TIPOS.get(tipo_crudo)
        if tipo is None:
            if not tipo_crudo:
                raise CsvFormatError(f"fila {fila}: no tiene tipo (buy/sell)")
            saltadas[tipo_crudo] += 1
            continue

        momento, era_hora_sin_zona = _fecha(valores["date"], fila)
        if era_hora_sin_zona:
            horas_sin_zona += 1
        comision_cruda = valores.get("fee", "")
        if not comision_cruda:
            sin_comision += 1
        try:
            actividad = Activity(
                timestamp=momento,
                type=tipo,
                symbol=valores["symbol"].upper(),
                quantity=_numero(valores["quantity"], "quantity", fila),
                unit_price=_numero(valores["unit price"], "unit price", fila),
                fee=_numero(comision_cruda, "fee", fila) if comision_cruda else CERO,
                source=fuente,
            )
        except ValueError as error:
            raise CsvFormatError(f"fila {fila}: {error}") from error

        previa = vistas.get(actividad.activity_id)
        if previa is not None:
            raise CsvFormatError(
                f"las filas {previa} y {fila} son identicas: el ledger no distingue una operacion "
                "repetida de una fila duplicada. Si son dos operaciones, anade la hora a la fecha "
                "(AAAA-MM-DDTHH:MM); si es un duplicado, borra una."
            )
        vistas[actividad.activity_id] = fila
        actividades.append(actividad)

        if divisa := valores.get("currency", "").upper():
            divisas.add(divisa)
        if cuenta := valores.get("account", ""):
            cuentas.add(cuenta)

    avisos = _avisos(
        saltadas=saltadas,
        divisas=divisas,
        cuentas=cuentas,
        sin_columna_de_comision="fee" not in columnas,
        sin_comision=sin_comision,
        horas_sin_zona=horas_sin_zona,
    )
    return CsvImportResult(
        activities=tuple(actividades),
        skipped_types=dict(saltadas),
        warnings=tuple(avisos),
    )


def _celda(celdas: list[str], indice: int) -> str:
    """El valor de la columna, o vacío si la fila es más corta que la cabecera."""
    return celdas[indice].strip() if indice < len(celdas) else ""


def _normalizar(cabecera: str) -> str:
    """`Unit Price` -> `unitprice`, `Comisión` -> `comision`."""
    sin_acentos = unicodedata.normalize("NFKD", cabecera)
    letras = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return "".join(c for c in letras.lower() if c.isalnum())


def _columnas(cabecera: list[str]) -> dict[str, int]:
    """Nombre canónico -> índice de columna. Falla si faltan las obligatorias o hay ambigüedad."""
    columnas: dict[str, int] = {}
    for indice, nombre in enumerate(cabecera):
        normalizado = _normalizar(nombre)
        for canonico, sinonimos in SINONIMOS.items():
            if normalizado not in sinonimos:
                continue
            if canonico in columnas:
                raise CsvFormatError(
                    f"las columnas {cabecera[columnas[canonico]]!r} y {nombre!r} significan lo "
                    f"mismo ({canonico}): deja solo una para que no haya que adivinar cual vale"
                )
            columnas[canonico] = indice

    faltan = [c for c in OBLIGATORIAS if c not in columnas]
    if faltan:
        raise CsvFormatError(
            f"faltan columnas obligatorias: {', '.join(faltan)} "
            f"(cabecera leida: {', '.join(cabecera)}). Se espera el formato Ghostfolio: "
            "Date,Symbol,Type,Quantity,Unit Price,Fee,Currency"
        )
    return columnas


def _fecha(texto: str, fila: int) -> tuple[datetime, bool]:
    """La fecha con zona horaria, y si traía hora sin zona (se toma como UTC y se avisa)."""
    if not texto:
        raise CsvFormatError(f"fila {fila}: no tiene fecha")

    momento: datetime | None = None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        for formato in FORMATOS_EUROPEOS:
            try:
                momento = datetime.strptime(texto, formato)
            except ValueError:
                continue
            break
    if momento is None:
        raise CsvFormatError(
            f"fila {fila}: fecha {texto!r} no reconocida (se admite AAAA-MM-DD o DD/MM/AAAA)"
        )

    if momento.tzinfo is not None:
        return momento, False
    con_hora = (momento.hour, momento.minute, momento.second, momento.microsecond) != (0, 0, 0, 0)
    return momento.replace(tzinfo=UTC), con_hora


def _numero(texto: str, campo: str, fila: int) -> Decimal:
    if not texto:
        raise CsvFormatError(f"fila {fila}: {campo} esta vacio")
    if "," in texto:
        raise CsvFormatError(
            f"fila {fila}: {campo} {texto!r} lleva coma. Usa punto decimal y sin separador de "
            "miles: '1,234' puede ser mil doscientos o uno coma dos, y no se adivina"
        )
    try:
        valor = Decimal(texto)
    except InvalidOperation as error:
        raise CsvFormatError(f"fila {fila}: {campo} {texto!r} no es un numero") from error
    if not valor.is_finite():
        raise CsvFormatError(f"fila {fila}: {campo} {texto!r} no es un numero finito")
    return valor


def _avisos(
    *,
    saltadas: Counter[str],
    divisas: set[str],
    cuentas: set[str],
    sin_columna_de_comision: bool,
    sin_comision: int,
    horas_sin_zona: int,
) -> list[str]:
    avisos: list[str] = []
    for tipo, cuantas in saltadas.items():
        if tipo in TIPOS_DE_EFECTIVO:
            avisos.append(
                f"{cuantas} fila(s) de tipo '{tipo}' no se importan: el efectivo se registra "
                "aparte, con invest-ll-portfolio cash deposit/withdraw."
            )
        else:
            avisos.append(
                f"{cuantas} fila(s) de tipo '{tipo}' no se importan: solo entran compras y "
                f"ventas. Un '{tipo}' modelado a medias falsearia el P&L; quedan fuera, contadas."
            )

    if len(divisas) > 1:
        avisos.append(
            f"El CSV mezcla divisas ({', '.join(sorted(divisas))}): la cartera es monodivisa y "
            "suma los importes tal cual, sin convertir. Para cifras comparables, importa cada "
            "divisa en su propia cartera (--store)."
        )
    if len(cuentas) > 1:
        avisos.append(
            f"El CSV trae varias cuentas ({', '.join(sorted(cuentas))}): se suman en una sola "
            "cartera."
        )

    if sin_columna_de_comision:
        avisos.append(
            "El CSV no trae columna de comision: los movimientos entran con comision 0. Si el "
            "broker cobro, el coste queda por debajo del real y el P&L por encima."
        )
    elif sin_comision:
        avisos.append(
            f"{sin_comision} fila(s) con la comision vacia entran con comision 0. Si el broker "
            "cobro, el coste queda por debajo del real."
        )

    if horas_sin_zona:
        avisos.append(
            f"{horas_sin_zona} fecha(s) con hora pero sin zona horaria se han tomado como UTC."
        )
    return avisos
