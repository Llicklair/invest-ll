"""Análisis de activos (T041, T043, T045, T046).

Lo que se prueba aquí es sobre todo **presentación**: que el operador siempre pueda saber qué
puede comprobar y qué es una lectura. Es una restricción sobre lo que el sistema puede decir, no
sobre lo que hace.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from invest_ll.analysis.models import ADVERTENCIA_TEMPORAL, AssetAnalysis, Fact

CUANDO = datetime(2026, 7, 25, tzinfo=UTC)


def dato(label: str = "Sector", value: str = "Tecnologia") -> Fact:
    return Fact(label=label, value=value, source="yfinance", as_of=date(2026, 7, 1))


def analisis(**cambios: object) -> AssetAnalysis:
    base: dict[str, object] = {
        "symbol": "AAPL",
        "kind": "empresa",
        "facts": (dato(),),
        "narrative": "fabrica telefonos y ordenadores",
        "scenarios": ("si suben los tipos, podria sufrir",),
        "retrieved_at": CUANDO,
    }
    base.update(cambios)
    return AssetAnalysis(**base)  # type: ignore[arg-type]


class TestFact:
    def test_un_dato_completo_se_construye(self) -> None:
        assert dato().value == "Tecnologia"

    def test_sin_fuente_no_se_construye(self) -> None:
        """FR-017: si no se puede decir de donde sale, no se presenta como dato."""
        with pytest.raises(ValueError, match="fuente"):
            Fact(label="Sector", value="x", source="  ", as_of=date(2026, 7, 1))

    def test_sin_etiqueta_no_se_construye(self) -> None:
        with pytest.raises(ValueError, match="etiqueta"):
            Fact(label="", value="x", source="yfinance", as_of=date(2026, 7, 1))

    def test_al_mostrarse_lleva_fuente_y_fecha(self) -> None:
        texto = dato().render()
        assert "yfinance" in texto
        assert "2026-07-01" in texto

    def test_es_inmutable(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            dato().value = "otro"  # type: ignore[misc]


class TestSeparacion:
    """FR-049: mezclar dato e interpretacion convierte un informe comprobable en uno dudoso."""

    def test_los_hechos_y_la_narrativa_son_campos_distintos(self) -> None:
        a = analisis()
        assert a.facts
        assert a.narrative
        assert a.narrative not in [f.value for f in a.facts]

    def test_la_salida_los_separa_en_secciones(self) -> None:
        texto = analisis().render()
        assert "DATOS VERIFICABLES" in texto
        assert "INTERPRETACION" in texto
        assert texto.index("DATOS VERIFICABLES") < texto.index("INTERPRETACION")

    def test_avisa_de_que_la_interpretacion_puede_estar_equivocada(self) -> None:
        assert "puede" in analisis().render()
        assert "equivocada" in analisis().render()


class TestEscenarios:
    """FR-018: escenarios, nunca predicciones."""

    def test_se_presentan_como_escenarios(self) -> None:
        texto = analisis().render()
        assert "NO son previsiones" in texto

    def test_dice_que_podrian_pasar_no_que_vayan_a_pasar(self) -> None:
        assert "no que vayan a pasar" in analisis().render()

    def test_sin_escenarios_no_aparece_la_seccion(self) -> None:
        assert "ESCENARIOS" not in analisis(scenarios=()).render()


class TestActivosSinEmpresaDetras:
    """FR-019: al oro no se le inventa una empresa."""

    def test_una_materia_prima_no_tiene_entidad(self) -> None:
        assert not analisis(symbol="GLD", kind="materia prima").has_entity

    def test_un_indice_no_tiene_entidad(self) -> None:
        assert not analisis(symbol="SPY", kind="indice").has_entity

    def test_una_empresa_si(self) -> None:
        assert analisis().has_entity

    def test_se_explica_que_es_aunque_no_haya_empresa(self) -> None:
        texto = analisis(symbol="GLD", kind="materia prima", facts=()).render()
        assert "materia prima" in texto
        assert "sin datos disponibles" in texto


class TestAdvertenciaTemporal:
    """FR-051: los datos actuales no valen para juzgar el pasado."""

    def test_toda_salida_la_lleva(self) -> None:
        assert ADVERTENCIA_TEMPORAL in analisis().render()

    def test_explica_por_que(self) -> None:
        assert "seria mirar el futuro" in ADVERTENCIA_TEMPORAL

    def test_es_imprimible_en_consola_windows(self) -> None:
        analisis().render().encode("cp1252")


class TestValidacion:
    def test_sin_simbolo_no_se_construye(self) -> None:
        with pytest.raises(ValueError, match="simbolo"):
            analisis(symbol="")

    def test_una_fecha_sin_zona_horaria_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            analisis(retrieved_at=datetime(2026, 7, 25))
