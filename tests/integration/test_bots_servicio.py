"""El motor de los bots como servicio aparte (`bots.servicio`): su API, el panel pasándole las
rutas de los bots, el stream preguntándole, el panel cuando no contesta, lanzarlo desligado y
arrancar con Windows. Sin red: el "servicio" es su app en este mismo proceso (`ASGITransport`) y
los procesos se sustituyen."""

from __future__ import annotations

import asyncio
import socket
import subprocess
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi.testclient import TestClient

from invest_ll.api import vivo as rutas_vivo
from invest_ll.bots import motor, servicio
from invest_ll.bots.motor import Motor

from ..unit.bots_apoyo import Mercado

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Iterator

    from .api_apoyo import Api

D = Decimal
_SOCKET_REAL = socket.socket  # antes de que el fixture de la suite corte la red
REJILLA = {"precio_bajo": "90", "precio_alto": "110", "escalones": "4"}


@pytest.fixture
def cliente_motor() -> Iterator[Callable[..., TestClient]]:
    """Crea clientes de la app del servicio como el `cliente` del panel: bucle de selectores y el
    socket de verdad solo mientras arranca (tests/integration/conftest.py explica por qué). Se
    cierran al acabar el test (un cliente abierto deja un hilo vivo y la suite no termina)."""
    abiertos: list[TestClient] = []

    def crear(base_url: str = "http://127.0.0.1") -> TestClient:
        bloqueado = socket.socket
        socket.socket = _SOCKET_REAL  # type: ignore[misc]
        try:
            c = TestClient(
                servicio.crear_app_motor(con_vida=False),
                base_url=base_url,
                backend_options={"loop_factory": asyncio.SelectorEventLoop},
            )
            c.__enter__()
        finally:
            socket.socket = bloqueado  # type: ignore[misc]
        abiertos.append(c)
        return c

    yield crear
    for c in abiertos:
        c.__exit__(None, None, None)


@pytest.fixture
def mercado(cliente: Api) -> Iterator[Mercado]:
    """El motor del servicio (sin su bucle) sobre `bots/` del directorio temporal del test."""
    m = Mercado()
    m.precio("BTC", 100)
    motor.usar(Motor(m.fuente, Path("bots"), reloj=m.reloj, zona=UTC))
    yield m
    motor.usar(None)
    servicio.usar_remoto(False)


