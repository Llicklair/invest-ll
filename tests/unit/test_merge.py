"""T021, T035, T036 — fusión de históricos (función pura).

El módulo con más riesgo de la feature. Un error aquí no rompe nada: deja un histórico
ligeramente mal que produce un backtest ligeramente falso, que es la peor clase de fallo que
puede tener este proyecto.
"""

from __future__ import annotations

from invest_ll.data.bar import Interval
from invest_ll.fetch.merge import merge

from ..fixtures.recorded_data import ORIGEN, alterar, velas

PASO = Interval.DAY_1.duration


class TestFusionBasica:
    def test_sin_nada_almacenado_el_resultado_es_lo_descargado(self) -> None:
        resultado = merge(None, velas(5))
        assert len(resultado.bars) == 5
        assert resultado.added_count == 5
        assert resultado.discrepancies == ()

    def test_el_resultado_queda_en_orden_cronologico(self) -> None:
        desordenadas = list(reversed(velas(5)))
        resultado = merge(None, desordenadas)
        marcas = [bar.timestamp for bar in resultado.bars]
        assert marcas == sorted(marcas)

    def test_los_duplicados_se_eliminan(self) -> None:
        base = velas(5)
        resultado = merge(None, [*base, *base])
        assert len(resultado.bars) == 5

    def test_nada_descargado_conserva_lo_almacenado(self) -> None:
        almacenado = velas(5)
        resultado = merge(almacenado, [])
        assert len(resultado.bars) == 5
        assert resultado.added_count == 0

    def test_rangos_contiguos_se_unen(self) -> None:
        primera_mitad = velas(5)
        segunda_mitad = velas(5, start=ORIGEN + PASO * 5, base=105.0)
        resultado = merge(primera_mitad, segunda_mitad)
        assert len(resultado.bars) == 10
        assert resultado.added_count == 5

    def test_rangos_disjuntos_se_unen_sin_inventar_lo_de_enmedio(self) -> None:
        """El hueco entre ambos sigue siendo un hueco: no se rellena (FR-020)."""
        primero = velas(3)
        tercero = velas(3, start=ORIGEN + PASO * 10, base=200.0)
        resultado = merge(primero, tercero)
        assert len(resultado.bars) == 6


class TestDiscrepancias:
    def test_datos_identicos_no_generan_discrepancia(self) -> None:
        almacenado = velas(5)
        resultado = merge(almacenado, list(almacenado))
        assert resultado.discrepancies == ()
        assert resultado.added_count == 0

    def test_un_valor_distinto_se_detecta(self) -> None:
        almacenado = velas(5)
        revisado = alterar(list(almacenado), 2, nuevo_cierre=999.0)
        resultado = merge(almacenado, revisado)
        assert len(resultado.discrepancies) >= 1

    def test_gana_lo_almacenado(self) -> None:
        """FR-026: el histórico sobre el que ya se decidió no cambia solo."""
        almacenado = velas(5)
        revisado = alterar(list(almacenado), 2, nuevo_cierre=999.0)
        resultado = merge(almacenado, revisado)
        assert resultado.bars[2].close == almacenado[2].close

    def test_el_aviso_identifica_fecha_y_ambos_valores(self) -> None:
        """FR-027, SC-011: un aviso que solo diga 'algo cambió' no permite decidir nada."""
        almacenado = velas(5)
        revisado = alterar(list(almacenado), 2, nuevo_cierre=999.0)
        discrepancias = merge(almacenado, revisado).discrepancies
        cierre = next(d for d in discrepancias if d.field == "close")

        assert cierre.timestamp == almacenado[2].timestamp
        assert cierre.stored_value == almacenado[2].close
        assert cierre.provider_value == 999.0
        assert "close" in cierre.describe()

    def test_una_discrepancia_no_cuenta_como_vela_anadida(self) -> None:
        almacenado = velas(5)
        revisado = alterar(list(almacenado), 2, nuevo_cierre=999.0)
        assert merge(almacenado, revisado).added_count == 0

    def test_las_velas_nuevas_entran_aunque_haya_discrepancias(self) -> None:
        """Una revisión en el solape no debe bloquear la ampliación del histórico."""
        almacenado = velas(5)
        revisado = alterar(list(almacenado), 2, nuevo_cierre=999.0)
        nuevas = velas(3, start=ORIGEN + PASO * 5, base=105.0)
        resultado = merge(almacenado, [*revisado, *nuevas])

        assert resultado.added_count == 3
        assert len(resultado.bars) == 8
        assert resultado.discrepancies


class TestRangosFaltantes:
    def test_sin_nada_almacenado_falta_el_rango_entero(self) -> None:
        from invest_ll.fetch.merge import missing_ranges

        inicio, fin = ORIGEN, ORIGEN + PASO * 10
        assert missing_ranges(None, inicio, fin, interval_duration=PASO) == [(inicio, fin)]

    def test_rango_totalmente_cubierto_no_falta_nada(self) -> None:
        """SC-005: cero peticiones cuando ya está todo."""
        from invest_ll.fetch.merge import missing_ranges

        almacenado = velas(10)
        assert missing_ranges(almacenado, ORIGEN, ORIGEN + PASO * 10, interval_duration=PASO) == []

    def test_ampliar_por_la_derecha_solo_pide_la_cola(self) -> None:
        from invest_ll.fetch.merge import missing_ranges

        almacenado = velas(5)
        faltantes = missing_ranges(almacenado, ORIGEN, ORIGEN + PASO * 10, interval_duration=PASO)
        assert len(faltantes) == 1
        assert faltantes[0][0] >= almacenado[-1].timestamp

    def test_ampliar_por_la_izquierda_solo_pide_la_cabeza(self) -> None:
        from invest_ll.fetch.merge import missing_ranges

        almacenado = velas(5, start=ORIGEN + PASO * 5)
        faltantes = missing_ranges(almacenado, ORIGEN, ORIGEN + PASO * 10, interval_duration=PASO)
        assert len(faltantes) == 1
        assert faltantes[0][1] <= almacenado[0].timestamp + PASO
