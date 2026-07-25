"""Calendarios de mercado (T015).

El motor depende de este protocolo, no de una librería externa. Es lo que permite que cripto y
bolsa corran sobre el mismo bucle sin que el bucle sepa cuál está simulando.

Nota sobre tipos: frontera con `exchange_calendars` y pandas, que no publican tipado completo.
La comprobación estricta se relaja solo en este módulo — ver `loader.py` para el razonamiento.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false, reportMissingTypeStubs=false
# pyright: reportArgumentType=false

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    import exchange_calendars as xcals


@runtime_checkable
class MarketCalendar(Protocol):
    """Dos preguntas: ¿está abierto?, ¿cuándo vuelve a abrir?"""

    def is_open(self, moment: datetime) -> bool:
        """¿Se puede negociar en este instante?"""
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

    def __init__(self, name: str = "XNYS") -> None:
        import exchange_calendars as xcals

        self._name = name
        self._calendar: xcals.ExchangeCalendar = xcals.get_calendar(name)

    def is_open(self, moment: datetime) -> bool:
        import pandas as pd

        ts = pd.Timestamp(moment)
        if ts.tz is None:  # pragma: no cover - las Bar validadas siempre traen zona
            ts = ts.tz_localize("UTC")
        return bool(self._calendar.is_open_on_minute(ts.tz_convert("UTC")))

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
