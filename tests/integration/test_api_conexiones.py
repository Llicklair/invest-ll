"""La API del panel v4: conectar varios exchanges, con los cerrojos de v2 generalizados.

El almacén de credenciales es el de memoria de la suite (`tests/conftest.py`) y los exchanges no
existen: cada test inyecta un `ConectorFalso` en el registro. Una comprobación recorre todo:
**ninguna respuesta ni ningún fichero lleva nunca una clave**.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from invest_ll.exchanges import registro
from invest_ll.exchanges.conector import Permisos
from invest_ll.exchanges.falso import ConectorFalso
from invest_ll.live.broker import OrderRequest, OrderResult, OrderStatus, Side
from invest_ll.live.ledger import ExecutionLedger

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from ..almacen_en_memoria import AlmacenEnMemoria
    from .api_apoyo import Api

D = Decimal
PRUEBAS = {"apiKey": "CLAVE-PRUEBAS-111", "secret": "SECRETO-PRUEBAS-222"}
REALES = {"apiKey": "CLAVE-REAL-333", "secret": "SECRETO-REAL-444"}
OKX_PRUEBAS = {**PRUEBAS, "password": "FRASE-PRUEBAS-555"}
CARTERA = "0x" + "ab" * 20
HL_PRUEBAS = {"walletAddress": CARTERA, "privateKey": "0x" + "1" * 64}
HL_REALES = {"walletAddress": CARTERA, "privateKey": "0x" + "2" * 64}
SECRETOS = (
    *PRUEBAS.values(),
    *REALES.values(),
    OKX_PRUEBAS["password"],
    HL_PRUEBAS["privateKey"],
    HL_REALES["privateKey"],
)
PUEDE_RETIRAR = Permisos(operar=True, retirar=True, texto="¡La clave PUEDE RETIRAR fondos!")
NO_SE_SABE = Permisos(operar=None, retirar=None, texto="No se pudieron leer los permisos.")


def _sin_secretos(r: httpx.Response) -> httpx.Response:
    for secreto in SECRETOS:
        assert secreto not in r.text, "una respuesta ha devuelto una clave"
    return r


def _falso(exchange: str, red: str = "pruebas", **kwargs: object) -> ConectorFalso:
    falso = ConectorFalso(exchange, red, saldo_inicial={"USDT": D(500), "BTC": D("0.01")})  # type: ignore[arg-type]
    for clave, valor in kwargs.items():
        setattr(falso, clave, valor)
    registro.inyectar(exchange, falso)
    return falso


def _estado(cliente: Api, exchange: str) -> dict[str, object]:
    cuerpo = _sin_secretos(cliente.get("/api/conexiones")).json()
    return next(e for e in cuerpo["exchanges"] if e["id"] == exchange)


def _guardar(cliente: Api, exchange: str, red: str, valores: dict[str, str]) -> httpx.Response:
    return _sin_secretos(
        cliente.put(f"/api/conexiones/{exchange}/claves/{red}", json={"valores": valores})
    )


def _orden_de_pruebas(exchange: str | None) -> None:
    cuando = datetime(2026, 10, 17, tzinfo=UTC)
    peticion = OrderRequest(
        symbol="BTC/USDT", side=Side.BUY, quantity=D("0.001"), requested_at=cuando
    )
    ExecutionLedger().record(
        OrderResult(
            request=peticion,
            status=OrderStatus.FILLED,
            filled_quantity=D("0.001"),
            fill_price=D(60000),
            executed_at=cuando,
        ),
        mode_name="pruebas",
        exchange=exchange,
        bot="bot-de-prueba",
    )


def _activar(
    cliente: Api, exchange: str, red: str, confirmacion: str | None = None
) -> httpx.Response:
    cuerpo: dict[str, str] = {"red": red}
    if confirmacion is not None:
        cuerpo["confirmacion"] = confirmacion
    return _sin_secretos(cliente.post(f"/api/conexiones/{exchange}/activar", json=cuerpo))


class TestEstado:
    def test_de_entrada_los_seis_sin_conectar(self, cliente: Api) -> None:
        cuerpo = _sin_secretos(cliente.get("/api/conexiones")).json()
        assert [e["id"] for e in cuerpo["exchanges"]] == [
            "binance",
            "hyperliquid",
            "bybit",
            "okx",
            "kraken",
            "coinbase",
        ]
        assert {e["activo"] for e in cuerpo["exchanges"]} == {"sin_conectar"}
        kraken = _estado(cliente, "kraken")
        assert [r["red"] for r in kraken["redes"]] == ["real"]  # type: ignore[index]
        bybit = _estado(cliente, "bybit")
        assert [r["red"] for r in bybit["redes"]] == ["pruebas", "real"]  # type: ignore[index]
        assert len(bybit["que_falta_real"]) == 2  # type: ignore[arg-type]

    def test_el_bloque_del_conector_con_claude(self, cliente: Api) -> None:
        mcp = cliente.get("/api/conexiones").json()["mcp"]
        assert Path(mcp["comando"]).is_absolute()
        assert Path(mcp["comando"]).stem == "invest-ll-mcp"
        assert ".venv" in mcp["comando"] or "Scripts" in mcp["comando"] or "bin" in mcp["comando"]
        bloque = json.loads(mcp["bloque_json"])
        assert bloque["mcpServers"]["invest-ll"]["command"] == mcp["comando"]
        assert bloque["mcpServers"]["invest-ll"]["args"] == mcp["argumentos"] == []
        assert "NO puede activar el dinero real" in mcp["nota"]
        assert "tocar tus claves" in mcp["nota"]

    def test_disponibles_con_sus_campos_y_pasos(self, cliente: Api) -> None:
        lista = cliente.get("/api/conexiones/disponibles").json()
        por_id = {e["id"]: e for e in lista}
        assert [c["clave"] for c in por_id["okx"]["campos"]] == ["apiKey", "secret", "password"]
        assert [c["clave"] for c in por_id["hyperliquid"]["campos"]] == [
            "walletAddress",
            "privateKey",
        ]
        assert [c["secreto"] for c in por_id["hyperliquid"]["campos"]] == [False, True]
        assert por_id["kraken"]["tiene_pruebas"] is False
        assert por_id["kraken"]["como_conseguir_pruebas"] == []
        assert "ficticio" in por_id["coinbase"]["aviso"]
        assert any("retir" in paso.lower() for paso in por_id["binance"]["como_conseguir_real"])

    def test_un_exchange_que_no_existe(self, cliente: Api) -> None:
        r = cliente.post("/api/conexiones/ftx/probar/real")
        assert r.status_code == 404
        assert "binance" in r.json()["detail"]


class TestClaves:
    def test_guardar_y_borrar(self, cliente: Api, almacen_de_claves: AlmacenEnMemoria) -> None:
        assert _guardar(cliente, "okx", "pruebas", OKX_PRUEBAS).status_code == 204
        assert ("invest-ll", "okx-pruebas:password") in almacen_de_claves.guardado
        red = _estado(cliente, "okx")["redes"][0]  # type: ignore[index]
        assert (red["claves_guardadas"], red["origen"]) == (True, "panel")
        assert (
            _sin_secretos(cliente.delete("/api/conexiones/okx/claves/pruebas")).status_code == 204
        )
        r = cliente.delete("/api/conexiones/okx/claves/pruebas")
        assert r.status_code == 404
        assert "No había claves de pruebas de OKX" in r.json()["detail"]

    def test_falta_un_campo(self, cliente: Api) -> None:
        r = _guardar(cliente, "okx", "pruebas", PRUEBAS)
        assert r.status_code == 422
        assert r.json()["detail"] == "Falta «Frase de contraseña (passphrase)»."

    def test_las_reales_tienen_que_ser_distintas(self, cliente: Api) -> None:
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        r = _guardar(cliente, "bybit", "real", {**REALES, "apiKey": PRUEBAS["apiKey"]})
        assert r.status_code == 422
        assert "distintas de las de pruebas" in r.json()["detail"]

    def test_sin_red_de_pruebas_no_hay_claves_de_pruebas(self, cliente: Api) -> None:
        r = _guardar(cliente, "kraken", "pruebas", PRUEBAS)
        assert r.status_code == 422
        assert "Kraken no tiene red de pruebas" in r.json()["detail"]

    def test_las_del_entorno_mandan_en_binance(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INVEST_LL_TESTNET_KEY", "CLAVE-PRUEBAS-111")
        monkeypatch.setenv("INVEST_LL_TESTNET_SECRET", "SECRETO-PRUEBAS-222")
        red = _estado(cliente, "binance")["redes"][0]  # type: ignore[index]
        assert (red["claves_guardadas"], red["origen"]) == (True, "entorno")
        assert _guardar(cliente, "binance", "pruebas", PRUEBAS).status_code == 409
        assert cliente.delete("/api/conexiones/binance/claves/pruebas").status_code == 409

    def test_binance_ve_las_claves_que_se_guardaron_en_v2(self, cliente: Api) -> None:
        r = cliente.put(
            "/api/conexion/claves/pruebas", json={"clave": "CLAVE-V2-123", "secreto": "SECRETO-V2"}
        )
        assert r.status_code == 204
        red = _estado(cliente, "binance")["redes"][0]  # type: ignore[index]
        assert (red["claves_guardadas"], red["origen"]) == (True, "panel")


class TestProbar:
    def test_sin_claves_no_hay_nada_que_probar(self, cliente: Api) -> None:
        r = cliente.post("/api/conexiones/bybit/probar/pruebas")
        assert r.status_code == 404
        assert "pégalas primero" in r.json()["detail"]

    def test_lee_saldo_y_permisos_y_lo_apunta(self, cliente: Api) -> None:
        falso = _falso("bybit")
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        cuerpo = _sin_secretos(cliente.post("/api/conexiones/bybit/probar/pruebas")).json()
        assert cuerpo["ok"] is True
        assert [s["moneda"] for s in cuerpo["saldo"]] == ["USDT", "BTC"]
        assert "no puede retirar" in cuerpo["permisos"]
        assert "testnet.bybit.com" in cuerpo["detalle"]
        assert falso.creadas == []  # probar no envía nada
        red = _estado(cliente, "bybit")["redes"][0]  # type: ignore[index]
        assert red["comprobado"] is not None
        assert red["puede_retirar"] is False

    def test_si_falla_lo_dice_en_llano(self, cliente: Api) -> None:
        _falso("bybit", caido="Bybit rechaza las claves (leer el saldo).")
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        cuerpo = _sin_secretos(cliente.post("/api/conexiones/bybit/probar/pruebas")).json()
        assert cuerpo["ok"] is False
        assert "rechaza las claves" in cuerpo["detalle"]
        assert _estado(cliente, "bybit")["redes"][0]["comprobado"] is None  # type: ignore[index]


class TestActivar:
    def test_pruebas_prueba_la_conexion_y_activa(self, cliente: Api) -> None:
        falso = _falso("bybit")
        assert _activar(cliente, "bybit", "pruebas").status_code == 422
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        r = _activar(cliente, "bybit", "pruebas")
        assert r.status_code == 200
        assert r.json()["activo"] == "pruebas"
        assert registro.conector("bybit", "pruebas") is falso
        with pytest.raises(Exception, match="no está activo con dinero real"):
            registro.conector("bybit", "real")

    def test_si_las_claves_no_funcionan_no_se_activa(self, cliente: Api) -> None:
        _falso("bybit", caido="No hay conexión con Bybit.")
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        r = _activar(cliente, "bybit", "pruebas")
        assert r.status_code == 422
        assert "No se activa la red de pruebas en Bybit" in r.json()["detail"]
        assert _estado(cliente, "bybit")["activo"] == "sin_conectar"

    def test_real_pide_dinero_real_tecleado(self, cliente: Api) -> None:
        r = _activar(cliente, "kraken", "real", "dinero real")
        assert r.status_code == 422
        assert "DINERO REAL" in r.json()["detail"]

    def test_real_exige_evidencia_de_pruebas_de_ese_exchange(self, cliente: Api) -> None:
        _falso("bybit", red_="real")
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        _guardar(cliente, "bybit", "real", REALES)
        _orden_de_pruebas("binance")  # de otro exchange: no cuenta
        r = _activar(cliente, "bybit", "real", "DINERO REAL")
        assert r.status_code == 422
        assert "orden en la red de pruebas de Bybit" in r.json()["detail"]

        _orden_de_pruebas("bybit")
        r = _activar(cliente, "bybit", "real", "DINERO REAL")
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["activo"] == "real"
        assert cuerpo["que_falta_real"] == []
        assert [red["verificada"] for red in cuerpo["redes"]] == [True, False]
        assert registro.conector("bybit", "real").exchange == "bybit"

    def test_una_clave_que_puede_retirar_no_activa_real(self, cliente: Api) -> None:
        _falso("coinbase", red_="real", permisos_=PUEDE_RETIRAR)
        _guardar(
            cliente,
            "coinbase",
            "real",
            {"apiKey": "organizations/o/apiKeys/k", "secret": "-----BEGIN EC PRIVATE KEY-----x"},
        )
        r = _activar(cliente, "coinbase", "real", "DINERO REAL")
        assert r.status_code == 422
        assert "puede retirar fondos" in r.json()["detail"]
        estado = _estado(cliente, "coinbase")
        assert estado["activo"] == "sin_conectar"
        assert estado["redes"][0]["puede_retirar"] is True  # type: ignore[index]
        assert any("puede retirar" in f for f in estado["que_falta_real"])  # type: ignore[union-attr]

    def test_si_no_se_sabe_si_puede_retirar_tampoco(self, cliente: Api) -> None:
        _falso("kraken", red_="real", permisos_=NO_SE_SABE)
        _guardar(cliente, "kraken", "real", REALES)
        r = _activar(cliente, "kraken", "real", "DINERO REAL")
        assert r.status_code == 422
        assert "No se pudo comprobar que la clave no pueda retirar" in r.json()["detail"]

    def test_sin_red_de_pruebas_va_directo_a_real(self, cliente: Api) -> None:
        _falso("kraken", red_="real")
        _guardar(cliente, "kraken", "real", REALES)
        assert _activar(cliente, "kraken", "pruebas").status_code == 422
        r = _activar(cliente, "kraken", "real", "DINERO REAL")
        assert r.status_code == 200
        assert r.json()["activo"] == "real"

    def test_hyperliquid_con_la_api_wallet(self, cliente: Api) -> None:
        _falso("hyperliquid")
        assert _guardar(cliente, "hyperliquid", "pruebas", HL_PRUEBAS).status_code == 204
        # La misma cartera en las dos redes es lo normal: lo que cambia es la API wallet.
        assert _guardar(cliente, "hyperliquid", "real", HL_REALES).status_code == 204
        assert _activar(cliente, "hyperliquid", "pruebas").json()["activo"] == "pruebas"

    def test_otras_claves_en_la_red_activa_la_desconectan(self, cliente: Api) -> None:
        _falso("kraken", red_="real")
        _guardar(cliente, "kraken", "real", REALES)
        _activar(cliente, "kraken", "real", "DINERO REAL")
        assert _estado(cliente, "kraken")["activo"] == "real"
        _guardar(cliente, "kraken", "real", REALES)  # las mismas: no cambia nada
        assert _estado(cliente, "kraken")["activo"] == "real"
        _guardar(cliente, "kraken", "real", {**REALES, "secret": "OTRO-SECRETO-999"})
        assert _estado(cliente, "kraken")["activo"] == "sin_conectar"

    def test_borrar_las_claves_de_la_red_activa_la_desconecta(self, cliente: Api) -> None:
        _falso("bybit")
        _guardar(cliente, "bybit", "pruebas", PRUEBAS)
        _activar(cliente, "bybit", "pruebas")
        cliente.delete("/api/conexiones/bybit/claves/pruebas")
        assert _estado(cliente, "bybit")["activo"] == "sin_conectar"


class TestMercados:
    def test_los_pares_de_contado(self, cliente: Api) -> None:
        _falso("okx", red_="real")
        cuerpo = cliente.get("/api/conexiones/okx/mercados").json()
        assert cuerpo["exchange"] == "okx"
        assert cuerpo["red"] == "real"
        btc = next(m for m in cuerpo["mercados"] if m["par"] == "BTC/USDT")
        assert btc["nombre"] == "Bitcoin"
        assert D(btc["minimo_importe"]) == D(5)
        assert D(btc["paso_cantidad"]) == D("0.00001")

    def test_sin_red_de_pruebas(self, cliente: Api) -> None:
        r = cliente.get("/api/conexiones/coinbase/mercados", params={"red": "pruebas"})
        assert r.status_code == 422

    def test_si_el_exchange_no_contesta_se_dice(self, cliente: Api) -> None:
        _falso("okx", caido="No hay conexión con OKX (leer sus mercados).")
        r = cliente.get("/api/conexiones/okx/mercados")
        assert r.status_code == 422
        assert "No hay conexión con OKX" in r.json()["detail"]


def test_ningun_fichero_lleva_las_claves(cliente: Api) -> None:
    """Después de guardar, probar y activar: ni la configuración ni el registro las llevan."""
    _falso("bybit")
    _guardar(cliente, "bybit", "pruebas", PRUEBAS)
    _activar(cliente, "bybit", "pruebas")
    _falso("okx")
    _guardar(cliente, "okx", "pruebas", OKX_PRUEBAS)
    cliente.post("/api/conexiones/okx/probar/pruebas")
    ficheros = [p for p in Path().rglob("*") if p.is_file()]
    assert ficheros, "no se escribió nada: el test pasaría por vacío"
    for fichero in ficheros:
        texto = fichero.read_text(encoding="utf-8", errors="replace")
        for secreto in SECRETOS:
            assert secreto not in texto, f"{fichero} lleva una clave"
