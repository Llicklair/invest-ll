"""Estimaciones y su comparación con la realidad (T049-T055).

El test que define la historia es `test_reescribir_una_estimacion_falla`. Un historial que se
puede editar a posteriori no prueba nada — y esta es la única evidencia limpia que vamos a tener
sobre si el LLM sirve para algo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.tracking.forecast import build_track_record, pending
from invest_ll.tracking.models import Forecast, Holding, Outcome
from invest_ll.tracking.store import ForecastAlreadyRecordedError, ForecastStore

D = Decimal
CUANDO = datetime(2026, 1, 1, tzinfo=UTC)


def estimacion(valor: str = "10000", *, cuando: datetime = CUANDO, dias: int = 90) -> Forecast:
    return Forecast(
        issued_at=cuando,
        horizon_days=dias,
        portfolio=(Holding(symbol="GLD", quantity=D("10")),),
        expected_value=D(valor),
        basis="aportaciones periodicas sobre cartera diversificada",
        model="claude-opus-5",
    )


class TestInmutabilidad:
    def test_una_estimacion_es_inmutable(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            estimacion().expected_value = D(999)  # type: ignore[misc]

    def test_el_identificador_sale_del_contenido(self) -> None:
        """Asi no se puede reescribir una estimacion fingiendo que es la misma."""
        assert estimacion("10000").forecast_id == estimacion("10000").forecast_id
        assert estimacion("10000").forecast_id != estimacion("20000").forecast_id

    def test_reescribir_una_estimacion_falla(self, tmp_path: Path) -> None:
        """FR-021. EL test de este fichero."""
        store = ForecastStore(tmp_path)
        store.append(estimacion())
        with pytest.raises(ForecastAlreadyRecordedError):
            store.append(estimacion())

    def test_el_almacen_solo_anade(self, tmp_path: Path) -> None:
        store = ForecastStore(tmp_path)
        store.append(estimacion("10000"))
        store.append(estimacion("20000"))
        assert len(store.forecasts()) == 2

    def test_lo_guardado_sobrevive_al_proceso(self, tmp_path: Path) -> None:
        ForecastStore(tmp_path).append(estimacion())
        assert len(ForecastStore(tmp_path).forecasts()) == 1

    def test_no_se_pierde_precision_al_ir_a_disco(self, tmp_path: Path) -> None:
        store = ForecastStore(tmp_path)
        store.append(estimacion("12345.6789"))
        assert store.forecasts()[0].expected_value == D("12345.6789")


class TestEvaluacion:
    def test_compara_estimado_con_real(self, tmp_path: Path) -> None:
        store = ForecastStore(tmp_path)
        f = estimacion("10000")
        store.append(f)
        store.record_outcome(
            Outcome(forecast_id=f.forecast_id, measured_at=CUANDO, actual_value=D("11000"))
        )
        historial = build_track_record(store)
        assert historial.count == 1
        assert historial.evaluations[0].error == D(1000)

    def test_sin_resultado_todavia_no_cuenta(self, tmp_path: Path) -> None:
        """Incluirla como acierto o como fallo seria inventarse un dato."""
        store = ForecastStore(tmp_path)
        store.append(estimacion())
        assert build_track_record(store).count == 0
        assert len(pending(store)) == 1

    def test_sobreestimar_se_detecta(self, tmp_path: Path) -> None:
        store = ForecastStore(tmp_path)
        f = estimacion("10000")
        store.append(f)
        store.record_outcome(
            Outcome(forecast_id=f.forecast_id, measured_at=CUANDO, actual_value=D("8000"))
        )
        assert build_track_record(store).evaluations[0].overestimated


class TestLosFallosSeQuedan:
    """FR-023: un historial que solo guarda los aciertos no mide nada."""

    def historial(self, tmp_path: Path, reales: list[str]):  # type: ignore[no-untyped-def]
        store = ForecastStore(tmp_path)
        for i, real in enumerate(reales):
            f = estimacion("10000", cuando=CUANDO + timedelta(days=i))
            store.append(f)
            store.record_outcome(
                Outcome(forecast_id=f.forecast_id, measured_at=CUANDO, actual_value=D(real))
            )
        return build_track_record(store)

    def test_los_fallos_aparecen_en_el_historial(self, tmp_path: Path) -> None:
        h = self.historial(tmp_path, ["12000", "3000", "11000"])
        assert h.count == 3
        assert h.overestimates == 1

    def test_detecta_el_optimismo_sistematico(self, tmp_path: Path) -> None:
        """FR-024: si el sistema siempre se pasa, hay que poder verlo."""
        h = self.historial(tmp_path, ["5000", "6000", "4000", "7000", "5500"])
        assert h.tendency == "tiende a ser demasiado optimista"

    def test_detecta_quedarse_corto(self, tmp_path: Path) -> None:
        h = self.historial(tmp_path, ["15000", "16000", "14000", "17000", "15500"])
        assert h.tendency == "tiende a quedarse corto"

    def test_sin_sesgo_claro_lo_dice(self, tmp_path: Path) -> None:
        h = self.historial(tmp_path, ["11000", "9000", "10500", "9500"])
        assert h.tendency == "no muestra un sesgo claro"

    def test_la_salida_dice_por_que_estan_los_fallos(self, tmp_path: Path) -> None:
        texto = self.historial(tmp_path, ["12000", "3000"]).render()
        assert "solo guarda los" in texto


class TestSalida:
    def test_un_historial_vacio_lo_explica_sin_alarmar(self, tmp_path: Path) -> None:
        texto = build_track_record(ForecastStore(tmp_path)).render()
        assert "Es lo normal al principio" in texto

    def test_es_imprimible_en_consola_windows(self, tmp_path: Path) -> None:
        store = ForecastStore(tmp_path)
        f = estimacion()
        store.append(f)
        store.record_outcome(
            Outcome(forecast_id=f.forecast_id, measured_at=CUANDO, actual_value=D("9000"))
        )
        build_track_record(store).render().encode("cp1252")


class TestValidacion:
    def test_un_horizonte_no_positivo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="horizonte"):
            estimacion(dias=0)

    def test_sin_explicar_en_que_se_basa_se_rechaza(self) -> None:
        """Una estimacion sin base no se puede evaluar despues."""
        with pytest.raises(ValueError, match="en que se basa"):
            Forecast(
                issued_at=CUANDO,
                horizon_days=90,
                portfolio=(),
                expected_value=D(1),
                basis="   ",
            )

    def test_una_cantidad_no_positiva_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="cantidad no positiva"):
            Holding(symbol="GLD", quantity=D(0))

    def test_el_vencimiento_se_calcula(self) -> None:
        assert estimacion(dias=90).due_at == CUANDO + timedelta(days=90)
        assert not estimacion(dias=90).is_due(CUANDO)
        assert estimacion(dias=90).is_due(CUANDO + timedelta(days=91))
