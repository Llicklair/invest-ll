"""El chat con Claude: lee y explica, nunca ejecuta, y no gasta cuota en los tests.

Ningún test de este fichero lanza el CLI real: el runner se inyecta. La suite entera corre con
los sockets bloqueados y sin gastar una sola llamada — la misma regla que la capa de decisiones.

El test que da sentido al módulo es `test_las_instrucciones_prohiben_ejecutar`: un chat que
pudiera lanzar órdenes sería un agente operando con tu dinero.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.chat.context import build_context
from invest_ll.chat.session import (
    INSTRUCCIONES,
    MAX_TURNOS_EN_PROMPT,
    ChatSession,
    ChatUnavailableError,
)
from invest_ll.cli.chat import main as chat_main
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.store import ActivityStore

D = Decimal


class TestLasInstrucciones:
    def test_las_instrucciones_prohiben_ejecutar(self) -> None:
        """EL test de este fichero."""
        assert "NO PUEDES EJECUTAR NADA" in INSTRUCCIONES
        assert "confirmarlo es cosa del operador" in INSTRUCCIONES

    def test_llevan_las_reglas_de_la_casa(self) -> None:
        """Las mismas advertencias que viajan en los comandos, dentro del prompt."""
        assert "win rate" in INSTRUCCIONES
        assert "predicciones" in INSTRUCCIONES
        assert "llevan fecha" in INSTRUCCIONES
        assert "No animes a operar" in INSTRUCCIONES

    def test_citan_lo_medido_no_una_opinion(self) -> None:
        assert "423" in INSTRUCCIONES, "el dato medido de operar menos, con sus numeros"


class TestElPrompt:
    def test_incluye_instrucciones_contexto_y_pregunta(self) -> None:
        sesion = ChatSession(runner=lambda p: "hola")
        prompt = sesion.build_prompt("que tengo?", "CARTERA: vacia")

        assert prompt.startswith(INSTRUCCIONES)
        assert "CARTERA: vacia" in prompt
        assert "operador: que tengo?" in prompt

    def test_el_historial_viaja_en_el_siguiente_mensaje(self) -> None:
        sesion = ChatSession(runner=lambda p: "respuesta uno")
        sesion.ask("primera", contexto="X")

        prompt = sesion.build_prompt("segunda", "X")
        assert "operador: primera" in prompt
        assert "asistente: respuesta uno" in prompt

    def test_el_historial_no_crece_sin_limite_en_el_prompt(self) -> None:
        """Cada mensaje gasta cuota: mandar 200 turnos viejos seria pagarlos cada vez."""
        sesion = ChatSession(runner=lambda p: "r")
        for i in range(MAX_TURNOS_EN_PROMPT * 2):
            sesion.ask(f"pregunta {i}", contexto="X")

        prompt = sesion.build_prompt("ultima", "X")
        assert "pregunta 0" not in prompt, "los turnos viejos se quedan fuera del prompt"
        assert len(sesion.history) == MAX_TURNOS_EN_PROMPT * 4, "pero el historial completo vive"


class TestLaSesion:
    def test_ask_devuelve_lo_del_runner_y_lo_recuerda(self) -> None:
        recibidos: list[str] = []

        def runner(prompt: str) -> str:
            recibidos.append(prompt)
            return "  la respuesta  "

        sesion = ChatSession(runner=runner)
        assert sesion.ask("hola", contexto="CTX") == "la respuesta"
        assert "CTX" in recibidos[0]
        assert sesion.history == [("operador", "hola"), ("asistente", "la respuesta")]

    def test_un_fallo_del_cli_es_un_error_del_dominio(self) -> None:
        def runner(prompt: str) -> str:
            raise ChatUnavailableError("no hay claude")

        with pytest.raises(ChatUnavailableError, match="no hay claude"):
            ChatSession(runner=runner).ask("hola", contexto="X")


class TestElContexto:
    def test_una_cartera_con_posicion_aparece(self, tmp_path: Path) -> None:
        store = ActivityStore(tmp_path)
        store.append(
            Activity(
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                type=ActivityType.BUY,
                symbol="AAA",
                quantity=D(10),
                unit_price=D(100),
            )
        )
        contexto = build_context(portfolio_root=tmp_path, data_root=tmp_path / "no-data")

        assert "ABIERTA AAA" in contexto
        assert "TRIGGERS: ninguno armado" in contexto
        assert "no hay historicos" in contexto

    def test_una_cartera_vacia_lo_dice(self, tmp_path: Path) -> None:
        contexto = build_context(portfolio_root=tmp_path, data_root=tmp_path / "no-data")
        assert "vacia" in contexto

    def test_el_contexto_distingue_valoracion_de_hecho(self, tmp_path: Path) -> None:
        """La distincion central de la cartera tiene que llegar tambien al modelo."""
        store = ActivityStore(tmp_path)
        store.append(
            Activity(
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
                type=ActivityType.BUY,
                symbol="AAA",
                quantity=D(10),
                unit_price=D(100),
            )
        )
        store.append(
            Activity(
                timestamp=datetime(2026, 3, 2, tzinfo=UTC),
                type=ActivityType.SELL,
                symbol="AAA",
                quantity=D(10),
                unit_price=D(120),
            )
        )
        contexto = build_context(portfolio_root=tmp_path, data_root=tmp_path / "no-data")
        assert "RETIRADA AAA" in contexto
        assert "P&L realizado" in contexto
        assert "valoracion, no hecho" in contexto


class TestElRepl:
    def test_pregunta_responde_y_sale(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entradas = iter(["que tengo?", "salir"])

        def leer(prompt: str = "") -> str:
            return next(entradas)

        def fabrica(**kwargs: object) -> ChatSession:
            return ChatSession(runner=lambda p: "no tienes nada registrado")

        monkeypatch.setattr("builtins.input", leer)
        monkeypatch.setattr("invest_ll.cli.chat.build_context", lambda: "CARTERA: vacia")
        monkeypatch.setattr("invest_ll.cli.chat.ChatSession", fabrica)

        assert chat_main([]) == 0
        salida = capsys.readouterr().out
        assert "no tienes nada registrado" in salida
        assert "gasta cuota" in salida, "el coste se dice antes de empezar"

    def test_sin_claude_instalado_falla_con_mensaje(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entradas = iter(["hola"])

        def leer(prompt: str = "") -> str:
            return next(entradas)

        def revienta(prompt: str) -> str:
            raise ChatUnavailableError("no se encontro 'claude' en el PATH")

        def fabrica(**kwargs: object) -> ChatSession:
            return ChatSession(runner=revienta)

        monkeypatch.setattr("builtins.input", leer)
        monkeypatch.setattr("invest_ll.cli.chat.build_context", lambda: "X")
        monkeypatch.setattr("invest_ll.cli.chat.ChatSession", fabrica)

        assert chat_main([]) == 1
        assert "claude" in capsys.readouterr().err

    def test_ctrl_c_sale_limpio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def interrumpe(*_: object) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", interrumpe)
        assert chat_main([]) == 0
