"""La recomendación: reglas fijas, comprobadas caso por caso (docs/panel-v2.md, sección 6).

La tabla de abajo está escrita a mano a partir de la especificación, sin reutilizar el código que
prueba: si alguien cambia una regla, falla el caso concreto que la contradice.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.estrategias.recomendacion import (
    AVISO_REGLAS,
    AnteCaida,
    CaidasDelCatalogo,
    Horizonte,
    QuiereCripto,
    Respuestas,
    recomendar,
)

D = Decimal

# (horizonte, ante una caida a la mitad, cripto) -> (estrategia de bolsa, % en btc-freno)
Caso = tuple[Horizonte, AnteCaida, QuiereCripto, str, int]
CASOS: list[Caso] = [
    ("2-5", "vender", "no", "bolsa-prudente", 0),
    ("2-5", "vender", "poco", "bolsa-prudente", 5),
    ("2-5", "vender", "si", "bolsa-prudente", 5),
    ("2-5", "esperar", "no", "bolsa-equilibrada", 0),
    ("2-5", "esperar", "poco", "bolsa-equilibrada", 5),
    ("2-5", "esperar", "si", "bolsa-equilibrada", 10),
    ("2-5", "comprar", "no", "bolsa-equilibrada", 0),
    ("2-5", "comprar", "poco", "bolsa-equilibrada", 5),
    ("2-5", "comprar", "si", "bolsa-equilibrada", 10),
    ("5-10", "vender", "no", "bolsa-prudente", 0),
    ("5-10", "vender", "poco", "bolsa-prudente", 5),
    ("5-10", "vender", "si", "bolsa-prudente", 5),
    ("5-10", "esperar", "no", "bolsa-equilibrada", 0),
    ("5-10", "esperar", "poco", "bolsa-equilibrada", 5),
    ("5-10", "esperar", "si", "bolsa-equilibrada", 10),
    ("5-10", "comprar", "no", "bolsa-eeuu", 0),
    ("5-10", "comprar", "poco", "bolsa-eeuu", 5),
    ("5-10", "comprar", "si", "bolsa-eeuu", 15),
    ("mas-10", "vender", "no", "bolsa-prudente", 0),
    ("mas-10", "vender", "poco", "bolsa-prudente", 5),
    ("mas-10", "vender", "si", "bolsa-prudente", 5),
    ("mas-10", "esperar", "no", "bolsa-equilibrada", 0),
    ("mas-10", "esperar", "poco", "bolsa-equilibrada", 5),
    ("mas-10", "esperar", "si", "bolsa-equilibrada", 10),
    ("mas-10", "comprar", "no", "bolsa-eeuu", 0),
    ("mas-10", "comprar", "poco", "bolsa-eeuu", 5),
    ("mas-10", "comprar", "si", "bolsa-eeuu", 15),
]


def _respuestas(
    horizonte: Horizonte,
    caida: AnteCaida,
    cripto: QuiereCripto,
    inicial: str = "6000",
    mensual: str = "200",
) -> Respuestas:
    return Respuestas(
        inicial=D(inicial),
        mensual=D(mensual),
        horizonte=horizonte,
        ante_caida=caida,
        cripto=cripto,
    )


@pytest.mark.parametrize(("horizonte", "caida", "cripto", "bolsa", "pct"), CASOS)
def test_cada_combinacion_de_respuestas(
    horizonte: Horizonte, caida: AnteCaida, cripto: QuiereCripto, bolsa: str, pct: int
) -> None:
    reparto = recomendar(_respuestas(horizonte, caida, cripto))

    assert reparto.no_invertir is False
    assert reparto.partes[0].estrategia == bolsa
    assert reparto.partes[0].porcentaje == 100 - pct
    if pct:
        assert len(reparto.partes) == 2
        assert reparto.partes[1].estrategia == "btc-freno"
        assert reparto.partes[1].porcentaje == pct
    else:
        assert len(reparto.partes) == 1


@pytest.mark.parametrize("caida", ["vender", "esperar", "comprar"])
@pytest.mark.parametrize("cripto", ["no", "poco", "si"])
def test_menos_de_dos_anios_no_es_para_invertir(caida: AnteCaida, cripto: QuiereCripto) -> None:
    reparto = recomendar(_respuestas("menos-2", caida, cripto))

    assert reparto.no_invertir is True
    assert [(p.estrategia, p.porcentaje) for p in reparto.partes] == [("bolsa-prudente", 100)]
    assert "menos de 2 años" in reparto.por_que[0]
    assert "cuenta remunerada" in reparto.por_que[0]


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: "-".join(map(str, c)))
def test_la_cripto_nunca_pasa_del_15_ni_del_5_si_venderias(caso: Caso) -> None:
    horizonte, caida, cripto, _, _ = caso
    reparto = recomendar(_respuestas(horizonte, caida, cripto))
    en_cripto = sum(p.porcentaje for p in reparto.partes if p.estrategia == "btc-freno")
    assert en_cripto <= 15
    if caida == "vender":
        assert en_cripto <= 5


def test_el_reparto_se_aplica_al_inicial_y_a_la_mensual_y_suma_exacto() -> None:
    reparto = recomendar(_respuestas("mas-10", "esperar", "poco", inicial="6000", mensual="199.99"))

    bolsa, cripto = reparto.partes
    assert (bolsa.inicial, cripto.inicial) == (D("5700.00"), D("300.00"))
    assert bolsa.mensual + cripto.mensual == D("199.99"), "ningún céntimo se pierde al repartir"
    assert cripto.mensual == D("10.00")


def test_el_por_que_cita_las_respuestas() -> None:
    reparto = recomendar(_respuestas("mas-10", "esperar", "poco"))
    texto = " ".join(reparto.por_que)
    assert "en más de 10 años" in texto
    assert "esperarías a que se recupere" in texto
    assert "un poco de cripto" in texto


@pytest.mark.parametrize(
    ("horizonte", "dicho"),
    [("2-5", "dentro de 2 a 5 años"), ("5-10", "dentro de 5 a 10 años")],
)
def test_los_plazos_intermedios_se_dicen_en_castellano(horizonte: Horizonte, dicho: str) -> None:
    """Salía "lo necesitarás en entre 5 y 10 años"."""
    for caida in ("esperar", "comprar"):  # "vender" no cita el plazo
        texto = " ".join(recomendar(_respuestas(horizonte, caida, "no")).por_que)
        assert dicho in texto
        assert "en entre" not in texto


def test_si_venderias_y_quieres_cripto_se_explica_el_tope() -> None:
    reparto = recomendar(_respuestas("mas-10", "vender", "si"))
    assert any("venderías para no perder más" in f and "5 %" in f for f in reparto.por_que)


def test_avisos_siempre_y_el_de_cripto_solo_con_cripto() -> None:
    sin = recomendar(_respuestas("mas-10", "esperar", "no"))
    con = recomendar(_respuestas("mas-10", "esperar", "si"))

    assert sin.avisos == (AVISO_REGLAS,)
    assert con.avisos[0] == AVISO_REGLAS
    assert "65 %" in con.avisos[1]


def test_las_caidas_que_se_citan_salen_del_catalogo_si_las_hay() -> None:
    caidas = CaidasDelCatalogo(menor=-0.12, mayor=-0.83, cripto=-0.61)
    reparto = recomendar(_respuestas("mas-10", "esperar", "si"), caidas)
    no_invertir = recomendar(_respuestas("menos-2", "esperar", "si"), caidas)

    assert "61 %" in reparto.avisos[1]
    assert "entre un 12 % y un 83 %" in no_invertir.por_que[0]


def test_alternativas_del_mismo_mercado() -> None:
    sin_cripto = recomendar(_respuestas("mas-10", "esperar", "no"))
    con_cripto = recomendar(_respuestas("mas-10", "esperar", "si"))

    assert sin_cripto.alternativas == ("bolsa-prudente", "bolsa-eeuu")
    assert con_cripto.alternativas == (
        "bolsa-prudente",
        "bolsa-eeuu",
        "cripto-cesta-freno",
        "btc-mantener",
    )
