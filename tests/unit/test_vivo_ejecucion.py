"""La ejecución ficticia contra el libro real: nivel a nivel, con su comisión, sin inventar precios."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from invest_ll.vivo.ejecucion import (
    Comisiones,
    LibroInsuficienteError,
    a_limite,
    a_mercado,
    limite_cruza,
)
from invest_ll.vivo.fuente import FuenteFalsa, Libro, Nivel

D = Decimal
AHORA = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)
SIN_COMISION = Comisiones(tomador=D(0), creador=D(0))


def libro() -> Libro:
    return Libro(
        coin="BTC",
        compras=(Nivel(D(99), D(1)), Nivel(D(98), D(2))),
        ventas=(Nivel(D(101), D(1)), Nivel(D(102), D(2)), Nivel(D(105), D(10))),
        at=AHORA,
    )


class TestAMercado:
    def test_comprar_dentro_del_primer_nivel_paga_ese_precio(self) -> None:
        e = a_mercado(libro(), "compra", cantidad=D("0.5"), comisiones=SIN_COMISION)
        assert e.precio_medio == D(101)
        assert e.niveles == 1

    def test_comprar_mas_que_el_primer_nivel_paga_los_siguientes(self) -> None:
        """Lo que hace creible la cuenta de practica: el impacto de una orden grande se paga."""
        e = a_mercado(libro(), "compra", cantidad=D(2), comisiones=SIN_COMISION)
        assert e.importe == D(101) + D(102)
        assert e.precio_medio == D("101.5")
        assert e.niveles == 2

    def test_vender_se_come_las_compras_de_mayor_a_menor(self) -> None:
        e = a_mercado(libro(), "venta", cantidad=D(2), comisiones=SIN_COMISION)
        assert e.importe == D(99) + D(98)

    def test_por_importe_compra_lo_que_da_ese_dinero(self) -> None:
        e = a_mercado(libro(), "compra", importe=D(203), comisiones=SIN_COMISION)
        assert e.cantidad == D(2)
        assert abs(e.importe - D(203)) < D("1e-9")

    def test_la_comision_de_tomador_se_cobra_aparte(self) -> None:
        e = a_mercado(libro(), "compra", cantidad=D(1))
        assert e.comision == D(101) * D("0.00045")
        assert e.neto == e.importe + e.comision

    def test_al_vender_la_comision_se_resta_de_lo_cobrado(self) -> None:
        e = a_mercado(libro(), "venta", cantidad=D(1))
        assert e.neto == D(99) - D(99) * D("0.00045")

    def test_sin_libro_suficiente_no_se_inventa_un_precio(self) -> None:
        with pytest.raises(LibroInsuficienteError, match="solo tiene 13"):
            a_mercado(libro(), "compra", cantidad=D(50))

    def test_hay_que_decir_cantidad_o_importe(self) -> None:
        with pytest.raises(ValueError, match="cantidad o el importe"):
            a_mercado(libro(), "compra")
        with pytest.raises(ValueError, match="cantidad o el importe"):
            a_mercado(libro(), "compra", cantidad=D(1), importe=D(1))

    def test_una_orden_de_cero_no_existe(self) -> None:
        with pytest.raises(ValueError, match="mayor que cero"):
            a_mercado(libro(), "compra", cantidad=D(0))


class TestConLimite:
    def test_comprar_con_limite_se_ejecuta_cuando_alguien_vende_a_ese_precio(self) -> None:
        assert limite_cruza(libro(), "compra", D(101))
        assert not limite_cruza(libro(), "compra", D(100))

    def test_vender_con_limite_se_ejecuta_cuando_alguien_compra_a_ese_precio(self) -> None:
        assert limite_cruza(libro(), "venta", D(99))
        assert not limite_cruza(libro(), "venta", D(100))

    def test_se_ejecuta_a_su_precio_con_comision_de_creador(self) -> None:
        e = a_limite("compra", D(2), D(100))
        assert e.precio_medio == D(100)
        assert e.comision == D(200) * D("0.00015")


class TestLaFuenteFalsa:
    def test_sin_precio_ni_libro_no_hay_precio(self) -> None:
        assert FuenteFalsa().precio("BTC") is None

    def test_sin_precio_suelto_usa_el_medio_del_libro(self) -> None:
        fuente = FuenteFalsa(libros={"BTC": libro()})
        assert fuente.precio("BTC") == D(100)
