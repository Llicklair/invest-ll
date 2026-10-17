"""`/api/vivo`: el mercado en vivo de Hyperliquid y su stream, sin red.

La fuente es una `FuenteHyperliquid` alimentada con mensajes reales guardados (o una `FuenteFalsa`),
puesta con `servicio.usar_fuente`; la hora de las respuestas, fija. Así el JSON de cada evento del
stream se compara con el de su ruta REST byte a byte, como promete el contrato.

El TestClient lee la respuesta entera antes de devolverla: los streams se cortan en las pruebas con
`MAX_EVENTOS` o `MAX_SEGUNDOS` (solo existen para esto).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll.api import vivo as rutas_vivo
from invest_ll.api.schemas_v3 import Bots, EstadoReal
from invest_ll.vivo import servicio
from invest_ll.vivo.fuente import FuenteFalsa, Libro, Nivel

from ..fixtures.vivo import Reloj, bucle, fuente_con_datos, mensaje

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator
    from pathlib import Path

    from invest_ll.vivo.hyperliquid import FuenteHyperliquid

    from .api_apoyo import Api

AHORA = datetime(2026, 10, 17, 17, 4, 31, tzinfo=UTC)


@pytest.fixture(autouse=True)
def hora_fija(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(servicio, "ahora", lambda: AHORA)
    yield
    servicio.usar_fuente(None)


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def fuente(reloj: Reloj) -> FuenteHyperliquid:
    f = fuente_con_datos(reloj)
    servicio.usar_fuente(f)
    return f


@pytest.fixture
def corto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streams que acaban solos: como mucho 3 s (una prueba que espera de más falla, no se cuelga)."""
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 3.0)


def eventos(texto: str) -> list[tuple[str, Any]]:
    """Los eventos de un cuerpo SSE: (nombre, JSON) y ("latido", None) por cada comentario."""
    salida: list[tuple[str, Any]] = []
    for bloque in texto.split("\n\n"):
        if not bloque.strip():
            continue
        if bloque.startswith(":"):
            salida.append(("latido", None))
            continue
        lineas = dict(linea.split(": ", 1) for linea in bloque.splitlines())
        salida.append((lineas["event"], json.loads(lineas["data"])))
    return salida


# -- Las rutas -----------------------------------------------------------------------------------


def test_sin_panel_arrancado_dice_que_no_hay_datos(cliente: Api) -> None:
    servicio.usar_fuente(None)
    estado = cliente.get("/api/vivo/estado").json()
    assert estado == {
        "conectado": False,
        "fuente": "Hyperliquid",
        "desde": None,
        "aviso": servicio.AVISO_SIN_PANEL,
    }
    monedas = cliente.get("/api/vivo/monedas").json()
    assert monedas["monedas"] == []
    assert monedas["estado"] == estado
    # Sin la lista de monedas no se sabe si existe: se pide y se espera, sin inventar un libro.
    libro = cliente.get("/api/vivo/libro", params={"coin": "BTC"}).json()
    assert (libro["compras"], libro["ventas"], libro["diferencial"]) == ([], [], None)


def test_estado_conectado(cliente: Api, fuente: FuenteHyperliquid, reloj: Reloj) -> None:
    estado = cliente.get("/api/vivo/estado").json()
    assert estado["conectado"] is True
    assert estado["aviso"] is None
    assert datetime.fromisoformat(estado["desde"]) == reloj.hora


def test_monedas_con_nombre_llano_las_mas_negociadas_primero(
    cliente: Api, fuente: FuenteHyperliquid
) -> None:
    respuesta = cliente.get("/api/vivo/monedas").json()
    monedas = respuesta["monedas"]
    assert [m["coin"] for m in monedas] == ["BTC", "ETH", "HYPE", "SOL", "ZEC", "kPEPE", "FARTCOIN"]
    btc = monedas[0]
    assert btc["nombre"] == "Bitcoin"
    assert btc["decimales_cantidad"] == 5
    assert btc["volumen_24h"] == pytest.approx(1655961618.0151107)
    assert btc["var_24h"] == pytest.approx((btc["precio"] - 81388) / 81388 * 100)
    nombres = {m["coin"]: m["nombre"] for m in monedas}
    assert nombres["kPEPE"] == "Pepe (por 1.000)"
    assert nombres["HYPE"] == "Hyperliquid"
    assert respuesta["estado"]["conectado"] is True


