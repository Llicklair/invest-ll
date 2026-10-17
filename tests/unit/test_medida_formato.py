"""El formato de las estrategias a medida: lo que vale, lo que no (en llano), sus límites, su JSON
Schema y sus reglas en llano. Y que NO es código: ningún intento de colar código pasa."""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema
import pytest

from invest_ll.estrategias_custom import formato
from invest_ll.estrategias_custom.formato import (
    EJEMPLOS,
    EstrategiaInvalidaError,
    a_json,
    huella,
    misma,
    reglas_en_llano,
    validar,
)

from .medida_apoyo import CRUCE, con


def errores(definicion: object) -> list[str]:
    with pytest.raises(EstrategiaInvalidaError) as info:
        validar(definicion)
    return info.value.errores


def texto_de_error(definicion: object) -> str:
    return " | ".join(errores(definicion))


class TestLoQueVale:
    @pytest.mark.parametrize("i", range(len(EJEMPLOS)))
    def test_los_ejemplos_valen_y_vuelven_igual(self, i: int) -> None:
        e = validar(EJEMPLOS[i])
        assert misma(validar(a_json(e)), e)
        assert a_json(e) == EJEMPLOS[i]

    def test_lo_que_falta_toma_su_valor_por_defecto(self) -> None:
        e = validar(CRUCE)
        assert e.formato == 1
        assert e.tamano.fraccion == 1.0
        assert e.tamano.reparto == "igual"
        assert e.riesgo.stop_perdida is None
        assert e.indicadores["corta"].de == "cierre"

    def test_las_monedas_en_minusculas_se_escriben_en_mayusculas(self) -> None:
        assert validar(con(CRUCE, monedas=["btc", "kPEPE"])).monedas == ("BTC", "kPEPE")

    def test_la_huella_es_de_lo_que_hace_no_de_como_se_llama(self) -> None:
        a = validar(CRUCE)
        renombrada = validar(con(CRUCE, nombre="Otro nombre", explicacion="Otra explicación."))
        otra = validar(con(CRUCE, intervalo="4h"))
        assert huella(a) == huella(renombrada)
        assert huella(a) != huella(otra)
        assert not misma(a, renombrada)

    def test_la_huella_no_depende_de_lo_que_se_omite(self) -> None:
        explicita = con(CRUCE, tamano={"fraccion": 1, "reparto": "igual"}, riesgo={})
        assert huella(validar(explicita)) == huella(validar(CRUCE))

    def test_un_numero_puede_ser_entero_o_decimal(self) -> None:
        d = con(
            CRUCE,
            indicadores={"rsi": {"tipo": "rsi", "periodo": 14}},
            entrar={"<": ["rsi", 30]},
            salir={">": ["rsi", 70.5]},
        )
        assert validar(d).salir is not None

    def test_multiplicador_sobre_un_indicador_o_el_precio(self) -> None:
        d = con(CRUCE, entrar={"cruza_arriba": ["precio", {"valor": "larga", "por": 1.05}]})
        validar(d)


