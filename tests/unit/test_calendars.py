"""T011 — calendarios de mercado (FR-021, FR-022).

Distinguir "el mercado estaba cerrado" de "faltan datos" es lo que permite que el mismo motor
sirva para cripto y para bolsa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter

# 2026-07-04 cae en sábado; el festivo de Independence Day se observa el viernes 3.
NAVIDAD = datetime(2026, 12, 25, 15, 0, tzinfo=UTC)
DOMINGO = datetime(2026, 7, 26, 15, 0, tzinfo=UTC)
LUNES_APERTURA = datetime(2026, 7, 27, 14, 0, tzinfo=UTC)  # 10:00 en Nueva York
MADRUGADA = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)


class TestContinuous24x7:
    def test_siempre_abierto(self) -> None:
        cal = Continuous24x7()
        assert cal.is_open(NAVIDAD)
        assert cal.is_open(DOMINGO)
        assert cal.is_open(MADRUGADA)

    def test_siguiente_apertura_es_el_propio_instante(self) -> None:
        cal = Continuous24x7()
        assert cal.next_open(DOMINGO) == DOMINGO


class TestExchangeCalendarAdapter:
    def test_cerrado_en_domingo(self) -> None:
        assert not ExchangeCalendarAdapter("XNYS").is_open(DOMINGO)

    def test_cerrado_en_navidad(self) -> None:
        assert not ExchangeCalendarAdapter("XNYS").is_open(NAVIDAD)

    def test_cerrado_de_madrugada(self) -> None:
        assert not ExchangeCalendarAdapter("XNYS").is_open(MADRUGADA)

    def test_abierto_en_sesion(self) -> None:
        assert ExchangeCalendarAdapter("XNYS").is_open(LUNES_APERTURA)

    def test_siguiente_apertura_tras_domingo_es_lunes(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        siguiente = cal.next_open(DOMINGO)
        assert siguiente is not None
        assert siguiente > DOMINGO
        assert siguiente.date() == datetime(2026, 7, 27, tzinfo=UTC).date()
        assert cal.is_open(siguiente)

    def test_siguiente_apertura_dentro_de_sesion_es_el_propio_instante(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        assert cal.next_open(LUNES_APERTURA) == LUNES_APERTURA


class TestClasificacionDeHuecos:
    """FR-021: un hueco solo es anomalía si el mercado estaba abierto."""

    def test_hueco_nocturno_no_es_anomalia(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        assert not cal.is_open(MADRUGADA)

    def test_hueco_en_sesion_si_es_anomalia(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        media_sesion = LUNES_APERTURA + timedelta(hours=1)
        assert cal.is_open(media_sesion)