def test_libro(cliente: Api, fuente: FuenteHyperliquid) -> None:
    libro = cliente.get("/api/vivo/libro", params={"coin": "btc"}).json()
    assert libro["coin"] == "BTC"
    assert len(libro["compras"]) == len(libro["ventas"]) == 20
    assert libro["compras"][0] == {"precio": 81175.0, "cantidad": 11.17651, "ordenes": 42}
    assert libro["ventas"][0]["precio"] == 81176.0
    assert libro["diferencial"] == 1.0
    assert datetime.fromisoformat(libro["at"]) == datetime.fromtimestamp(1792256647.062, tz=UTC)


def test_moneda_que_no_existe_es_404_en_llano(cliente: Api, fuente: FuenteHyperliquid) -> None:
    for ruta in ("/api/vivo/libro", "/api/vivo/operaciones", "/api/vivo/velas", "/api/vivo/stream"):
        respuesta = cliente.get(ruta, params={"coin": "NOEXISTE"})
        assert respuesta.status_code == 404, ruta
        assert respuesta.json() == {
            "detail": "Hyperliquid no tiene ninguna moneda llamada «NOEXISTE»."
        }
    assert cliente.get("/api/vivo/libro", params={"coin": "MATIC"}).status_code == 404  # retirada


def test_operaciones_la_mas_reciente_primero(cliente: Api, fuente: FuenteHyperliquid) -> None:
    respuesta = cliente.get("/api/vivo/operaciones", params={"coin": "BTC"}).json()
    operaciones = respuesta["operaciones"]
    assert len(operaciones) == 11
    assert operaciones[0] == {
        "coin": "BTC",
        "at": "2026-10-17T17:04:08.450000Z",
        "precio": 81180.0,
        "cantidad": 0.01827,
        "lado": "venta",
    }
    assert {o["lado"] for o in operaciones} == {"compra", "venta"}


def test_velas_con_la_en_curso(cliente: Api, fuente: FuenteHyperliquid) -> None:
    respuesta = cliente.get(
        "/api/vivo/velas", params={"coin": "BTC", "intervalo": "1m", "limite": 4}
    ).json()
    velas = respuesta["velas"]
    assert (respuesta["coin"], respuesta["intervalo"], len(velas)) == ("BTC", "1m", 4)
    assert [v["cerrada"] for v in velas] == [True, True, True, False]
    assert velas[-1]["inicio"] == "2026-10-17T17:04:00Z"
    assert velas[-1]["volumen"] == 0.17315


def test_velas_de_un_intervalo_que_no_existe(cliente: Api, fuente: FuenteHyperliquid) -> None:
    respuesta = cliente.get("/api/vivo/velas", params={"coin": "BTC", "intervalo": "2m"})
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"].startswith("No hay velas de «2m». Valen: 1m, 3m, 5m")


def test_una_serie_nueva_espera_su_historico_solo_con_conexion(
    cliente: Api, fuente: FuenteHyperliquid
) -> None:
    fuente.cerrada("corte")  # sin conexión no se espera: se responde con lo que hay
    empezo = time.monotonic()
    respuesta = cliente.get("/api/vivo/velas", params={"coin": "ETH", "intervalo": "4h"}).json()
    assert respuesta["velas"] == []
    assert time.monotonic() - empezo < 2
    assert fuente.rellenando("ETH", "4h")


