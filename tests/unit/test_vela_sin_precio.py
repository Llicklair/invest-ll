"""Una vela sin precio es ausencia de dato, no un dato.

Regresión encontrada el 2026-07-26 al actualizar los ETF de bolsa. Yahoo devolvió la última
sesión así:

    Date                       Open  High  Low  Close   Volume
    2026-07-24 00:00:00-04:00   NaN   NaN  NaN    NaN  3784137

Volumen sí, precios no: la sesión estaba a medias de consolidar. `float(fila["Open"])` produce
`nan`, y `Bar` lo rechaza — con razón — con «open no es un número finito: nan». El resultado era
que **ningún** histórico de bolsa se podía actualizar: fallaban los nueve activos, y el mensaje no
decía ni qué fila ni que sobraba una sola vela.

Descartar esa fila no es perder información: no había ninguna. Y no queda en silencio, porque la
cobertura descargada pasa a ser menor que la pedida y eso ya dispara el aviso de rango parcial.

La tolerancia tiene que ser estrecha: una vela con precios de verdad, aunque sean raros, debe
seguir entrando. Solo se descarta lo que no es un número.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from invest_ll.data.bar import Interval
from invest_ll.fetch.providers.equity import YFinanceProvider

DESDE = datetime(2026, 7, 20, tzinfo=UTC)
HASTA = datetime(2026, 7, 27, tzinfo=UTC)

# La fila real que rompió la descarga de GLD.
VOLUMEN_HUERFANO = 3_784_137.0


def _marco(filas: list[dict[str, float]], fechas: list[str]) -> pd.DataFrame:
    indice = pd.DatetimeIndex(pd.to_datetime(fechas, utc=True))  # pyright: ignore[reportUnknownMemberType]
    return pd.DataFrame(filas, index=indice)


def _proveedor_con(frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> YFinanceProvider:
    """Sustituye yfinance por un doble: la suite corre sin red a propósito."""
    import yfinance

    class TickerFalso:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **_: object) -> pd.DataFrame:
            return frame

    monkeypatch.setattr(yfinance, "Ticker", TickerFalso)
    return YFinanceProvider()


VELA_BUENA = {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000.0}
VELA_BUENA_2 = {"Open": 100.5, "High": 102.0, "Low": 100.0, "Close": 101.5, "Volume": 1200.0}
VELA_SIN_PRECIO = {
    "Open": float("nan"),
    "High": float("nan"),
    "Low": float("nan"),
    "Close": float("nan"),
    "Volume": VOLUMEN_HUERFANO,
}


class TestVelaSinPrecio:
    def test_la_ultima_vela_sin_precios_no_rompe_la_descarga(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        frame = _marco(
            [VELA_BUENA, VELA_BUENA_2, VELA_SIN_PRECIO],
            ["2026-07-22", "2026-07-23", "2026-07-24"],
        )
        proveedor = _proveedor_con(frame, monkeypatch)

        barras = proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)

        assert len(barras) == 2
        assert [b.close for b in barras] == [100.5, 101.5]

    def test_una_vela_sin_precios_en_medio_tambien_se_descarta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        frame = _marco(
            [VELA_BUENA, VELA_SIN_PRECIO, VELA_BUENA_2],
            ["2026-07-22", "2026-07-23", "2026-07-24"],
        )
        proveedor = _proveedor_con(frame, monkeypatch)

        barras = proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)

        assert len(barras) == 2
        assert [b.close for b in barras] == [100.5, 101.5]

    @pytest.mark.parametrize("columna", ["Open", "High", "Low", "Close"])
    def test_da_igual_cual_de_los_cuatro_precios_falte(
        self, columna: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rota = dict(VELA_BUENA_2)
        rota[columna] = float("nan")
        frame = _marco([VELA_BUENA, rota], ["2026-07-22", "2026-07-23"])
        proveedor = _proveedor_con(frame, monkeypatch)

        barras = proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)

        assert len(barras) == 1

    def test_un_infinito_tampoco_es_un_precio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rota = dict(VELA_BUENA_2)
        rota["High"] = float("inf")
        frame = _marco([VELA_BUENA, rota], ["2026-07-22", "2026-07-23"])
        proveedor = _proveedor_con(frame, monkeypatch)

        barras = proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)

        assert len(barras) == 1


class TestNoDescartaDeMas:
    def test_las_velas_con_precio_entran_todas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = _marco([VELA_BUENA, VELA_BUENA_2], ["2026-07-22", "2026-07-23"])
        proveedor = _proveedor_con(frame, monkeypatch)

        assert len(proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)) == 2

    def test_un_volumen_sin_precio_no_arrastra_a_las_demas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lo que importaba del bug: una fila mala tiraba las 161 buenas."""
        filas = [VELA_BUENA] * 5 + [VELA_SIN_PRECIO]
        fechas = [f"2026-07-{dia:02d}" for dia in (20, 21, 22, 23, 24, 25)]
        proveedor = _proveedor_con(_marco(filas, fechas), monkeypatch)

        assert len(proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)) == 5

    def test_volumen_cero_es_legitimo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un dia sin negociacion tiene precios; el volumen a cero no lo invalida."""
        quieta = dict(VELA_BUENA, Volume=0.0)
        frame = _marco([quieta], ["2026-07-22"])
        proveedor = _proveedor_con(frame, monkeypatch)

        barras = proveedor.fetch("GLD", Interval.DAY_1, DESDE, HASTA)

        assert len(barras) == 1
        assert barras[0].volume == 0.0
