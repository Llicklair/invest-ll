"""Qué ve el panel cuando hay una reserva de datos, y qué no.

La reserva existe para que un **backtest** no toque el tramo guardado para validar. Aplicarla
también a la vista del mercado tuvo un efecto que nadie quería: al fijarla, el panel pasó a
mostrar precios de año y medio antes **sin decirlo**. Una cifra que parece de hoy y no lo es es
exactamente lo que este proyecto existe para no hacer.

La separación que fija este fichero:

- **Mirar el mercado** (cotizaciones, rendimiento por periodo, gráficas) usa todo el histórico.
  Ver el precio de ayer no contamina ninguna decisión de estrategia.
- **Medir una estrategia** sigue recortando en la reserva, y avisando de que lo hace.

Si algún día alguien unifica las dos cargas «por simplificar», uno de los dos lados se rompe: o el
panel vuelve a mentir, o la reserva deja de proteger.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from invest_ll.dashboard.data import AvailableAsset, aviso_de_reserva
from invest_ll.data.bar import Interval
from invest_ll.data.reserved import save_reservation

CABECERA = "timestamp,open,high,low,close,volume\n"


@pytest.fixture
def activo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AvailableAsset:
    """Un activo con datos a ambos lados del corte, y una reserva vigente."""
    csv = tmp_path / "DAY_1.csv"
    filas = [
        f"{dia.isoformat()}T00:00:00+00:00,100,101,99,100,1000"
        for dia in (
            date(2024, 12, 29),
            date(2024, 12, 30),
            date(2024, 12, 31),
            date(2025, 1, 2),
            date(2025, 1, 3),
        )
    ]
    csv.write_text(CABECERA + "\n".join(filas) + "\n", encoding="utf-8")

    fichero = tmp_path / "reserved.json"
    save_reservation(date(2025, 1, 1), reason="validacion fuera de muestra", path=fichero)
    monkeypatch.setattr(
        "invest_ll.data.loader.load_reservation",
        lambda: __import__(
            "invest_ll.data.reserved", fromlist=["load_reservation"]
        ).load_reservation(fichero),
    )
    monkeypatch.setattr("invest_ll.dashboard.data.load_reservation", lambda: None)

    return AvailableAsset(
        symbol="BTC/USDT",
        provider="ccxt-binance",
        interval=Interval.DAY_1,
        path=csv,
        provenance=None,
    )


class TestMedirRespetaLaReserva:
    def test_load_recorta_en_el_corte(self, activo: AvailableAsset) -> None:
        serie = activo.load()
        assert serie.bars[-1].timestamp.date() == date(2024, 12, 31)

    def test_y_dice_que_ha_recortado(self, activo: AvailableAsset) -> None:
        _, avisos = activo.load_con_avisos()
        assert any("reservad" in a.message.lower() for a in avisos)


class TestMirarElMercadoVeTodo:
    def test_load_completa_llega_al_ultimo_dato(self, activo: AvailableAsset) -> None:
        serie = activo.load_completa()
        assert serie.bars[-1].timestamp.date() == date(2025, 1, 3)

    def test_ve_mas_velas_que_la_recortada(self, activo: AvailableAsset) -> None:
        assert len(activo.load_completa()) > len(activo.load())


class TestLaCacheNoSirveSeriesViejas:
    """El panel pide la misma serie en cada pantalla, y se guarda en memoria por su contenido."""

    def test_la_misma_serie_no_se_vuelve_a_validar(self, activo: AvailableAsset) -> None:
        assert activo.load_completa() is activo.load_completa()

    def test_reescribir_el_fichero_la_invalida_aunque_mida_lo_mismo(
        self, activo: AvailableAsset
    ) -> None:
        """Mismo tamaño y, en Windows, quizá la misma fecha de modificación: manda el contenido."""
        assert activo.load_completa().bars[-1].close == 100
        texto = activo.path.read_text(encoding="utf-8")
        nuevo = texto.replace("100,101,99,100,1000", "100,101,99,101,1000")
        assert len(nuevo) == len(texto)
        activo.path.write_text(nuevo, encoding="utf-8")

        assert activo.load_completa().bars[-1].close == 101


class TestElPanelPuedeDecirloEnVozAlta:
    def test_sin_reserva_no_hay_nada_que_avisar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("invest_ll.dashboard.data.load_reservation", lambda: None)
        assert aviso_de_reserva() is None

    def test_con_reserva_dice_la_fecha_del_corte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fichero = tmp_path / "reserved.json"
        save_reservation(date(2025, 1, 1), reason="validacion honesta", path=fichero)
        monkeypatch.setattr(
            "invest_ll.dashboard.data.load_reservation",
            lambda: __import__(
                "invest_ll.data.reserved", fromlist=["load_reservation"]
            ).load_reservation(fichero),
        )

        aviso = aviso_de_reserva()

        assert aviso is not None
        assert "2025-01-01" in aviso
        assert "backtest" in aviso.lower()
