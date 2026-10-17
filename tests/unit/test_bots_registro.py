"""Los bots en disco: lo que se guarda vuelve igual, los registros solo añaden y un id nunca sale
de `bots/`."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from invest_ll.bots.cuenta import Cuenta, Posicion
from invest_ll.bots.registro import (
    BotNoEncontradoError,
    Definicion,
    Estado,
    Evento,
    Operacion,
    Punto,
    Registro,
    id_valido,
    nuevo_id,
)

from .bots_apoyo import INICIO

if TYPE_CHECKING:  # pragma: no cover
    from pathlib import Path

D = Decimal


def definicion(bot_id: str = "mi-bot-abc123") -> Definicion:
    return Definicion(
        id=bot_id,
        nombre="Mi bot",
        plantilla="tendencia",
        monedas=("BTC", "ETH"),
        capital=D(1000),
        parametros={"media_corta": "20", "media_larga": "50", "intervalo": "1h"},
        creado=INICIO,
    )


def estado() -> Estado:
    return Estado(
        estado="en_marcha",
        cuenta=Cuenta(
            efectivo=D("500.123456"), posiciones={"BTC": Posicion(D("0.0075"), D("499.9"))}
        ),
        memoria={"escalon_1": "0.5"},
        precios_arranque={"BTC": D(67000)},
        ultimos_precios={"BTC": D(67100)},
        ultima_vez=INICIO,
        maximo=D(1001),
        peor_caida=-0.02,
        operaciones=3,
        ultima_operacion=INICIO,
        aviso="Panel cerrado de 14:02 a 18:30: no pudo operar.",
        aviso_hasta=INICIO,
    )


def test_lo_guardado_vuelve_igual(tmp_path: Path) -> None:
    r = Registro(tmp_path)
    r.crear(definicion(), estado())
    assert r.ids() == ["mi-bot-abc123"]
    assert r.definicion("mi-bot-abc123") == definicion()
    leido = r.estado("mi-bot-abc123")
    assert leido.cuenta.efectivo == D("500.123456")
    assert leido.cuenta.posiciones["BTC"].cantidad == D("0.0075")
    assert leido.memoria == {"escalon_1": "0.5"}
    assert leido.peor_caida == -0.02
    assert leido.aviso == estado().aviso
    assert leido.ultima_vez == INICIO


def test_los_registros_solo_anaden_y_una_linea_cortada_se_ignora(tmp_path: Path) -> None:
    r = Registro(tmp_path)
    r.crear(definicion(), estado())
    op = Operacion(INICIO, "BTC", "compra", D("0.01"), D(67010), D("670.1"), D("0.3"), "Compré…")
    r.operacion("mi-bot-abc123", op)
    r.operacion("mi-bot-abc123", op)
    r.evento("mi-bot-abc123", Evento(INICIO, "arranque", "Desplegado."))
    r.punto("mi-bot-abc123", Punto(INICIO, D(1000), None))
    with (tmp_path / "mi-bot-abc123" / "operaciones.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"at": "2026-10-01T00:00:00+00:00", "coin": "BT')  # un cierre a medias
    assert r.operaciones("mi-bot-abc123") == [op, op]
    assert [e.texto for e in r.eventos("mi-bot-abc123")] == ["Desplegado."]
    assert r.curva("mi-bot-abc123") == [Punto(INICIO, D(1000), None)]


def test_guardar_el_estado_no_deja_temporales(tmp_path: Path) -> None:
    r = Registro(tmp_path)
    r.crear(definicion(), estado())
    for _ in range(3):
        r.guardar_estado("mi-bot-abc123", estado())
    assert sorted(p.name for p in (tmp_path / "mi-bot-abc123").iterdir()) == [
        "definicion.json",
        "estado.json",
    ]


def test_borrar_se_lleva_la_carpeta(tmp_path: Path) -> None:
    r = Registro(tmp_path)
    r.crear(definicion(), estado())
    r.borrar("mi-bot-abc123")
    assert r.ids() == []
    with pytest.raises(BotNoEncontradoError):
        r.borrar("mi-bot-abc123")


@pytest.mark.parametrize("malo", ["../fuera", "..", "a/b", "Mayus", "", "con espacio", "x" * 81])
def test_un_id_nunca_sale_de_la_carpeta(tmp_path: Path, malo: str) -> None:
    assert not id_valido(malo)
    with pytest.raises(BotNoEncontradoError):
        Registro(tmp_path).estado(malo)


def test_el_id_sale_del_nombre(tmp_path: Path) -> None:
    bot_id = nuevo_id("Tendencia rápida: BTC y ETH!")
    assert bot_id.startswith("tendencia-rapida-btc-y-eth-")
    assert id_valido(bot_id)
    assert nuevo_id("¿?").startswith("bot-")


def test_sin_carpeta_no_hay_bots(tmp_path: Path) -> None:
    assert Registro(tmp_path / "no-existe").ids() == []