def test_con_una_fuente_falsa_tambien(cliente: Api) -> None:
    libro = Libro(
        coin="BTC",
        compras=(Nivel(Decimal(99), Decimal(1)),),
        ventas=(Nivel(Decimal(101), Decimal(2)),),
        at=AHORA,
    )
    servicio.usar_fuente(FuenteFalsa(libros={"BTC": libro}))
    monedas = cliente.get("/api/vivo/monedas").json()["monedas"]
    assert monedas == [
        {
            "coin": "BTC",
            "nombre": "Bitcoin",
            "precio": 100.0,
            "var_24h": None,
            "volumen_24h": None,
            "decimales_cantidad": 8,
        }
    ]
    assert cliente.get("/api/vivo/libro", params={"coin": "BTC"}).json()["diferencial"] == 2.0
    assert cliente.get("/api/vivo/velas", params={"coin": "BTC"}).json()["velas"] == []
    assert cliente.get("/api/vivo/operaciones", params={"coin": "BTC"}).json()["operaciones"] == []


# -- El stream -----------------------------------------------------------------------------------


def test_cada_evento_lleva_el_json_de_su_ruta(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch, corto: None
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_EVENTOS", 5)
    respuesta = cliente.get(
        "/api/vivo/stream",
        params={"coin": "BTC", "intervalo": "1m", "canales": "estado,monedas,libro,vela,cuenta"},
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/event-stream")
    assert respuesta.headers["cache-control"] == "no-cache"
    recibidos = dict(eventos(respuesta.text))
    assert set(recibidos) == {"estado", "monedas", "libro", "vela", "cuenta"}
    assert recibidos["estado"] == cliente.get("/api/vivo/estado").json()
    assert recibidos["monedas"] == cliente.get("/api/vivo/monedas").json()
    assert recibidos["libro"] == cliente.get("/api/vivo/libro", params={"coin": "BTC"}).json()
    velas = cliente.get("/api/vivo/velas", params={"coin": "BTC", "intervalo": "1m"}).json()
    assert recibidos["vela"] == velas["velas"][-1]
    assert recibidos["cuenta"] == cliente.get("/api/practica").json()


def test_el_json_del_evento_es_el_mismo_texto_que_el_de_la_ruta(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch, corto: None
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_EVENTOS", 1)
    texto = cliente.get("/api/vivo/stream", params={"coin": "BTC", "canales": "libro"}).text
    data = texto.split("data: ", 1)[1].split("\n", 1)[0]
    assert data == cliente.get("/api/vivo/libro", params={"coin": "BTC"}).text


def test_filtra_por_canales(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 0.5)
    texto = cliente.get("/api/vivo/stream", params={"coin": "BTC", "canales": "estado,libro"}).text
    assert [nombre for nombre, _ in eventos(texto)] == ["estado", "libro"]  # sin cambios, no repite
    sin_moneda = cliente.get("/api/vivo/stream", params={"canales": "libro,estado"}).text
    assert [nombre for nombre, _ in eventos(sin_moneda)] == ["estado"]


def test_operaciones_nuevas_segun_llegan(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch, corto: None
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_EVENTOS", 1)

    def llega_una() -> None:
        time.sleep(0.3)
        fuente.recibir(mensaje("ws_trades.json")[1])

    hilo = threading.Thread(target=llega_una)
    hilo.start()
    texto = cliente.get("/api/vivo/stream", params={"coin": "BTC", "canales": "operaciones"}).text
    hilo.join()
    [(nombre, datos)] = eventos(texto)
    assert nombre == "operaciones"
    assert len(datos) == 1  # solo la nueva, no las que ya había
    assert datos[0]["precio"] == 81180.0


def test_la_vela_que_se_cierra_llega_cerrada_antes_de_la_siguiente(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch, corto: None
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_EVENTOS", 3)
    en_curso = mensaje("ws_candle.json")[2]["data"]

    def empieza_otra() -> None:
        time.sleep(0.3)
        siguiente = dict(en_curso, t=en_curso["t"] + 60_000, T=en_curso["T"] + 60_000)
        fuente.recibir({"channel": "candle", "data": siguiente})

    hilo = threading.Thread(target=empieza_otra)
    hilo.start()
    texto = cliente.get(
        "/api/vivo/stream", params={"coin": "BTC", "intervalo": "1m", "canales": "vela"}
    ).text
    hilo.join()
    velas = [datos for _, datos in eventos(texto)]
    assert [(v["inicio"], v["cerrada"]) for v in velas] == [
        ("2026-10-17T17:04:00Z", False),
        ("2026-10-17T17:04:00Z", True),
        ("2026-10-17T17:05:00Z", False),
    ]


def test_el_canal_de_bots_calla_si_los_bots_no_responden(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_hacer() -> Bots:
        raise NotImplementedError("pendiente")

    monkeypatch.setattr("invest_ll.api.bots.lista", sin_hacer)
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 0.5)
    texto = cliente.get("/api/vivo/stream", params={"canales": "bots,estado"}).text
    assert [nombre for nombre, _ in eventos(texto)] == ["estado"]


def test_el_canal_de_bots_lleva_lo_de_su_ruta(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch, corto: None
) -> None:
    bots = Bots(
        bots=[],
        capital=Decimal(0),
        valor=None,
        ganancia=None,
        ganancia_pct=None,
        real=EstadoReal(
            bots_reales=0,
            en_marcha=0,
            perdida_hoy=Decimal(0),
            limite_diario=None,
            parado_todo=False,
            aviso=None,
        ),
        at=AHORA,
        nota="Dinero ficticio. Los bots solo funcionan con el panel abierto.",
    )
    monkeypatch.setattr("invest_ll.api.bots.lista", lambda: bots)
    monkeypatch.setattr(rutas_vivo, "MAX_EVENTOS", 1)
    [(nombre, datos)] = eventos(cliente.get("/api/vivo/stream", params={"canales": "bots"}).text)
    assert nombre == "bots"
    assert datos == bots.model_dump(mode="json")


def test_latido(cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rutas_vivo, "LATIDO", 0.1)
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 0.5)
    texto = cliente.get("/api/vivo/stream", params={"canales": "estado"}).text
    assert ": latido\n\n" in texto
    assert [n for n, _ in eventos(texto) if n != "latido"] == ["estado"]


def test_canales_o_intervalo_que_no_existen(cliente: Api, fuente: FuenteHyperliquid) -> None:
    respuesta = cliente.get("/api/vivo/stream", params={"canales": "libro,precios"})
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == (
        "Canales que no existen: precios. Valen: monedas, libro, operaciones, vela, cuenta, "
        "bots, estado."
    )
    respuesta = cliente.get("/api/vivo/stream", params={"intervalo": "2m"})
    assert respuesta.status_code == 422


def test_varios_clientes_a_la_vez(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 1.0)
    textos: list[str] = []

    def escuchar() -> None:
        textos.append(cliente.get("/api/vivo/stream", params={"canales": "estado,monedas"}).text)

    hilos = [threading.Thread(target=escuchar) for _ in range(3)]
    empezo = time.monotonic()
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert time.monotonic() - empezo < 2.5  # a la vez, no uno detrás de otro
    assert len(textos) == 3
    for texto in textos:
        assert {n for n, _ in eventos(texto)} == {"estado", "monedas"}


def test_cuando_el_cliente_se_va_el_stream_se_corta_limpio(
    fuente: FuenteHyperliquid, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Starlette cancela la tarea del stream al irse el navegador: la cancelación sale tal cual
    (sin errores por el camino) y no queda nada en marcha."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("invest_ll.api.bots.lista", lambda: None)

    async def prueba() -> None:
        recibidos: list[str] = []

        async def escuchar() -> None:
            async for texto in rutas_vivo.eventos("BTC", "1m", set(rutas_vivo.CANALES)):
                recibidos.append(texto)

        tarea = asyncio.create_task(escuchar())
        while len(recibidos) < 3:
            await asyncio.sleep(0.01)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
        await asyncio.sleep(0.05)
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []

    with bucle() as runner:
        runner.run(prueba())


def test_el_stream_sigue_la_moneda(
    cliente: Api, fuente: FuenteHyperliquid, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rutas_vivo, "MAX_SEGUNDOS", 0.3)
    cliente.get("/api/vivo/stream", params={"coin": "ETH", "intervalo": "4h", "canales": "vela"})
    assert ("candle", "ETH", "4h") in fuente.suscripciones()
    assert ("l2Book", "ETH", "") not in fuente.suscripciones()  # no pidió libro
