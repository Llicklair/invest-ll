"""Cambio de horario en series diarias de bolsa.

Regresión encontrada por la comprobación manual contra el proveedor real (T058), que es
precisamente lo que ningún proveedor grabado podía revelar.

Yahoo devuelve las velas diarias con la hora local del mercado. En Nueva York eso significa 05:00
UTC en invierno y 04:00 UTC en verano. El fin de semana del cambio de horario, el salto entre dos
velas consecutivas es de 71 horas en vez de 72, y una validación que exija múltiplos exactos del
intervalo rechaza la serie entera.

El error real fue:
    marca no alineada al intervalo DAY_1: 2025-03-10 04:00:00+00:00 está a 255600.0s de la anterior
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter
from invest_ll.data.series import PriceSeries

from ..fixtures.recorded_data import velas

# Viernes 7 de marzo de 2025, medianoche en Nueva York (EST = UTC-5).
VIERNES_EST = datetime(2025, 3, 7, 5, 0, tzinfo=UTC)
# Lunes 10 de marzo, medianoche en Nueva York, ya en horario de verano (EDT = UTC-4).
LUNES_EDT = datetime(2025, 3, 10, 4, 0, tzinfo=UTC)


def bar_en(momento: datetime, precio: float = 100.0):  # type: ignore[no-untyped-def]
    from invest_ll.data.bar import Bar

    return Bar(
        timestamp=momento,
        open=precio,
        high=precio + 1,
        low=precio - 1,
        close=precio,
        volume=1000.0,
    )


def test_el_salto_del_cambio_de_horario_es_de_71_horas() -> None:
    """Confirma el diagnóstico antes de arreglar nada."""
    assert (LUNES_EDT - VIERNES_EST).total_seconds() == 255600.0


def test_una_serie_diaria_que_cruza_el_cambio_de_horario_se_acepta() -> None:
    """El caso que rompía en real: no es un dato corrupto, es el reloj del proveedor."""
    bars = (
        bar_en(VIERNES_EST - timedelta(days=1)),
        bar_en(VIERNES_EST),
        bar_en(LUNES_EDT),
        bar_en(LUNES_EDT + timedelta(days=1)),
    )
    serie = PriceSeries(
        symbol="AAPL",
        interval=Interval.DAY_1,
        calendar=ExchangeCalendarAdapter("XNYS"),
        bars=bars,
    )
    assert len(serie) == 4


def test_una_serie_diaria_con_desorden_real_sigue_rechazandose() -> None:
    """La tolerancia al cambio de horario no puede convertirse en barra libre."""
    import pytest

    from invest_ll.errors import InvalidSeriesError

    bars = (
        bar_en(VIERNES_EST),
        bar_en(VIERNES_EST + timedelta(hours=7)),  # siete horas: eso no es un cambio de horario
    )
    with pytest.raises(InvalidSeriesError, match=r"alineada|intervalo"):
        PriceSeries(
            symbol="AAPL",
            interval=Interval.DAY_1,
            calendar=ExchangeCalendarAdapter("XNYS"),
            bars=bars,
        )


def test_las_series_intradia_siguen_siendo_estrictas() -> None:
    """En una serie horaria, una hora de desviación SÍ es un dato descolocado."""
    import pytest

    from invest_ll.errors import InvalidSeriesError

    bars = (
        bar_en(VIERNES_EST),
        bar_en(VIERNES_EST + timedelta(hours=1)),
        bar_en(VIERNES_EST + timedelta(hours=2, minutes=30)),
    )
    with pytest.raises(InvalidSeriesError, match=r"alineada|intervalo"):
        PriceSeries(
            symbol="AAPL",
            interval=Interval.HOUR_1,
            calendar=ExchangeCalendarAdapter("XNYS"),
            bars=bars,
        )


def test_una_serie_de_cripto_normal_sigue_funcionando() -> None:
    serie = PriceSeries(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        calendar=Continuous24x7(),
        bars=tuple(velas(30)),
    )
    assert len(serie) == 30


class TestNormalizacionEnElProveedor:
    """La otra mitad del arreglo: la hora no debería llegar sucia desde el principio.

    Una vela "diaria" de bolsa representa una sesión entera, no un instante. La hora concreta que
    ponga el proveedor es ruido, y normalizarla en el borde evita que ese ruido se propague.
    """

    def test_las_marcas_diarias_se_normalizan_a_medianoche(self) -> None:
        from invest_ll.fetch.providers.equity import normalize_daily

        normalizada = normalize_daily(LUNES_EDT, Interval.DAY_1)
        assert normalizada == datetime(2025, 3, 10, tzinfo=UTC)

    def test_dos_dias_consecutivos_quedan_a_un_intervalo_exacto(self) -> None:
        from invest_ll.fetch.providers.equity import normalize_daily

        a = normalize_daily(VIERNES_EST, Interval.DAY_1)
        b = normalize_daily(LUNES_EDT, Interval.DAY_1)
        assert (b - a).total_seconds() % Interval.DAY_1.duration.total_seconds() == 0

    def test_las_marcas_intradia_no_se_tocan(self) -> None:
        """En intradía la hora es el dato, no ruido."""
        from invest_ll.fetch.providers.equity import normalize_daily

        momento = datetime(2025, 3, 10, 14, 30, tzinfo=UTC)
        assert normalize_daily(momento, Interval.HOUR_1) == momento
