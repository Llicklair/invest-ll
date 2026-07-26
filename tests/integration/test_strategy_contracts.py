"""Toda estrategia cumple el contrato, sin que nadie tenga que acordarse de comprobarlo.

El `Protocol` dice qué forma tiene una estrategia, pero por sí solo no obliga a nada en tiempo de
ejecución: una clase nueva puede olvidarse de `decide`, devolver algo que no es una `Signal`, o
reventar cuando la ventana todavía no tiene datos suficientes. Eso no se descubriría hasta la
mitad de un backtest.

Este fichero recorre **todas** las estrategias de un solo activo y les exige lo mismo. Es
parametrizado a propósito: añadir una estrategia nueva a la lista cuesta una línea, y olvidarse de
añadirla la caza `test_no_falta_ninguna_por_revisar`, que compara la lista con lo que hay en el
paquete. Un contrato que solo cubre lo que alguien recordó apuntar no es un contrato.

No prueba si una estrategia gana dinero — eso es el backtester. Prueba que se puede ejecutar sin
sorpresas.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import invest_ll.strategy as paquete_estrategias
from invest_ll.data.series import PriceSeries
from invest_ll.engine.view import MarketView
from invest_ll.strategy.breakout import BreakoutHighs
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.price_vs_average import PriceVsAverage
from invest_ll.strategy.protocol import Signal, SignalKind, Strategy

from ..fixtures.builders import series_from_closes

# Cada estrategia de un solo activo, con parámetros pequeños para que la serie de prueba baste.
ESTRATEGIAS: list[tuple[str, Strategy]] = [
    ("ma-cross", MovingAverageCrossover(short=3, long=8)),
    ("breakout", BreakoutHighs(lookback=5)),
    ("precio-vs-media", PriceVsAverage(periods=5)),
]

# Las que no entran aquí y por qué. Sin esta lista, `test_no_falta_ninguna_por_revisar` no puede
# distinguir "todavía no cubierta" de "no aplica".
FUERA_DE_CONTRATO = {
    "protocol",  # define el contrato, no lo implementa
    "rotation",  # otro contrato: elige entre varios activos, no emite señales
    "scoring",   # puntúa activos, no decide entradas
    "llm",       # necesita un proveedor de decisiones; se cubre en sus propios tests
}


def serie(precios: list[float]) -> PriceSeries:
    return series_from_closes(precios)


SUBIDA = [100.0 + i for i in range(30)]
BAJADA = [130.0 - i for i in range(30)]
PLANA = [100.0] * 30
DIENTE_DE_SIERRA = [100.0 + (5 if i % 2 else -5) for i in range(30)]


@pytest.mark.parametrize(("nombre", "estrategia"), ESTRATEGIAS, ids=[e[0] for e in ESTRATEGIAS])
class TestContratoDeEstrategia:
    def test_cumple_el_protocolo(self, nombre: str, estrategia: Strategy) -> None:
        assert isinstance(estrategia, Strategy), f"{nombre} no satisface el Protocol"

    @pytest.mark.parametrize(
        "precios", [SUBIDA, BAJADA, PLANA, DIENTE_DE_SIERRA], ids=["sube", "baja", "plana", "sierra"]
    )
    def test_decide_devuelve_senal_o_nada(
        self, nombre: str, estrategia: Strategy, precios: list[float]
    ) -> None:
        """Nunca un string, un bool ni un objeto a medias: o `Signal` o `None`."""
        datos = serie(precios)
        for i in range(len(datos)):
            resultado = estrategia.decide(MarketView(datos, i))
            assert resultado is None or isinstance(resultado, Signal), (
                f"{nombre} devolvio {type(resultado).__name__} en el periodo {i}"
            )
            if isinstance(resultado, Signal):
                assert isinstance(resultado.kind, SignalKind)

    def test_al_arrancar_se_abstiene_en_vez_de_reventar(
        self, nombre: str, estrategia: Strategy
    ) -> None:
        """El arranque es donde mas facil es pasarse de indice: aun no hay historia.

        Con una sola vela ninguna de estas estrategias puede calcular su media ni su maximo, asi
        que lo correcto es abstenerse. Emitir una senal ahi seria inventarsela.
        """
        datos = serie(SUBIDA)
        assert estrategia.decide(MarketView(datos, 0)) is None, (
            f"{nombre} emitio una senal con una sola vela, sin historia con la que decidir"
        )

    def test_no_mira_al_futuro(self, nombre: str, estrategia: Strategy) -> None:
        """La decision en el periodo i no cambia si el futuro cambia.

        Es el Principio II hecho comprobacion mecanica: se recorta la serie en i y se compara con
        la serie entera vista desde i. Si algo distinto sale, la estrategia estaba leyendo velas
        que en ese momento no existian.
        """
        completa = serie(SUBIDA + [500.0] * 5)  # el futuro es escandalosamente distinto
        recortada = serie(SUBIDA)

        for i in range(len(recortada)):
            con_futuro = estrategia.decide(MarketView(completa, i))
            sin_futuro = estrategia.decide(MarketView(recortada, i))
            assert type(con_futuro) is type(sin_futuro), (
                f"{nombre} decide distinto en el periodo {i} segun lo que venga DESPUES"
            )
            if con_futuro is not None and sin_futuro is not None:
                assert con_futuro.kind is sin_futuro.kind

    def test_es_determinista(self, nombre: str, estrategia: Strategy) -> None:
        datos = serie(DIENTE_DE_SIERRA)
        primera = [estrategia.decide(MarketView(datos, i)) for i in range(len(datos))]
        segunda = [estrategia.decide(MarketView(datos, i)) for i in range(len(datos))]

        assert [None if s is None else s.kind for s in primera] == [
            None if s is None else s.kind for s in segunda
        ], f"{nombre} da resultados distintos con la misma entrada"


class TestLaListaEstaCompleta:
    """Un contrato que solo cubre lo que alguien recordo apuntar no es un contrato."""

    def test_no_falta_ninguna_por_revisar(self) -> None:
        modulos = {
            nombre
            for _, nombre, _ in pkgutil.iter_modules(paquete_estrategias.__path__)
            if not nombre.startswith("_")
        }
        cubiertas = {
            type(estrategia).__module__.rsplit(".", 1)[-1] for _, estrategia in ESTRATEGIAS
        }
        sin_revisar = modulos - cubiertas - FUERA_DE_CONTRATO

        assert not sin_revisar, (
            f"estrategias sin contrato comprobado: {sorted(sin_revisar)}. "
            "Anadela a ESTRATEGIAS, o a FUERA_DE_CONTRATO explicando por que no aplica."
        )

    def test_lo_excluido_existe_de_verdad(self) -> None:
        """Una exclusion que apunta a un modulo borrado esconde una estrategia sin cubrir."""
        modulos = {
            nombre for _, nombre, _ in pkgutil.iter_modules(paquete_estrategias.__path__)
        }
        assert modulos >= FUERA_DE_CONTRATO, (
            f"FUERA_DE_CONTRATO nombra modulos que ya no existen: {sorted(FUERA_DE_CONTRATO - modulos)}"
        )

    def test_toda_estrategia_cubierta_declara_decide(self) -> None:
        for nombre, estrategia in ESTRATEGIAS:
            metodo = getattr(type(estrategia), "decide", None)
            assert callable(metodo), f"{nombre} no expone decide()"
            firma = inspect.signature(metodo)
            assert "view" in firma.parameters, f"{nombre}.decide no recibe una vista de mercado"

    def test_el_paquete_se_puede_importar_entero(self) -> None:
        """Un modulo que no importa no falla hasta que alguien lo usa en produccion."""
        for _, nombre, _ in pkgutil.iter_modules(paquete_estrategias.__path__):
            importlib.import_module(f"invest_ll.strategy.{nombre}")
