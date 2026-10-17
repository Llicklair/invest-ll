"""La API del panel v2: conectar Binance y cambiar de modo, con los cuatro cerrojos de siempre.

El almacén de credenciales es el de memoria de la suite (`tests/conftest.py`) y el exchange no
existe: `leer_saldo` y el broker se sustituyen. Una comprobación recorre todo: **ninguna respuesta
lleva nunca una clave ni un secreto**.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from invest_ll.api import cartera as rutas_cartera
from invest_ll.api import conexion as rutas_conexion
from invest_ll.live import credenciales
from invest_ll.live.broker import (
    Confirmation,
    ExecutionError,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Side,
)
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import Testnet

from .test_api_cartera import BrokerFalso

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from invest_ll.live.mode import OperatingMode

    from ..almacen_en_memoria import AlmacenEnMemoria
    from .api_apoyo import Api

D = Decimal
PRUEBAS = {"clave": "CLAVE-DE-PRUEBAS-123", "secreto": "SECRETO-DE-PRUEBAS-456"}
REALES = {"clave": "CLAVE-REAL-789", "secreto": "SECRETO-REAL-000"}
SECRETOS = (*PRUEBAS.values(), *REALES.values())


def _sin_secretos(r: httpx.Response) -> httpx.Response:
    for secreto in SECRETOS:
        assert secreto not in r.text, "una respuesta ha devuelto una clave"
    return r


def _orden_de_pruebas_ejecutada() -> None:
    peticion = OrderRequest(
        symbol="BTC/USDT",
        side=Side.BUY,
        quantity=D("0.001"),
        requested_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    resultado = BrokerFalso(Testnet(key="k", secret="s")).submit(
        peticion, confirmation=Confirmation.para(peticion, at=peticion.requested_at)
    )
    ExecutionLedger().record(resultado, mode_name="pruebas")


def _modo(cliente: Api) -> str:
    return _sin_secretos(cliente.get("/api/conexion")).json()["modo"]


@pytest.fixture(autouse=True)
def saldos_leidos(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, credenciales.Claves]]:
    """El exchange contesta con un saldo a cualquier clave: activar un modo lo lee primero.

    Los tests de claves que fallan lo sustituyen otra vez por uno que rechaza.
    """
    pedidos: list[tuple[str, credenciales.Claves]] = []

    def saldo(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
        pedidos.append((red, claves))
        return {"USDT": D(100)}

    monkeypatch.setattr(rutas_conexion, "leer_saldo", saldo)
    return pedidos


def _rechaza(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
    raise type("AuthenticationError", (Exception,), {})(
        f'binance {{"code":-2015}} apiKey={claves.clave}'
    )


class TestEstado:
    def test_de_entrada_simulacion_sin_claves(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/conexion").json()

        assert cuerpo["modo"] == "simulacion"
        assert cuerpo["modo_origen"] == "panel"
        assert [r["origen"] for r in cuerpo["redes"]] == ["ninguno", "ninguno"]
        modos = {m["modo"]: m for m in cuerpo["modos"]}
        assert modos["simulacion"]["disponible"] is True
        assert modos["pruebas"]["disponible"] is False
        assert len(modos["real"]["que_falta"]) == 2
        assert [c["ok"] for c in cuerpo["cerrojos_real"]] == [False, False, False, False]
        assert cliente.get("/api/estado").json()["modo"]["nombre"] == "simulacion"

    def test_si_el_entorno_fija_el_modo_lo_dice_y_no_se_cambia(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INVEST_LL_MODE", "simulation")
        cuerpo = cliente.get("/api/conexion").json()
        assert cuerpo["modo_origen"] == "entorno"
        r = cliente.put("/api/conexion/modo", json={"modo": "simulacion"})
        assert r.status_code == 409
        assert "INVEST_LL_MODE" in r.json()["detail"]

    def test_una_config_estropeada_no_tumba_el_panel(self, cliente: Api) -> None:
        Path("config").mkdir()
        Path("config/panel.json").write_text("{roto", encoding="utf-8")

        assert cliente.get("/api/estado").json()["modo"]["nombre"] == "simulacion"
        cuerpo = cliente.get("/api/conexion").json()
        simulacion = next(m for m in cuerpo["modos"] if m["modo"] == "simulacion")
        assert any("no se puede leer" in q for q in simulacion["que_falta"])
        assert any("no se puede leer" in a for a in cliente.get("/api/inicio").json()["avisos"])
        assert cliente.put("/api/conexion/modo", json={"modo": "simulacion"}).status_code == 200
        assert cliente.get("/api/conexion").json()["modos"][0]["que_falta"] == []


class TestClaves:
    def test_guardar_en_el_almacen_y_nunca_devolverlas(
        self, cliente: Api, almacen_de_claves: AlmacenEnMemoria
    ) -> None:
        r = cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)

        assert r.status_code == 204
        assert credenciales.leer("pruebas") == credenciales.Claves(**PRUEBAS)
        assert len(almacen_de_claves.guardado) == 2
        estado = _sin_secretos(cliente.get("/api/conexion")).json()
        assert estado["redes"][0] == {
            "red": "pruebas",
            "claves_guardadas": True,
            "origen": "panel",
            "verificada": False,
        }
        for ruta in ("/api/estado", "/api/inicio", "/api/plan/hoy", "/api/cartera"):
            _sin_secretos(cliente.get(ruta))
        for fichero in Path().rglob("*"):
            if fichero.is_file():
                texto = fichero.read_bytes()
                assert all(s.encode() not in texto for s in SECRETOS), f"clave escrita en {fichero}"

    def test_las_reales_tienen_que_ser_distintas(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        misma = {"clave": PRUEBAS["clave"], "secreto": "otro-secreto-cualquiera"}
        r = _sin_secretos(cliente.put("/api/conexion/claves/real", json=misma))
        assert r.status_code == 422
        assert "distintas" in r.json()["detail"]
        assert credenciales.leer("real") is None

    def test_claves_demasiado_cortas_422(self, cliente: Api) -> None:
        r = cliente.put("/api/conexion/claves/pruebas", json={"clave": "x", "secreto": "y"})
        assert r.status_code == 422

    def test_borrar(self, cliente: Api) -> None:
        assert cliente.delete("/api/conexion/claves/pruebas").status_code == 404
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        assert cliente.delete("/api/conexion/claves/pruebas").status_code == 204
        assert credenciales.leer("pruebas") is None

    def test_borrar_las_del_modo_activo_vuelve_a_simulacion(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/modo", json={"modo": "pruebas"})
        assert _modo(cliente) == "pruebas"
        cliente.delete("/api/conexion/claves/pruebas")
        assert _modo(cliente) == "simulacion"


class TestProbar:
    def test_sin_claves(self, cliente: Api) -> None:
        cuerpo = cliente.post("/api/conexion/probar/pruebas").json()
        assert cuerpo["ok"] is False
        assert cuerpo["saldo"] == []

    def test_con_claves_lee_el_saldo_sin_red(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pedidas: list[tuple[str, credenciales.Claves]] = []

        def saldo(red: credenciales.Red, claves: credenciales.Claves) -> dict[str, Decimal]:
            pedidas.append((red, claves))
            return {"BTC": D(1), "USDT": D(10000), "LDBNB": D(0)}

        monkeypatch.setattr(rutas_conexion, "leer_saldo", saldo)
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)

        cuerpo = _sin_secretos(cliente.post("/api/conexion/probar/pruebas")).json()

        assert cuerpo["ok"] is True
        assert cuerpo["saldo"] == [
            {"moneda": "USDT", "cantidad": "10000"},
            {"moneda": "BTC", "cantidad": "1"},
        ]
        assert pedidas == [("pruebas", credenciales.Claves(**PRUEBAS))]

    def test_un_fallo_se_explica_en_llano(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rutas_conexion, "leer_saldo", _rechaza)
        cliente.put("/api/conexion/claves/real", json=REALES)

        cuerpo = _sin_secretos(cliente.post("/api/conexion/probar/real")).json()

        assert cuerpo["ok"] is False
        assert "HMAC-SHA256" in cuerpo["detalle"]
        assert "testnet.binance.vision" in cuerpo["detalle"]


class TestCambiarModo:
    def test_pruebas_sin_claves_422(self, cliente: Api) -> None:
        r = cliente.put("/api/conexion/modo", json={"modo": "pruebas"})
        assert r.status_code == 422
        assert "claves de la red de pruebas" in r.json()["detail"]
        assert not Path("config/panel.json").exists()

    def test_pruebas_con_claves_y_toda_la_api_lo_usa(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        r = _sin_secretos(cliente.put("/api/conexion/modo", json={"modo": "pruebas"}))

        assert r.status_code == 200
        assert r.json()["modo"] == "pruebas"
        assert "pruebas" in Path("config/panel.json").read_text(encoding="utf-8")
        assert cliente.get("/api/estado").json()["modo"]["nombre"] == "pruebas"
        assert cliente.get("/api/plan/hoy").json()["modo"] == "pruebas"
        assert cliente.get("/api/cartera/movimientos").json()["cartera"] == "pruebas"
        assert cliente.get("/api/inicio").json()["patrimonio"]["cartera"] == "pruebas"
        comprobar = cliente.post(
            "/api/ordenes/comprobar", json={"cantidad": "0.001", "escrito": "0.001"}
        )
        assert comprobar.json() == {"puede": True, "motivo": None}

    def test_activar_un_modo_prueba_antes_las_claves(
        self, cliente: Api, saldos_leidos: list[tuple[str, credenciales.Claves]]
    ) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        assert cliente.put("/api/conexion/modo", json={"modo": "pruebas"}).status_code == 200
        assert saldos_leidos == [("pruebas", credenciales.Claves(**PRUEBAS))]
        assert cliente.put("/api/conexion/modo", json={"modo": "simulacion"}).status_code == 200
        assert len(saldos_leidos) == 1, "volver a simulación no habla con nadie"

    def test_pruebas_con_claves_que_no_funcionan_422_en_llano(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rutas_conexion, "leer_saldo", _rechaza)
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)

        r = _sin_secretos(cliente.put("/api/conexion/modo", json={"modo": "pruebas"}))

        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert detalle.startswith("No se activa la red de pruebas: ")
        assert "rechaza las claves" in detalle and "HMAC-SHA256" in detalle
        assert '"code"' not in detalle
        assert _modo(cliente) == "simulacion"
        assert not Path("config/panel.json").exists()

    def test_real_con_claves_que_no_funcionan_no_se_activa(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/claves/real", json=REALES)
        _orden_de_pruebas_ejecutada()
        monkeypatch.setattr(rutas_conexion, "leer_saldo", _rechaza)

        r = _sin_secretos(
            cliente.put("/api/conexion/modo", json={"modo": "real", "confirmacion": "DINERO REAL"})
        )

        assert r.status_code == 422
        assert r.json()["detail"].startswith("No se activa dinero real: ")
        assert "testnet.binance.vision" in r.json()["detail"], "qué revisar, en llano"
        assert _modo(cliente) == "simulacion"

    def test_real_exige_la_confirmacion_tecleada(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/claves/real", json=REALES)
        _orden_de_pruebas_ejecutada()
        for confirmacion in (None, "dinero real", "SI"):
            r = cliente.put(
                "/api/conexion/modo", json={"modo": "real", "confirmacion": confirmacion}
            )
            assert r.status_code == 422
            assert "DINERO REAL" in r.json()["detail"]
        assert _modo(cliente) == "simulacion"

    def test_real_sin_haber_operado_en_pruebas_422(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/claves/real", json=REALES)
        r = cliente.put("/api/conexion/modo", json={"modo": "real", "confirmacion": "DINERO REAL"})
        assert r.status_code == 422
        assert "red de pruebas" in r.json()["detail"]

    def test_una_orden_rechazada_no_es_evidencia(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/real", json=REALES)
        peticion = OrderRequest(
            symbol="BTC/USDT", side=Side.BUY, quantity=D("0.001"), requested_at=datetime.now(UTC)
        )
        rechazada = OrderResult(
            request=peticion,
            status=OrderStatus.REJECTED,
            filled_quantity=D(0),
            fill_price=None,
            executed_at=None,
        )
        ExecutionLedger().record(rechazada, mode_name="pruebas")
        r = cliente.put("/api/conexion/modo", json={"modo": "real", "confirmacion": "DINERO REAL"})
        assert r.status_code == 422

    def test_real_con_todo_en_regla(self, cliente: Api) -> None:
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/claves/real", json=REALES)
        _orden_de_pruebas_ejecutada()

        r = _sin_secretos(
            cliente.put(
                "/api/conexion/modo", json={"modo": "real", "confirmacion": " DINERO REAL "}
            )
        )

        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["modo"] == "real"
        assert [c["ok"] for c in cuerpo["cerrojos_real"]] == [True, True, True, True]
        estado = cliente.get("/api/estado").json()["modo"]
        assert estado == {"nombre": "REAL", "envia_ordenes": True, "es_real": True}
        assert cliente.get("/api/cartera/movimientos").json()["cartera"] == "real"


class TestSaldo:
    def test_en_simulacion_409(self, cliente: Api) -> None:
        assert cliente.get("/api/saldo").status_code == 409

    def test_en_pruebas_con_el_broker_del_modo(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class ConSaldo(BrokerFalso):
            def balance(self) -> dict[str, Decimal]:
                return {"USDT": D(500), "BTC": D("0.5"), "XYZ": D(0)}

        modos: list[OperatingMode] = []

        def fabrica(modo: OperatingMode) -> ConSaldo:
            modos.append(modo)
            return ConSaldo(modo)

        monkeypatch.setattr(rutas_cartera, "broker_para", fabrica)
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/modo", json={"modo": "pruebas"})

        cuerpo = _sin_secretos(cliente.get("/api/saldo")).json()

        assert cuerpo["modo"] == "pruebas"
        assert [s["moneda"] for s in cuerpo["saldo"]] == ["USDT", "BTC"]
        assert isinstance(modos[0], Testnet)

    def test_un_fallo_del_exchange_se_explica_en_llano(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Caso real: con claves mal copiadas, Invertir enseñaba el JSON crudo de Binance
        ('binance {"code":-2014,"msg":"API-key format invalid."}'), y Probar la conexión, para
        el mismo fallo, ya lo explicaba en llano."""

        class SinSaldo(BrokerFalso):
            def balance(self) -> dict[str, Decimal]:
                raise ExecutionError(
                    'no se pudo leer el saldo: binance {"code":-2014,"msg":"API-key format invalid."}'
                )

        monkeypatch.setattr(rutas_cartera, "broker_para", SinSaldo)
        cliente.put("/api/conexion/claves/pruebas", json=PRUEBAS)
        cliente.put("/api/conexion/modo", json={"modo": "pruebas"})

        r = _sin_secretos(cliente.get("/api/saldo"))

        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert "rechaza las claves" in detalle and "HMAC-SHA256" in detalle
        assert '"code"' not in detalle
