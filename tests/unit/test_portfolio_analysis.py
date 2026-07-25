"""Análisis de diversificación de una cartera."""

from __future__ import annotations

import math

import pytest

from invest_ll.data.universe import Universe, build_universe
from invest_ll.report.portfolio import (
    CORRELACION_ALTA,
    MINIMO_ACTIVOS_EFECTIVOS,
    analyze_portfolio,
)

from ..fixtures.builders import series_from_closes


def universo(**activos: list[float]) -> Universe:
    return build_universe(
        [series_from_closes(precios, symbol=nombre) for nombre, precios in activos.items()]
    )


def onda(n: int, *, fase: float = 0.0, base: float = 100.0) -> list[float]:
    return [base + 20.0 * math.sin(i / 10.0 + fase) for i in range(n)]


def sube(n: int, tasa: float = 1.0) -> list[float]:
    return [100.0 + tasa * i for i in range(n)]


class TestCorrelacion:
    def test_dos_activos_identicos_estan_perfectamente_correlacionados(self) -> None:
        precios = onda(200)
        analisis = analyze_portfolio(universo(A=precios, B=list(precios)))
        assert analisis.average_correlation == pytest.approx(1.0, abs=0.01)

    def test_dos_activos_opuestos_estan_correlacionados_negativamente(self) -> None:
        """Uno sube cuando el otro baja: la diversificacion ideal."""
        a = onda(200)
        b = [200.0 - (p - 100.0) for p in a]
        analisis = analyze_portfolio(universo(A=a, B=b))
        assert analisis.average_correlation < -0.9

    def test_activos_desfasados_correlacionan_menos(self) -> None:
        analisis = analyze_portfolio(universo(A=onda(300), B=onda(300, fase=math.pi / 2)))
        assert abs(analisis.average_correlation) < 0.5

    def test_se_calcula_sobre_rendimientos_no_sobre_precios(self) -> None:
        """Dos activos que suben en linea recta tienen precios muy correlacionados...

        ...pero sus rendimientos diarios no dicen nada. Medir sobre precios daria una correlacion
        casi perfecta y una falsa sensacion de concentracion.
        """
        analisis = analyze_portfolio(universo(A=sube(200, 1.0), B=sube(200, 3.0)))
        assert abs(analisis.average_correlation) < 0.99


class TestDiversificacion:
    def test_activos_identicos_no_diversifican(self) -> None:
        precios = onda(200)
        analisis = analyze_portfolio(universo(A=precios, B=list(precios), C=list(precios)))
        assert not analisis.is_diversified
        assert analisis.effective_assets == pytest.approx(1.0, abs=0.1)

    def test_activos_independientes_si_diversifican(self) -> None:
        analisis = analyze_portfolio(universo(A=onda(300), B=onda(300, fase=math.pi / 2)))
        assert analisis.is_diversified
        assert analisis.effective_assets > 1.5

    def test_los_activos_efectivos_nunca_superan_a_los_reales(self) -> None:
        analisis = analyze_portfolio(universo(A=onda(200), B=onda(200, fase=1.0), C=sube(200)))
        assert analisis.effective_assets <= len(analisis.symbols)

    def test_el_umbral_de_alerta_esta_documentado(self) -> None:
        assert 0.0 < CORRELACION_ALTA < 1.0
        assert MINIMO_ACTIVOS_EFECTIVOS >= 2.0

    def test_seis_activos_que_equivalen_a_uno_y_medio_no_diversifican(self) -> None:
        """El caso real que destapo el fallo de calibracion.

        Seis sectores de bolsa dan correlacion media 0,60 -- por debajo del umbral de 0,7 -- y aun
        asi equivalen a 1,5 activos. El aviso tiene que saltar ahi.
        """
        base = onda(300)
        casi_iguales = {f"S{i}": [p + i * 0.01 for p in base] for i in range(6)}
        analisis = analyze_portfolio(universo(**casi_iguales))
        assert analisis.effective_assets < 2.0
        assert not analisis.is_diversified


class TestPares:
    def test_identifica_el_par_mas_parecido(self) -> None:
        precios = onda(300)
        analisis = analyze_portfolio(
            universo(A=precios, B=list(precios), C=onda(300, fase=math.pi / 2))
        )
        mas = analisis.most_correlated
        assert mas is not None
        assert {mas.a, mas.b} == {"A", "B"}

    def test_hay_un_par_por_cada_combinacion(self) -> None:
        analisis = analyze_portfolio(universo(A=onda(200), B=onda(200, fase=1.0), C=sube(200)))
        assert len(analisis.pairs) == 3  # 3 activos -> 3 pares


class TestSalida:
    def test_avisa_cuando_la_cartera_no_diversifica(self) -> None:
        precios = onda(200)
        texto = analyze_portfolio(universo(A=precios, B=list(precios))).render()
        assert "se" in texto.lower()
        assert "[!]" in texto

    def test_no_avisa_cuando_si_diversifica(self) -> None:
        texto = analyze_portfolio(universo(A=onda(300), B=onda(300, fase=math.pi / 2))).render()
        assert "[!]" not in texto

    def test_es_imprimible_en_consola_windows(self) -> None:
        analyze_portfolio(universo(A=onda(200), B=sube(200))).render().encode("cp1252")


def test_una_serie_demasiado_corta_se_rechaza() -> None:
    """Con veinte dias, la correlacion es ruido con aspecto de dato."""
    with pytest.raises(ValueError, match="al menos"):
        analyze_portfolio(universo(A=onda(20), B=onda(20)))
