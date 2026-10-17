"""La cuenta de un bot: ejecuta contra el libro con comisión, sin gastar de más ni vender lo que no
tiene, y "mantener" como referencia."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.bots.cuenta import (
    Cuenta,
    OrdenPequenaError,
    cantidades_mantener,
    valor_mantener,
)
from invest_ll.vivo.ejecucion import LibroInsuficienteError
from invest_ll.vivo.fuente import Libro, Nivel

from .bots_apoyo import INICIO

D = Decimal
TOMADOR = D("0.00045")


def libro() -> Libro:
    return Libro(
        coin="BTC",
        compras=(Nivel(D(99), D(1)), Nivel(D(98), D(2))),
        ventas=(Nivel(D(101), D(1)), Nivel(D(102), D(2)), Nivel(D(105), D(10))),
        at=INICIO,
    )


class TestComprar:
    def test_gasta_lo_pedido_con_la_comision_dentro(self) -> None:
        c = Cuenta(efectivo=D(1000))
        h = c.comprar(libro(), D(50))
        assert h.lado == "compra"
        assert h.precio == D(101)
        assert h.importe + h.comision <= D(50)
        assert D(50) - (h.importe + h.comision) < D("0.0002")
        assert h.comision == (h.importe * TOMADOR).quantize(D("1e-6"))
        assert c.efectivo == D(1000) - h.importe - h.comision
        assert c.posiciones["BTC"].cantidad == h.cantidad

    def test_la_cantidad_se_redondea_hacia_abajo_a_8_decimales(self) -> None:
        c = Cuenta(efectivo=D(1000))
        h = c.comprar(libro(), D(50))
        assert h.cantidad == h.cantidad.quantize(D("1e-8"))

    def test_una_compra_grande_paga_los_niveles_siguientes(self) -> None:
        c = Cuenta(efectivo=D(10_000))
        h = c.comprar(libro(), D(400))
        assert h.precio > D(101)

    def test_nunca_gasta_mas_del_efectivo(self) -> None:
        c = Cuenta(efectivo=D(100))
        c.comprar(libro(), D(1000))
        assert D(0) <= c.efectivo < D("0.01")

    def test_por_debajo_del_minimo_no_compra(self) -> None:
        c = Cuenta(efectivo=D(9))
        with pytest.raises(OrdenPequenaError):
            c.comprar(libro(), D(9))
        assert c.efectivo == D(9)

    def test_si_el_libro_no_da_no_se_inventa_y_la_cuenta_no_cambia(self) -> None:
        c = Cuenta(efectivo=D(100_000))
        with pytest.raises(LibroInsuficienteError):
            c.comprar(libro(), D(100_000))
        assert c.efectivo == D(100_000)
        assert c.posiciones == {}

    def test_el_precio_medio_incluye_las_comisiones(self) -> None:
        c = Cuenta(efectivo=D(1000))
        h = c.comprar(libro(), D(50))
        assert c.posiciones["BTC"].precio_medio > h.precio


class TestVender:
    def test_vende_todo_y_cobra_menos_la_comision(self) -> None:
        c = Cuenta(efectivo=D(1000))
        c.comprar(libro(), D(50))
        antes = c.efectivo
        h = c.vender(libro())
        assert h.precio == D(99)
        assert c.efectivo == antes + h.importe - h.comision
        assert "BTC" not in c.posiciones

    def test_vender_una_parte_reduce_el_coste_en_proporcion(self) -> None:
        c = Cuenta(efectivo=D(1000))
        c.comprar(libro(), D(80))
        p = c.posiciones["BTC"]
        medio = p.precio_medio
        c.vender(libro(), p.cantidad / 2)
        assert abs(c.posiciones["BTC"].precio_medio - medio) < D("0.001")

    def test_no_vende_lo_que_no_tiene(self) -> None:
        with pytest.raises(OrdenPequenaError, match="no queda BTC"):
            Cuenta(efectivo=D(1000)).vender(libro())

    def test_pedir_mas_de_lo_que_hay_vende_lo_que_hay(self) -> None:
        c = Cuenta(efectivo=D(1000))
        h = c.comprar(libro(), D(50))
        assert c.vender(libro(), D(5)).cantidad == h.cantidad


class TestValorYMantener:
    def test_valor_con_precios(self) -> None:
        c = Cuenta(efectivo=D(1000))
        h = c.comprar(libro(), D(50))
        assert c.valor({"BTC": D(200)}) == c.efectivo + h.cantidad * 200
        assert c.valor({}) is None

    def test_mantener_reparte_el_capital_al_precio_de_arranque_con_una_comision(self) -> None:
        q = cantidades_mantener(D(1000), ("BTC", "ETH"), {"BTC": D(100), "ETH": D(10)})
        assert q == {"BTC": D(500) * (1 - TOMADOR) / 100, "ETH": D(500) * (1 - TOMADOR) / 10}
        valor = valor_mantener(q, {"BTC": D(200), "ETH": D(10)})
        assert valor == D(1500) * (1 - TOMADOR)

    def test_sin_precio_de_arranque_no_hay_mantener(self) -> None:
        assert cantidades_mantener(D(1000), ("BTC",), {}) is None
        assert valor_mantener(None, {"BTC": D(1)}) is None
