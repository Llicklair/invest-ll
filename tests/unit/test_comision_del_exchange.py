"""De dónde se saca la comisión según cómo la sirva el exchange.

Cada uno la publica en un sitio distinto, y ccxt no siempre la normaliza. Binance, comprobado
contra su red de pruebas el 2026-07-26, **no rellena `fee` en una orden de mercado**: reparte el
cobro entre los `fills`, uno por cada trozo ejecutado. Mirar solo `fee` habría perdido en silencio
la comisión de un exchange entero — y una cartera construida sobre eso parecería más rentable de
lo que fue.

`None` significa «no se sabe», nunca cero. Es la distinción que permite que el importador de
cartera avise en vez de inventar.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from invest_ll.live.ccxt_broker import comision_declarada

D = Decimal


class TestDondeMirar:
    def test_el_campo_normalizado_de_ccxt(self) -> None:
        assert comision_declarada({"fee": {"cost": "0.0647", "currency": "USDT"}}) == D("0.0647")

    def test_variascomision_declaradaes_en_monedas_distintas_se_suman(self) -> None:
        crudo: dict[str, Any] = {"fees": [{"cost": "0.04"}, {"cost": "0.02"}]}
        assert comision_declarada(crudo) == D("0.06")

    def test_los_trades_cuando_ccxt_los_desglosa(self) -> None:
        crudo: dict[str, Any] = {"trades": [{"fee": {"cost": "0.03"}}, {"fee": {"cost": "0.01"}}]}
        assert comision_declarada(crudo) == D("0.04")

    def test_los_fills_crudos_de_binance(self) -> None:
        """El caso real: Binance cobra por fill y lo deja en info.fills."""
        crudo: dict[str, Any] = {
            "fee": None,
            "fees": [],
            "info": {
                "fills": [
                    {"price": "64703.52", "qty": "0.0006", "commission": "0.00000060"},
                    {"price": "64704.10", "qty": "0.0004", "commission": "0.00000040"},
                ]
            },
        }
        assert comision_declarada(crudo) == D("0.00000100")

    def test_el_campo_normalizado_gana_al_desglose(self) -> None:
        """Si el exchange ya da el total, no hace falta sumar trozos."""
        crudo: dict[str, Any] = {"fee": {"cost": "0.10"}, "info": {"fills": [{"commission": "999"}]}}
        assert comision_declarada(crudo) == D("0.10")


class TestCuandoNoSeSabe:
    def test_sin_ningun_dato_es_desconocida(self) -> None:
        assert comision_declarada({"id": "1", "filled": 0.001}) is None

    def test_listas_vacias_no_son_cero(self) -> None:
        """Lo que devolvio Binance al consultar la orden ya ejecutada."""
        assert comision_declarada({"fee": None, "fees": [], "info": {}}) is None

    def test_fills_sin_el_campo_decomision_declarada(self) -> None:
        assert comision_declarada({"info": {"fills": [{"price": "1", "qty": "1"}]}}) is None

    def test_algo_que_no_es_un_numero_no_se_convierte_en_cero(self) -> None:
        assert comision_declarada({"fee": {"cost": "no-es-un-numero"}}) is None

    def test_una_respuesta_rara_no_revienta(self) -> None:
        raros: list[dict[str, Any]] = [
            {"fee": "0.1"},
            {"fees": "0.1"},
            {"trades": {}},
            {"info": []},
        ]
        for crudo in raros:
            assert comision_declarada(crudo) is None
