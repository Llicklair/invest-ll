"""La API del panel: cabecera y pestaña Mercado.

Lo que se prueba es lo que el panel de Streamlit garantizaba y no puede perderse por el camino:
el modo en la cabecera, cada cifra de mercado con su fecha, `None` (no 0%) cuando no hay
histórico suficiente, y que lo que toca la red pase por funciones que aquí se sustituyen.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from invest_ll.api import mercado
from invest_ll.fetch.live import LiveDataError, LiveQuote
from invest_ll.portfolio.triggers import TriggerStore

from .api_apoyo import BTC, GLD, TLT, Api, guardar, subida


class TestEstado:
    def test_sin_nada_arranca_en_simulacion_y_lo_dice(self, cliente: Api) -> None:
        r = cliente.get("/api/estado")
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["modo"] == {"nombre": "simulacion", "envia_ordenes": False, "es_real": False}
        assert cuerpo["activos"] == []
        assert cuerpo["pausa"] is None
        assert cuerpo["reserva"] is None

    def test_lista_los_activos_con_su_id_y_sus_fechas(self, cliente: Api) -> None:
        guardar("GLD", subida(30), hasta=date(2026, 9, 30))
        guardar("BTC/USDT", subida(30), proveedor="ccxt-binance", hasta=date(2026, 9, 30))

        activos = {a["id"]: a for a in cliente.get("/api/estado").json()["activos"]}

        assert set(activos) == {GLD, BTC}, "el simbolo conserva su '/' dentro del id"
        assert activos[BTC]["is_crypto"] is True
        assert activos[GLD]["is_crypto"] is False
        assert activos[GLD]["hasta"] == "2026-09-30"

    def test_la_pausa_va_en_la_cabecera(self, cliente: Api) -> None:
        TriggerStore().halt(reason="mercado raro", at=datetime(2026, 10, 1, tzinfo=UTC))
        assert "mercado raro" in cliente.get("/api/estado").json()["pausa"]

    def test_un_modo_mal_configurado_es_un_422_con_su_texto(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INVEST_LL_MODE", "testnet")  # sin credenciales
        r = cliente.get("/api/estado")
        assert r.status_code == 422
        assert "INVEST_LL_TESTNET_KEY" in r.json()["detail"]


class TestRendimiento:
    def test_separa_bolsa_y_cripto(self, cliente: Api) -> None:
        guardar("GLD", subida(300), hasta=date(2026, 9, 30))
        guardar("BTC/USDT", subida(300), proveedor="ccxt-binance")

        cuerpo = cliente.get("/api/mercado/rendimiento").json()

        assert [f["activo"] for f in cuerpo["bolsa"]] == ["GLD"]
        assert [f["activo"] for f in cuerpo["cripto"]] == ["BTC/USDT"]
        fila = cuerpo["bolsa"][0]
        assert fila["que_es"] == "Oro"
        assert fila["datos_hasta"] == "2026-09-30", "sin fecha, un historico parado parece de hoy"
        assert len(fila["sparkline"]) == 63

    def test_sin_historico_suficiente_es_null_no_cero(self, cliente: Api) -> None:
        guardar("GLD", subida(30))
        fila = cliente.get("/api/mercado/rendimiento").json()["bolsa"][0]
        assert fila["var_1a"] is None
        assert fila["var_5a"] is None
        assert fila["var_1d"] is not None


class TestSerie:
    def test_el_tramo_recorta_y_la_fecha_viaja(self, cliente: Api) -> None:
        guardar("BTC/USDT", subida(400), proveedor="ccxt-binance", hasta=date(2026, 9, 30))

        tres_meses = cliente.get(
            "/api/mercado/serie", params={"symbol": "BTC/USDT", "tramo": "3m"}
        ).json()
        todo = cliente.get("/api/mercado/serie", params={"symbol": "BTC/USDT", "tramo": "todo"})

        assert tres_meses["sesiones"] == 63
        assert tres_meses["hasta"] == "2026-09-30"
        assert tres_meses["puntos"][-1]["valor"] == 499.0
        assert todo.json()["sesiones"] == 400

    def test_un_simbolo_sin_historico_es_404(self, cliente: Api) -> None:
        r = cliente.get("/api/mercado/serie", params={"symbol": "NOEXISTE"})
        assert r.status_code == 404
        assert "NOEXISTE" in r.json()["detail"]

    def test_un_tramo_desconocido_lo_rechaza_el_contrato(self, cliente: Api) -> None:
        guardar("GLD", subida(30))
        r = cliente.get("/api/mercado/serie", params={"symbol": "GLD", "tramo": "2s"})
        assert r.status_code == 422


class TestComparacion:
    def test_todos_empiezan_en_100(self, cliente: Api) -> None:
        guardar("GLD", subida(100, desde=200))
        guardar("TLT", subida(100, desde=50))

        r = cliente.get("/api/mercado/comparacion", params={"activos": [GLD, TLT]})

        assert r.status_code == 200
        primeros: dict[str, float] = {}
        for punto in r.json()["puntos"]:
            primeros.setdefault(punto["activo"], punto["valor"])
        assert primeros == {"GLD": 100.0, "TLT": 100.0}

    def test_la_ventana_recorta(self, cliente: Api) -> None:
        guardar("GLD", subida(100))
        r = cliente.get("/api/mercado/comparacion", params={"activos": [GLD], "ventana": "1 mes"})
        assert len(r.json()["puntos"]) == 21

    def test_una_ventana_desconocida_es_422(self, cliente: Api) -> None:
        guardar("GLD", subida(100))
        r = cliente.get("/api/mercado/comparacion", params={"activos": [GLD], "ventana": "2 dias"})
        assert r.status_code == 422
        assert "1 mes" in r.json()["detail"]

    def test_un_id_inexistente_es_404(self, cliente: Api) -> None:
        r = cliente.get("/api/mercado/comparacion", params={"activos": ["yfinance:XXX:DAY_1"]})
        assert r.status_code == 404

    def test_un_id_mal_formado_es_422(self, cliente: Api) -> None:
        r = cliente.get("/api/mercado/comparacion", params={"activos": ["GLD"]})
        assert r.status_code == 422


class TestDatos:
    def test_ultimo_cierre_con_su_fecha_y_los_desfasados(self, cliente: Api) -> None:
        guardar("GLD", [100.0, 110.0])
        guardar("TLT", [50.0, 50.0], hasta=datetime.now(UTC).date() - timedelta(days=60))

        cuerpo = cliente.get("/api/mercado/datos").json()

        filas = {f["activo"]: f for f in cuerpo["filas"]}
        assert filas["GLD"]["ultimo_cierre"] == 110.0
        assert filas["GLD"]["variacion"] == pytest.approx(0.1)
        assert filas["GLD"]["descargado"] == "2026-10-01"
        assert cuerpo["desfasados"] == ["TLT"]

    def test_sin_historicos_no_hay_filas(self, cliente: Api) -> None:
        assert cliente.get("/api/mercado/datos").json() == {"filas": [], "desfasados": []}


def _cotizacion(simbolo: str, precio: float) -> LiveQuote:
    return LiveQuote(
        symbol=simbolo,
        price=precio,
        change_24h_pct=1.5,
        volume_24h=12_345_678.0,
        source="prueba",
        fetched_at=datetime(2026, 10, 17, tzinfo=UTC),
    )


class TestCotizaciones:
    def test_foto_fechada_y_marca_lo_ya_descargado(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        guardar("BTC/USDT", subida(30), proveedor="ccxt-binance")
        monkeypatch.setattr(
            mercado,
            "pedir_cripto",
            lambda: [_cotizacion("BTC/USDT", 90_000.0), _cotizacion("SOL/USDT", 150.0)],
        )
        monkeypatch.setattr(mercado, "pedir_bolsa", lambda: [_cotizacion("AAPL", 250.0)])

        cuerpo = cliente.post("/api/mercado/cotizaciones").json()

        assert cuerpo["at"]
        assert cuerpo["errores"] == []
        cripto = {c["activo"]: c for c in cuerpo["cripto"]}
        assert cripto["BTC/USDT"]["descargado"] is True
        assert cripto["SOL/USDT"]["descargado"] is False
        assert cripto["SOL/USDT"]["volumen_24h_m"] == 12.35
        assert cuerpo["bolsa"][0]["activo"] == "AAPL"

    def test_si_la_red_falla_se_dice_y_el_resto_sigue(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sin_red() -> list[LiveQuote]:
            raise LiveDataError("binance no respondio: timeout")

        monkeypatch.setattr(mercado, "pedir_cripto", sin_red)
        monkeypatch.setattr(mercado, "pedir_bolsa", lambda: [_cotizacion("AAPL", 250.0)])

        cuerpo = cliente.post("/api/mercado/cotizaciones").json()

        assert cuerpo["cripto"] == []
        assert cuerpo["errores"] == ["Cripto: binance no respondio: timeout"]
        assert len(cuerpo["bolsa"]) == 1


class _FetchFalso:
    def __init__(self, bien: bool = True, salida: str = "") -> None:
        self.llamadas: list[list[str]] = []
        self.bien = bien
        self.salida = salida

    def __call__(self, argumentos: list[str]) -> tuple[bool, str]:
        self.llamadas.append(argumentos)
        return self.bien, self.salida


class TestDescargar:
    def test_descarga_el_historico_completo_sin_uv_run(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        falso = _FetchFalso()
        monkeypatch.setattr(mercado, "ejecutar_fetch", falso)

        r = cliente.post("/api/mercado/descargar", json={"symbol": "SOL/USDT", "mercado": "crypto"})

        assert r.status_code == 200
        assert r.json()["ok"] is True
        (argumentos,) = falso.llamadas
        assert argumentos[1:3] == ["-m", "invest_ll.cli_fetch"]
        assert "uv" not in argumentos
        assert argumentos[argumentos.index("--start") + 1] == "2015-01-01"
        assert argumentos[-2:] == ["--exchange", "binance"]

    def test_un_fallo_trae_su_motivo(self, cliente: Api, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mercado, "ejecutar_fetch", _FetchFalso(False, "activo desconocido"))
        cuerpo = cliente.post(
            "/api/mercado/descargar", json={"symbol": "ZZZ", "mercado": "equity"}
        ).json()
        assert cuerpo["ok"] is False
        assert "activo desconocido" in cuerpo["detalle"]

    def test_lo_ya_descargado_no_se_vuelve_a_bajar(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        guardar("GLD", subida(30))
        falso = _FetchFalso()
        monkeypatch.setattr(mercado, "ejecutar_fetch", falso)

        cuerpo = cliente.post(
            "/api/mercado/descargar", json={"symbol": "GLD", "mercado": "equity"}
        ).json()

        assert cuerpo["ok"] is True
        assert "ya tiene historico" in cuerpo["detalle"]
        assert falso.llamadas == []

    @pytest.mark.parametrize("simbolo", ["", "  ", "--help"])
    def test_un_simbolo_que_no_lo_es_es_422(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch, simbolo: str
    ) -> None:
        falso = _FetchFalso()
        monkeypatch.setattr(mercado, "ejecutar_fetch", falso)
        r = cliente.post("/api/mercado/descargar", json={"symbol": simbolo, "mercado": "equity"})
        assert r.status_code == 422
        assert falso.llamadas == []


class TestActualizar:
    def test_sin_procedencia_se_salta_no_se_adivina(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        guardar("GLD", subida(30))
        guardar("TLT", subida(30), procedencia=False)
        falso = _FetchFalso(salida="")
        monkeypatch.setattr(mercado, "ejecutar_fetch", falso)

        cuerpo = cliente.post("/api/mercado/actualizar").json()

        assert cuerpo["saltados"] == ["TLT"]
        assert [r["symbol"] for r in cuerpo["resultados"]] == ["GLD"]
        assert cuerpo["resultados"][0]["ok"] is True
        (argumentos,) = falso.llamadas
        assert "GLD" in argumentos and "--market" in argumentos
