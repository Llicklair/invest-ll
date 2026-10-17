"""La prueba sobre el pasado: con velas sintéticas y un conector falso (sin red), con costes, frente
a mantener, y contando las versiones probadas para avisar del sobreajuste."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.estrategias_custom.biblioteca import Biblioteca
from invest_ll.estrategias_custom.formato import validar
from invest_ll.estrategias_custom.prueba import (
    PruebaError,
    aviso_sobreajuste,
    descargar,
    probar,
    resultado_a_json,
    resultado_de_json,
    simular,
)

from .medida_apoyo import CRUCE, INICIO, ConectorFalso, con, onda, serie

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

    from invest_ll.estrategias_custom.prueba import Resultado

D = Decimal
DESDE = INICIO + timedelta(days=20)
HASTA = INICIO + timedelta(days=400)


class TestSimular:
    def test_opera_con_comisiones_y_frente_a_mantener(self) -> None:
        velas = {"BTC": serie("BTC", onda(400, periodo=30, tendencia=0.1))}
        r = simular(
            validar(CRUCE), velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA
        )
        assert r.operaciones > 10
        assert r.comisiones > 0
        assert r.desde == velas["BTC"][20].fin  # la primera vela que cierra después de `desde`
        assert r.hasta == velas["BTC"][-1].fin
        assert 0 < r.tiempo_dentro < 1
        assert r.peor_caida <= 0
        assert len(r.curva) <= 200
        assert r.curva[-1].valor == r.valor_final
        assert r.ganancia_pct == pytest.approx(float(r.valor_final / 1000 - 1))
        # Mantener: comprado al primer cierre con deslizamiento y comisión, valorado al último.
        primero, ultimo = velas["BTC"][20].cierre, velas["BTC"][-1].cierre
        cantidad = D(1000) * (1 - D("0.001")) / (primero * (1 + D("0.0005")))
        assert r.curva_mantener[-1].valor == (cantidad * ultimo).quantize(D("1e-6"))
        assert r.lista_operaciones[0].motivo.startswith("Compré ")
        assert "cruzó por encima" in r.lista_operaciones[0].motivo

    def test_sin_costes_y_sin_cruces_no_cambia_nada(self) -> None:
        velas = {"BTC": serie("BTC", [100.0] * 100)}
        r = simular(
            validar(CRUCE),
            velas,
            exchange="falso",
            capital=D(1000),
            desde=DESDE,
            hasta=HASTA,
            comision=D(0),
            deslizamiento=D(0),
        )
        assert r.operaciones == 0
        assert r.valor_final == D(1000)
        assert r.mantener_pct == 0
        assert any("ninguna operación" in a for a in r.avisos)

    def test_dice_como_ejecuta_lo_que_no_se_puede_saber(self) -> None:
        velas = {"BTC": serie("BTC", onda(200, periodo=30))}
        r = simular(
            validar(CRUCE), velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA
        )
        texto = " ".join(r.avisos)
        assert "no hay libro de órdenes" in texto
        assert "0,05 % de deslizamiento" in texto
        assert "El pasado no es una promesa" in texto

    def test_la_compra_paga_cierre_mas_deslizamiento_y_la_venta_cierre_menos(self) -> None:
        velas = {"BTC": serie("BTC", onda(120, periodo=30))}
        r = simular(
            validar(CRUCE), velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA
        )
        por_fin = {v.fin: v.cierre for v in velas["BTC"]}
        compra = next(o for o in r.lista_operaciones if o.lado == "compra")
        venta = next(o for o in r.lista_operaciones if o.lado == "venta")
        assert compra.precio == pytest.approx(por_fin[compra.at] * D("1.0005"), rel=D("1e-9"))
        assert venta.precio == pytest.approx(por_fin[venta.at] * D("0.9995"), rel=D("1e-9"))
        assert compra.comision == (compra.importe * D("0.001")).quantize(D("1e-6"))

    def test_varias_monedas_con_una_que_empieza_tarde(self) -> None:
        definicion = validar(con(CRUCE, monedas=["BTC", "ETH"]))
        tarde = INICIO + timedelta(days=100)
        velas = {
            "BTC": serie("BTC", onda(300, periodo=25)),
            "ETH": serie("ETH", onda(200, periodo=20, centro=50), desde=tarde),
        }
        r = simular(definicion, velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA)
        assert {o.coin for o in r.lista_operaciones} == {"BTC", "ETH"}
        assert min(o.at for o in r.lista_operaciones if o.coin == "ETH") > tarde
        # Hasta que ETH cotiza, su mitad de "mantener" espera en efectivo.
        antes = [p for p in r.curva_mantener if p.at <= tarde]
        assert antes and antes[0].valor < D(1000)

    def test_sin_velas_en_el_periodo(self) -> None:
        velas = {"BTC": serie("BTC", [1.0] * 10)}
        with pytest.raises(PruebaError, match="No hay velas"):
            simular(
                validar(CRUCE),
                velas,
                exchange="falso",
                capital=D(1000),
                desde=HASTA,
                hasta=HASTA + timedelta(days=5),
            )

    def test_ida_y_vuelta_a_json(self) -> None:
        velas = {"BTC": serie("BTC", onda(200, periodo=30))}
        r = simular(
            validar(CRUCE), velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA
        )
        assert resultado_de_json(resultado_a_json(r)) == r


class TestConElExchange:
    def test_pide_las_velas_por_paginas_con_calentamiento(self) -> None:
        conector = ConectorFalso()
        conector.poner("BTC/USDT", serie("BTC", onda(2500, periodo=40)))
        ahora = INICIO + timedelta(days=2500)
        r = probar(
            validar(CRUCE),
            "falso",
            desde=INICIO + timedelta(days=100),
            hasta=ahora,
            ahora=ahora,
            conector_publico=lambda _e: conector,
        )
        assert len(conector.pedidas) >= 3  # 2.400 velas en páginas de 1.000
        primera = conector.pedidas[0][2]
        assert primera is not None
        assert primera <= INICIO + timedelta(days=100) - timedelta(
            days=6
        )  # 6 velas de calentamiento
        assert r.desde == INICIO + timedelta(days=101)
        assert r.comision == D("0.001")

    def test_la_comision_del_mercado_o_un_01_si_no_se_sabe(self) -> None:
        conector = ConectorFalso(comision=D("0.00075"))
        conector.poner("BTC/USDT", serie("BTC", onda(200, periodo=30)))
        ahora = INICIO + timedelta(days=200)
        r = probar(
            validar(CRUCE), "falso", desde=DESDE, ahora=ahora, conector_publico=lambda _e: conector
        )
        assert r.comision == D("0.00075")
        sin = ConectorFalso(comision=None)
        sin.poner("BTC/USDT", serie("BTC", onda(200, periodo=30)))
        r = probar(
            validar(CRUCE), "falso", desde=DESDE, ahora=ahora, conector_publico=lambda _e: sin
        )
        assert r.comision == D("0.001")
        assert any("se ha supuesto un 0,1 %" in a for a in r.avisos)

    def test_prefiere_usdc_y_si_no_usdt(self) -> None:
        conector = ConectorFalso(pares=(("BTC", "EUR"), ("BTC", "USDT"), ("BTC", "USDC")))
        conector.poner("BTC/USDC", serie("BTC", onda(200, periodo=30)))
        ahora = INICIO + timedelta(days=200)
        probar(
            validar(CRUCE), "falso", desde=DESDE, ahora=ahora, conector_publico=lambda _e: conector
        )
        assert {p[0] for p in conector.pedidas} == {"BTC/USDC"}

    def test_una_moneda_que_el_exchange_no_tiene(self) -> None:
        conector = ConectorFalso(pares=(("ETH", "USDT"),))
        with pytest.raises(PruebaError, match="no tiene par de contado de BTC"):
            probar(validar(CRUCE), "falso", conector_publico=lambda _e: conector)

    def test_sin_velas_en_el_exchange(self) -> None:
        with pytest.raises(PruebaError, match="no da velas"):
            probar(validar(CRUCE), "falso", conector_publico=lambda _e: ConectorFalso())

    def test_avisa_si_el_exchange_tiene_menos_historia(self) -> None:
        conector = ConectorFalso()
        conector.poner(
            "BTC/USDT", serie("BTC", onda(200, periodo=30), desde=INICIO + timedelta(days=50))
        )
        ahora = INICIO + timedelta(days=250)
        r = probar(
            validar(CRUCE), "falso", desde=INICIO, ahora=ahora, conector_publico=lambda _e: conector
        )
        assert any("solo tiene velas de Bitcoin desde" in a for a in r.avisos)

    def test_fechas_imposibles(self) -> None:
        conector = ConectorFalso()
        with pytest.raises(PruebaError, match="anterior"):
            probar(
                validar(CRUCE),
                "falso",
                desde=HASTA,
                hasta=DESDE,
                conector_publico=lambda _e: conector,
            )
        with pytest.raises(PruebaError, match="mayor que cero"):
            probar(validar(CRUCE), "falso", capital=D(0), conector_publico=lambda _e: conector)

    def test_descargar_solo_cerradas_y_sin_repetir(self) -> None:
        conector = ConectorFalso()
        velas = serie("BTC", [1.0] * 10)
        conector.poner("BTC/USDT", [*velas, *velas[-3:]])
        hasta = velas[-1].fin
        assert descargar(conector, "BTC/USDT", "1d", INICIO, hasta) == velas


class TestSobreajuste:
    def test_el_aviso_llega_a_la_tercera_version(self) -> None:
        assert aviso_sobreajuste(2) is None
        aviso = aviso_sobreajuste(3)
        assert aviso is not None
        assert "se parece a hacer trampa" in aviso
        assert "3 versiones" in aviso

    def test_la_biblioteca_cuenta_versiones_distintas(self, tmp_path: Path) -> None:
        b = Biblioteca(tmp_path)
        velas = {"BTC": serie("BTC", onda(200, periodo=30))}

        def prueba(definicion: dict[str, Any]) -> Resultado:
            e = validar(definicion)
            r = simular(e, velas, exchange="falso", capital=D(1000), desde=DESDE, hasta=HASTA)
            return b.registrar_prueba(ficha.id, r)

        ficha = b.guardar(CRUCE, autor="claude")
        r1 = prueba(CRUCE)
        r1b = prueba(CRUCE)  # la misma versión otra vez: no suma
        v2 = con(
            CRUCE,
            indicadores={
                "corta": {"tipo": "sma", "periodo": 4},
                "larga": {"tipo": "sma", "periodo": 5},
            },
        )
        b.guardar(v2, autor="claude", estrategia_id=ficha.id)
        r2 = prueba(v2)
        v3 = con(CRUCE, riesgo={"stop_perdida": 0.1})
        b.guardar(v3, autor="claude", estrategia_id=ficha.id)
        r3 = prueba(v3)
        resultados = [r1, r1b, r2, r3]
        assert [r.versiones_probadas for r in resultados] == [1, 1, 2, 3]
        assert [r.aviso_sobreajuste is None for r in resultados] == [True, True, True, False]
        assert [r.version for r in resultados] == [1, 1, 2, 3]
        assert len(b.pruebas(ficha.id)) == 4
