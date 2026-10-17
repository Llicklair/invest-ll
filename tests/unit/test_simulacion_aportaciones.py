"""Tus números: inicial + mensual desde un año, sobre la curva de una estrategia.

Curvas construidas a mano para que cada cifra se pueda comprobar con lápiz.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from invest_ll.estrategias.simulacion import Curva, SinDatosDesdeError, simular, simular_reparto


def _dias(desde: date, n: int, paso: int = 1) -> list[int]:
    cero = int(datetime(desde.year, desde.month, desde.day, tzinfo=UTC).timestamp()) // 86_400
    return [cero + i * paso for i in range(n)]


def test_una_estrategia_plana_vale_lo_que_pusiste() -> None:
    dias = _dias(date(2020, 1, 1), 366)
    r = simular(dias, [10_000.0] * 366, inicial=1000, mensual=100, desde=date(2020, 1, 1))

    # Enero (con el inicial) y once meses más: 1000 + 12 x 100.
    assert r.aportado == pytest.approx(2200)
    assert r.valor_final == pytest.approx(2200)
    assert r.ganancia == pytest.approx(0)
    assert r.peor_caida == 0
    assert r.meses_por_debajo == 0


def test_las_aportaciones_entran_el_primer_dia_con_datos_de_cada_mes() -> None:
    # Sesiones de bolsa: el 1 de febrero de 2020 fue sábado; la aportación entra el lunes 3.
    dias: list[int] = []
    d = date(2020, 1, 2)
    while d <= date(2020, 3, 10):
        if d.weekday() < 5:
            dias.append(_dias(d, 1)[0])
        d += timedelta(days=1)
    r = simular(dias, [100.0] * len(dias), inicial=0, mensual=50, desde=date(2020, 1, 1))

    escalones = {p.fecha: p.aportado for p in r.puntos}
    assert r.aportado == pytest.approx(150)
    assert r.desde == date(2020, 1, 2)
    assert max(f for f, a in escalones.items() if a == pytest.approx(50)) < date(2020, 2, 3)


def test_si_la_estrategia_se_dobla_tu_dinero_tambien_pero_no_las_aportaciones_futuras() -> None:
    dias = _dias(date(2021, 1, 1), 59)  # enero y febrero
    valor = [100.0] * 31 + [200.0] * 28  # se dobla el 1 de febrero, antes de aportar
    r = simular(dias, valor, inicial=1000, mensual=100, desde=date(2021, 1, 1))

    # Enero: 1100 puestos que pasan a 2200; febrero: 100 más, a precio doble.
    assert r.aportado == pytest.approx(1200)
    assert r.valor_final == pytest.approx(2300)


def test_el_peor_momento_es_el_de_menos_valor_respecto_a_lo_puesto() -> None:
    dias = _dias(date(2022, 1, 1), 90)
    valor = [100.0] * 20 + [40.0] * 30 + [100.0] * 40
    r = simular(dias, valor, inicial=1000, mensual=0, desde=date(2022, 1, 1))

    assert r.peor_momento_valor == pytest.approx(400)
    assert r.peor_momento_aportado == pytest.approx(1000)
    assert r.peor_momento_fecha == date(2022, 1, 21)
    assert r.peor_caida == pytest.approx(-0.6)
    assert r.meses_por_debajo == 1  # enero acaba por debajo; febrero y marzo, no


def test_la_peor_caida_no_la_disimulan_tus_aportaciones() -> None:
    """Medida sobre el rendimiento de la estrategia, no sobre tu saldo, que crece al aportar."""
    dias = _dias(date(2022, 1, 1), 70)
    valor = [100.0] * 35 + [50.0] * 35
    r = simular(dias, valor, inicial=100, mensual=10_000, desde=date(2022, 1, 1))
    assert r.peor_caida == pytest.approx(-0.5)


def test_muestreo_semanal_con_el_primer_y_el_ultimo_dia() -> None:
    dias = _dias(date(2023, 1, 2), 30)  # lunes 2 de enero de 2023, 30 días
    r = simular(dias, [1.0] * 30, inicial=10, mensual=0, desde=date(2023, 1, 1))

    fechas = [p.fecha for p in r.puntos]
    assert fechas[0] == date(2023, 1, 2)
    assert fechas[-1] == date(2023, 1, 31)
    assert all(f.weekday() == 6 for f in fechas[1:-1]), "uno por semana: su último día (domingo)"


def test_bolsa_y_cripto_comparten_las_fechas_de_sus_puntos_semanales() -> None:
    """La gráfica junta las estrategias por fecha: si la bolsa marcaba su semana el viernes y la
    cripto el domingo, ninguna fecha coincidía y cada línea salía con huecos ("—" en la ayuda y
    una tabla con el doble de filas, media vacía)."""
    desde = date(2021, 1, 4)  # lunes
    diarios = _dias(desde, 60)
    sesiones = [d for d in diarios if _fecha_de(d).weekday() < 5]
    # Viernes 15 de enero sin sesión, como un festivo de bolsa.
    sesiones = [d for d in sesiones if _fecha_de(d) != date(2021, 1, 15)]
    bolsa = simular(sesiones, [1.0] * len(sesiones), inicial=10, mensual=1, desde=desde)
    cripto = simular(diarios, [1.0] * len(diarios), inicial=10, mensual=1, desde=desde)

    fechas_bolsa = [p.fecha for p in bolsa.puntos]
    fechas_cripto = [p.fecha for p in cripto.puntos]
    assert fechas_bolsa[:-1] == fechas_cripto[:-1]
    assert all(f.weekday() == 6 for f in fechas_bolsa[1:-1]), "cada semana, en su domingo"
    # El valor sigue siendo el del último día con datos de esa semana, y el último punto, el real.
    assert fechas_bolsa[-1] == date(2021, 3, 4)
    assert fechas_cripto[-1] == date(2021, 3, 4)


def _fecha_de(dia: int) -> date:
    return datetime.fromtimestamp(dia * 86_400, UTC).date()


def test_avisa_si_los_datos_empiezan_despues_de_lo_pedido() -> None:
    dias = _dias(date(2018, 1, 1), 40)
    r = simular(
        dias, [1.0] * 40, inicial=10, mensual=1, desde=date(2015, 1, 1), fecha_texto="1 ene 2018"
    )
    assert r.desde == date(2018, 1, 1)
    assert r.aviso is not None
    assert "1 ene 2018" in r.aviso


def test_sin_aviso_si_empieza_cuando_se_pidio() -> None:
    dias = _dias(date(2018, 1, 2), 40)
    r = simular(dias, [1.0] * 40, inicial=10, mensual=1, desde=date(2018, 1, 1))
    assert r.aviso is None


def test_sin_datos_desde_ese_anio_falla() -> None:
    with pytest.raises(SinDatosDesdeError):
        simular(
            _dias(date(2018, 1, 1), 10), [1.0] * 10, inicial=1, mensual=1, desde=date(2030, 1, 1)
        )


def test_con_cero_no_hay_nada_que_simular() -> None:
    with pytest.raises(ValueError, match="pon una cantidad"):
        simular(
            _dias(date(2018, 1, 1), 10), [1.0] * 10, inicial=0, mensual=0, desde=date(2018, 1, 1)
        )


# -- Tu reparto entero: varias estrategias como una sola cuenta ---------------------------------


def test_con_una_sola_curva_el_reparto_es_lo_mismo_que_una_estrategia() -> None:
    dias = _dias(date(2022, 1, 1), 90)
    valor = [100.0] * 20 + [40.0] * 30 + [100.0 + i for i in range(40)]
    sola = simular(dias, valor, inicial=1000, mensual=100, desde=date(2022, 1, 1))
    repartida = simular_reparto(
        [Curva(dias, valor, 1.0)], inicial=1000, mensual=100, desde=date(2022, 1, 1)
    )
    assert repartida == sola


def test_cada_parte_sigue_su_estrategia_con_su_parte_de_cada_aportacion() -> None:
    dias = _dias(date(2021, 1, 1), 59)  # enero y febrero
    plana = [100.0] * 59
    doble = [100.0] * 31 + [200.0] * 28  # se dobla el 1 de febrero, antes de aportar
    r = simular_reparto(
        [Curva(dias, plana, 0.75), Curva(dias, doble, 0.25)],
        inicial=1000,
        mensual=100,
        desde=date(2021, 1, 1),
    )
    # Enero: 1100 puestos, 825 + 275; la parte que se dobla pasa a 550. Febrero: 75 + 25 más.
    assert r.aportado == pytest.approx(1200)
    assert r.valor_final == pytest.approx(825 + 75 + 550 + 25)


def test_la_peor_caida_es_la_del_reparto_entero() -> None:
    dias = _dias(date(2022, 1, 1), 60)
    plana = [100.0] * 60
    a_la_mitad = [100.0] * 30 + [50.0] * 30
    r = simular_reparto(
        [Curva(dias, plana, 0.5), Curva(dias, a_la_mitad, 0.5)],
        inicial=1000,
        mensual=0,
        desde=date(2022, 1, 1),
    )
    assert r.peor_caida == pytest.approx(-0.25)
    assert r.peor_momento_valor == pytest.approx(750)


def test_bolsa_y_cripto_se_juntan_por_fecha_con_el_ultimo_cierre() -> None:
    """Un fin de semana sin bolsa vale lo del viernes: la cuenta sigue cada día de la cripto."""
    desde = date(2021, 1, 4)  # lunes
    diarios = _dias(desde, 60)
    sesiones = [d for d in diarios if _fecha_de(d).weekday() < 5]
    sube = [1.0 + 0.01 * i for i in range(len(sesiones))]
    r = simular_reparto(
        [Curva(sesiones, sube, 0.5), Curva(diarios, [1.0] * len(diarios), 0.5)],
        inicial=100,
        mensual=0,
        desde=desde,
    )
    sola = simular(diarios, [1.0] * len(diarios), inicial=100, mensual=0, desde=desde)
    assert [p.fecha for p in r.puntos] == [p.fecha for p in sola.puntos], "la misma muestra"
    assert r.hasta == date(2021, 3, 4)
    assert r.valor_final == pytest.approx(50 * sube[-1] + 50)


def test_el_reparto_empieza_cuando_todas_tienen_datos_y_lo_avisa() -> None:
    antigua = _dias(date(2018, 1, 1), 1200)
    nueva = _dias(date(2020, 3, 1), 300)
    r = simular_reparto(
        [Curva(antigua, [1.0] * 1200, 0.9), Curva(nueva, [1.0] * 300, 0.1)],
        inicial=10,
        mensual=1,
        desde=date(2018, 1, 1),
        escribir_fecha=lambda d: f"{d.day}/{d.month}/{d.year}",
        sujeto="tu reparto",
    )
    assert r.desde == date(2020, 3, 1)
    assert r.aviso == "Los datos de tu reparto empiezan el 1/3/2020: tus números empiezan ahí."


def test_sin_datos_desde_ese_anio_en_una_parte_falla() -> None:
    with pytest.raises(SinDatosDesdeError):
        simular_reparto(
            [
                Curva(_dias(date(2018, 1, 1), 10), [1.0] * 10, 0.5),
                Curva(_dias(date(2025, 1, 1), 10), [1.0] * 10, 0.5),
            ],
            inicial=1,
            mensual=1,
            desde=date(2019, 1, 1),
        )
