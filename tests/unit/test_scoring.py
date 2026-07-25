"""Nota de 1 a 10 para candidatos a inversión."""

from __future__ import annotations

import pytest

from invest_ll.data.universe import Universe, build_universe
from invest_ll.engine.universe_view import UniverseView
from invest_ll.strategy.rotation import RotationStrategy
from invest_ll.strategy.scoring import (
    NOTA_MAXIMA,
    NOTA_MINIMA,
    UMBRAL_CANDIDATO,
    ScoredRotation,
    score_all,
    score_asset,
)

from ..fixtures.builders import series_from_closes


def universo(a: list[float], b: list[float]) -> Universe:
    return build_universe([series_from_closes(a, symbol="A"), series_from_closes(b, symbol="B")])


def sube(n: int, tasa: float = 1.0) -> list[float]:
    return [100.0 + tasa * i for i in range(n)]


def baja(n: int, tasa: float = 0.3) -> list[float]:
    return [200.0 - tasa * i for i in range(n)]


def plano(n: int) -> list[float]:
    return [100.0] * n


class TestNota:
    def test_sin_historico_suficiente_no_puntua(self) -> None:
        """Puntuar con menos datos daria notas altas por azar."""
        u = universo(sube(50), sube(50))
        assert score_asset(UniverseView(u, cursor=40), "A") is None

    def test_la_nota_esta_en_la_escala(self) -> None:
        u = universo(sube(300), baja(300))
        for symbol in ("A", "B"):
            nota = score_asset(UniverseView(u, cursor=250), symbol)
            assert nota is not None
            assert NOTA_MINIMA <= nota.score <= NOTA_MAXIMA

    def test_un_activo_alcista_puntua_alto(self) -> None:
        u = universo(sube(300, 2.0), plano(300))
        nota = score_asset(UniverseView(u, cursor=250), "A")
        assert nota is not None
        assert nota.score >= UMBRAL_CANDIDATO

    def test_un_activo_bajista_puntua_bajo(self) -> None:
        u = universo(baja(300, 0.5), plano(300))
        nota = score_asset(UniverseView(u, cursor=250), "A")
        assert nota is not None
        assert nota.score < UMBRAL_CANDIDATO

    def test_un_activo_plano_no_es_candidato(self) -> None:
        """Ni sube ni baja: no hay razon para invertir en el."""
        u = universo(plano(300), sube(300))
        nota = score_asset(UniverseView(u, cursor=250), "A")
        assert nota is not None
        assert not nota.is_candidate

    def test_el_desglose_explica_la_nota(self) -> None:
        """Una nota de 7 sin explicacion es un numero que hay que creerse."""
        u = universo(sube(300, 2.0), plano(300))
        nota = score_asset(UniverseView(u, cursor=250), "A")
        assert nota is not None
        texto = nota.describe()
        for parte in ("tendencia", "impulso", "regularidad", "riesgo"):
            assert parte in texto
        texto.encode("cp1252")


class TestSinLookAhead:
    def test_la_nota_no_depende_del_futuro(self) -> None:
        """Mismo pasado, futuros opuestos: la nota de hoy debe ser identica."""
        # La caida del futuro "malo" no puede llegar a cero: el motor rechaza precios no positivos.
        pasado = sube(200)
        u_bueno = universo([*pasado, *sube(100, 5.0)], sube(300))
        u_malo = universo([*pasado, *baja(100, 1.0)], sube(300))

        a = score_asset(UniverseView(u_bueno, cursor=180), "A")
        b = score_asset(UniverseView(u_malo, cursor=180), "A")

        assert a is not None
        assert b is not None
        assert a.score == b.score

    def test_es_determinista(self) -> None:
        u = universo(sube(300), baja(300))
        vista = UniverseView(u, cursor=250)
        assert score_asset(vista, "A") == score_asset(vista, "A")


class TestOrdenacion:
    def test_score_all_ordena_de_mejor_a_peor(self) -> None:
        u = universo(sube(300, 2.0), baja(300, 0.5))
        notas = score_all(UniverseView(u, cursor=250))
        assert [n.symbol for n in notas] == ["A", "B"]
        assert notas[0].score >= notas[1].score

    def test_omite_los_que_no_se_pueden_puntuar(self) -> None:
        u = universo(sube(300), sube(300))
        assert score_all(UniverseView(u, cursor=50)) == []


class TestEstrategia:
    def test_cumple_el_protocolo_de_rotacion(self) -> None:
        assert isinstance(ScoredRotation(), RotationStrategy)

    def test_elige_el_de_mejor_nota_si_supera_el_umbral(self) -> None:
        u = universo(sube(300, 2.0), plano(300))
        assert ScoredRotation(threshold=7.0).choose(UniverseView(u, cursor=250)) == "A"

    def test_si_ninguno_llega_al_umbral_se_queda_fuera(self) -> None:
        """La diferencia con el momentum puro: aquel elige al mejor de una clase suspendida."""
        u = universo(baja(300, 0.5), baja(300, 0.3))
        assert ScoredRotation(threshold=7.0).choose(UniverseView(u, cursor=250)) is None

    def test_un_umbral_mas_bajo_admite_mas_activos(self) -> None:
        u = universo(plano(300), baja(300, 0.2))
        assert ScoredRotation(threshold=10.0).choose(UniverseView(u, cursor=250)) is None
        assert ScoredRotation(threshold=1.0).choose(UniverseView(u, cursor=250)) is not None

    @pytest.mark.parametrize("umbral", [0.0, 11.0, -3.0])
    def test_umbral_fuera_de_escala_se_rechaza(self, umbral: float) -> None:
        with pytest.raises(ValueError, match="umbral"):
            ScoredRotation(threshold=umbral)


def test_el_desglose_es_imprimible_en_consola_windows() -> None:
    """Tercera vez que un separador no-ASCII rompe la salida. Ahora hay test."""
    u = universo(sube(300, 2.0), plano(300))
    nota = score_asset(UniverseView(u, cursor=250), "A")
    assert nota is not None
    nota.describe().encode("cp1252")
