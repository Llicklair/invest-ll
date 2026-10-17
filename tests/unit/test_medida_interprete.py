"""El intérprete de estrategias a medida: lo que decide, por qué, con qué velas (solo cerradas,
sin mirar el futuro), sus stops con el cierre de cada vela y cuánto compra."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.bots.decisiones import Decision
from invest_ll.estrategias_custom import indicadores, interprete
from invest_ll.estrategias_custom.formato import EstrategiaInvalidaError, Indicador, validar
from invest_ll.estrategias_custom.interprete import decidir, velas_necesarias

from .medida_apoyo import CRUCE, INICIO, con, ejemplo, onda, serie, situacion, vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.vivo.fuente import Vela

D = Decimal
BAJA_Y_SUBE = [10, 9, 8, 7, 6, 5, 9, 12]
"""La media de 3 cruza por encima de la de 5 en la última vela."""
SUBE_Y_BAJA = [5, 6, 7, 8, 9, 10, 6, 3]


def ordenes(d: Decision) -> list[tuple[str, str]]:
    return [(o.coin, o.lado) for o in d.ordenes]


class TestContrato:
    def test_intervalo_monedas_y_velas_necesarias(self) -> None:
        assert interprete.intervalo(CRUCE) == "1d"
        assert interprete.monedas(ejemplo(2)) == ["BTC", "ETH", "SOL"]
        assert velas_necesarias(CRUCE) == 6  # la media de 5, más una para ver el cruce
        # EMA y RSI miran una ventana fija de tres veces su periodo.
        ema = con(
            CRUCE,
            indicadores={
                "corta": {"tipo": "ema", "periodo": 10},
                "larga": {"tipo": "sma", "periodo": 5},
            },
        )
        assert velas_necesarias(ema) == 31
        assert velas_necesarias(ejemplo(2)) == 22  # máximo de 20 de las anteriores, más una

    def test_decidir_valida_la_definicion(self) -> None:
        with pytest.raises(EstrategiaInvalidaError, match="no vale"):
            decidir(con(CRUCE, intervalo="1m"), situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}))


class TestEntrarYSalir:
    def test_compra_al_cruzar_con_su_porque_y_sus_cifras(self) -> None:
        d = decidir(CRUCE, situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}))
        assert ordenes(d) == [("BTC", "compra")]
        assert d.ordenes[0].porque == (
            "la media de 3 velas (8,67) cruzó por encima de la de 5 velas (7,80)"
        )
        assert d.ordenes[0].importe == D(1000)

    def test_vende_al_cruzar_por_debajo(self) -> None:
        s = situacion({"BTC": serie("BTC", SUBE_Y_BAJA)}, posiciones={"BTC": D(1)})
        d = decidir(CRUCE, s)
        assert ordenes(d) == [("BTC", "venta")]
        assert "cruzó por debajo" in d.ordenes[0].porque

    def test_sin_cruce_no_hace_nada(self) -> None:
        d = decidir(CRUCE, situacion({"BTC": serie("BTC", [1, 2, 3, 4, 5, 6, 7, 8])}))
        assert d.ordenes == ()

    def test_con_la_moneda_no_vuelve_a_comprar(self) -> None:
        s = situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}, posiciones={"BTC": D(1)})
        assert decidir(CRUCE, s).ordenes == ()

    def test_sin_historia_espera_y_lo_dice(self) -> None:
        d = decidir(CRUCE, situacion({"BTC": serie("BTC", [1, 2, 3])}))
        assert d.ordenes == ()
        assert d.notas == ("Esperando historia de BTC: necesita 6 velas de 1d cerradas.",)

    def test_o_explica_solo_lo_que_se_cumplio(self) -> None:
        d = con(
            CRUCE,
            indicadores={"larga": {"tipo": "sma", "periodo": 5}},
            entrar={"o": [{">": ["precio", 100]}, {">": ["precio", "larga"]}]},
            salir={"<": ["precio", "larga"]},
        )
        decision = decidir(d, situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}))
        assert decision.ordenes[0].porque == (
            "el precio (12,00) está por encima de la media de 5 velas (7,80)"
        )

    def test_multiplicador(self) -> None:
        d = con(
            CRUCE,
            indicadores={"larga": {"tipo": "sma", "periodo": 5}},
            entrar={">": ["precio", {"valor": "larga", "por": 1.5}]},
            salir={"<": ["precio", "larga"]},
        )
        # 12 > 7,8 por 1,5 = 11,7: compra; con 11 no.
        assert ordenes(decidir(d, situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}))) == [
            ("BTC", "compra")
        ]
        menos = [*BAJA_Y_SUBE[:-1], 11]
        assert decidir(d, situacion({"BTC": serie("BTC", menos)})).ordenes == ()


class TestSoloVelasCerradas:
    def test_la_vela_en_curso_no_cuenta(self) -> None:
        velas = [
            *serie("BTC", BAJA_Y_SUBE[:-1]),
            vela("BTC", INICIO + timedelta(days=7), 12, cerrada=False),
        ]
        d = decidir(CRUCE, situacion({"BTC": velas}, ahora=velas[-1].inicio + timedelta(hours=5)))
        assert d.ordenes == ()

    def test_una_vela_que_termina_despues_de_ahora_tampoco(self) -> None:
        """Aunque la fuente la diera por cerrada (un fallo): termina en el futuro."""
        velas = serie("BTC", BAJA_Y_SUBE)
        d = decidir(CRUCE, situacion({"BTC": velas}, ahora=velas[-2].fin))
        assert d.ordenes == ()

    def _decisiones(
        self, cierres: list[float], definicion: dict[str, Any]
    ) -> list[list[tuple[str, str]]]:
        """Decisión a decisión, como el motor: la fuente le da TODAS las velas (también las
        futuras, marcadas como cerradas) y el intérprete solo puede usar las de antes de `ahora`."""
        todas = serie("BTC", cierres)
        resultado: list[list[tuple[str, str]]] = []
        posiciones: dict[str, Decimal] = {}
        memoria: dict[str, str] = {}
        for i in range(10, 70):
            s = situacion(
                {"BTC": todas}, ahora=todas[i].fin, posiciones=posiciones, memoria=memoria
            )
            d = decidir(definicion, s)
            resultado.append(ordenes(d))
            for o in d.ordenes:
                posiciones = {"BTC": D(1)} if o.lado == "compra" else {}
                memoria.update(o.memoria)
            memoria.update(d.memoria or {})
        return resultado

    CORTAS: tuple[tuple[str, dict[str, Any]], ...] = (
        ("cruce de medias", CRUCE),
        (
            "rsi con filtro, stop y pausa",
            con(
                CRUCE,
                indicadores={
                    "rsi": {"tipo": "rsi", "periodo": 3},
                    "ema": {"tipo": "ema", "periodo": 4},
                },
                entrar={"y": [{"<": ["rsi", 40]}, {">": ["precio", {"valor": "ema", "por": 0.9}]}]},
                salir={">": ["rsi", 60]},
                riesgo={"stop_perdida": 0.05, "pausa_tras_stop": 2},
            ),
        ),
        (
            "ruptura con stop que sigue",
            con(
                CRUCE,
                indicadores={
                    "alto": {"tipo": "maximo", "periodo": 5, "atras": 1},
                    "bajo": {"tipo": "minimo", "periodo": 3, "atras": 1},
                },
                entrar={">": ["precio", "alto"]},
                salir={"<": ["precio", "bajo"]},
                riesgo={"stop_seguimiento": 0.08},
            ),
        ),
        (
            "rebote con toma de beneficio",
            con(
                CRUCE,
                indicadores={"bajo": {"tipo": "minimo", "periodo": 6}},
                entrar={"cruza_arriba": ["precio", {"valor": "bajo", "por": 1.1}]},
                salir=None,
                riesgo={"stop_perdida": 0.1, "toma_beneficio": 0.15},
            ),
        ),
    )

    @pytest.mark.parametrize(("que", "definicion"), CORTAS, ids=[q for q, _ in CORTAS])
    def test_cambiar_las_velas_posteriores_no_cambia_las_decisiones_anteriores(
        self, que: str, definicion: dict[str, Any]
    ) -> None:
        base = onda(80, periodo=12, amplitud=15, tendencia=0.4)
        otra = base[:40] + [200 - p for p in base[40:]]
        antes, despues = self._decisiones(base, definicion), self._decisiones(otra, definicion)
        hasta = 40 - 10  # las decisiones tomadas con velas hasta la 39
        assert antes[:hasta] == despues[:hasta]
        assert any(antes[:hasta]), "la serie no daba ninguna orden: el test pasaría por vacío"
        assert antes != despues, "las velas cambiadas no cambian nada: el test no demuestra nada"

    def test_la_historia_de_mas_no_cambia_nada(self) -> None:
        """Con más velas antiguas delante, la decisión es la misma: cada indicador mira su ventana."""
        definicion = con(
            CRUCE,
            indicadores={
                "corta": {"tipo": "ema", "periodo": 3},
                "larga": {"tipo": "sma", "periodo": 5},
            },
        )
        cierres = onda(60, periodo=9)
        corta = serie("BTC", cierres)[-velas_necesarias(definicion) :]
        larga = serie("BTC", cierres)
        assert decidir(definicion, situacion({"BTC": corta})) == decidir(
            definicion, situacion({"BTC": larga})
        )


def _comprada(
    cierres: Sequence[float],
    definicion: dict[str, Any],
    entrada: float,
    *,
    maximo: float | None = None,
) -> Decision:
    velas = serie("BTC", cierres)
    memoria = {
        "entrada_BTC": str(entrada),
        "desde_BTC": velas[0].fin.isoformat(),
        "maximo_BTC": str(maximo if maximo is not None else entrada),
    }
    return decidir(definicion, situacion({"BTC": velas}, posiciones={"BTC": D(1)}, memoria=memoria))


SOLO_STOPS = con(CRUCE, salir=None)


class TestStops:
    def test_stop_de_perdida_con_el_cierre(self) -> None:
        d = _comprada([100] * 9 + [91], con(SOLO_STOPS, riesgo={"stop_perdida": 0.08}), 100)
        assert ordenes(d) == [("BTC", "venta")]
        assert d.ordenes[0].porque == (
            "stop de pérdida: Bitcoin cerró a 91,00, un -9,0 % desde la compra a 100,00"
        )

    def test_no_salta_si_el_cierre_no_llega(self) -> None:
        assert (
            _comprada([100] * 9 + [93], con(SOLO_STOPS, riesgo={"stop_perdida": 0.08}), 100).ordenes
            == ()
        )

    def test_un_minimo_de_la_vela_por_debajo_no_lo_hace_saltar(self) -> None:
        """Se mira el cierre de cada vela cerrada, no lo que hizo el precio dentro."""
        velas = serie("BTC", [100] * 9)
        velas.append(vela("BTC", velas[-1].fin, 95, minimo=80))
        memoria = {"entrada_BTC": "100", "desde_BTC": velas[0].fin.isoformat(), "maximo_BTC": "100"}
        s = situacion({"BTC": velas}, posiciones={"BTC": D(1)}, memoria=memoria)
        assert decidir(con(SOLO_STOPS, riesgo={"stop_perdida": 0.08}), s).ordenes == ()

    def test_toma_de_beneficio(self) -> None:
        d = _comprada([100] * 9 + [121], con(SOLO_STOPS, riesgo={"toma_beneficio": 0.2}), 100)
        assert d.ordenes[0].porque.startswith(
            "toma de beneficio: Bitcoin cerró a 121,00, un +21,0 %"
        )

    def test_stop_que_sigue_al_precio_con_lo_mas_alto_visto(self) -> None:
        """Lo apuntado era 100, pero las velas después de la compra llegaron a 130 (el panel
        estaba cerrado): cuenta 130, y 115 es un -11,5 % desde ahí."""
        cierres = [100, 110, 130, 125, 120, 118, 117, 116, 115]
        d = _comprada(cierres, con(SOLO_STOPS, riesgo={"stop_seguimiento": 0.1}), 100)
        assert ordenes(d) == [("BTC", "venta")]
        assert "un -11,5 % desde su cierre más alto tras la compra (130,00)" in d.ordenes[0].porque

    def test_apunta_lo_mas_alto_mientras_no_vende(self) -> None:
        cierres = [100, 100, 100, 100, 105, 112, 111]
        d = _comprada(cierres, con(SOLO_STOPS, riesgo={"stop_seguimiento": 0.1}), 100)
        assert d.ordenes == ()
        assert d.memoria == {"maximo_BTC": "112"}

    def test_al_vender_por_stop_lo_apunta(self) -> None:
        definicion = con(CRUCE, riesgo={"stop_perdida": 0.05, "pausa_tras_stop": 3})
        d = _comprada([100] * 9 + [90], definicion, 100)
        memoria = dict(d.ordenes[0].memoria)
        assert memoria["entrada_BTC"] == ""
        assert memoria["stop_BTC"] == serie("BTC", [100] * 10)[-1].fin.isoformat()

    def test_tras_un_stop_espera_sus_velas(self) -> None:
        definicion = con(CRUCE, riesgo={"stop_perdida": 0.05, "pausa_tras_stop": 3})
        velas = serie("BTC", BAJA_Y_SUBE)  # cruza por encima en la última
        hace_dos = {"stop_BTC": (velas[-1].fin - timedelta(days=2)).isoformat()}
        hace_tres = {"stop_BTC": (velas[-1].fin - timedelta(days=3)).isoformat()}
        assert decidir(definicion, situacion({"BTC": velas}, memoria=hace_dos)).ordenes == ()
        despues = decidir(definicion, situacion({"BTC": velas}, memoria=hace_tres))
        assert ordenes(despues) == [("BTC", "compra")]

    def test_la_compra_apunta_su_referencia(self) -> None:
        velas = serie("BTC", BAJA_Y_SUBE)
        d = decidir(con(CRUCE, riesgo={"stop_perdida": 0.1}), situacion({"BTC": velas}))
        memoria = dict(d.ordenes[0].memoria)
        assert memoria["entrada_BTC"] == "12"
        assert memoria["desde_BTC"] == velas[-1].fin.isoformat()

    def test_salir_por_la_regla_no_pone_pausa(self) -> None:
        s = situacion({"BTC": serie("BTC", SUBE_Y_BAJA)}, posiciones={"BTC": D(1)})
        d = decidir(con(CRUCE, riesgo={"pausa_tras_stop": 5}), s)
        assert dict(d.ordenes[0].memoria)["stop_BTC"] == ""


class TestTamano:
    def test_fraccion_del_valor(self) -> None:
        d = decidir(
            con(CRUCE, tamano={"fraccion": 0.5}), situacion({"BTC": serie("BTC", BAJA_Y_SUBE)})
        )
        assert d.ordenes[0].importe == D(500)

    def test_partes_iguales_entre_monedas_contando_lo_que_vale_lo_comprado(self) -> None:
        definicion = con(CRUCE, monedas=["BTC", "ETH"])
        velas = {"BTC": serie("BTC", BAJA_Y_SUBE), "ETH": serie("ETH", [1, 2, 3, 4, 5, 6, 7, 8])}
        # 600 de efectivo y 1 ETH que vale 8 → valor 608: la parte de BTC es 304.
        s = situacion(velas, efectivo="600", posiciones={"ETH": D(1)}, monedas=("BTC", "ETH"))
        d = decidir(definicion, s)
        assert ordenes(d) == [("BTC", "compra")]
        assert d.ordenes[0].importe == D(304)

    def test_maximo_por_moneda(self) -> None:
        definicion = con(CRUCE, tamano={"maximo_por_moneda": 0.3})
        d = decidir(definicion, situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}))
        assert d.ordenes[0].importe == D(300)

    def test_por_volatilidad_mas_a_la_que_menos_se_mueve(self) -> None:
        definicion = con(
            CRUCE,
            monedas=["BTC", "ETH"],
            tamano={"reparto": "volatilidad", "periodo_volatilidad": 5},
        )
        tranquila = [100, 99, 98, 97, 96, 95, 99, 102]
        movida = [100, 90, 80, 70, 60, 50, 90, 120]
        velas = {"BTC": serie("BTC", tranquila), "ETH": serie("ETH", movida)}
        d = decidir(definicion, situacion(velas, monedas=("BTC", "ETH")))
        importes = {o.coin: o.importe for o in d.ordenes}
        assert importes["BTC"] is not None and importes["ETH"] is not None
        assert importes["BTC"] > importes["ETH"]
        assert importes["BTC"] + importes["ETH"] <= D(1000)

    def test_por_debajo_del_minimo_no_compra_y_lo_dice(self) -> None:
        d = decidir(CRUCE, situacion({"BTC": serie("BTC", BAJA_Y_SUBE)}, efectivo="8"))
        assert d.ordenes == ()
        assert d.notas == (
            "No compra BTC: le tocarían 8,00 USDC y el mínimo por orden es 10 USDC.",
        )

    def test_lo_que_cobra_una_venta_paga_una_compra(self) -> None:
        definicion = con(CRUCE, monedas=["BTC", "ETH"])
        velas = {"BTC": serie("BTC", BAJA_Y_SUBE), "ETH": serie("ETH", SUBE_Y_BAJA)}
        s = situacion(velas, efectivo="0", posiciones={"ETH": D(100)}, monedas=("BTC", "ETH"))
        d = decidir(definicion, s)
        assert ordenes(d) == [("ETH", "venta"), ("BTC", "compra")]
        assert d.ordenes[1].importe == D(150)  # la mitad de 300 (100 ETH a 3)


class TestIndicadores:
    def _uno(self, tipo: str, periodo: int, cierres: list[float], **mas: Any) -> float | None:
        ind = Indicador.model_validate({"tipo": tipo, "periodo": periodo, **mas})
        return indicadores.calcular(ind, serie("BTC", cierres))

    def test_media_maximo_minimo_y_cambio(self) -> None:
        assert self._uno("sma", 3, [1, 2, 3, 4]) == 3
        assert self._uno("maximo", 3, [5, 1, 2, 3], fuente="cierre") == 3
        assert self._uno("maximo", 3, [5, 1, 2, 3], fuente="cierre", atras=1) == 5
        assert self._uno("minimo", 2, [5, 1, 2, 3], fuente="cierre") == 2
        cambio = self._uno("retorno", 2, [1, 2, 4, 5])
        assert cambio == pytest.approx(5 / 2 - 1)

    def test_rsi(self) -> None:
        assert self._uno("rsi", 3, [float(i) for i in range(1, 20)]) == 100
        assert self._uno("rsi", 3, [10.0] * 19) == 50
        rsi = self._uno("rsi", 3, onda(19, periodo=6))
        assert rsi is not None and 0 < rsi < 100

    def test_ema_arranca_de_la_media_de_su_ventana(self) -> None:
        assert self._uno("ema", 2, [3.0] * 6) == pytest.approx(3)
        larga = [100.0] * 50 + [1, 2, 3, 4, 5, 6]
        assert self._uno("ema", 2, larga) == self._uno("ema", 2, larga[-6:])

    def test_atr_cuenta_el_hueco_con_el_cierre_anterior(self) -> None:
        velas: list[Vela] = [
            vela("BTC", INICIO, 100, maximo=101, minimo=99),
            vela("BTC", INICIO + timedelta(days=1), 110, maximo=111, minimo=108),
        ]
        ind = Indicador.model_validate({"tipo": "atr", "periodo": 1})
        assert indicadores.calcular(ind, velas) == pytest.approx(11)

    def test_sin_bastantes_velas_no_hay_valor(self) -> None:
        assert self._uno("sma", 5, [1, 2, 3]) is None
        assert self._uno("rsi", 3, [1, 2, 3]) is None

    def test_un_precio_cero_no_rompe_nada(self) -> None:
        assert self._uno("retorno", 2, [0, 1, 2]) is None
        assert self._uno("volatilidad", 2, [0, 1, 2]) is None

    def test_volumen_medio(self) -> None:
        velas = [
            vela("BTC", INICIO + timedelta(days=i), 10, volumen=v) for i, v in enumerate((1, 2, 3))
        ]
        ind = Indicador.model_validate({"tipo": "volumen_medio", "periodo": 3})
        assert indicadores.calcular(ind, velas) == 2


def test_la_situacion_es_la_de_los_bots() -> None:
    """Misma `Situacion` y misma `Decision` que las plantillas de v3."""
    s = situacion({"BTC": serie("BTC", BAJA_Y_SUBE)})
    d = decidir(CRUCE, replace(s, parametros={"lo": "que sea"}))
    assert isinstance(d, Decision)
    validar(CRUCE)
