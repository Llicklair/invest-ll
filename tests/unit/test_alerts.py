"""Las alertas por activo.

Hay dos tests que son la razón de ser del fichero, y no miden números:

- `test_una_serie_que_solo_sube_no_produce_ninguna_alerta`: las alertas saltan por riesgo, nunca
  por ganancias. Una que dijera "GLD subió un 20%" no informa de nada que necesites — existe para
  que abras la aplicación, que es exactamente el mecanismo que la FCA midió en +11% de
  operaciones.
- `test_ningun_mensaje_pide_actuar`: informan de un estado, no piden una acción.

El resto comprueba que las cuentas están bien, que es necesario pero no es lo difícil.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from invest_ll.alerts.engine import NADA_QUE_CONTAR, evaluate, render
from invest_ll.alerts.models import (
    CAIDA_DESDE_MAXIMO,
    DATOS_OBSOLETOS,
    DESVIACION_DEL_PLAN,
    PEOR_DE_LO_SIMULADO,
    PERDIDA_DESDE_TU_ENTRADA,
    Alert,
    Nivel,
    Position,
    Umbrales,
)
from invest_ll.alerts.rules import (
    caida_desde_maximo,
    datos_obsoletos,
    desviacion_del_plan,
    peor_de_lo_simulado,
    perdida_desde_tu_entrada,
)
from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.series import PriceSeries
from invest_ll.errors import InvalidSeriesError

from ..fixtures.builders import ORIGIN, series_from_closes

D = Decimal
AHORA = ORIGIN + timedelta(days=400)


def serie(cierres: list[float], *, symbol: str = "AAA") -> PriceSeries:
    return series_from_closes(cierres, symbol=symbol)


def ultimo_dia(s: PriceSeries) -> datetime:
    return s.bars[-1].timestamp


class TestDatosObsoletos:
    def test_una_serie_al_dia_no_avisa(self) -> None:
        s = serie([100.0] * 10)
        assert datos_obsoletos(s, ahora=ultimo_dia(s)) is None

    def test_una_serie_vieja_avisa_y_pide_revisar(self) -> None:
        s = serie([100.0] * 10)
        alerta = datos_obsoletos(s, ahora=ultimo_dia(s) + timedelta(days=30))

        assert alerta is not None
        assert alerta.code == DATOS_OBSOLETOS
        assert alerta.level is Nivel.REVISAR, "datos viejos invalidan todo lo demas"
        assert alerta.measured == D(30)

    def test_justo_en_el_umbral_no_avisa(self) -> None:
        """Un dia menos que el umbral no es motivo: los limites se comprueban en su borde."""
        s = serie([100.0] * 10)
        umbrales = Umbrales(dias_sin_datos=7)
        assert (
            datos_obsoletos(s, ahora=ultimo_dia(s) + timedelta(days=6), umbrales=umbrales) is None
        )
        assert (
            datos_obsoletos(s, ahora=ultimo_dia(s) + timedelta(days=7), umbrales=umbrales)
            is not None
        )

    def test_el_mensaje_dice_de_cuando_son_los_datos(self) -> None:
        """Sin la fecha, "llevan 30 dias" obliga a calcular mentalmente de que dia se habla."""
        s = serie([100.0] * 10)
        alerta = datos_obsoletos(s, ahora=ultimo_dia(s) + timedelta(days=30))
        assert alerta is not None
        assert str(ultimo_dia(s).date()) in alerta.message


class TestCaidaDesdeMaximo:
    def test_una_caida_grande_avisa(self) -> None:
        alerta = caida_desde_maximo(serie([100.0, 120.0, 80.0]))
        assert alerta is not None
        assert alerta.code == CAIDA_DESDE_MAXIMO
        assert alerta.measured is not None
        assert abs(alerta.measured - D("0.3333")) < D("0.001")

    def test_una_caida_pequenha_no_avisa(self) -> None:
        assert caida_desde_maximo(serie([100.0, 105.0, 100.0])) is None

    def test_dice_que_es_del_activo_y_no_de_tu_posicion(self) -> None:
        """La confusion entre las dos cosas es la forma mas facil de asustar sin motivo."""
        alerta = caida_desde_maximo(serie([100.0, 120.0, 80.0]))
        assert alerta is not None
        assert "no de tu posicion" in alerta.message

    def test_una_serie_de_una_vela_no_revienta(self) -> None:
        assert caida_desde_maximo(serie([100.0])) is None


class TestPeorDeLoSimulado:
    """La regla que da sentido al modulo: compara lo que vives con lo que aceptaste."""

    def test_cuando_la_realidad_supera_al_plan_avisa(self) -> None:
        # Cae un 30% sobre 10.000 = 3.000 de caida real, contra 1.000 simulados.
        alerta = peor_de_lo_simulado(
            serie([100.0, 100.0, 70.0]), drawdown_simulado=D(-1000), capital=D(10000)
        )
        assert alerta is not None
        assert alerta.code == PEOR_DE_LO_SIMULADO
        assert alerta.level is Nivel.REVISAR

    def test_dentro_de_lo_previsto_no_avisa(self) -> None:
        alerta = peor_de_lo_simulado(
            serie([100.0, 100.0, 98.0]), drawdown_simulado=D(-5000), capital=D(10000)
        )
        assert alerta is None

    def test_el_signo_del_drawdown_da_igual(self) -> None:
        """Los informes lo dan negativo; que alguien lo pase positivo no puede cambiar el veredicto."""
        argumentos = {"capital": D(10000)}
        con_negativo = peor_de_lo_simulado(
            serie([100.0, 100.0, 70.0]), drawdown_simulado=D(-1000), **argumentos
        )
        con_positivo = peor_de_lo_simulado(
            serie([100.0, 100.0, 70.0]), drawdown_simulado=D(1000), **argumentos
        )
        assert (con_negativo is None) == (con_positivo is None)

    def test_no_dice_que_hacer(self) -> None:
        """Es donde mas tentador seria decir 'vende'. Y donde mas dano haria."""
        alerta = peor_de_lo_simulado(
            serie([100.0, 100.0, 70.0]), drawdown_simulado=D(-1000), capital=D(10000)
        )
        assert alerta is not None
        assert "salir corriendo" in alerta.message, "el mensaje desaconseja reaccionar en caliente"

    def test_sin_simulacion_de_referencia_no_hay_comparacion(self) -> None:
        assert (
            peor_de_lo_simulado(serie([100.0, 70.0]), drawdown_simulado=D(0), capital=D(10000))
            is None
        )


class TestPerdidaDesdeTuEntrada:
    def test_una_perdida_real_avisa(self) -> None:
        posicion = Position(symbol="AAA", quantity=D(10), entry_price=D(100))
        alerta = perdida_desde_tu_entrada(serie([100.0, 80.0]), posicion)

        assert alerta is not None
        assert alerta.code == PERDIDA_DESDE_TU_ENTRADA
        assert alerta.measured == D("-0.2")

    def test_si_entraste_despues_de_la_caida_no_pierdes(self) -> None:
        """El activo puede estar un 30% bajo su maximo y tu ir ganando.

        Es la distincion que separa un dato util de un susto.
        """
        posicion = Position(symbol="AAA", quantity=D(10), entry_price=D(70))
        assert perdida_desde_tu_entrada(serie([100.0, 120.0, 85.0]), posicion) is None

    def test_ir_ganando_nunca_produce_alerta(self) -> None:
        posicion = Position(symbol="AAA", quantity=D(10), entry_price=D(50))
        assert perdida_desde_tu_entrada(serie([100.0, 200.0]), posicion) is None

    def test_una_posicion_invalida_se_rechaza_al_crearla(self) -> None:
        """Fallar aqui es mejor que producir una alerta con numeros sin sentido."""
        with pytest.raises(ValueError, match="positiva"):
            Position(symbol="AAA", quantity=D(0), entry_price=D(100))
        with pytest.raises(ValueError, match="positivo"):
            Position(symbol="AAA", quantity=D(10), entry_price=D(-1))


class TestDesviacionDelPlan:
    def test_una_deriva_grande_avisa(self) -> None:
        posiciones = [
            Position(symbol="AAA", quantity=D(10), entry_price=D(100)),
            Position(symbol="BBB", quantity=D(10), entry_price=D(100)),
        ]
        precios = {"AAA": D(300), "BBB": D(100)}  # 75% / 25%
        alertas = desviacion_del_plan(posiciones, precios, {"AAA": D("0.5"), "BBB": D("0.5")})

        assert len(alertas) == 2
        assert {a.code for a in alertas} == {DESVIACION_DEL_PLAN}

    def test_una_cartera_en_su_sitio_no_avisa(self) -> None:
        posiciones = [
            Position(symbol="AAA", quantity=D(10), entry_price=D(100)),
            Position(symbol="BBB", quantity=D(10), entry_price=D(100)),
        ]
        precios = {"AAA": D(100), "BBB": D(100)}
        assert desviacion_del_plan(posiciones, precios, {"AAA": D("0.5"), "BBB": D("0.5")}) == []

    def test_recuerda_que_corregir_cuesta_dinero(self) -> None:
        """Sin esto, la alerta empuja a reequilibrar -- y reequilibrar son comisiones."""
        posiciones = [
            Position(symbol="AAA", quantity=D(10), entry_price=D(100)),
            Position(symbol="BBB", quantity=D(10), entry_price=D(100)),
        ]
        alertas = desviacion_del_plan(
            posiciones, {"AAA": D(300), "BBB": D(100)}, {"AAA": D("0.5"), "BBB": D("0.5")}
        )
        assert any("comisiones" in a.message for a in alertas)

    def test_un_activo_fuera_del_plan_se_ignora(self) -> None:
        posiciones = [Position(symbol="ZZZ", quantity=D(10), entry_price=D(100))]
        assert desviacion_del_plan(posiciones, {"ZZZ": D(100)}, {"AAA": D("1")}) == []


class TestSoloRiesgoNuncaGanancias:
    """LA regla dura del modulo."""

    def test_una_serie_que_solo_sube_no_produce_ninguna_alerta(self) -> None:
        """EL test de este fichero.

        Si alguna vez una regla salta con una serie estrictamente creciente, alguien habra
        anhadido una alerta de celebracion -- que es el mecanismo medido por la FCA en +11% de
        operaciones, y con mas efecto en quien menos sabe de inversion.
        """
        subiendo = serie([100.0 + i for i in range(200)])
        posicion = Position(symbol="AAA", quantity=D(10), entry_price=D(100))

        alertas = evaluate(
            [subiendo],
            ahora=ultimo_dia(subiendo),
            posiciones=[posicion],
            objetivo={"AAA": D(1)},
            drawdown_simulado=D(-1000),
            capital=D(10000),
        )
        assert alertas == [], f"una serie que solo sube no puede alertar de nada: {alertas}"

    def test_ninguna_regla_menciona_ganar(self) -> None:
        """Comprobacion sobre el codigo: no hay ni el vocabulario para celebrar."""
        from pathlib import Path

        fuente = Path("src/invest_ll/alerts/rules.py").read_text(encoding="utf-8")
        for prohibida in ("enhorabuena", "felicidades", "ganancia record", "objetivo alcanzado"):
            assert prohibida not in fuente.lower()


class TestNingunMensajePideActuar:
    """Informan de un estado; no piden una accion."""

    VERBOS = (
        r"\bcompra\b",
        r"\bvende\b",
        r"\bvender ahora\b",
        r"\bdeberias\b",
        r"\bte recomendamos\b",
        r"\baprovecha\b",
        r"\bno te lo pierdas\b",
        r"\bultima oportunidad\b",
        r"\bactua ahora\b",
    )

    def todas_las_alertas(self) -> list[Alert]:
        """Una de cada tipo, para revisar sus textos reales."""
        cayendo = serie([100.0, 150.0, 60.0])
        posicion = Position(symbol="AAA", quantity=D(10), entry_price=D(140))
        return evaluate(
            [cayendo],
            ahora=ultimo_dia(cayendo) + timedelta(days=60),
            posiciones=[posicion],
            drawdown_simulado=D(-100),
            capital=D(10000),
        )

    def test_hay_alertas_que_revisar(self) -> None:
        """Si la lista viniera vacia, el test de abajo pasaria sin comprobar nada."""
        assert len(self.todas_las_alertas()) >= 3

    @pytest.mark.parametrize("patron", VERBOS)
    def test_ningun_mensaje_pide_actuar(self, patron: str) -> None:
        for alerta in self.todas_las_alertas():
            assert not re.search(patron, alerta.message, re.IGNORECASE), (
                f"la alerta {alerta.code} usa lenguaje de accion: {alerta.message!r}"
            )

    def test_el_detector_funciona(self) -> None:
        """Contra un texto que SI deberia marcar."""
        assert any(re.search(p, "Compra ya antes de que suba", re.IGNORECASE) for p in self.VERBOS)


class TestElOrden:
    def test_los_datos_obsoletos_van_los_primeros(self) -> None:
        """Invalidan todo lo demas: leerlos al final seria leerlos tarde."""
        cayendo = serie([100.0, 150.0, 60.0])
        alertas = evaluate([cayendo], ahora=ultimo_dia(cayendo) + timedelta(days=60))

        assert alertas[0].code == DATOS_OBSOLETOS

    def test_lo_que_pide_revisar_va_antes(self) -> None:
        cayendo = serie([100.0, 150.0, 60.0])
        alertas = evaluate(
            [cayendo],
            ahora=ultimo_dia(cayendo),
            drawdown_simulado=D(-100),
            capital=D(10000),
        )
        niveles = [a.level for a in alertas]
        assert niveles == sorted(niveles, key=lambda n: 0 if n is Nivel.REVISAR else 1)


class TestSinAlertasNoSeDiceQueTodoVaBien:
    def test_el_texto_explica_lo_que_no_se_ha_mirado(self) -> None:
        """Decir "todo correcto" seria tranquilizar sobre cosas que este programa no mide."""
        texto = render([])
        assert texto == NADA_QUE_CONTAR
        assert "no significa que todo vaya bien" in texto
        assert "noticias" in texto

    def test_una_serie_tranquila_no_produce_nada(self) -> None:
        s = serie([100.0, 101.0, 100.0, 99.0])
        assert evaluate([s], ahora=ultimo_dia(s)) == []


class TestTodoLoOpcionalLoEsDeVerdad:
    def test_sin_posiciones_ni_plan_sigue_funcionando(self) -> None:
        cayendo = serie([100.0, 150.0, 60.0])
        alertas = evaluate([cayendo], ahora=ultimo_dia(cayendo))
        assert [a.code for a in alertas] == [CAIDA_DESDE_MAXIMO]

    def test_sin_series_no_hay_alertas(self) -> None:
        assert evaluate([], ahora=AHORA) == []

    def test_una_serie_vacia_no_puede_ni_construirse(self) -> None:
        """No hace falta defenderse de ella: `PriceSeries` la rechaza al crearse.

        Este test empezo siendo "una serie vacia no revienta", con guardas defensivas en cada
        regla. Se cayo al escribirlo: la invariante ya estaba garantizada mas arriba, y esas
        guardas eran codigo imposible de ejecutar que APARENTABA manejar un caso. Se quitaron.
        """
        with pytest.raises(InvalidSeriesError, match="vac"):
            PriceSeries(symbol="AAA", interval=Interval.DAY_1, calendar=Continuous24x7(), bars=())


class TestUmbrales:
    def test_un_umbral_imposible_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="entre 0 y 1"):
            Umbrales(caida_desde_maximo=D(2))
        with pytest.raises(ValueError, match="al menos 1"):
            Umbrales(dias_sin_datos=0)

    def test_bajar_el_umbral_produce_mas_alertas(self) -> None:
        s = serie([100.0, 110.0, 105.0])
        assert caida_desde_maximo(s) is None
        assert caida_desde_maximo(s, umbrales=Umbrales(caida_desde_maximo=D("0.01"))) is not None


class TestElTextoEsImprimibleEnWindows:
    def test_las_alertas_se_pueden_escribir_en_consola(self) -> None:
        cayendo = serie([100.0, 150.0, 60.0])
        alertas = evaluate([cayendo], ahora=ultimo_dia(cayendo) + timedelta(days=60))
        render(alertas).encode("cp1252")

    def test_el_texto_vacio_tambien(self) -> None:
        NADA_QUE_CONTAR.encode("cp1252")