@pytest.fixture
def pasadas(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """El panel pasa las rutas de los bots al servicio (su app, aquí mismo): las que pasaron."""
    app_motor = servicio.crear_app_motor(con_vida=False)
    vistas: list[str] = []

    class Contador(httpx.ASGITransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            vistas.append(f"{request.method} {request.url.path}")
            return await super().handle_async_request(request)

    def cliente_proxy() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=Contador(app=app_motor), base_url="http://127.0.0.1")

    monkeypatch.setattr(servicio, "cliente_proxy", cliente_proxy)
    servicio.usar_remoto(True)
    return vistas


class TestLaAppDelServicio:
    def test_salud_bots_y_lo_nuevo_del_feed(
        self, mercado: Mercado, cliente_motor: Callable[..., TestClient]
    ) -> None:
        c = cliente_motor()
        r = c.post(
            "/api/bots",
            json={
                "plantilla": "rejilla",
                "nombre": "R",
                "monedas": ["BTC"],
                "capital": "1000",
                "parametros": REJILLA,
            },
        )
        assert r.status_code == 201, r.text
        salud = c.get("/api/motor/salud").json()
        assert (salud["bots"], salud["en_marcha"]) == (1, 1)
        primera = c.get("/api/actividad/nueva").json()
        assert [m["tipo"] for m in primera["actividad"]["movimientos"]] == ["arranque"]
        assert primera["actividad"]["inicial"] is True
        nada = c.get("/api/actividad/nueva", params={"vista": primera["numero"]}).json()
        assert nada == {"numero": primera["numero"], "actividad": None}
        assert c.post("/api/motor/apagar").json() == {"apagando": True}

    def test_solo_atiende_a_este_equipo(
        self, mercado: Mercado, cliente_motor: Callable[..., TestClient]
    ) -> None:
        c = cliente_motor("http://ataque.example")
        assert c.get("/api/motor/salud").status_code == 400


class TestElPanelPasaLasRutas:
    def test_las_de_los_bots_van_al_servicio_y_las_demas_no(
        self, cliente: Api, mercado: Mercado, pasadas: list[str]
    ) -> None:
        r = cliente.post(
            "/api/bots",
            json={
                "plantilla": "rejilla",
                "nombre": "Por el panel",
                "monedas": ["BTC"],
                "capital": "1000",
                "parametros": REJILLA,
            },
        )
        assert r.status_code == 201, r.text
        assert cliente.get("/api/bots").json()["bots"][0]["nombre"] == "Por el panel"
        assert cliente.get("/api/actividad", params={"limite": 5}).status_code == 200
        cliente.get("/api/vivo/estado")  # del panel: no pasa
        assert pasadas == ["POST /api/bots", "GET /api/bots", "GET /api/actividad"]

    def test_si_el_servicio_no_contesta_503_y_se_arranca(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sin_motor() -> httpx.AsyncClient:
            def caido(request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("no contesta", request=request)

            return httpx.AsyncClient(
                transport=httpx.MockTransport(caido), base_url="http://127.0.0.1"
            )

        arranques: list[bool] = []
        monkeypatch.setattr(servicio, "cliente_proxy", sin_motor)
        monkeypatch.setattr(servicio, "arrancar_si_hace_falta", lambda: arranques.append(True))
        servicio.usar_remoto(True)
        try:
            r = cliente.get("/api/bots")
        finally:
            servicio.usar_remoto(False)
        assert r.status_code == 503
        assert "se está arrancando" in r.json()["detail"]
        assert arranques == [True]

    def test_el_stream_pregunta_al_servicio(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mercado: Mercado,
        cliente_motor: Callable[..., TestClient],
    ) -> None:
        app_motor = cliente_motor()
        app_motor.post(
            "/api/bots",
            json={
                "plantilla": "rejilla",
                "nombre": "R",
                "monedas": ["BTC"],
                "capital": "1000",
                "parametros": REJILLA,
            },
        )
        monkeypatch.setattr(servicio, "bots_remotos", lambda: app_motor.get("/api/bots").json())

        def actividad(vista: int | None) -> dict[str, Any]:
            return app_motor.get(
                "/api/actividad/nueva", params={} if vista is None else {"vista": vista}
            ).json()

        monkeypatch.setattr(servicio, "actividad_remota", actividad)
        servicio.usar_remoto(True)
        bots = rutas_vivo._bots()  # pyright: ignore[reportPrivateUsage]
        assert bots is not None
        assert bots.model_dump()["bots"][0]["nombre"] == "R"
        leida = rutas_vivo.actividad_nueva(None)
        assert leida is not None
        numero, nueva = leida
        assert nueva is not None
        assert rutas_vivo.actividad_nueva(numero) == (numero, None)


class TestLanzarlo:
    def test_desligado_y_fuera_del_job(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llamadas: list[tuple[list[str], int]] = []

        def popen(orden: list[str], **kw: Any) -> object:
            llamadas.append((orden, int(kw.get("creationflags", 0))))
            return object()

        monkeypatch.setattr(servicio.subprocess, "Popen", popen)
        servicio.arrancar_en_segundo_plano()
        [(orden, banderas)] = llamadas
        assert orden[-3:] == ["-m", "invest_ll.bots.servicio", "lanzar"]
        assert orden[0].lower().endswith("pythonw.exe")
        assert banderas & servicio.DETACHED_PROCESS
        assert banderas & servicio.CREATE_BREAKAWAY_FROM_JOB

    def test_si_el_job_no_deja_salir_se_lanza_igual(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llamadas: list[int] = []

        def popen(orden: list[str], **kw: Any) -> object:
            banderas = int(kw.get("creationflags", 0))
            llamadas.append(banderas)
            if banderas & servicio.CREATE_BREAKAWAY_FROM_JOB:
                raise OSError("Acceso denegado")
            return object()

        monkeypatch.setattr(servicio.subprocess, "Popen", popen)
        servicio.lanzar()
        assert len(llamadas) == 2
        assert not llamadas[1] & servicio.CREATE_BREAKAWAY_FROM_JOB


class TestDesdeElPanel:
    def test_parado_arrancar_y_opciones(
        self, cliente: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inicio = tmp_path / "Inicio"
        estado: dict[str, Any] = {"salud": None}
        monkeypatch.setattr(servicio, "carpeta_inicio", lambda: inicio)
        monkeypatch.setattr(servicio, "en_marcha", lambda: estado["salud"])
        monkeypatch.setattr(servicio, "version_del_codigo", lambda: 1000.0)

        def arrancar() -> None:
            estado["salud"] = {
                "pid": 4321,
                "desde": "2026-10-18T03:00:00+00:00",
                "version": 1000.0,
                "bots": 4,
                "en_marcha": 3,
            }

        monkeypatch.setattr(servicio, "arrancar_en_segundo_plano", arrancar)
        monkeypatch.setattr(servicio, "esperar_en_marcha", lambda: estado["salud"])

        parado = cliente.get("/api/motor").json()
        assert parado["en_marcha"] is False
        assert "ningún bot opera" in parado["texto"]
        en_marcha = cliente.post("/api/motor/arrancar").json()
        assert (en_marcha["en_marcha"], en_marcha["pid"], en_marcha["bots_en_marcha"]) == (
            True,
            4321,
            3,
        )
        assert en_marcha["codigo_nuevo"] is False
        assert "aunque cierres esta ventana" in en_marcha["texto"]

        con_windows = cliente.put(
            "/api/motor/opciones", json={"arranca_con_windows": True, "mantener_despierto": True}
        ).json()
        assert con_windows["arranca_con_windows"] is True
        assert con_windows["mantener_despierto"] is True
        vbs = (inicio / servicio.NOMBRE_INICIO).read_text(encoding="utf-8")
        assert "-m invest_ll.bots.servicio lanzar" in vbs
        assert 'Run """' in vbs and ", 0, False" in vbs  # oculto y sin esperar
        sin = cliente.put("/api/motor/opciones", json={"arranca_con_windows": False}).json()
        assert sin["arranca_con_windows"] is False
        assert not (inicio / servicio.NOMBRE_INICIO).exists()

    def test_dice_si_el_motor_lleva_codigo_viejo(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            servicio,
            "en_marcha",
            lambda: {"pid": 1, "desde": None, "version": 1000.0, "bots": 0, "en_marcha": 0},
        )
        monkeypatch.setattr(servicio, "version_del_codigo", lambda: 5000.0)
        assert cliente.get("/api/motor").json()["codigo_nuevo"] is True


def test_la_orden_estado_sin_motor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(servicio, "en_marcha", lambda: None)
    assert servicio.main(["estado"]) == 1
    assert "invest-ll-motor arrancar" in capsys.readouterr().out


def test_lanzar_no_abre_ventana(monkeypatch: pytest.MonkeyPatch) -> None:
    vistas: list[dict[str, Any]] = []

    def popen(_orden: list[str], **kw: Any) -> object:
        vistas.append(kw)
        return object()

    monkeypatch.setattr(servicio.subprocess, "Popen", popen)
    servicio.lanzar()
    assert vistas[0]["stdout"] is subprocess.DEVNULL
    assert vistas[0]["creationflags"] & servicio.CREATE_NO_WINDOW


class TestUnSoloMotor:
    def test_el_cerrojo_deja_pasar_a_uno_solo(self, tmp_path: Path) -> None:
        primero = servicio.tomar_cerrojo(tmp_path)
        assert primero is not None
        assert servicio.tomar_cerrojo(tmp_path) is None  # otro motor: no pasa
        primero.close()  # el primero se va (o muere): el sistema suelta el cerrojo
        tercero = servicio.tomar_cerrojo(tmp_path)
        assert tercero is not None
        tercero.close()

    def test_muchas_peticiones_a_la_vez_lanzan_un_solo_arranque(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lanzados: list[bool] = []
        monkeypatch.setattr(servicio, "en_marcha", lambda: None)
        monkeypatch.setattr(servicio, "arrancar_en_segundo_plano", lambda: lanzados.append(True))
        monkeypatch.setattr(servicio, "_ultimo_arranque", float("-inf"))
        resultados = [servicio.arrancar_si_hace_falta() for _ in range(5)]
        assert resultados == [True, False, False, False, False]
        assert lanzados == [True]

    def test_si_ya_contesta_no_se_lanza(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(servicio, "en_marcha", lambda: {"pid": 1})
        monkeypatch.setattr(servicio, "_ultimo_arranque", float("-inf"))
        monkeypatch.setattr(servicio, "arrancar_en_segundo_plano", lambda: pytest.fail("no tocaba"))
        assert servicio.arrancar_si_hace_falta() is False
