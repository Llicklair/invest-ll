"""Datos reservados que ningún backtest puede tocar por accidente.

El test que da sentido al módulo es `test_la_serie_se_recorta_de_verdad`. Una reserva que se
declara pero no recorta es peor que no tenerla: da la sensación de estar protegido sin estarlo —
exactamente el defecto de la pestaña que se definió y nunca se conectó.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.data.reserved import (
    Reservation,
    aviso_al_saltarsela,
    load_reservation,
    save_reservation,
)
from invest_ll.errors import InvalidSeriesError

INICIO = datetime(2020, 1, 1, tzinfo=UTC)


def escribir_csv(destino: Path, velas: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i in range(velas):
            precio = 100.0 + i
            w.writerow(
                [
                    (INICIO + timedelta(days=i)).isoformat(),
                    precio,
                    precio * 1.01,
                    precio * 0.99,
                    precio,
                    1000,
                ]
            )


def cargar(csv_path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    return load_series(
        csv_path,
        symbol="TEST",
        interval=Interval.DAY_1,
        calendar=Continuous24x7(),
        **kwargs,  # type: ignore[arg-type]
    )


class TestFicheroDeReserva:
    def test_sin_fichero_no_hay_reserva(self, tmp_path: Path) -> None:
        """Un proyecto que no la use tiene que seguir funcionando igual."""
        assert load_reservation(tmp_path / "no-existe.json") is None

    def test_guardar_y_leer_conserva_todo(self, tmp_path: Path) -> None:
        destino = tmp_path / "reserved.json"
        save_reservation(date(2025, 1, 1), reason="ultimo anho fuera de muestra", path=destino)

        leida = load_reservation(destino)
        assert leida is not None
        assert leida.cutoff == date(2025, 1, 1)
        assert "fuera de muestra" in leida.reason

    def test_sin_motivo_no_se_puede_reservar(self, tmp_path: Path) -> None:
        """Una reserva sin motivo no se puede evaluar despues."""
        with pytest.raises(ValueError, match="por que reservas"):
            save_reservation(date(2025, 1, 1), reason="  ", path=tmp_path / "r.json")

    def test_un_fichero_corrupto_se_trata_como_ausencia(self, tmp_path: Path) -> None:
        """Fallar aqui impediria cargar cualquier serie: el aviso lo da quien la consulta."""
        destino = tmp_path / "reserved.json"
        destino.write_text("{no es json", encoding="utf-8")
        assert load_reservation(destino) is None

    def test_sabe_que_instantes_cubre(self) -> None:
        r = Reservation(
            cutoff=date(2025, 6, 30), reason="x", created_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert not r.covers(datetime(2025, 6, 30, tzinfo=UTC)), "el dia del corte NO se reserva"
        assert r.covers(datetime(2025, 7, 1, tzinfo=UTC))


class TestElRecorteOcurreDeVerdad:
    """Una reserva que se declara pero no recorta es peor que no tenerla."""

    @pytest.fixture
    def con_reserva(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        fichero = tmp_path / "reserved.json"
        save_reservation(date(2020, 2, 1), reason="reservado para validacion honesta", path=fichero)
        monkeypatch.setattr(
            "invest_ll.data.loader.load_reservation", lambda: load_reservation(fichero)
        )
        return tmp_path / "serie.csv"

    def test_la_serie_se_recorta_de_verdad(self, con_reserva: Path) -> None:
        """EL test de este fichero."""
        escribir_csv(con_reserva, 100)  # del 2020-01-01 al 2020-04-09
        serie, _ = cargar(con_reserva)

        assert len(serie) == 32, "solo enero y el 1 de febrero"
        assert serie.bars[-1].timestamp.date() == date(2020, 2, 1)

    def test_avisa_de_cuantas_velas_reserva(self, con_reserva: Path) -> None:
        escribir_csv(con_reserva, 100)
        _, avisos = cargar(con_reserva)

        recorte = [a for a in avisos if "datos reservados" in a.message]
        assert recorte, "el recorte debe avisar, no ser silencioso"
        assert "68" in recorte[0].message
        assert "validacion honesta" in recorte[0].message

    def test_una_serie_anterior_al_corte_no_se_toca(self, con_reserva: Path) -> None:
        escribir_csv(con_reserva, 10)  # todas anteriores al corte
        serie, avisos = cargar(con_reserva)

        assert len(serie) == 10
        assert not [a for a in avisos if "reservad" in a.message]

    def test_usar_los_reservados_exige_pedirlo(self, con_reserva: Path) -> None:
        escribir_csv(con_reserva, 100)
        serie, avisos = cargar(con_reserva, use_reserved=True)

        assert len(serie) == 100, "con la bandera, la serie llega entera"
        usados = [a for a in avisos if "USA los datos reservados" in a.message]
        assert usados, "saltarsela tiene que quedar por escrito"

    def test_el_aviso_dice_por_que_importa(self, con_reserva: Path) -> None:
        escribir_csv(con_reserva, 100)
        _, avisos = cargar(con_reserva, use_reserved=True)
        detalle = next(a.message for a in avisos if "USA los datos reservados" in a.message)

        assert "no es evidencia fuera de muestra" in detalle
        assert "el mismo backtest otra vez" in detalle

    def test_si_todo_es_posterior_al_corte_falla(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Devolver una serie vacia produciria un informe de cero operaciones sin explicacion."""
        fichero = tmp_path / "reserved.json"
        save_reservation(date(2019, 1, 1), reason="todo reservado", path=fichero)
        monkeypatch.setattr(
            "invest_ll.data.loader.load_reservation", lambda: load_reservation(fichero)
        )

        csv_path = tmp_path / "serie.csv"
        escribir_csv(csv_path, 50)
        with pytest.raises(InvalidSeriesError, match="posterior al corte"):
            cargar(csv_path)


class TestSinReservaNoCambiaNada:
    def test_una_serie_normal_llega_entera(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "serie.csv"
        escribir_csv(csv_path, 50)
        serie, avisos = cargar(csv_path)

        assert len(serie) == 50
        assert not [a for a in avisos if "reservad" in a.message]


class TestTextos:
    def test_el_aviso_es_imprimible_en_consola_windows(self) -> None:
        r = Reservation(
            cutoff=date(2025, 1, 1), reason="prueba", created_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        aviso_al_saltarsela(r).encode("cp1252")
        r.render().encode("cp1252")

    def test_la_reserva_explica_como_saltarsela(self) -> None:
        r = Reservation(
            cutoff=date(2025, 1, 1), reason="prueba", created_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert "explicitamente" in r.render()
