"""Las claves en el almacén (de memoria en la suite) y la prueba de conexión sin red."""

from __future__ import annotations

from decimal import Decimal

import keyring
import pytest

from invest_ll.live import credenciales
from invest_ll.live.prueba_conexion import explicar_fallo, ordenar_saldo, probar

from ..almacen_en_memoria import AlmacenEnMemoria

CLAVES = credenciales.Claves(clave="ABCDEFGH12345678", secreto="SECRETOSECRETO99")


def test_la_suite_nunca_usa_el_almacen_del_sistema(almacen_de_claves: AlmacenEnMemoria) -> None:
    assert keyring.get_keyring() is almacen_de_claves


def test_guardar_leer_y_borrar(almacen_de_claves: AlmacenEnMemoria) -> None:
    assert credenciales.leer("pruebas") is None
    credenciales.guardar("pruebas", CLAVES)

    assert credenciales.leer("pruebas") == CLAVES
    assert credenciales.leer("real") is None
    assert set(almacen_de_claves.guardado) == {
        ("invest-ll", "binance-pruebas:clave"),
        ("invest-ll", "binance-pruebas:secreto"),
    }
    assert credenciales.borrar("pruebas") is True
    assert credenciales.borrar("pruebas") is False
    assert credenciales.leer("pruebas") is None


def test_las_claves_no_se_dejan_imprimir() -> None:
    texto = f"{CLAVES!r} {CLAVES}"
    assert CLAVES.clave not in texto
    assert CLAVES.secreto not in texto


def test_claves_vacias_no_valen() -> None:
    with pytest.raises(ValueError, match="vacíos"):
        credenciales.Claves(clave="  ", secreto="x")


# -- Explicar los fallos típicos, sin ccxt y sin red -------------------------------------------


def _error(nombre: str, mensaje: str = "") -> Exception:
    """Un error con el nombre de la clase de ccxt: se reconoce por el nombre, no por importarla."""
    return type(nombre, (Exception,), {})(mensaje)


def test_clave_rechazada_explica_red_equivocada_y_tipo_hmac() -> None:
    texto = explicar_fallo(
        _error("AuthenticationError", 'binance {"code":-2015,"msg":"Invalid API-key"}'), "pruebas"
    )
    assert "rechaza las claves" in texto
    assert "cuenta real" in texto, "la causa típica en pruebas: son las claves de la otra red"
    assert "HMAC-SHA256" in texto


def test_en_real_la_red_equivocada_es_la_de_pruebas() -> None:
    texto = explicar_fallo(_error("AuthenticationError"), "real")
    assert "testnet.binance.vision" in texto


def test_formato_de_clave_invalido() -> None:
    texto = explicar_fallo(
        _error("ExchangeError", '{"code":-2014,"msg":"API-key format invalid."}'), "real"
    )
    assert "formato" in texto and "HMAC-SHA256" in texto


def test_sin_conexion() -> None:
    assert "No hay conexión" in explicar_fallo(_error("RequestTimeout"), "pruebas")
    assert "No hay conexión" in explicar_fallo(_error("NetworkError"), "real")


def test_reloj_desajustado() -> None:
    assert "hora de tu ordenador" in explicar_fallo(_error("InvalidNonce"), "real")


def test_un_mensaje_con_credenciales_no_se_repite() -> None:
    texto = explicar_fallo(_error("ExchangeError", "fallo con apiKey=XYZ123 secret=abc"), "real")
    assert "XYZ123" not in texto
    assert "abc" not in texto


def test_el_saldo_va_con_las_monedas_de_referencia_primero() -> None:
    saldo = {
        "ZZZ": Decimal(5),
        "BTC": Decimal(1),
        "AAA": Decimal(3),
        "USDT": Decimal(100),
        "X": Decimal(0),
    }
    assert [m for m, _ in ordenar_saldo(saldo)] == ["USDT", "BTC", "AAA", "ZZZ"]


def test_probar_sin_claves_no_llama_a_nadie() -> None:
    def lector(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
        raise AssertionError("no debería llamarse")

    resultado = probar("pruebas", None, lector)
    assert resultado.ok is False
    assert "pégalas" in resultado.detalle


def test_probar_bien_y_mal() -> None:
    def bien(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
        return {"USDT": Decimal(10000), "BTC": Decimal(1)}

    def mal(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
        raise _error("AuthenticationError")

    ok = probar("pruebas", CLAVES, bien)
    assert ok.ok is True
    assert ok.saldo == (("USDT", Decimal(10000)), ("BTC", Decimal(1)))
    assert "dinero ficticio" in ok.detalle

    fallo = probar("pruebas", CLAVES, mal)
    assert fallo.ok is False
    assert "rechaza" in fallo.detalle
    assert CLAVES.clave not in fallo.detalle and CLAVES.secreto not in fallo.detalle
