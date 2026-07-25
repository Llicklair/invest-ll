"""El investigador de datos fundamentales (T044).

Con un doble en lugar de la red: la suite entera corre con los sockets bloqueados.
"""

from __future__ import annotations

from typing import Any

from invest_ll.analysis.yfinance_researcher import SIN_EMPRESA, YFinanceResearcher

CRUDO_APPLE: dict[str, Any] = {
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "country": "United States",
    "fullTimeEmployees": 164000,
    "marketCap": 3_400_000_000_000,
    "trailingPE": 33.5,
    "profitMargins": 0.246,
    "debtToEquity": 145.0,
    "longBusinessSummary": "Disena y vende telefonos, ordenadores y servicios.",
}


def investigador(datos: dict[str, Any] | None = None) -> YFinanceResearcher:
    return YFinanceResearcher(fetch=lambda _: datos if datos is not None else CRUDO_APPLE)


class TestEmpresas:
    def test_extrae_los_datos_basicos(self) -> None:
        a = investigador().analyze("AAPL")
        etiquetas = {f.label for f in a.facts}
        assert "Sector" in etiquetas
        assert "Valor de mercado" in etiquetas

    def test_todos_los_datos_llevan_fuente_y_fecha(self) -> None:
        for f in investigador().analyze("AAPL").facts:
            assert f.source == "yfinance"
            assert f.as_of is not None

    def test_el_valor_de_mercado_se_lee_en_castellano(self) -> None:
        """3.4e12 no le dice nada a nadie."""
        a = investigador().analyze("AAPL")
        valor = next(f.value for f in a.facts if f.label == "Valor de mercado")
        assert "billones" in valor

    def test_los_porcentajes_salen_como_porcentajes(self) -> None:
        a = investigador().analyze("AAPL")
        margen = next(f.value for f in a.facts if f.label == "Margen de beneficio")
        assert margen.endswith("%")

    def test_la_descripcion_va_en_la_narrativa_no_en_los_hechos(self) -> None:
        a = investigador().analyze("AAPL")
        assert "telefonos" in a.narrative
        assert not any("telefonos" in f.value for f in a.facts)

    def test_lo_primero_que_se_lee_es_a_que_se_dedica(self) -> None:
        a = investigador().analyze("AAPL")
        assert a.facts[0].label == "Sector"


class TestCamposQueFaltan:
    def test_un_campo_ausente_no_inventa_un_dato(self) -> None:
        a = investigador({"sector": "Technology"}).analyze("XYZ")
        assert {f.label for f in a.facts} == {"Sector"}

    def test_un_valor_no_numerico_se_descarta(self) -> None:
        a = investigador({"marketCap": "no aplicable", "sector": "X"}).analyze("XYZ")
        assert not any(f.label == "Valor de mercado" for f in a.facts)

    def test_sin_ningun_dato_el_tipo_es_desconocido(self) -> None:
        assert investigador({}).analyze("XYZ").kind == "desconocido"


class TestActivosSinEmpresa:
    def test_el_oro_no_recibe_una_empresa_inventada(self) -> None:
        """FR-019."""
        a = investigador().analyze("GLD")
        assert a.kind == "materia prima"
        assert not a.has_entity
        assert "metal" in a.narrative

    def test_los_conocidos_se_explican_sin_consultar_al_proveedor(self) -> None:
        def explota(_: str) -> dict[str, Any]:
            raise AssertionError("no deberia consultarse para un activo conocido")

        for simbolo in SIN_EMPRESA:
            YFinanceResearcher(fetch=explota).analyze(simbolo)


class TestFallos:
    def test_un_error_del_proveedor_no_revienta_el_analisis(self) -> None:
        """Que falle yfinance no puede tumbar el comando: se dice y se sigue."""

        def falla(_: str) -> dict[str, Any]:
            raise RuntimeError("proveedor caido")

        a = YFinanceResearcher(fetch=falla).analyze("AAPL")
        assert a.kind == "desconocido"
        assert "No se pudieron obtener datos" in a.narrative
        assert a.facts == ()

    def test_el_fallo_no_se_presenta_como_dato(self) -> None:
        def falla(_: str) -> dict[str, Any]:
            raise RuntimeError("proveedor caido")

        a = YFinanceResearcher(fetch=falla).analyze("AAPL")
        assert "DATOS VERIFICABLES" in a.render()
        assert "sin datos disponibles" in a.render()
