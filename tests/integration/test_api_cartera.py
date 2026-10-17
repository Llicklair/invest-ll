"""La API del panel: Mi cartera y las órdenes.

Los invariantes que importan, los mismos que tenía el panel de Streamlit:

- El dinero sale como TEXTO (`"1100.0"`), nunca como float.
- Registrar un movimiento es contabilidad: escribe en el ledger y no toca ningún broker.
- En simulación, enviar una orden es un 403 y el broker ni se construye.
- Fuera de simulación hace falta teclear la cantidad exacta, y lo enviado queda en el registro.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.api import cartera as rutas_cartera
from invest_ll.live.broker import (
    Confirmation,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Side,
)
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import OperatingMode, Testnet

from .api_apoyo import Api, guardar

D = Decimal
REGISTRO_ORDENES = Path("ledger/orders.jsonl")
LEDGER_CARTERA = Path("portfolio/activities.jsonl")


class BrokerFalso:
    """Un broker de pruebas que apunta lo que le llega. No sale a ningún sitio."""

    def __init__(self, modo: OperatingMode, estado: OrderStatus = OrderStatus.FILLED) -> None:
        self._modo = modo
        self._estado = estado
        self.enviadas: list[OrderRequest] = []

    @property
    def mode(self) -> OperatingMode:
        return self._modo

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult:
        assert confirmation.authorises(request)
        self.enviadas.append(request)
        lleno = self._estado is OrderStatus.FILLED
        return OrderResult(
            request=request,
            status=self._estado,
            filled_quantity=request.quantity if lleno else D(0),
            fill_price=D("90000") if lleno else None,
            executed_at=request.requested_at,
            broker_reference="ref-1",
            commission=D("0.09") if lleno else None,
        )

    def balance(self) -> dict[str, Decimal]:
        return {}


def _prohibir_broker(monkeypatch: pytest.MonkeyPatch) -> list[OperatingMode]:
    """Sustituye la fábrica de brokers por una que apunta si alguien la llama."""
    llamadas: list[OperatingMode] = []

    def fabrica(modo: OperatingMode) -> BrokerFalso:
        llamadas.append(modo)
        return BrokerFalso(modo)

    monkeypatch.setattr(rutas_cartera, "broker_para", fabrica)
    return llamadas


def _compra(simbolo: str = "GLD", cantidad: str = "10", precio: str = "100") -> dict[str, object]:
    return {
        "tipo": "compra",
        "simbolo": simbolo,
        "fecha": "2026-09-01",
        "cantidad": cantidad,
        "precio": precio,
        "comision": "2",
    }


class TestCartera:
    def test_vacia_sin_movimientos(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/cartera").json()
        assert cuerpo["vacia"] is True
        assert cuerpo["error"] is None
        assert cuerpo["efectivo"] == "0"

    def test_valorada_con_el_ultimo_cierre_y_su_fecha(self, cliente: Api) -> None:
        guardar("GLD", [105.0, 110.0], hasta=date(2026, 9, 30))
        assert cliente.post("/api/cartera/movimientos", json=_compra()).status_code == 201

        cuerpo = cliente.get("/api/cartera").json()

        (posicion,) = cuerpo["abiertas"]
        assert posicion["precio_fecha"] == "2026-09-30"
        for campo in ("cantidad", "coste_medio", "invertido", "precio", "valor"):
            assert isinstance(posicion[campo], str), f"{campo} viaja como float"
        assert D(posicion["valor"]) == D("1100")
        assert D(posicion["invertido"]) == D("1002"), "la comision forma parte del coste"
        assert D(posicion["pnl_no_realizado"]) == D("98")
        assert D(cuerpo["valor_total"]) == D("1100")

    def test_sin_precio_el_total_no_se_inventa(self, cliente: Api) -> None:
        cliente.post("/api/cartera/movimientos", json=_compra("XYZ"))
        cuerpo = cliente.get("/api/cartera").json()
        assert cuerpo["abiertas"][0]["precio"] is None
        assert cuerpo["valor_total"] is None

    def test_una_retirada_tiene_pnl_realizado(self, cliente: Api) -> None:
        cliente.post("/api/cartera/movimientos", json=_compra())
        venta = {**_compra(precio="120"), "tipo": "venta", "fecha": "2026-09-20"}
        cliente.post("/api/cartera/movimientos", json=venta)

        cuerpo = cliente.get("/api/cartera").json()

        (retirada,) = cuerpo["retiradas"]
        assert retirada["dias"] == 19
        assert D(retirada["pnl_realizado"]) == D("196")  # 1198 cobrado - 1002 pagado
        assert cuerpo["abiertas"] == []

    def test_un_ledger_imposible_se_dice_en_vez_de_derivar(self, cliente: Api) -> None:
        venta = {**_compra(), "tipo": "venta"}
        assert cliente.post("/api/cartera/movimientos", json=venta).status_code == 201

        cuerpo = cliente.get("/api/cartera").json()

        assert cuerpo["error"].startswith(
            "Tu registro de movimientos cuenta una historia imposible"
        )
        assert "ledger" not in cuerpo["error"], "jerga prohibida en la interfaz principal"
        assert cuerpo["abiertas"] == []

    def test_comprar_sin_ingresos_se_avisa_en_llano_y_sin_comandos(self, cliente: Api) -> None:
        """El aviso de `derive` habla a la terminal ("-1,002.00 el 2026-09-01 ... Registralos
        con: invest-ll-portfolio cash deposit"); en el panel salía tal cual."""
        cliente.post("/api/cartera/movimientos", json=_compra())

        (aviso,) = cliente.get("/api/cartera").json()["avisos"]

        assert "1.002 €" in aviso and "1 sep 2026" in aviso
        assert "Anotar un movimiento" in aviso
        assert "invest-ll" not in aviso and "derivado" not in aviso and "2026-09-01" not in aviso

    def test_un_ingreso_del_mismo_dia_quita_el_aviso(self, cliente: Api) -> None:
        cliente.post("/api/cartera/movimientos", json=_compra())
        ingreso = {"tipo": "deposito", "fecha": "2026-09-01", "cantidad": "5000"}
        cliente.post("/api/cartera/movimientos", json=ingreso)

        assert cliente.get("/api/cartera").json()["avisos"] == []


class TestRegistrarMovimiento:
    def test_registrar_no_envia_ninguna_orden(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llamadas = _prohibir_broker(monkeypatch)

        r = cliente.post("/api/cartera/movimientos", json=_compra())

        assert r.status_code == 201
        assert len(r.json()["activity_id"]) == 16
        assert LEDGER_CARTERA.exists()
        assert llamadas == [], "registrar es contabilidad: no se construye ningun broker"
        assert not REGISTRO_ORDENES.exists(), "nada sale al registro de ordenes enviadas"
        assert '"source": "panel"' in LEDGER_CARTERA.read_text(encoding="utf-8")

    def test_un_deposito_va_sin_simbolo_y_a_precio_uno(self, cliente: Api) -> None:
        deposito = {"tipo": "deposito", "fecha": "2026-09-01", "cantidad": "5000"}
        assert cliente.post("/api/cartera/movimientos", json=deposito).status_code == 201
        assert cliente.get("/api/cartera").json()["efectivo"] == "5000"

    def test_una_compra_sin_precio_es_422(self, cliente: Api) -> None:
        sin_precio = {**_compra(), "precio": None}
        r = cliente.post("/api/cartera/movimientos", json=sin_precio)
        assert r.status_code == 422
        assert r.json()["detail"].startswith("No registrado")

    def test_una_cantidad_no_positiva_es_422_con_el_texto_del_dominio(self, cliente: Api) -> None:
        r = cliente.post("/api/cartera/movimientos", json=_compra(cantidad="0"))
        assert r.status_code == 422
        assert "cantidad no positiva" in r.json()["detail"]

    def test_registrar_dos_veces_lo_mismo_es_422(self, cliente: Api) -> None:
        assert cliente.post("/api/cartera/movimientos", json=_compra()).status_code == 201
        r = cliente.post("/api/cartera/movimientos", json=_compra())
        assert r.status_code == 422
        assert "ya esta registrado" in r.json()["detail"]


class TestOrdenesEnviadas:
    def test_vacio_sin_registro(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/ordenes").json()
        assert cuerpo["filas"] == []
        assert cuerpo["registro"] == "ledger/orders.jsonl"

    def test_la_mas_reciente_primero_y_lo_que_pide_atencion(self, cliente: Api) -> None:
        registro = ExecutionLedger()
        for i, estado in enumerate((OrderStatus.FILLED, OrderStatus.UNKNOWN)):
            peticion = OrderRequest(
                symbol="BTC/USDT",
                side=Side.BUY,
                quantity=D("0.001"),
                requested_at=datetime(2026, 10, 1 + i, tzinfo=UTC),
            )
            broker = BrokerFalso(Testnet(key="k", secret="s"), estado)
            resultado = broker.submit(
                peticion, confirmation=Confirmation.para(peticion, at=peticion.requested_at)
            )
            registro.record(resultado, mode_name="pruebas")

        cuerpo = cliente.get("/api/ordenes").json()

        assert [f["estado"] for f in cuerpo["filas"]] == ["unknown", "filled"]
        assert cuerpo["filas"][1]["pedida"] == "0.001"
        assert cuerpo["filas"][1]["precio"] == "90000"
        assert cuerpo["total"] == 2
        assert cuerpo["reales"] == 0
        assert len(cuerpo["atencion"]) == 1
        assert "ESTADO DESCONOCIDO" in cuerpo["atencion"][0]


class TestEnviar:
    def test_en_simulacion_es_403_y_no_toca_el_broker(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llamadas = _prohibir_broker(monkeypatch)
        orden = {"par": "BTC/USDT", "lado": "buy", "cantidad": "0.001", "escrito": "0.001"}

        r = cliente.post("/api/ordenes", json=orden)

        assert r.status_code == 403
        assert "simulacion" in r.json()["detail"]
        assert llamadas == []
        assert not REGISTRO_ORDENES.exists()

    def test_comprobar_explica_por_que_no(self, cliente: Api) -> None:
        cuerpo = cliente.post(
            "/api/ordenes/comprobar", json={"cantidad": "0.001", "escrito": "0.001"}
        ).json()
        assert cuerpo["puede"] is False
        assert "simulacion" in cuerpo["motivo"]

    @pytest.fixture
    def en_pruebas(self, cliente: Api, monkeypatch: pytest.MonkeyPatch) -> Api:
        """La API en red de pruebas. Depende de `cliente`, que limpia el modo al arrancar."""
        monkeypatch.setenv("INVEST_LL_MODE", "testnet")
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "clave")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "secreto")
        return cliente

    def test_comprobar_en_pruebas_exige_la_cantidad_escrita(self, en_pruebas: Api) -> None:
        mal = en_pruebas.post("/api/ordenes/comprobar", json={"cantidad": "0.001", "escrito": "si"})
        bien = en_pruebas.post(
            "/api/ordenes/comprobar", json={"cantidad": "0.001", "escrito": " 0.0010 "}
        )
        assert mal.json()["puede"] is False
        assert bien.json() == {"puede": True, "motivo": None}

    def test_lo_escrito_tiene_que_coincidir(
        self, en_pruebas: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llamadas = _prohibir_broker(monkeypatch)
        orden = {"par": "BTC/USDT", "lado": "buy", "cantidad": "0.001", "escrito": "0.01"}

        r = en_pruebas.post("/api/ordenes", json=orden)

        assert r.status_code == 422
        assert "no coincide" in r.json()["detail"]
        assert llamadas == []

    def test_en_pruebas_envia_y_lo_deja_en_el_registro(
        self, en_pruebas: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cliente = en_pruebas
        brokers: list[BrokerFalso] = []

        def fabrica(modo: OperatingMode) -> BrokerFalso:
            brokers.append(BrokerFalso(modo))
            return brokers[-1]

        monkeypatch.setattr(rutas_cartera, "broker_para", fabrica)
        orden = {"par": "BTC/USDT", "lado": "sell", "cantidad": "0.001", "escrito": "0.001"}

        r = cliente.post("/api/ordenes", json=orden)

        assert r.status_code == 200
        assert r.json() == {
            "estado": "filled",
            "descripcion": "BTC/USDT: ejecutada 0.001 a 90000.",
            "necesita_atencion": False,
            "modo": "pruebas",
        }
        (broker,) = brokers
        (enviada,) = broker.enviadas
        assert enviada.side is Side.SELL
        assert ExecutionLedger().entries()[0].mode_name == "pruebas"
