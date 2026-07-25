"""T044 — invariantes de la fusión sobre rangos generados (US3).

`merge` es la función con más riesgo de la feature: sus errores son silenciosos. Los casos que se
me ocurrieron están en `test_merge.py`; estos son los que no se me ocurrieron.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from invest_ll.data.bar import Bar, Interval
from invest_ll.fetch.merge import merge, missing_ranges

from ..fixtures.recorded_data import ORIGEN, velas

pytestmark = pytest.mark.property

PASO = Interval.DAY_1.duration

# Un tramo se describe por su desplazamiento desde el origen y su longitud. Con dos tramos
# cualesquiera se cubren todas las relaciones posibles: contiguos, solapados, disjuntos,
# idénticos y contenidos.
desplazamientos = st.integers(min_value=0, max_value=40)
longitudes = st.integers(min_value=0, max_value=30)


def tramo(desplazamiento: int, longitud: int) -> list[Bar]:
    if longitud == 0:
        return []
    return velas(longitud, start=ORIGEN + PASO * desplazamiento, base=100.0 + desplazamiento)


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_el_resultado_siempre_queda_ordenado(a: int, la: int, b: int, lb: int) -> None:
    resultado = merge(tramo(a, la) or None, tramo(b, lb))
    marcas = [bar.timestamp for bar in resultado.bars]
    assert marcas == sorted(marcas)


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_nunca_hay_duplicados(a: int, la: int, b: int, lb: int) -> None:
    resultado = merge(tramo(a, la) or None, tramo(b, lb))
    marcas = [bar.timestamp for bar in resultado.bars]
    assert len(set(marcas)) == len(marcas)


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_ninguna_vela_almacenada_se_pierde(a: int, la: int, b: int, lb: int) -> None:
    almacenado = tramo(a, la)
    resultado = merge(almacenado or None, tramo(b, lb))
    presentes = {bar.timestamp for bar in resultado.bars}
    assert {bar.timestamp for bar in almacenado} <= presentes


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_ninguna_vela_almacenada_cambia_de_valor(a: int, la: int, b: int, lb: int) -> None:
    """La regla central del módulo: ante conflicto, gana lo almacenado (FR-026)."""
    almacenado = tramo(a, la)
    resultado = merge(almacenado or None, tramo(b, lb))
    por_marca = {bar.timestamp: bar for bar in resultado.bars}

    for original in almacenado:
        assert por_marca[original.timestamp].close == original.close
        assert por_marca[original.timestamp].open == original.open


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_el_recuento_de_anadidas_cuadra(a: int, la: int, b: int, lb: int) -> None:
    almacenado = tramo(a, la)
    resultado = merge(almacenado or None, tramo(b, lb))
    assert len(resultado.bars) == len(almacenado) + resultado.added_count


@given(a=desplazamientos, la=longitudes, b=desplazamientos, lb=longitudes)
@settings(max_examples=120, deadline=None)
def test_fusionar_dos_veces_no_cambia_nada(a: int, la: int, b: int, lb: int) -> None:
    """Idempotencia: repetir una descarga no debe alterar el resultado."""
    almacenado = tramo(a, la)
    descargado = tramo(b, lb)

    primera = merge(almacenado or None, descargado)
    segunda = merge(primera.bars or None, descargado)

    assert [b_.timestamp for b_ in primera.bars] == [b_.timestamp for b_ in segunda.bars]
    assert segunda.added_count == 0


@given(desplazamiento=desplazamientos, longitud=longitudes, fin=st.integers(1, 60))
@settings(max_examples=120, deadline=None)
def test_los_tramos_faltantes_nunca_piden_lo_ya_cubierto(
    desplazamiento: int, longitud: int, fin: int
) -> None:
    """Si un tramo faltante se solapara con lo almacenado, gastaría peticiones para nada."""
    almacenado = tramo(desplazamiento, longitud)
    inicio_pedido = ORIGEN
    fin_pedido = ORIGEN + PASO * fin

    faltantes = missing_ranges(
        almacenado or None,
        inicio_pedido,
        fin_pedido,
        interval_duration=PASO,
        overlap_bars=0,  # sin el solape deliberado, ningun tramo debe invadir lo cubierto
    )

    for inicio, final in faltantes:
        assert inicio < final, "un tramo faltante no puede estar vacío ni invertido"

    if almacenado:
        cubierto_desde = almacenado[0].timestamp
        cubierto_hasta = almacenado[-1].timestamp + PASO
        for inicio, final in faltantes:
            solapa = inicio < cubierto_hasta and final > cubierto_desde
            assert not solapa, f"({inicio}, {final}) invade lo ya almacenado"
