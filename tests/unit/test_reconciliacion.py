"""Lo que el exchange dice que tienes, frente a lo que tu cartera cree.

Es la única comprobación que no se puede hacer desde dentro: todo lo demás en este proyecto deriva
del registro, así que si el registro está incompleto, todo lo que sale de él está mal **de forma
coherente** — cuadra consigo mismo y no chirría por ningún lado.

El caso que la motiva: ingresas 500 USDT en el exchange y no lo anotas. Tu cartera no se entera,
tu efectivo derivado se queda a cero, y cualquier cifra de rentabilidad que dependa del capital
empleado queda inflada. Aquí eso aparece como una diferencia con nombre y cantidad.

**No arregla nada por su cuenta.** Dice qué falta y qué comando lo cuadraría; registrar es una
decisión tuya. Un reconciliador que ajusta solo tapa justamente el error que debía enseñarte.
"""

from __future__ import annotations

from decimal import Decimal

from invest_ll.portfolio.reconcile import Diferencia, reconciliar

D = Decimal


class TestCuandoTodoCuadra:
    def test_mismas_cantidades_no_dan_diferencias(self) -> None:
        informe = reconciliar(
            exchange={"BTC": D("0.006"), "USDT": D("500")},
            cartera={"BTC": D("0.006"), "USDT": D("500")},
        )
        assert informe.cuadra
        assert not informe.diferencias

    def test_una_diferencia_ridicula_no_cuenta(self) -> None:
        """El polvo de decimales del exchange no es un descuadre."""
        informe = reconciliar(exchange={"BTC": D("0.00600001")}, cartera={"BTC": D("0.006")})
        assert informe.cuadra

    def test_un_activo_a_cero_en_ambos_lados_no_es_diferencia(self) -> None:
        informe = reconciliar(exchange={"BTC": D(0)}, cartera={})
        assert informe.cuadra


class TestCuandoNoCuadra:
    def test_lo_que_hay_de_mas_en_el_exchange_se_reporta(self) -> None:
        """El caso del ingreso sin registrar."""
        informe = reconciliar(exchange={"USDT": D("500")}, cartera={})

        assert not informe.cuadra
        assert len(informe.diferencias) == 1
        d = informe.diferencias[0]
        assert d.symbol == "USDT"
        assert d.en_el_exchange == D("500")
        assert d.en_la_cartera == D(0)
        assert d.falta_registrar == D("500")

    def test_lo_que_sobra_en_la_cartera_tambien(self) -> None:
        """Una posicion que crees tener y el exchange no ve: peor senal que la contraria."""
        informe = reconciliar(exchange={}, cartera={"BTC": D("0.5")})

        assert not informe.cuadra
        assert informe.diferencias[0].falta_registrar == D("-0.5")

    def test_las_diferencias_salen_de_mayor_a_menor(self) -> None:
        informe = reconciliar(
            exchange={"USDT": D("500"), "BTC": D("0.006"), "ETH": D("2")},
            cartera={"USDT": D("100"), "BTC": D("0.001"), "ETH": D("2")},
        )
        simbolos = [d.symbol for d in informe.diferencias]
        assert simbolos == ["USDT", "BTC"]

    def test_dice_como_cuadrar_el_efectivo(self) -> None:
        informe = reconciliar(exchange={"USDT": D("500")}, cartera={})
        sugerencia = informe.diferencias[0].como_cuadrarlo()
        assert "cash deposit" in sugerencia
        assert "500" in sugerencia

    def test_para_un_activo_sugiere_registrar_la_compra(self) -> None:
        informe = reconciliar(exchange={"BTC": D("0.006")}, cartera={})
        sugerencia = informe.diferencias[0].como_cuadrarlo()
        assert "add buy" in sugerencia
        assert "BTC" in sugerencia


class TestSoloSeMiraLoQueHasTocado:
    def test_lo_que_nunca_operaste_no_es_un_descuadre(self) -> None:
        """La red de pruebas regala saldo en cientos de monedas: enterraria lo tuyo."""
        informe = reconciliar(
            exchange={"BTC": D("0.006"), "DOGE": D("18466"), "SHIB": D("18466")},
            cartera={"BTC": D("0.006")},
            relevantes={"BTC", "USDT"},
        )
        assert informe.cuadra
        assert informe.otros_con_saldo == ("DOGE", "SHIB")

    def test_lo_ignorado_se_cuenta_en_el_resumen(self) -> None:
        informe = reconciliar(exchange={"DOGE": D("18466")}, cartera={}, relevantes={"BTC"})
        assert "1 activo(s) con saldo" in informe.describe()

    def test_el_descuadre_de_lo_relevante_sigue_saliendo(self) -> None:
        informe = reconciliar(
            exchange={"USDT": D("500"), "DOGE": D("18466")},
            cartera={},
            relevantes={"USDT"},
        )
        assert [d.symbol for d in informe.diferencias] == ["USDT"]

    def test_sin_filtro_se_compara_todo(self) -> None:
        informe = reconciliar(exchange={"DOGE": D("18466")}, cartera={})
        assert not informe.cuadra


class TestElResumenSigueSiendoUnResumen:
    def test_no_escupe_cuatrocientos_nombres(self) -> None:
        muchos = {f"MONEDA{i}": D(100 + i) for i in range(50)}
        texto = reconciliar(exchange=muchos, cartera={}).describe()

        assert "y 45 mas" in texto
        assert len(texto) < 400


class TestElInformeSeExplica:
    def test_cuando_cuadra_lo_dice(self) -> None:
        assert "cuadra" in reconciliar(exchange={}, cartera={}).describe().lower()

    def test_cuando_no_cuadra_nombra_lo_que_falta(self) -> None:
        texto = reconciliar(exchange={"USDT": D("500")}, cartera={}).describe()
        assert "USDT" in texto

    def test_no_promete_haber_arreglado_nada(self) -> None:
        """Un reconciliador que ajusta solo tapa el error que debia ensenar."""
        texto = reconciliar(exchange={"USDT": D("500")}, cartera={}).describe().lower()
        assert "registra" in texto or "registrar" in texto


class TestLaDiferenciaSabeDeQueLado:
    def test_falta_en_la_cartera(self) -> None:
        d = Diferencia(symbol="USDT", en_el_exchange=D("500"), en_la_cartera=D("100"))
        assert d.falta_registrar == D("400")
        assert d.falta_en_la_cartera

    def test_sobra_en_la_cartera(self) -> None:
        d = Diferencia(symbol="BTC", en_el_exchange=D("0.001"), en_la_cartera=D("0.5"))
        assert not d.falta_en_la_cartera
