"""El examen de un bot sobre el pasado (`bots.examen`): el veredicto, la regla de «a favor», un
examen completo contra un exchange falso con un año de velas, y cuándo deja de valer."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, NoReturn

import pytest

from invest_ll.bots import examen
from invest_ll.bots.examen import ExamenError, Tramo, examinar, firma_de, regla_del_bot
from invest_ll.bots.motor import Motor
from invest_ll.bots.registro import Definicion
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.falso import ConectorFalso, con_velas, mercado_falso

from .bots_apoyo import INICIO, Mercado, onda, serie

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from pathlib import Path

    from invest_ll.exchanges.conector import Conector

D = Decimal
HORAS = 400 * 24
AHORA = INICIO
DESDE = INICIO - timedelta(hours=HORAS)
TENDENCIA = Definicion(
    id="tendencia-1",
    nombre="Tendencia",
    plantilla="tendencia",
    monedas=("BTC",),
    capital=D(1000),
    parametros={"media_corta": "5", "media_larga": "20", "intervalo": "1h"},
    creado=INICIO,
)


def _tramo(ganancia: float, mantener: float, caida: float = -0.1, caida_m: float = -0.1) -> Tramo:
    return Tramo(AHORA, AHORA, ganancia, mantener, caida, caida_m, operaciones=2)


def _falso(exchange: str, coin: str = "BTC") -> ConectorFalso:
    """Un año largo de velas de una hora que suben y bajan cada diez días."""
    par = f"{coin}/USDT"
    falso = ConectorFalso(exchange_=exchange, mercados_=(mercado_falso(coin),))
    return con_velas(
        falso, serie(par, "1h", onda(HORAS, centro=100, amplitud=15, periodo=240), DESDE)
    )


def _solo(**falsos: ConectorFalso) -> Callable[[str], Conector]:
    def conector(exchange: str) -> Conector:
        if exchange not in falsos:
            raise ExchangeError(f"{exchange} no está en esta prueba.")
        return falsos[exchange]

    return conector


class TestVeredicto:
    def test_aprueba_con_dos_de_cada_tres_a_favor_y_operaciones(self) -> None:
        tramos = [_tramo(0.05, 0.0)] * 4 + [_tramo(-0.2, 0.0)] * 2
        e = examen._veredicto("f", "binance", "1h", tramos, (), AHORA)  # pyright: ignore[reportPrivateUsage]
        assert e.aprobado
        assert (
            e.veredicto
            == "Aprobado: en 4 de 6 tramos le fue al menos como a mantener, con 12 operaciones."
        )
        assert e.motivos == ()

    @pytest.mark.parametrize(
        ("tramos", "motivo"),
        [
            ([_tramo(0.05, 0.0)] * 3 + [_tramo(-0.2, 0.0)] * 3, "Solo en 3 de 6 tramos"),
            ([_tramo(0.05, 0.0)] * 3, "Solo hay 3 tramos con velas"),
            ([replace(_tramo(0.05, 0.0), operaciones=0)] * 6, "Solo hizo 0 operaciones"),
        ],
    )
    def test_lo_que_falta_se_dice(self, tramos: list[Tramo], motivo: str) -> None:
        e = examen._veredicto("f", "binance", "1h", tramos, (), AHORA)  # pyright: ignore[reportPrivateUsage]
        assert not e.aprobado
        assert e.veredicto.startswith("No aprobado.")
        assert any(m.startswith(motivo) for m in e.motivos), e.motivos

    @pytest.mark.parametrize(
        ("tramo", "a_favor"),
        [
            (_tramo(0.10, 0.08), True),
            (_tramo(-0.03, 0.0, caida=-0.05, caida_m=-0.20), True),  # cae menos de la mitad
            (_tramo(-0.08, 0.0, caida=-0.05, caida_m=-0.20), False),  # pero se queda muy atrás
            (_tramo(-0.03, 0.0, caida=-0.15, caida_m=-0.20), False),  # cae casi lo mismo
        ],
    )
    def test_a_favor(self, tramo: Tramo, *, a_favor: bool) -> None:
        assert tramo.a_favor is a_favor


class TestExaminar:
    def test_un_ano_en_seis_tramos_con_su_firma(self) -> None:
        e = examinar(TENDENCIA, ahora=AHORA, conector_publico=_solo(binance=_falso("binance")))
        assert (e.exchange, e.intervalo, len(e.tramos)) == ("binance", "1h", 6)
        assert e.operaciones > 0
        assert e.tramos[0].desde >= AHORA - examen.PERIODO
        assert e.firma == firma_de(TENDENCIA, regla_del_bot(TENDENCIA)[0])
        assert examen.de_json(examen.a_json(e)) == e

    def test_vale_para_su_regla_y_un_mes(self) -> None:
        e = examinar(TENDENCIA, ahora=AHORA, conector_publico=_solo(binance=_falso("binance")))
        assert e.vigente(e.firma, AHORA + timedelta(days=29))
        assert not e.vigente(e.firma, AHORA + timedelta(days=31))
        otra = replace(TENDENCIA, parametros={**TENDENCIA.parametros, "media_corta": "7"})
        assert firma_de(otra, regla_del_bot(otra)[0]) != e.firma

    def test_sin_la_moneda_en_binance_usa_hyperliquid(self) -> None:
        sol = replace(TENDENCIA, monedas=("SOL",))
        conector = _solo(binance=_falso("binance"), hyperliquid=_falso("hyperliquid", "SOL"))
        assert examinar(sol, ahora=AHORA, conector_publico=conector).exchange == "hyperliquid"

    def test_la_rejilla_se_examina_con_el_cierre_de_cada_hora_y_lo_dice(self) -> None:
        rejilla = replace(
            TENDENCIA,
            plantilla="rejilla",
            parametros={"precio_bajo": "85", "precio_alto": "115", "escalones": "6"},
        )
        e = examinar(rejilla, ahora=AHORA, conector_publico=_solo(binance=_falso("binance")))
        assert e.intervalo == "1h"
        assert any("cierre de cada hora" in a for a in e.avisos)
        assert e.operaciones > 0

    def test_sin_velas_en_ningun_sitio_lo_dice(self) -> None:
        def ninguno(exchange: str) -> NoReturn:
            raise ExchangeError(f"{exchange} no contesta.")

        with pytest.raises(ExamenError, match="No se pudieron conseguir las velas"):
            examinar(TENDENCIA, ahora=AHORA, conector_publico=ninguno)


def test_el_motor_lo_guarda_y_lo_apunta(tmp_path: Path) -> None:
    mercado = Mercado()
    mercado.precio("BTC", 100)
    m = Motor(mercado.fuente, tmp_path / "bots", reloj=mercado.reloj, zona=UTC)
    bot = m.desplegar("tendencia", "Tendencia", ["BTC"], D(1000), TENDENCIA.parametros)
    assert m.examen(bot) == (None, False)
    hecho = m.examinar(bot.id, conector_publico=_solo(binance=_falso("binance")))
    guardado, vigente = m.examen(m.bot(bot.id))
    assert guardado == hecho
    assert vigente
    assert m.eventos(bot.id)[0].texto.startswith("Examen sobre el pasado.")
