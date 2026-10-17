"""Si unos datos están al día: el último cierre que ya debería estar descargado, y si lo está.

Un dato de ayer no es viejo en bolsa un lunes (el último cierre es el del viernes), y sí lo es en
cripto, que cotiza todos los días. La regla, la misma para el panel y para el arranque:

- **Cripto**: al día si tiene el día anterior a hoy (UTC). Las velas diarias se cierran a las
  00:00 UTC y las descargas no guardan la de hoy, que sigue abierta.
- **Bolsa**: al día si tiene la última sesión de la bolsa de Nueva York anterior a hoy (UTC): un
  lunes, la del viernes; el día después de un festivo de EE.UU., la de antes del festivo. Las
  descargas tampoco guardan la de hoy. Si el calendario de sesiones no se puede cargar, se toman
  los días de lunes a viernes: un día después de un festivo saldría "no al día" sin estarlo, que
  es el error del lado prudente.

Solo fechas: no toca la red.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.data.calendars import ExchangeCalendarAdapter

DIAS_ATRAS: Final = 10
"""Cuántos días se mira hacia atrás buscando la última sesión (más que cualquier puente)."""


def hoy_utc() -> date:
    return datetime.now(UTC).date()


@lru_cache(maxsize=2)
def _calendario(anio: int) -> ExchangeCalendarAdapter:
    from invest_ll.data.calendars import ExchangeCalendarAdapter

    # Desde el año anterior: basta para mirar unos días atrás y se carga en un momento.
    return ExchangeCalendarAdapter("XNYS", start=f"{anio - 1}-01-01")


def ultima_sesion_de_bolsa(hoy: date) -> date:
    """La última sesión de Nueva York anterior a `hoy` (de lunes a viernes si no hay calendario)."""
    return _por_calendario(hoy) or _de_lunes_a_viernes(hoy)


def _por_calendario(hoy: date) -> date | None:
    try:
        calendario = _calendario(hoy.year)
        for atras in range(1, DIAS_ATRAS + 1):
            dia = hoy - timedelta(days=atras)
            if calendario.is_session(datetime(dia.year, dia.month, dia.day, tzinfo=UTC)):
                return dia
    except Exception:
        return None  # sin calendario (o fuera de su rango), la regla de lunes a viernes
    return None


def _de_lunes_a_viernes(hoy: date) -> date:
    dia = hoy - timedelta(days=1)
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia


def esperado(hoy: date, *, cripto: bool) -> date:
    """El último día que ya debería estar descargado."""
    return hoy - timedelta(days=1) if cripto else ultima_sesion_de_bolsa(hoy)


def esta_al_dia(hasta: date | None, hoy: date, *, cripto: bool) -> bool:
    return hasta is not None and hasta >= esperado(hoy, cripto=cripto)


@lru_cache(maxsize=8)
def _ultimo_dia(ruta: str, huella: tuple[int, int]) -> date | None:
    del huella  # solo indexa la caché: cambia si el fichero se reescribe
    import pyarrow.compute
    import pyarrow.parquet

    # Frontera con pyarrow, que no publica tipos: lo que devuelve se trata como `Any` y se
    # comprueba al salir.
    parquet: Any = pyarrow.parquet
    calculo: Any = pyarrow.compute
    dias = parquet.read_table(ruta, columns=["day"]).column("day")
    maximo: object = calculo.max(dias).as_py() if len(dias) else None
    if not isinstance(maximo, int):
        return None
    return datetime.fromtimestamp(maximo * 86_400, UTC).date()


def ultimo_dia_del_panel(fichero: Path) -> date | None:
    """El último día con datos de un panel de `invest-ll-quant download` (columna `day`, en días
    desde 1970). `None` si no está descargado. Solo lee esa columna: el de Binance pesa decenas
    de MB y aquí basta una fecha."""
    if not fichero.exists():
        return None
    ruta = str(fichero.resolve())
    try:
        estado = fichero.stat()
        ultimo = _ultimo_dia(ruta, (estado.st_mtime_ns, estado.st_size))
    except (OSError, ValueError):
        # Se está reescribiendo justo ahora (una descarga de otra herramienta, que no lo hace de
        # una vez): vale lo último que se leyó bien, que es lo que había hasta hace un momento.
        return _LEIDO_BIEN.get(ruta)
    _LEIDO_BIEN[ruta] = ultimo
    return ultimo


_LEIDO_BIEN: dict[str, date | None] = {}
