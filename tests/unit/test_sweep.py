"""Barrido de estrategias con corrección por número de pruebas."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.research.sweep import (
    SweepEntry,
    SweepSummary,
    probabilidad_por_azar,
)

D = Decimal


def entrada(label: str, *, train: float, val: float, ops: int = 40) -> SweepEntry:
    return SweepEntry(
        label=label,
        train_excess=D(str(train)),
        train_trades=ops,
        validation_excess=D(str(val)),
        validation_trades=ops,
    )


class TestProbabilidadPorAzar:
    def test_la_mitad_de_exitos_es_lo_esperable(self) -> None:
        """10 de 20 es exactamente lo que predice tirar monedas."""
        assert probabilidad_por_azar(10, 20) > 0.5

    def test_todos_los_exitos_es_improbable(self) -> None:
        assert probabilidad_por_azar(20, 20) == pytest.approx(1 / 2**20)

    def test_muchos_mas_de_la_mitad_es_significativo(self) -> None:
        assert probabilidad_por_azar(17, 20) < 0.05

    def test_sin_pruebas_no_hay_nada_que_decir(self) -> None:
        assert probabilidad_por_azar(0, 0) == 1.0

    def test_sin_exitos_no_hay_nada_que_decir(self) -> None:
        assert probabilidad_por_azar(0, 10) == 1.0

    def test_es_monotona(self) -> None:
        """Mas exitos nunca puede ser mas probable por azar."""
        anterior = 1.0
        for exitos in range(1, 21):
            actual = probabilidad_por_azar(exitos, 20)
            assert actual <= anterior
            anterior = actual


class TestSupervivencia:
    def test_positiva_en_validacion_sobrevive(self) -> None:
        assert entrada("a", train=100, val=50).survives

    def test_negativa_en_validacion_no_sobrevive(self) -> None:
        assert not entrada("a", train=100, val=-50).survives

    def test_promesa_cumplida_exige_las_dos_cosas(self) -> None:
        """Ir mal en entrenamiento y bien en validacion no cuenta: no la habrias elegido."""
        assert entrada("buena", train=100, val=50).promise_kept
        assert not entrada("suerte", train=-100, val=50).promise_kept
        assert not entrada("fallida", train=100, val=-50).promise_kept


class TestResumen:
    def test_cuenta_las_probadas(self) -> None:
        resumen = SweepSummary(entries=tuple(entrada(f"c{i}", train=10, val=10) for i in range(7)))
        assert resumen.tested == 7

    def test_lo_esperable_por_azar_es_la_mitad(self) -> None:
        resumen = SweepSummary(entries=tuple(entrada(f"c{i}", train=10, val=10) for i in range(20)))
        assert resumen.expected_by_chance == 10.0

    def test_la_mitad_de_supervivientes_no_bate_al_azar(self) -> None:
        """El caso que este modulo existe para detectar."""
        entradas = [entrada(f"g{i}", train=10, val=10) for i in range(10)]
        entradas += [entrada(f"m{i}", train=10, val=-10) for i in range(10)]
        resumen = SweepSummary(entries=tuple(entradas))

        assert len(resumen.survivors) == 10
        assert not resumen.beats_chance

    def test_casi_todas_supervivientes_si_bate_al_azar(self) -> None:
        entradas = [entrada(f"g{i}", train=10, val=10) for i in range(18)]
        entradas += [entrada(f"m{i}", train=10, val=-10) for i in range(2)]
        resumen = SweepSummary(entries=tuple(entradas))

        assert resumen.beats_chance

    def test_la_elegida_es_la_mejor_del_entrenamiento(self) -> None:
        """En la vida real no puedes ver la validacion antes de decidir."""
        resumen = SweepSummary(
            entries=(
                entrada("mediocre", train=10, val=1000),
                entrada("prometedora", train=500, val=-200),
            )
        )
        mejor = resumen.best_by_training
        assert mejor is not None
        assert mejor.label == "prometedora"
        assert not mejor.survives


class TestSalida:
    def test_avisa_cuando_el_resultado_es_azar(self) -> None:
        entradas = [entrada(f"g{i}", train=10, val=10) for i in range(10)]
        entradas += [entrada(f"m{i}", train=10, val=-10) for i in range(10)]
        texto = SweepSummary(entries=tuple(entradas)).render()

        assert "[!]" in texto
        assert "monedas al aire" in texto

    def test_no_avisa_cuando_supera_al_azar(self) -> None:
        entradas = [entrada(f"g{i}", train=10, val=10) for i in range(18)]
        entradas += [entrada(f"m{i}", train=10, val=-10) for i in range(2)]
        texto = SweepSummary(entries=tuple(entradas)).render()

        assert "[!]" not in texto

    def test_muestra_que_paso_con_la_que_habrias_elegido(self) -> None:
        resumen = SweepSummary(
            entries=(
                entrada("mediocre", train=10, val=1000),
                entrada("prometedora", train=500, val=-200),
            )
        )
        texto = resumen.render()
        assert "habrias elegido: prometedora" in texto
        assert "NO cumplio" in texto

    def test_un_barrido_vacio_no_rompe(self) -> None:
        assert "sin configuraciones" in SweepSummary(entries=()).render()

    def test_es_imprimible_en_consola_windows(self) -> None:
        entradas = [entrada(f"c{i}", train=10, val=-10) for i in range(5)]
        SweepSummary(entries=tuple(entradas)).render().encode("cp1252")


class TestDesventajaSistematica:
    """El caso real del barrido de 40 configuraciones: cero supervivientes.

    La primera version de este modulo solo miraba el extremo bueno y se habria callado ante el
    resultado mas informativo que ha dado el proyecto.
    """

    def test_cero_de_cuarenta_es_desventaja_no_neutralidad(self) -> None:
        from invest_ll.research.sweep import probabilidad_cola_inferior

        resumen = SweepSummary(
            entries=tuple(entrada(f"c{i}", train=100, val=-100) for i in range(40))
        )
        assert len(resumen.survivors) == 0
        assert resumen.systematically_worse
        assert not resumen.beats_chance
        assert probabilidad_cola_inferior(0, 40) == pytest.approx(1 / 2**40)

    def test_la_mitad_no_es_desventaja(self) -> None:
        entradas = [entrada(f"g{i}", train=10, val=10) for i in range(10)]
        entradas += [entrada(f"m{i}", train=10, val=-10) for i in range(10)]
        resumen = SweepSummary(entries=tuple(entradas))
        assert not resumen.systematically_worse

    def test_el_aviso_distingue_desventaja_de_ausencia_de_ventaja(self) -> None:
        resumen = SweepSummary(
            entries=tuple(entrada(f"c{i}", train=100, val=-100) for i in range(40))
        )
        texto = resumen.render()
        assert "DESVENTAJA" in texto
        assert "friccion" in texto
        texto.encode("cp1252")

    def test_las_dos_colas_son_complementarias(self) -> None:
        from invest_ll.research.sweep import (
            probabilidad_cola_inferior,
            probabilidad_por_azar,
        )

        for k in range(11):
            assert probabilidad_por_azar(k, 10) + probabilidad_cola_inferior(k, 10) > 1.0
