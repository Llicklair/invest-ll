"""La API del panel: Estimado vs real, Investigación y Chat.

El chat gasta cuota de verdad, así que aquí la sesión se sustituye por una con un `runner` falso:
lo que se prueba es que el contexto se reconstruye en cada pregunta, que el historial se conserva
por sesión y que una sesión que no existe es un 404, no una conversación nueva disfrazada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from invest_ll.api import chat as rutas_chat
from invest_ll.api import investigacion as rutas_investigacion
from invest_ll.chat.session import ChatSession, ChatUnavailableError
from invest_ll.quant.paper import record
from invest_ll.tracking.models import Forecast, Holding, Outcome
from invest_ll.tracking.store import ForecastStore

from ..quant.builders import panel_from_closes
from .api_apoyo import Api

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.quant.panel import Panel

D = Decimal


class TestSeguimiento:
    def test_sin_estimaciones(self, cliente: Api) -> None:
        assert cliente.get("/api/seguimiento").json() == {
            "evaluadas": 0,
            "pendientes": 0,
            "sobreestimaciones": 0,
            "tendencia": None,
            "filas": [],
        }

    def test_los_fallos_siguen_en_la_tabla(self, cliente: Api) -> None:
        almacen = ForecastStore()
        cartera = (Holding(symbol="GLD", quantity=D(10)),)
        for i, (estimado, real) in enumerate(((D(1100), D(1000)), (D(1200), D(1300)))):
            prevision = Forecast(
                issued_at=datetime(2026, 1, 1 + i, tzinfo=UTC),
                horizon_days=30,
                portfolio=cartera,
                expected_value=estimado,
                basis="prueba",
            )
            almacen.append(prevision)
            almacen.record_outcome(
                Outcome(
                    forecast_id=prevision.forecast_id,
                    measured_at=datetime(2026, 3, 1, tzinfo=UTC),
                    actual_value=real,
                )
            )
        almacen.append(
            Forecast(
                issued_at=datetime(2026, 9, 1, tzinfo=UTC),
                horizon_days=90,
                portfolio=cartera,
                expected_value=D(1500),
                basis="pendiente",
            )
        )

        cuerpo = cliente.get("/api/seguimiento").json()

        assert cuerpo["evaluadas"] == 2
        assert cuerpo["pendientes"] == 1
        assert cuerpo["sobreestimaciones"] == 1
        assert cuerpo["tendencia"] == "no muestra un sesgo claro"
        assert [f["error"] for f in cuerpo["filas"]] == ["-100", "100"]


def _panel(dias: int = 150) -> Panel:
    rng = np.random.default_rng(7)
    cierres = {
        s: list(100 * np.cumprod(1 + rng.normal(0.001, 0.03, size=dias)))
        for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
    }
    return panel_from_closes(cierres)


class TestInvestigacion:
    def test_sin_datos_lo_dice_y_como_conseguirlos(self, cliente: Api) -> None:
        cuerpo = cliente.get("/api/investigacion").json()
        assert cuerpo["disponible"] is False
        assert "invest-ll-quant download" in cuerpo["motivo"]
        assert cuerpo["objetivo"] == []
        assert cuerpo["estudio"] is None

    def test_objetivo_de_hoy_y_prueba_hacia_delante(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        panel = _panel()
        klines = Path("data/market/binance-universe/klines_1d.parquet")
        klines.parent.mkdir(parents=True)
        klines.write_bytes(b"")

        def cargar(_: Path) -> Panel:
            return panel  # el parquet de verdad pesa cientos de MB; aqui basta su forma

        monkeypatch.setattr(rutas_investigacion, "cargar_panel", cargar)
        # Un registro diez dias antes del final: hay dias despues para medir.
        anterior = panel.slice_rows(0, len(panel) - 10)
        pesos = np.zeros(len(panel.symbols))
        pesos[panel.column("ETHUSDT")] = 0.5
        record(anterior, pesos, "prueba", ledger=Path("paper/momentum.jsonl"))

        cuerpo = cliente.get("/api/investigacion", params={"capital": 2000}).json()

        assert cuerpo["disponible"] is True
        assert cuerpo["ultimo_dato"] == panel.date_at(len(panel) - 1).isoformat()
        assert cuerpo["dias_desfase"] > 2, "datos de 2024: el desfase viaja para avisar"
        objetivo = cuerpo["objetivo"]
        assert objetivo[-1]["moneda"] == "liquidez"
        assert sum(f["peso"] for f in objetivo) == pytest.approx(1.0)
        assert sum(f["usdt"] for f in objetivo) == pytest.approx(2000.0)
        pruebas = {p["clave"]: p for p in cuerpo["prueba_adelante"]}
        assert set(pruebas) == {"preregistered", "filtered", "btc-trend"}
        prerregistrada = pruebas["preregistered"]
        assert prerregistrada["registros"] == 1
        assert prerregistrada["valor_final"] is not None
        assert prerregistrada["mantener_btc"] is not None
        assert prerregistrada["nota"] is None
        assert "Todavía no hay registros" in pruebas["filtered"]["nota"]

    def test_el_ultimo_estudio(self, cliente: Api) -> None:
        assert cliente.get("/api/investigacion/estudio").status_code == 404
        informe = Path("research/runs/2026-10-01/report.html")
        informe.parent.mkdir(parents=True)
        informe.write_text("<h1>Estudio</h1>", encoding="utf-8")

        r = cliente.get("/api/investigacion/estudio")

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.text == "<h1>Estudio</h1>"
        estudio = cliente.get("/api/investigacion").json()["estudio"]
        assert estudio["ruta"] == "research/runs/2026-10-01/report.html"


class _ClaudeFalso:
    def __init__(self, falla: bool = False) -> None:
        self.prompts: list[str] = []
        self.falla = falla

    def __call__(self, prompt: str) -> str:
        if self.falla:
            raise ChatUnavailableError("no se encontro 'claude' en el PATH")
        self.prompts.append(prompt)
        return f"respuesta {len(self.prompts)}"


class TestChat:
    @pytest.fixture
    def claude(self, monkeypatch: pytest.MonkeyPatch) -> _ClaudeFalso:
        falso = _ClaudeFalso()
        monkeypatch.setattr(rutas_chat, "nueva_sesion", lambda: ChatSession(runner=falso))
        return falso

    def test_la_primera_respuesta_trae_la_sesion_y_la_segunda_la_continua(
        self, cliente: Api, claude: _ClaudeFalso
    ) -> None:
        primera = cliente.post("/api/chat", json={"pregunta": "que tengo?"}).json()
        segunda = cliente.post(
            "/api/chat", json={"pregunta": "y ahora?", "sesion": primera["sesion"]}
        ).json()

        assert primera["respuesta"] == "respuesta 1"
        assert segunda["sesion"] == primera["sesion"]
        assert [(m["autor"], m["texto"]) for m in segunda["historial"]] == [
            ("operador", "que tengo?"),
            ("claude", "respuesta 1"),
            ("operador", "y ahora?"),
            ("claude", "respuesta 2"),
        ]
        assert "CARTERA: vacia" in claude.prompts[0], "el contexto real va en cada pregunta"

    def test_cada_sesion_nueva_es_otra_conversacion(
        self, cliente: Api, claude: _ClaudeFalso
    ) -> None:
        una = cliente.post("/api/chat", json={"pregunta": "hola"}).json()
        otra = cliente.post("/api/chat", json={"pregunta": "hola"}).json()
        assert una["sesion"] != otra["sesion"]
        assert len(otra["historial"]) == 2

    def test_una_sesion_que_no_existe_es_404(self, cliente: Api, claude: _ClaudeFalso) -> None:
        r = cliente.post("/api/chat", json={"pregunta": "hola", "sesion": "inventada"})
        assert r.status_code == 404
        assert claude.prompts == [], "no se gasta cuota en una conversacion que no existe"

    def test_si_claude_no_esta_es_422_con_el_motivo(
        self, cliente: Api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        falso = _ClaudeFalso(falla=True)
        monkeypatch.setattr(rutas_chat, "nueva_sesion", lambda: ChatSession(runner=falso))
        r = cliente.post("/api/chat", json={"pregunta": "hola"})
        assert r.status_code == 422
        assert "PATH" in r.json()["detail"]

    def test_una_pregunta_vacia_la_rechaza_el_contrato(self, cliente: Api) -> None:
        assert cliente.post("/api/chat", json={"pregunta": ""}).status_code == 422
