"""Hyperliquid sin red: los mensajes reales se leen bien y la fuente guarda lo que debe.

Los mensajes de `tests/fixtures/hyperliquid/` son reales (capturados del servicio el 17-oct-2026,
recortados): si Hyperliquid cambia sus formas, se vuelven a capturar y estos tests dicen qué se
rompió. Nada aquí toca la red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from invest_ll.vivo import hyperliquid as hl
from invest_ll.vivo.fuente import FuentePrecios
from invest_ll.vivo.hyperliquid import FuenteHyperliquid, MensajeRaroError
from invest_ll.vivo.mercado import Mercado

from ..fixtures.vivo import Reloj, mensaje


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def fuente(reloj: Reloj) -> FuenteHyperliquid:
    return FuenteHyperliquid(reloj=reloj.ahora, monotono=reloj.monotono)


def con_lista(fuente: FuenteHyperliquid) -> FuenteHyperliquid:
    """La fuente tras abrir la conexión y recibir la lista de monedas y precios."""
    fuente.abierta()
    fuente.recibir_meta(mensaje("rest_metaAndAssetCtxs.json"))
    fuente.recibir(mensaje("ws_allMids.json"))
    return fuente


# -- Interpretar ---------------------------------------------------------------------------------


def test_all_mids_solo_trae_los_perpetuos() -> None:
    mids = hl.leer_mids(mensaje("ws_allMids.json")["data"])
    assert mids["BTC"] == Decimal("81180.5")
    assert mids["kPEPE"] == Decimal("0.003854")
    assert not [c for c in mids if c.startswith(("#", "@")) or "/" in c]
    assert hl.leer_mids(mensaje("rest_allMids.json"))["BTC"] == Decimal("81181.0")


def test_meta_da_decimales_precio_de_ayer_y_volumen_sin_las_retiradas() -> None:
    info = hl.leer_meta(mensaje("rest_metaAndAssetCtxs.json"))
    assert set(info) == {"BTC", "ETH", "SOL", "kPEPE", "HYPE", "FARTCOIN", "ZEC"}  # MATIC fuera
    btc = info["BTC"]
    assert btc.decimales_cantidad == 5
    assert btc.precio_ayer == Decimal("81388.0")
    assert btc.volumen_24h == Decimal("1655961618.0151107311")
    assert btc.precio == Decimal("81173.5")
    assert btc.variacion_24h == pytest.approx((81173.5 - 81388) / 81388 * 100)
    assert info["kPEPE"].decimales_cantidad == 0


def test_libro_del_websocket_y_del_rest() -> None:
    libro = hl.leer_libro(mensaje("ws_l2Book.json")["data"])
    assert libro.coin == "BTC"
    assert libro.at == datetime.fromtimestamp(1792256647.062, tz=UTC)
    assert libro.mejor_compra == Decimal("81175.0")
    assert libro.mejor_venta == Decimal("81176.0")
    assert libro.compras[0].cantidad == Decimal("11.17651")
    assert libro.compras[0].ordenes == 42
    assert len(libro.compras) == len(libro.ventas) == 20
    precios_compra = [n.precio for n in libro.compras]
    precios_venta = [n.precio for n in libro.ventas]
    assert precios_compra == sorted(precios_compra, reverse=True)
    assert precios_venta == sorted(precios_venta)

    rest = hl.leer_libro(mensaje("rest_l2Book.json"))
    assert (rest.mejor_compra, rest.mejor_venta) == (Decimal("81173.0"), Decimal("81174.0"))


def test_operaciones_con_el_lado_de_quien_las_inicio() -> None:
    primeras = hl.leer_operaciones(mensaje("ws_trades.json")[0]["data"])
    assert len(primeras) == 10
    op = primeras[0]
    assert (op.coin, op.precio, op.cantidad, op.lado) == (
        "BTC",
        Decimal("81205.0"),
        Decimal("0.00106"),
        "venta",  # "A": quien vendió se comió las compras del libro
    )
    assert op.id == 258809292809346
    assert {o.lado for o in primeras} == {"compra", "venta"}
    assert [o.at for o in primeras] == sorted(o.at for o in primeras)  # de la más antigua


def test_velas_del_websocket_y_del_historico() -> None:
    vela = hl.leer_vela(mensaje("ws_candle.json")[0]["data"])
    assert (vela.coin, vela.intervalo) == ("BTC", "1m")
    assert vela.inicio == datetime.fromtimestamp(1792256640, tz=UTC)
    assert vela.fin == vela.inicio + timedelta(minutes=1)
    assert vela.cierre == Decimal("81180.0")
    assert vela.volumen == Decimal("0.1321")

    historico = [hl.leer_vela(v) for v in mensaje("rest_candleSnapshot_1m.json")]
    assert [v.inicio for v in historico] == sorted(v.inicio for v in historico)
    assert historico[0].apertura == Decimal("81210.0")


LIBROS_ROTOS: list[dict[str, Any]] = [
    {"coin": "BTC", "time": 1, "levels": [[]]},  # falta un lado
    {"coin": "BTC", "time": 1, "levels": [[{"px": "x", "sz": "1"}], []]},  # precio no numérico
    {"time": 1, "levels": [[], []]},  # sin moneda
]


@pytest.mark.parametrize("roto", LIBROS_ROTOS)
def test_un_libro_roto_se_dice(roto: dict[str, Any]) -> None:
    with pytest.raises(MensajeRaroError):
        hl.leer_libro(roto)


def test_los_mensajes_que_se_mandan() -> None:
    assert hl.mensaje_suscripcion(("allMids", "", "")) == {
        "method": "subscribe",
        "subscription": {"type": "allMids"},
    }
    assert hl.mensaje_suscripcion(("l2Book", "BTC", ""))["subscription"] == {
        "type": "l2Book",
        "coin": "BTC",
        "fast": True,
    }
    assert hl.mensaje_suscripcion(("candle", "ETH", "4h"))["subscription"] == {
        "type": "candle",
        "coin": "ETH",
        "interval": "4h",
    }
    desde = datetime(2026, 10, 1, tzinfo=UTC)
    peticion = hl.peticion_velas("BTC", "1h", desde, desde + timedelta(hours=2))
    assert peticion == {
        "type": "candleSnapshot",
        "req": {
            "coin": "BTC",
            "interval": "1h",
            "startTime": 1790812800000,
            "endTime": 1790820000000,
        },
    }


# -- La fuente en memoria ------------------------------------------------------------------------


def test_cumple_los_protocolos(fuente: FuenteHyperliquid) -> None:
    precios: FuentePrecios = fuente
    assert isinstance(precios, Mercado)


def test_sin_nada_no_inventa(fuente: FuenteHyperliquid) -> None:
    assert not fuente.conectada()
    assert fuente.precio("BTC") is None
    assert fuente.libro("BTC") is None
    assert fuente.velas("BTC", "1m") == []
    assert fuente.monedas() == []
    assert fuente.existe("BTC") is None
    assert fuente.estado().aviso == "Conectando con Hyperliquid…"


def test_conectada_solo_mientras_llegan_mensajes(fuente: FuenteHyperliquid, reloj: Reloj) -> None:
    fuente.abierta()
    assert not fuente.conectada()  # abierta, pero aún no ha llegado nada
    fuente.recibir(mensaje("ws_pong.json"))
    assert fuente.conectada()
    assert fuente.estado().desde == reloj.hora
    reloj.pasar(hl.SIN_NOTICIAS + 1)
    assert not fuente.conectada()
    assert "no manda datos" in (fuente.estado().aviso or "")
    fuente.recibir(mensaje("ws_allMids.json"))
    assert fuente.conectada()


def test_al_cortarse_lo_dice_con_la_hora_y_el_intento(
    fuente: FuenteHyperliquid, reloj: Reloj
) -> None:
    fuente.abierta()
    fuente.recibir(mensaje("ws_pong.json"))
    fuente.cerrada("OSError: red caída")
    reloj.pasar(5)
    fuente.cerrada("OSError: red caída")
    estado = fuente.estado()
    assert not estado.conectada
    assert estado.desde is None
    assert estado.aviso is not None
    assert "Sin conexión con Hyperliquid desde las" in estado.aviso
    assert "intento 2" in estado.aviso
    fuente.abierta()
    fuente.recibir(mensaje("ws_pong.json"))
    assert fuente.estado().aviso is None


def test_lista_de_monedas_las_mas_negociadas_primero(fuente: FuenteHyperliquid) -> None:
    con_lista(fuente)
    monedas = fuente.monedas()
    assert [m.coin for m in monedas][:3] == ["BTC", "ETH", "HYPE"]
    assert "MATIC" not in {m.coin for m in monedas}
    btc = monedas[0]
    assert btc.precio == Decimal("81180.5")  # el de allMids, más reciente que el de la lista
    assert btc.decimales_cantidad == 5
    assert fuente.existe("MATIC") is False
    assert fuente.existe("NOEXISTE") is False
    assert fuente.canonica("kpepe") == "kPEPE"
    assert fuente.canonica("btc") == "BTC"


def test_seguir_avisa_y_solo_pide_monedas_que_existen(fuente: FuenteHyperliquid) -> None:
    avisos: list[int] = []
    fuente.al_seguir = lambda: avisos.append(1)
    fuente.seguir("BTC", libro=True, intervalos=["1m", "nada"])
    assert avisos == [1]
    # Antes de conocer la lista no se suscribe a nada más que a los precios: suscribirse a una
    # moneda que no existe hace que Hyperliquid cierre la conexión entera.
    assert fuente.suscripciones() == [("allMids", "", "")]
    con_lista(fuente)
    assert fuente.suscripciones() == [
        ("allMids", "", ""),
        ("l2Book", "BTC", ""),
        ("trades", "BTC", ""),
        ("candle", "BTC", "1m"),
    ]
    fuente.seguir("NOEXISTE", libro=True)
    fuente.seguir("BTC", libro=True)  # ya seguida: nada nuevo
    assert avisos == [1, 1]  # el segundo, al llegar la lista
    assert ("l2Book", "NOEXISTE", "") not in fuente.suscripciones()


def test_lo_pedido_antes_de_la_lista_se_descarta_si_no_existe(fuente: FuenteHyperliquid) -> None:
    fuente.seguir("NOEXISTE", libro=True, intervalos=["1h"])
    con_lista(fuente)
    assert fuente.suscripciones() == [("allMids", "", "")]
    assert fuente.por_rellenar() == []


def test_el_precio_es_el_mas_reciente_entre_libro_y_lista(
    fuente: FuenteHyperliquid, reloj: Reloj
) -> None:
    con_lista(fuente)
    assert fuente.precio("BTC") == Decimal("81180.5")
    reloj.pasar(0.5)
    fuente.recibir(mensaje("ws_l2Book.json"))
    assert fuente.precio("BTC") == Decimal("81175.5")  # medio del libro
    reloj.pasar(0.5)
    fuente.recibir(mensaje("ws_allMids.json"))
    assert fuente.precio("BTC") == Decimal("81180.5")
    assert fuente.precio("NOEXISTE") is None


def test_operaciones_la_mas_reciente_primero_y_con_limite(fuente: FuenteHyperliquid) -> None:
    for m in mensaje("ws_trades.json"):
        fuente.recibir(m)
    assert fuente.contador_operaciones("BTC") == 11
    ultimas = fuente.operaciones("BTC", limite=3)
    assert ultimas[0].id == 281399444455858  # la del segundo mensaje
    assert len(ultimas) == 3
    lote = mensaje("ws_trades.json")[1]
    for _ in range(hl.MAX_OPERACIONES + 10):
        fuente.recibir(lote)
    assert len(fuente.operaciones("BTC", limite=10_000)) == hl.MAX_OPERACIONES
    assert fuente.contador_operaciones("BTC") == 11 + hl.MAX_OPERACIONES + 10


def test_velas_historico_y_vela_en_curso(fuente: FuenteHyperliquid, reloj: Reloj) -> None:
    con_lista(fuente)
    fuente.seguir("BTC", intervalos=["1m"])
    pendientes = fuente.por_rellenar()
    assert [(c, i) for c, i, _ in pendientes] == [("BTC", "1m")]
    assert pendientes[0][2] == reloj.hora - timedelta(minutes=hl.MAX_VELAS)
    assert fuente.rellenando("BTC", "1m")
    assert fuente.por_rellenar() == []  # se dan una vez

    pedidas = fuente.marca()
    fuente.recibir_velas("BTC", "1m", mensaje("rest_candleSnapshot_1m.json"), pedidas_en=pedidas)
    assert not fuente.rellenando("BTC", "1m")
    velas = fuente.velas("BTC", "1m")
    assert len(velas) == 5
    assert all(v.cerrada for v in velas)  # la última ya pasó su hora (17:04:30)

    for m in mensaje("ws_candle.json"):  # la de las 17:04, en curso
        fuente.recibir(m)
    velas = fuente.velas("BTC", "1m")
    assert len(velas) == 6
    assert [v.cerrada for v in velas] == [True] * 5 + [False]
    assert velas[-1].volumen == Decimal("0.17315")  # la última actualización
    assert fuente.velas("BTC", "1m", limite=2)[0].inicio == velas[-2].inicio

    reloj.pasar(60)
    assert fuente.velas("BTC", "1m")[-1].cerrada


def test_el_historico_largo_no_se_pide_desde_antes_de_hyperliquid(
    fuente: FuenteHyperliquid,
) -> None:
    con_lista(fuente)
    fuente.seguir("BTC", intervalos=["1w"])
    [(_, _, desde)] = fuente.por_rellenar()
    assert desde == hl.ANTES_DE_HYPERLIQUID


def test_el_historico_no_pisa_lo_que_el_websocket_trajo_despues(
    fuente: FuenteHyperliquid, reloj: Reloj
) -> None:
    con_lista(fuente)
    pedidas = fuente.marca()
    reloj.pasar(0.2)
    nueva = mensaje("ws_candle.json")[2]
    fuente.recibir(nueva)
    vieja = dict(nueva["data"], v="0.001")  # la misma vela, como venía en el histórico
    fuente.recibir_velas("BTC", "1m", [vieja], pedidas_en=pedidas)
    assert fuente.velas("BTC", "1m")[-1].volumen == Decimal("0.17315")
    # Pedido después de la actualización del WebSocket, el histórico sí manda.
    fuente.recibir_velas("BTC", "1m", [vieja], pedidas_en=fuente.marca())
    assert fuente.velas("BTC", "1m")[-1].volumen == Decimal("0.001")


def test_tras_un_corte_rellena_desde_la_ultima_vela_que_habia(
    fuente: FuenteHyperliquid, reloj: Reloj
) -> None:
    con_lista(fuente)
    fuente.seguir("BTC", intervalos=["1m"])
    fuente.por_rellenar()
    fuente.recibir_velas("BTC", "1m", mensaje("rest_candleSnapshot_1m.json"), pedidas_en=0)
    fuente.cerrada("corte")
    fuente.abierta()
    for m in mensaje("ws_candle.json"):  # el WebSocket vuelve antes que el histórico
        fuente.recibir(m)
    pendientes = fuente.por_rellenar()
    assert pendientes == [("BTC", "1m", datetime.fromtimestamp(1792256580, tz=UTC))]


def test_una_vela_vieja_que_llega_tarde_queda_cerrada(fuente: FuenteHyperliquid) -> None:
    historico = mensaje("rest_candleSnapshot_1m.json")
    fuente.recibir_velas("BTC", "1m", historico[-1:], pedidas_en=0)
    fuente.recibir_velas("BTC", "1m", historico[:1], pedidas_en=0)
    velas = fuente.velas("BTC", "1m")
    assert [v.cerrada for v in velas] == [True, True]


def test_las_velas_tienen_limite(
    fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hl, "MAX_VELAS", 10)
    base = mensaje("ws_candle.json")[0]["data"]
    for i in range(30):
        vela = dict(base, t=base["t"] + i * 60_000, T=base["T"] + i * 60_000)
        fuente.recibir({"channel": "candle", "data": vela})
    velas = fuente.velas("BTC", "1m", limite=100)
    assert 10 <= len(velas) <= 11
    assert velas[-1].inicio == datetime.fromtimestamp((base["t"] + 29 * 60_000) / 1000, tz=UTC)


def test_un_mensaje_raro_se_ignora_sin_romper_nada(fuente: FuenteHyperliquid) -> None:
    fuente.recibir({"channel": "l2Book", "data": {"coin": "BTC", "levels": "basura"}})
    fuente.recibir({"channel": "trades", "data": [{"side": "X"}]})
    fuente.recibir({"channel": "subscriptionResponse", "data": {}})
    fuente.recibir({"channel": "error", "data": "Invalid subscription"})
    fuente.recibir(mensaje("ws_l2Book.json"))
    assert fuente.libro("BTC") is not None


def test_seguir_tiene_limite(fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hl, "MAX_SEGUIDAS", 2)
    for coin in ("BTC", "ETH", "SOL"):
        fuente.seguir(coin, libro=True)
    con_lista(fuente)
    libros = [s for s in fuente.suscripciones() if s[0] == "l2Book"]
    assert len(libros) == 2
