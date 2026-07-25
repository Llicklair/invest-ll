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


class TestRangoHistorico:
    """Regresion encontrada al descargar SPY del ano 2000.

    exchange_calendars solo carga por defecto las sesiones de los ultimos 20 anos. Pedir datos
    anteriores fallaba con "cannot be earlier than the first session of calendar". Backtestear la
    decada perdida (2000-2010) es justo uno de los casos que mas valor tiene, asi que el
    calendario tiene que llegar mas atras.
    """

    def test_el_calendario_cubre_el_ano_2000(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        # 3 de enero de 2000: primer dia habil del milenio, sesion normal en Nueva York.
        assert cal.is_session(datetime(2000, 1, 3, tzinfo=UTC))

    def test_el_calendario_cubre_los_anos_noventa(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS")
        assert cal.is_session(datetime(1995, 6, 15, tzinfo=UTC))

    def test_un_festivo_antiguo_no_es_sesion(self) -> None:
        """No basta con que responda: tiene que responder bien."""
        cal = ExchangeCalendarAdapter("XNYS")
        assert not cal.is_session(datetime(2000, 12, 25, tzinfo=UTC))

    def test_el_inicio_es_configurable(self) -> None:
        cal = ExchangeCalendarAdapter("XNYS", start="2015-01-01")
        assert cal.is_session(datetime(2020, 6, 15, tzinfo=UTC))
