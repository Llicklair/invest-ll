"""Consistencia semana a semana.

El mes natural es como se vive el resultado, pero esconde la pregunta que hace cualquiera que
empieza: «¿y si pruebo una semana?». Una semana suelta no dice nada — eso ya lo demuestra el
backtester negándose a firmarla. Lo que sí dice algo es la **distribución de todas** las semanas:
cuántas acabaron en verde, cuánto pesa la peor y cuántas seguidas se puede pasar perdiendo.

Se agrupa por semana ISO y no por bloques de siete días para que las semanas no se desplacen a lo
largo del histórico: la semana ISO empieza siempre en lunes, así que dos activos distintos se
trocean por las mismas fronteras y sus resultados semanales son comparables.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from invest_ll.report.consistency import monthly_consistency, weekly_consistency

D = Decimal


def _lunes(semana: int) -> datetime:
    """Lunes de la semana ISO indicada de 2026 (la 1 empieza el 2025-12-29)."""
    return datetime(2025, 12, 29, tzinfo=UTC) + timedelta(weeks=semana - 1)


class TestAgrupacionSemanal:
    def test_cada_semana_iso_es_un_periodo(self) -> None:
        # Tres semanas, dos velas por semana: el cierre de cada semana es la segunda.
        marcas = [_lunes(s) + timedelta(days=d) for s in (1, 2, 3) for d in (0, 3)]
        curva = [D(100), D(110), D(110), D(120), D(120), D(90)]

        c = weekly_consistency(curva, marcas)

        # La primera semana queda fuera: no hay semana anterior con la que comparar.
        assert c.periods == 2
        assert c.positive_periods == 1

    def test_el_lunes_abre_semana_nueva(self) -> None:
        """Domingo y lunes consecutivos son semanas distintas, aunque sean dias seguidos."""
        domingo = _lunes(1) + timedelta(days=6)
        lunes = _lunes(2)
        curva = [D(100), D(100), D(150)]
        marcas = [_lunes(1), domingo, lunes]

        c = weekly_consistency(curva, marcas)

        assert c.periods == 1
        assert c.best_period == D(50)

    def test_una_semana_sola_no_da_ningun_periodo(self) -> None:
        """Sin una semana previa no hay variacion que medir: no se inventa un cero."""
        marcas = [_lunes(1), _lunes(1) + timedelta(days=2), _lunes(1) + timedelta(days=4)]

        c = weekly_consistency([D(100), D(120), D(130)], marcas)

        assert c.periods == 0
        assert c.positive_ratio == 0.0

    def test_cruza_el_ano_sin_mezclar_semanas(self) -> None:
        """La semana 1 de 2026 arranca en diciembre de 2025: agrupar solo por numero las juntaria."""
        finales = [datetime(2024, 12, 30, tzinfo=UTC), datetime(2025, 12, 29, tzinfo=UTC)]
        c = weekly_consistency([D(100), D(200)], finales)

        assert c.periods == 1
        assert c.positive_periods == 1


class TestSemanalFrenteAMensual:
    def test_hay_mas_semanas_que_meses_en_el_mismo_periodo(self) -> None:
        marcas = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(120)]
        curva = [D(100 + i) for i in range(120)]

        semanal = weekly_consistency(curva, marcas)
        mensual = monthly_consistency(curva, marcas)

        assert semanal.periods > mensual.periods

    def test_una_subida_constante_da_todas_las_semanas_en_verde(self) -> None:
        marcas = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(70)]
        curva = [D(100 + i) for i in range(70)]

        c = weekly_consistency(curva, marcas)

        assert c.positive_ratio == 1.0
        assert c.longest_losing_streak == 0

    def test_la_racha_en_rojo_cuenta_semanas_seguidas(self) -> None:
        marcas = [_lunes(s) for s in range(1, 7)]
        curva = [D(100), D(90), D(80), D(70), D(95), D(60)]

        c = weekly_consistency(curva, marcas)

        assert c.longest_losing_streak == 3

    def test_la_asimetria_delata_ganar_poco_y_perder_mucho(self) -> None:
        marcas = [_lunes(s) for s in range(1, 6)]
        curva = [D(100), D(102), D(104), D(106), D(50)]

        c = weekly_consistency(curva, marcas)

        assert c.positive_ratio == 0.75
        assert c.asymmetry > 1