class TestNoEsCodigo:
    """Una estrategia es un formato cerrado: nada que se parezca a código pasa la validación."""

    INTENTOS: tuple[tuple[str, dict[str, Any]], ...] = (
        ("python en un operando", con(CRUCE, entrar={">": ["__import__('os').system('x')", 1]})),
        ("expresión en un operando", con(CRUCE, entrar={">": ["corta * 2 + larga", 1]})),
        ("lambda", con(CRUCE, entrar={">": ["lambda: 1", 1]})),
        ("plantilla jinja", con(CRUCE, entrar={">": ["{{ 7*7 }}", 1]})),
        ("plantilla js", con(CRUCE, entrar={">": ["${process.exit()}", 1]})),
        ("eval como condición", con(CRUCE, entrar={"eval": "corta > larga"})),
        ("exec como condición", con(CRUCE, entrar={"exec": ["import os"]})),
        ("condición en texto", con(CRUCE, entrar="corta > larga")),
        ("campo de código", con(CRUCE, codigo="print('hola')")),
        ("campo python", con(CRUCE, python="import os")),
        (
            "tipo de indicador inventado",
            con(
                CRUCE,
                indicadores={
                    "corta": {"tipo": "eval", "periodo": 3},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        (
            "fórmula en un indicador",
            con(
                CRUCE,
                indicadores={
                    "corta": {"tipo": "sma", "periodo": 3, "formula": "close*2"},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        (
            "periodo en texto",
            con(
                CRUCE,
                indicadores={
                    "corta": {"tipo": "sma", "periodo": "__import__('os')"},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        (
            "nombre de indicador con puntos",
            con(
                CRUCE,
                indicadores={
                    "os.system": {"tipo": "sma", "periodo": 3},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        (
            "dunder",
            con(
                CRUCE,
                indicadores={
                    "__class__": {"tipo": "sma", "periodo": 3},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        (
            "referencia con código",
            con(CRUCE, entrar={">": [{"valor": "open('x').read()", "por": 1}, 1]}),
        ),
        (
            "referencia con clave de más",
            con(CRUCE, entrar={">": [{"valor": "corta", "por": 1, "codigo": "x"}, 1]}),
        ),
        (
            "fuente inventada",
            con(
                CRUCE,
                indicadores={
                    "corta": {"tipo": "sma", "periodo": 3, "fuente": "os.environ"},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
        ),
        ("intervalo inventado", con(CRUCE, intervalo="1d; rm -rf /")),
        ("reparto inventado", con(CRUCE, tamano={"reparto": "eval"})),
    )

    @pytest.mark.parametrize(("que", "definicion"), INTENTOS, ids=[q for q, _ in INTENTOS])
    def test_se_rechaza(self, que: str, definicion: dict[str, Any]) -> None:
        assert errores(definicion), que

    def test_el_operando_con_codigo_se_explica(self) -> None:
        texto = texto_de_error(con(CRUCE, entrar={">": ["__import__('os')", 1]}))
        assert "no admiten expresiones ni código" in texto

    def test_ni_un_json_enorme_ni_uno_muy_anidado(self) -> None:
        anidado: dict[str, Any] = {">": ["corta", 1]}
        for _ in range(200):
            anidado = {"no": anidado}
        assert "demasiado" in texto_de_error(con(CRUCE, entrar=anidado))
        enorme = con(CRUCE, entrar={"y": [{">": ["corta", i]} for i in range(5000)]})
        assert "demasiado" in texto_de_error(enorme)

    def test_tampoco_un_texto_gigante(self) -> None:
        assert errores(con(CRUCE, explicacion="x" * 10_000))

    def test_no_es_un_objeto(self) -> None:
        assert "objeto JSON" in texto_de_error("{'nombre': 'x'}")
        assert errores([CRUCE])


class TestErroresEnLlano:
    def test_lo_que_falta(self) -> None:
        texto = texto_de_error({"nombre": "x"})
        assert "falta «monedas»" in texto
        assert "falta «entrar»" in texto

    def test_ni_una_palabra_en_ingles(self) -> None:
        malos = [
            {"nombre": "x"},
            con(CRUCE, intervalo="1m"),
            con(CRUCE, tamano={"fraccion": 2}),
            con(
                CRUCE,
                indicadores={
                    "corta": {"tipo": "sma", "periodo": 0},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            ),
            con(CRUCE, entrar={">": ["corta"]}),
            con(CRUCE, entrar={"y": []}),
            con(CRUCE, monedas=[]),
            con(CRUCE, extra=1),
        ]
        for d in malos:
            texto = texto_de_error(d)
            for ingles in ("Field required", "Input should", " or ", "Extra inputs", "Value error"):
                assert ingles not in texto, (ingles, texto)

    def test_cifras_como_se_leen(self) -> None:
        assert "no puede pasar de 1" in texto_de_error(con(CRUCE, tamano={"fraccion": 2}))
        assert "1.0" not in texto_de_error(con(CRUCE, tamano={"fraccion": 2}))

    def test_dice_donde_esta_el_problema(self) -> None:
        d = con(CRUCE, entrar={"y": [{">": ["corta", 1]}, {"cruza_arriba": ["corta"]}]})
        assert "«entrar → y → 2.ª»" in texto_de_error(d)

    def test_un_indicador_que_no_existe(self) -> None:
        texto = texto_de_error(con(CRUCE, entrar={"cruza_arriba": ["corta", "sma200"]}))
        assert "usa «sma200», que no está en «indicadores»" in texto

    def test_un_indicador_que_nadie_usa(self) -> None:
        indicadores = {**CRUCE["indicadores"], "rsi": {"tipo": "rsi", "periodo": 14}}
        assert "ninguna regla lo usa" in texto_de_error(con(CRUCE, indicadores=indicadores))

    def test_sin_forma_de_vender(self) -> None:
        texto = texto_de_error(
            con(
                CRUCE,
                salir=None,
                indicadores={
                    "corta": {"tipo": "sma", "periodo": 3},
                    "larga": {"tipo": "sma", "periodo": 5},
                },
            )
        )
        assert "no tiene forma de vender" in texto

    def test_comparar_dos_numeros_no_depende_del_mercado(self) -> None:
        assert "compara dos números" in texto_de_error(con(CRUCE, salir={">": [70, 50]}))

    def test_un_si_no_no_se_compara(self) -> None:
        assert "true/false" in texto_de_error(con(CRUCE, salir={">": ["corta", True]}))

    def test_numeros_raros(self) -> None:
        assert errores(con(CRUCE, salir={">": ["corta", float("nan")]}))
        assert errores(con(CRUCE, salir={">": ["corta", float("inf")]}))
        assert errores(con(CRUCE, salir={">": ["corta", 1e300]}))

    def test_monedas_repetidas(self) -> None:
        assert "repetidas" in texto_de_error(con(CRUCE, monedas=["BTC", "btc"]))

    def test_condicion_con_dos_claves(self) -> None:
        texto = texto_de_error(con(CRUCE, entrar={">": ["corta", 1], "<": ["corta", 2]}))
        assert "UNA sola clave" in texto

    def test_atr_y_volumen_no_llevan_fuente(self) -> None:
        ind = {"atr": {"tipo": "atr", "periodo": 14, "fuente": "cierre"}}
        assert "«atr» no lleva «fuente»" in texto_de_error(
            con(CRUCE, indicadores=ind, entrar={">": ["atr", 1]}, salir={"<": ["atr", 1]})
        )


class TestLimites:
    def test_periodo(self) -> None:
        ind = {"corta": {"tipo": "sma", "periodo": 3}, "larga": {"tipo": "sma", "periodo": 401}}
        assert "no puede pasar de 400" in texto_de_error(con(CRUCE, indicadores=ind))

    def test_rsi_y_ema_necesitan_dos_velas(self) -> None:
        ind = {"corta": {"tipo": "ema", "periodo": 1}, "larga": {"tipo": "sma", "periodo": 5}}
        assert "2 velas o más" in texto_de_error(con(CRUCE, indicadores=ind))

    def test_comparaciones_por_lado(self) -> None:
        muchas = [{">": ["corta", i]} for i in range(8)]
        entrar = {"y": [{"y": muchas}, {"y": muchas[:5]}]}
        assert "comparaciones y el máximo es 12" in texto_de_error(con(CRUCE, entrar=entrar))

    def test_ramas_por_grupo(self) -> None:
        entrar = {"o": [{">": ["corta", i]} for i in range(9)]}
        assert "como mucho 8" in texto_de_error(con(CRUCE, entrar=entrar))

    def test_profundidad(self) -> None:
        entrar: dict[str, Any] = {">": ["corta", 1]}
        for _ in range(5):
            entrar = {"no": entrar}
        assert "más de 4 niveles" in texto_de_error(con(CRUCE, entrar=entrar))

    def test_monedas(self) -> None:
        assert errores(con(CRUCE, monedas=["A", "B", "C", "D", "E", "F"]))

    def test_indicadores(self) -> None:
        ind = {f"m{i}": {"tipo": "sma", "periodo": i + 2} for i in range(13)}
        assert errores(con(CRUCE, indicadores=ind))

    def test_stops_en_fraccion(self) -> None:
        assert errores(con(CRUCE, riesgo={"stop_perdida": 8}))
        assert errores(con(CRUCE, riesgo={"stop_perdida": 0}))


class TestEsquema:
    def test_es_json_schema_y_los_ejemplos_lo_cumplen(self) -> None:
        esquema = formato.esquema()
        json.dumps(esquema)
        validador: Any = jsonschema.Draft202012Validator(esquema)
        for ejemplo in EJEMPLOS:
            validador.validate(ejemplo)

    def test_el_esquema_tambien_rechaza_lo_que_no_es_formato(self) -> None:
        validador: Any = jsonschema.Draft202012Validator(formato.esquema())
        assert not validador.is_valid(con(CRUCE, codigo="x"))
        assert not validador.is_valid(con(CRUCE, entrar={"eval": "1"}))

    def test_la_explicacion_nombra_todas_las_piezas(self) -> None:
        for pieza in (*formato.TIPOS, *formato.CLAVES, "precio", "stop_perdida", "pausa_tras_stop"):
            assert pieza in formato.EXPLICACION, pieza


class TestReglasEnLlano:
    def test_cruce_de_medias(self) -> None:
        reglas = reglas_en_llano(validar(EJEMPLOS[0]))
        assert reglas[1] == "Compra cuando la media de 20 velas cruza por encima de la de 50 velas."
        assert reglas[2] == "Vende cuando la media de 20 velas cruza por debajo de la de 50 velas."
        assert "stop de pérdida" in reglas[3]
        assert "10 %" in reglas[3]

    def test_grupos_y_numeros(self) -> None:
        reglas = reglas_en_llano(validar(EJEMPLOS[1]))
        assert reglas[1] == (
            "Compra cuando el RSI de 14 velas está por debajo de 35 y el precio está por encima "
            "de la media de 200 velas."
        )

    def test_atras_y_contracciones(self) -> None:
        reglas = reglas_en_llano(validar(EJEMPLOS[2]))
        assert reglas[1] == (
            "Compra cuando el precio está por encima del máximo de las 20 velas anteriores."
        )

    def test_multiplicador(self) -> None:
        reglas = reglas_en_llano(validar(EJEMPLOS[3]))
        assert reglas[1] == (
            "Compra cuando el precio cruza por encima del mínimo de 30 velas más un 5 %."
        )

    def test_cambio_en_porcentaje(self) -> None:
        d = con(
            CRUCE,
            indicadores={"ret": {"tipo": "retorno", "periodo": 30}},
            entrar={">": ["ret", 0.05]},
            salir={"no": {">": ["ret", 0]}},
        )
        reglas = reglas_en_llano(validar(d))
        assert reglas[1] == "Compra cuando el cambio en 30 velas está por encima de 5 %."
        assert (
            reglas[2]
            == "Vende cuando no se cumple que el cambio en 30 velas está por encima de 0 %."
        )

    def test_grupo_dentro_de_grupo_va_entre_parentesis(self) -> None:
        d = con(
            CRUCE,
            entrar={"y": [{">": ["corta", 1]}, {"o": [{"<": ["larga", 2]}, {">": ["precio", 3]}]}]},
        )
        assert (
            "(la media de 5 velas está por debajo de 2 o el precio"
            in reglas_en_llano(validar(d))[1]
        )

    def test_tamano_con_varias_monedas(self) -> None:
        reglas = reglas_en_llano(validar(EJEMPLOS[2]))
        assert "más en las que menos se mueven" in reglas[-1]
        assert "como mucho el 50 % en una moneda" in reglas[-1]

    def test_sin_palabras_raras(self) -> None:
        for ejemplo in EJEMPLOS:
            for regla in reglas_en_llano(validar(ejemplo)):
                assert not re.search(r"\bde el\b|\ba el\b|None|\{|_", regla), regla
