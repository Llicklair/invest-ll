"""Coherencia OHLC frente al redondeo de coma flotante.

Regresión encontrada al descargar SPY de verdad. El error fue:

    close (95.01583862304688) fuera del rango [93.40606615050764, 95.01583862304686]

Los dos números difieren en 2e-14. No es un dato corrupto: es que el ajuste por splits y
dividendos multiplica cada precio por un factor, y en un día que cerró en su máximo el redondeo
deja el cierre una fracción infinitesimal por encima del máximo.

Rechazar la serie entera por eso es un falso positivo que impide descargar activos legítimos. Pero
la tolerancia tiene que ser lo bastante estrecha para que un dato de verdad incoherente siga
cayendo: una diferencia real en datos de mercado es de céntimos, no de femtos.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from invest_ll.data.bar import Bar
from invest_ll.errors import InvalidSeriesError

TS = datetime(2005, 6, 15, tzinfo=UTC)

# Los valores exactos que devolvió yfinance para SPY.
HIGH_REAL = 95.01583862304686
CLOSE_REAL = 95.01583862304688
LOW_REAL = 93.40606615050764


def test_el_caso_exacto_de_spy_se_acepta() -> None:
    bar = Bar(
        timestamp=TS,
        open=93.5,
        high=HIGH_REAL,
        low=LOW_REAL,
        close=CLOSE_REAL,
        volume=1000.0,
    )
    assert bar.close == CLOSE_REAL


def test_la_diferencia_del_caso_real_es_infinitesimal() -> None:
    """Confirma el diagnóstico: el problema es aritmética, no datos."""
    assert 0 < CLOSE_REAL - HIGH_REAL < 1e-10


def test_una_apertura_ligeramente_fuera_por_redondeo_se_acepta() -> None:
    bar = Bar(
        timestamp=TS,
        open=HIGH_REAL + 1e-13,
        high=HIGH_REAL,
        low=LOW_REAL,
        close=94.0,
        volume=1000.0,
    )
    assert bar.high == HIGH_REAL


@pytest.mark.parametrize("campo", ["open", "close"])
def test_una_incoherencia_de_verdad_sigue_rechazandose(campo: str) -> None:
    """Un céntimo fuera de rango no es redondeo: es un dato mal."""
    valores = {
        "timestamp": TS,
        "open": 94.0,
        "high": 95.0,
        "low": 93.0,
        "close": 94.0,
        "volume": 1000.0,
    }
    valores[campo] = 95.01  # un centimo por encima del maximo
    with pytest.raises(InvalidSeriesError):
        Bar(**valores)  # type: ignore[arg-type]


def test_un_precio_muy_fuera_de_rango_sigue_rechazandose() -> None:
    with pytest.raises(InvalidSeriesError):
        Bar(timestamp=TS, open=94.0, high=95.0, low=93.0, close=200.0, volume=1000.0)


def test_high_menor_que_low_sigue_rechazandose() -> None:
    """La tolerancia no puede convertirse en barra libre."""
    with pytest.raises(InvalidSeriesError):
        Bar(timestamp=TS, open=94.0, high=93.0, low=95.0, close=94.0, volume=1000.0)


def test_la_tolerancia_escala_con_el_precio() -> None:
    """En un activo a 60.000 el redondeo relativo es mayor en valor absoluto."""
    caro = 60000.0
    bar = Bar(
        timestamp=TS,
        open=caro,
        high=caro,
        low=59000.0,
        close=caro + 1e-9,
        volume=1.0,
    )
    assert bar.close > bar.high  # lo tolera, pero no modifica el dato


def test_la_tolerancia_no_deja_pasar_un_error_relativo_grande() -> None:
    caro = 60000.0
    with pytest.raises(InvalidSeriesError):
        Bar(timestamp=TS, open=caro, high=caro, low=59000.0, close=caro + 1.0, volume=1.0)


class TestNormalizacionEnElProveedor:
    """La otra mitad: el proveedor no debería entregar velas incoherentes.

    Si el cierre ajustado supera al máximo ajustado por redondeo, el máximo correcto es ese
    cierre. No se inventa nada — el máximo del día fue al menos el precio de cierre.
    """

    def test_el_maximo_engloba_al_cierre(self) -> None:
        from invest_ll.fetch.providers.equity import coherent_ohlc

        alto, bajo = coherent_ohlc(open_=93.5, high=HIGH_REAL, low=LOW_REAL, close=CLOSE_REAL)
        assert alto >= CLOSE_REAL
        assert bajo <= LOW_REAL

    def test_el_minimo_engloba_a_la_apertura(self) -> None:
        from invest_ll.fetch.providers.equity import coherent_ohlc

        alto, bajo = coherent_ohlc(open_=90.0, high=95.0, low=93.0, close=94.0)
        assert bajo <= 90.0
        assert alto >= 95.0

    def test_una_vela_coherente_no_se_toca(self) -> None:
        from invest_ll.fetch.providers.equity import coherent_ohlc

        assert coherent_ohlc(open_=94.0, high=95.0, low=93.0, close=94.5) == (95.0, 93.0)
