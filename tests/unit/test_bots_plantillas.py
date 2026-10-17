"""Las plantillas de bot: lo que dicen de sí mismas y la validación de lo que llega al desplegar."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from invest_ll.bots.plantillas import PLANTILLAS, BotInvalidoError, plantilla, validar

D = Decimal
PRECIOS = {"BTC": D("67010"), "ETH": D("2401.5"), "SOL": D("150")}


def precio(coin: str) -> Decimal | None:
    return PRECIOS.get(coin)


def valida(
    clave: str = "tendencia",
    *,
    monedas: list[str] | None = None,
    capital: str = "1000",
    parametros: dict[str, str] | None = None,
) -> dict[str, str]:
    return validar(
        clave, "Mi bot", monedas or ["BTC"], D(capital), parametros or {}, precio
    ).parametros


class TestLasCuatro:
    def test_estan_las_de_la_especificacion(self) -> None:
        assert list(PLANTILLAS) == ["btc-freno", "tendencia", "rejilla", "periodica"]

    def test_solo_bitcoin_con_freno_tiene_evidencia_medida(self) -> None:
        tipos = {p.clave: p.evidencia.tipo for p in PLANTILLAS.values()}
        assert tipos["btc-freno"] == "prueba_real"
        assert "15 oct 2026" in PLANTILLAS["btc-freno"].evidencia.texto
        assert tipos["tendencia"] == tipos["rejilla"] == "ninguna"
        assert PLANTILLAS["tendencia"].evidencia.texto.startswith("Ninguna")
        assert PLANTILLAS["rejilla"].evidencia.texto.startswith("Ninguna")

    def test_las_que_no_tienen_evidencia_lo_avisan_tambien(self) -> None:
        for clave in ("tendencia", "rejilla"):
            assert any("Ninguna prueba" in a for a in PLANTILLAS[clave].avisos)

    def test_cada_una_dice_su_riesgo_operaciones_y_parametros(self) -> None:
        for p in PLANTILLAS.values():
            assert 1 <= p.riesgo <= 5
            assert p.riesgo_texto
            assert p.operaciones_esperadas
            assert p.como_funciona
            assert p.monedas_sugeridas
            for q in p.parametros:
                assert q.explicacion, f"{p.clave}.{q.clave} sin explicación"

    def test_valores_por_defecto(self) -> None:
        defectos = {
            p.clave: {q.clave: q.defecto for q in p.parametros} for p in PLANTILLAS.values()
        }
        assert defectos == {
            "btc-freno": {"dias": "30"},
            "tendencia": {"media_corta": "20", "media_larga": "50", "intervalo": "1h"},
            "rejilla": {"precio_bajo": "", "precio_alto": "", "escalones": "10"},
            "periodica": {"importe": "100", "cada_horas": "24"},
        }

    def test_con_que_velas_decide(self) -> None:
        assert PLANTILLAS["btc-freno"].intervalo({"dias": "30"}) == "1d"
        assert PLANTILLAS["tendencia"].intervalo({"intervalo": "4h"}) == "4h"
        assert PLANTILLAS["rejilla"].intervalo({}) is None
        assert PLANTILLAS["periodica"].intervalo({}) is None

    def test_bitcoin_con_freno_con_otra_moneda_no_tiene_evidencia(self) -> None:
        p = PLANTILLAS["btc-freno"]
        assert p.evidencia_para(["BTC"]).tipo == "prueba_real"
        otra = p.evidencia_para(["ETH"])
        assert otra.tipo == "ninguna"
        assert "Ethereum" in otra.texto


class TestValidar:
    def test_lo_que_falta_toma_su_valor_por_defecto(self) -> None:
        assert valida() == {"media_corta": "20", "media_larga": "50", "intervalo": "1h"}

    def test_normaliza_los_numeros(self) -> None:
        assert (
            valida(parametros={"media_corta": " 10 ", "media_larga": "60.0"})["media_larga"] == "60"
        )
        assert valida("periodica", parametros={"importe": "25,5"})["importe"] == "25.5"

    def test_la_rejilla_sin_rango_va_del_10_por_ciento_abajo_al_10_arriba(self) -> None:
        p = valida("rejilla")
        assert (p["precio_bajo"], p["precio_alto"], p["escalones"]) == ("60309", "73711", "10")

    def test_minusculas_se_entienden(self) -> None:
        v = validar("tendencia", "x", ["btc", "eth"], D(1000), {}, precio)
        assert v.monedas == ("BTC", "ETH")

    @pytest.mark.parametrize(
        ("clave", "monedas", "capital", "parametros", "mensaje"),
        [
            ("nada", ["BTC"], "1000", {}, "No hay ninguna plantilla «nada»"),
            ("tendencia", ["BTC"], "1000", {"otra": "1"}, "no tiene el parámetro otra"),
            (
                "tendencia",
                ["BTC"],
                "1000",
                {"media_corta": "diez"},
                "«Media corta» tiene que ser un número",
            ),
            ("tendencia", ["BTC"], "1000", {"media_corta": "2.5"}, "número entero"),
            ("tendencia", ["BTC"], "1000", {"media_corta": "1"}, "entre 2 y 200"),
            (
                "tendencia",
                ["BTC"],
                "1000",
                {"intervalo": "1m"},
                "una de estas: 15m, 30m, 1h, 2h, 4h",
            ),
            (
                "tendencia",
                ["BTC"],
                "1000",
                {"media_corta": "50"},
                "La media larga (50) tiene que ser mayor",
            ),
            ("tendencia", ["BTC", "BTC"], "1000", {}, "BTC está repetida"),
            ("tendencia", ["DOGE"], "1000", {}, "Hyperliquid no da precio de DOGE"),
            ("tendencia", ["BTC/USDT"], "1000", {}, "no parece el nombre de una moneda"),
            ("tendencia", ["BTC", "ETH"], "15", {}, "no llegaría al mínimo de 10 USDC"),
            ("rejilla", ["BTC", "ETH"], "1000", {}, "funciona con una sola moneda"),
            ("rejilla", ["BTC"], "50", {}, "Cada escalón tendría 5,00 USDC"),
            (
                "rejilla",
                ["BTC"],
                "1000",
                {"precio_bajo": "70000", "precio_alto": "60000"},
                "tiene que ser mayor que «Precio bajo»",
            ),
            ("periodica", ["BTC"], "50", {"importe": "100"}, "no puede pasar del capital"),
            (
                "periodica",
                ["BTC", "ETH"],
                "1000",
                {"importe": "15"},
                "cada compra sería de 7,50 USDC",
            ),
            ("btc-freno", ["BTC"], "1000", {"dias": "400"}, "entre 2 y 365"),
            ("btc-freno", ["BTC"], "20000000", {}, "Como mucho 10.000.000 USDC"),
        ],
    )
    def test_los_errores_se_explican_en_llano(
        self,
        clave: str,
        monedas: list[str],
        capital: str,
        parametros: dict[str, str],
        mensaje: str,
    ) -> None:
        with pytest.raises(BotInvalidoError, match=re.escape(mensaje)):
            validar(clave, "Mi bot", monedas, D(capital), parametros, precio)

    def test_sin_nombre_no(self) -> None:
        with pytest.raises(BotInvalidoError, match="Ponle un nombre"):
            validar("tendencia", "   ", ["BTC"], D(1000), {}, precio)

    def test_la_rejilla_sin_precio_pide_el_rango_a_mano(self) -> None:
        with pytest.raises(BotInvalidoError, match="Hyperliquid no da precio de BTC"):
            validar("rejilla", "x", ["BTC"], D(1000), {}, lambda _: None)

    def test_plantilla_por_clave(self) -> None:
        assert plantilla("rejilla").nombre == "Rejilla"
