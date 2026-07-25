"""Calendarios de mercado (T015).

El motor depende de este protocolo, no de una librería externa. Es lo que permite que cripto y
bolsa corran sobre el mismo bucle sin que el bucle sepa cuál está simulando.

Nota sobre tipos: frontera con `exchange_calendars` y pandas, que no publican tipado completo.
La comprobación estricta se relaja solo en este módulo — ver `loader.py` para el razonamiento.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from invest_ll.errors import InvalidSeriesError

if TYPE_CHECKING:  # pragma: no cover
    import exchange_calendars as xcals


# Hasta donde llega hacia atras el calendario burstail. Cargar mas anos cuesta algo de memoria al
# construirlo, y es un precio pequeno a cambio de poder medir una estrategia contra los mercados
# bajistas de 2000-2002 y 2008, que son los que de verdad la ponen a prueba.
INICIO_HISTORICO = "1990-01-01"


@runtime_checkable
class MarketCalendar(Protocol):
    """Tres preguntas: ¿está abierto ahora?, ¿fue sesión este día?, ¿cuándo vuelve a abrir?

    La distinción entre las dos primeras no es un matiz. Una vela diaria representa una sesión
    entera, y suele fecharse a medianoche — un instante en el que ningún mercado con horario está
    abierto. Preguntar `is_open` sobre ella responde siempre que no, y un motor que use esa
    respuesta para decidir si opera no ejecutará jamás una orden.
    """

    def is_open(self, moment: datetime) -> bool:
        """¿Se puede negociar en este instante concreto? Para velas intradía."""
        ...

    def is_session(self, moment: datetime) -> bool:
        """¿El día al que pertenece este instante fue día de negociación?

        Para velas de un día o más, esta es la pregunta correcta.
        """
        ...

    def next_open(self, moment: datetime) -> datetime | None:
        """Primer instante negociable desde `moment` incluido.

        Devuelve `moment` si ya está abierto, y `None` si no hay ninguno conocido.
        """
        ...


class Continuous24x7:
    """Mercado que nunca cierra: cripto."""

    __slots__ = ()

    def is_open(self, moment: datetime) -> bool:
        return True

    def is_session(self, moment: datetime) -> bool:
        return True

    def next_open(self, moment: datetime) -> datetime | None:
        return moment

    def __repr__(self) -> str:
        return "Continuous24x7()"


class ExchangeCalendarAdapter:
    """Adaptador sobre `exchange_calendars` para mercados con sesión.

    Se envuelve en lugar de usarse directamente para que el motor no dependa de su API: los
    festivos son datos irregulares que no tiene sentido mantener a mano, pero la dependencia se
    queda en esta capa.
    """

    __slots__ = ("_calendar", "_name")

    def __init__(self, name: str = "XNYS", *, start: str = INICIO_HISTORICO) -> None:
        import exchange_calendars as xcals

        self._name = name
        # `start` explícito: por defecto la librería solo carga las sesiones de los últimos veinte
        # años, y pedir datos anteriores falla con "cannot be earlier than the first session".
        # Backtestear la década perdida (2000-2010) es justo uno de los casos que más dicen sobre
        # una estrategia, porque incluye dos mercados bajistas de verdad.
        self._calendar: xcals.ExchangeCalendar = xcals.get_calendar(name, start=start)

    def is_open(self, moment: datetime) -> bool:
        import pandas as pd
        from exchange_calendars.errors import MinuteOutOfBounds

        ts = pd.Timestamp(moment)
        if ts.tz is None:  # pragma: no cover - las Bar validadas siempre traen zona
            ts = ts.tz_localize("UTC")
        try:
            return bool(self._calendar.is_open_on_minute(ts.tz_convert("UTC")))
        except MinuteOutOfBounds as error:
            raise InvalidSeriesError(
                f"{moment} cae fuera del rango que conoce el calendario '{self._name}' "
                f"(sesiones entre {self._calendar.first_session} y {self._calendar.last_session}). "
                "No se puede saber si el mercado estaba abierto en ese instante: revisa las "
                "fechas del CSV, o reconstruye el calendario con un rango que las cubra."
            ) from error

    def is_session(self, moment: datetime) -> bool:
        """¿Hubo negociación el día al que pertenece este instante?

        Se compara solo la fecha, no la hora. Una vela diaria fechada a medianoche pertenece a su
        día aunque a esa hora concreta el mercado estuviera cerrado.
        """
        import pandas as pd
        from exchange_calendars.errors import DateOutOfBounds

        ts = pd.Timestamp(moment)
        if ts.tz is None:  # pragma: no cover - las Bar validadas siempre traen zona
            ts = ts.tz_localize("UTC")
        fecha = ts.tz_convert("UTC").normalize().tz_localize(None)
        try:
            return bool(self._calendar.is_session(fecha))
        except DateOutOfBounds as error:
            raise InvalidSeriesError(
                f"{moment} cae fuera del rango que conoce el calendario '{self._name}' "
                f"(sesiones entre {self._calendar.first_session} y {self._calendar.last_session}). "
                "No se puede saber si ese dia fue sesion de mercado: revisa las fechas del CSV, o "
                "reconstruye el calendario con un rango que las cubra."
            ) from error

    def next_open(self, moment: datetime) -> datetime | None:
        import pandas as pd

        if self.is_open(moment):
            return moment

        ts = pd.Timestamp(moment)
        if ts.tz is None:  # pragma: no cover
            ts = ts.tz_localize("UTC")
        ts = ts.tz_convert("UTC")

        try:
            siguiente = self._calendar.next_open(ts)
        except (ValueError, KeyError):  # pragma: no cover - fuera del rango del calendario
            return None
        return siguiente.to_pydatetime()

    def __repr__(self) -> str:
        return f"ExchangeCalendarAdapter({self._name!r})"
