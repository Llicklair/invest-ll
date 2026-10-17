"""Diseñar con Claude: cómo se llama al CLI (solo el conector, sin herramientas propias, sin poder
activar real), la conversación que sigue, la estrategia que detecta y los errores en llano. Con un
runner falso: ningún test gasta cuota."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from invest_ll import claude_cli
from invest_ll.estrategias_custom import disenar
from invest_ll.estrategias_custom.biblioteca import Biblioteca
from invest_ll.estrategias_custom.disenar import (
    HERRAMIENTAS,
    PROMPT_SISTEMA,
    ClaudeNoDisponibleError,
    Disenador,
    SesionNoEncontradaError,
    leer_salida,
)

from .medida_apoyo import CRUCE

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence


def linea(datos: dict[str, Any]) -> str:
    return json.dumps(datos, ensure_ascii=False)


def salida_cli(
    texto: str, herramientas: Sequence[str] = (), *, conectado: bool = True, error: bool = False
) -> str:
    """Lo que escribe `claude -p --output-format stream-json --verbose`."""
    estado = "connected" if conectado else "failed"
    lineas = [
        linea(
            {
                "type": "system",
                "subtype": "init",
                "mcp_servers": [{"name": "invest-ll", "status": estado}],
            }
        ),
    ]
    for h in herramientas:
        uso: dict[str, Any] = {"type": "tool_use", "name": f"mcp__invest-ll__{h}", "input": {}}
        lineas.append(linea({"type": "assistant", "message": {"content": [uso]}}))
        lineas.append(linea({"type": "user", "message": {"content": [{"type": "tool_result"}]}}))
    lineas.append(
        linea({"type": "assistant", "message": {"content": [{"type": "text", "text": texto}]}})
    )
    lineas.append(
        linea(
            {
                "type": "result",
                "subtype": "error_during_execution" if error else "success",
                "is_error": error,
                "result": texto,
            }
        )
    )
    return "\n".join(lineas) + "\n"


class RunnerFalso:
    """Apunta cada llamada y contesta lo que se le diga; `efecto` hace lo que haría el conector
    durante el turno (guardar una estrategia en la biblioteca)."""

    def __init__(self, respuesta: str, efecto: Callable[[], object] | None = None) -> None:
        self.respuesta = respuesta
        self.efecto = efecto
        self.llamadas: list[tuple[list[str], str, Path]] = []

    def __call__(self, argumentos: Sequence[str], entrada: str, cwd: Path) -> str:
        self.llamadas.append((list(argumentos), entrada, cwd))
        if self.efecto is not None:
            self.efecto()
        return self.respuesta


def valor(argumentos: list[str], opcion: str) -> str:
    return argumentos[argumentos.index(opcion) + 1]


def _ninguno(_nombre: str) -> str | None:
    return None


def _siempre(ruta: str) -> Callable[[str], str | None]:
    def which(_nombre: str) -> str | None:
        return ruta

    return which


@pytest.fixture
def biblioteca(tmp_path: Path) -> Biblioteca:
    return Biblioteca(tmp_path / "medida")


class TestComoSeLlamaAlCli:
    def test_solo_el_conector_y_nada_mas(self, biblioteca: Biblioteca, tmp_path: Path) -> None:
        runner = RunnerFalso(salida_cli("Hecho."))
        Disenador(biblioteca, runner=runner, cwd=tmp_path).turno("Una estrategia de BTC")
        args, entrada, cwd = runner.llamadas[0]
        assert entrada == "Una estrategia de BTC"
        assert cwd == tmp_path
        assert args[0] == "-p"
        assert valor(args, "--output-format") == "stream-json"
        assert valor(args, "--tools") == ""  # sin terminal, ficheros ni web
        assert "--strict-mcp-config" in args
        assert valor(args, "--permission-mode") == "dontAsk"
        permitidas = valor(args, "--allowedTools").split(",")
        assert permitidas == [f"mcp__invest-ll__{h}" for h in HERRAMIENTAS]
        assert not any(p in " ".join(args) for p in ("Bash", "Edit", "Write", "WebFetch"))
        assert "--dangerously-skip-permissions" not in args
        config = json.loads(Path(valor(args, "--mcp-config")).read_text(encoding="utf-8"))
        servidores = config["mcpServers"]
        assert list(servidores) == ["invest-ll"]
        assert servidores["invest-ll"]["args"][:2] == ["-m", "invest_ll.mcp"]
        assert servidores["invest-ll"]["args"][-1] == str(biblioteca.raiz.resolve())

    def test_el_prompt_de_sistema_pone_las_reglas(self, biblioteca: Biblioteca) -> None:
        runner = RunnerFalso(salida_cli("Hecho."))
        Disenador(biblioteca, runner=runner).turno("Hola")
        prompt = valor(runner.llamadas[0][0], "--system-prompt")
        assert prompt == PROMPT_SISTEMA
        for regla in (
            "NUNCA puedes activar dinero real",
            "El pasado no es una promesa",
            "Sobreajuste",
            "CON SUS PEGAS",
            "version nueva de la MISMA",
            "Nada de promesas",
            "cruza_arriba",  # el formato va dentro
        ):
            assert regla in prompt, regla

    def test_la_conversacion_sigue_con_la_sesion_del_cli(self, biblioteca: Biblioteca) -> None:
        runner = RunnerFalso(salida_cli("Primera respuesta."))
        d = Disenador(biblioteca, runner=runner)
        primero = d.turno("Hola")
        runner.respuesta = salida_cli("Segunda respuesta.")
        segundo = d.turno("Y ahora prueba otra", primero.sesion)
        id_cli = valor(runner.llamadas[0][0], "--session-id")
        assert "--resume" not in runner.llamadas[0][0]
        assert valor(runner.llamadas[1][0], "--resume") == id_cli
        assert "--session-id" not in runner.llamadas[1][0]
        assert segundo.sesion == primero.sesion
        assert [(m.autor, m.texto) for m in segundo.historial] == [
            ("marcos", "Hola"),
            ("claude", "Primera respuesta."),
            ("marcos", "Y ahora prueba otra"),
            ("claude", "Segunda respuesta."),
        ]


class TestElTurno:
    def test_respuesta_herramientas_y_estrategia_creada(self, biblioteca: Biblioteca) -> None:
        guardadas: list[str] = []

        def guarda() -> None:
            guardadas.append(biblioteca.guardar(CRUCE, autor="claude").id)

        runner = RunnerFalso(
            salida_cli("La he guardado y probado.", ["esquema", "validar", "guardar", "probar"]),
            efecto=guarda,
        )
        t = Disenador(biblioteca, runner=runner).turno("Cruce de medias en BTC")
        assert t.respuesta == "La he guardado y probado."
        assert t.herramientas == ("esquema", "validar", "guardar", "probar")
        assert t.estrategia == guardadas[0]

    def test_detecta_una_version_nueva(self, biblioteca: Biblioteca) -> None:
        previa = biblioteca.guardar(CRUCE, autor="claude")
        otra = biblioteca.guardar({**CRUCE, "nombre": "Otra"}, autor="marcos")

        def version_nueva() -> None:
            biblioteca.guardar(
                {**CRUCE, "intervalo": "4h"}, autor="claude", estrategia_id=previa.id
            )

        runner = RunnerFalso(salida_cli("Versión 2."), efecto=version_nueva)
        t = Disenador(biblioteca, runner=runner).turno("Pásala a 4 horas")
        assert t.estrategia == previa.id != otra.id

    def test_si_no_toca_ninguna_no_hay_estrategia(self, biblioteca: Biblioteca) -> None:
        biblioteca.guardar(CRUCE, autor="claude")
        t = Disenador(biblioteca, runner=RunnerFalso(salida_cli("Solo hablo."))).turno("Hola")
        assert t.estrategia is None
        assert t.herramientas == ()

    def test_queda_guardada_y_se_puede_leer(self, biblioteca: Biblioteca) -> None:
        d = Disenador(biblioteca, runner=RunnerFalso(salida_cli("Hecho.", ["validar"])))
        t = d.turno("Hola")
        guardada = Disenador(biblioteca).conversacion(t.sesion)
        assert guardada == t
        assert (biblioteca.raiz / "sesiones" / f"{t.sesion}.json").is_file()

    def test_avisa_si_el_conector_no_arranco(self, biblioteca: Biblioteca) -> None:
        runner = RunnerFalso(salida_cli("No tengo herramientas.", conectado=False))
        t = Disenador(biblioteca, runner=runner).turno("Hola")
        assert "El conector de INVEST LL no arrancó" in t.respuesta


class TestErrores:
    def test_una_sesion_que_no_existe(self, biblioteca: Biblioteca) -> None:
        d = Disenador(biblioteca, runner=RunnerFalso(salida_cli("x")))
        with pytest.raises(SesionNoEncontradaError):
            d.conversacion("0123456789abcdef")
        with pytest.raises(SesionNoEncontradaError):
            d.turno("Hola", "0123456789abcdef")
        with pytest.raises(SesionNoEncontradaError):
            d.conversacion("../../bots/x")

    def test_si_claude_falla_en_el_primer_turno_no_queda_conversacion(
        self, biblioteca: Biblioteca
    ) -> None:
        runner = RunnerFalso(salida_cli("", error=True))
        with pytest.raises(ClaudeNoDisponibleError, match="Claude no pudo responder"):
            Disenador(biblioteca, runner=runner).turno("Hola")
        carpeta = biblioteca.raiz / "sesiones"
        assert not carpeta.exists() or list(carpeta.iterdir()) == []

    def test_mensaje_vacio_o_enorme(self, biblioteca: Biblioteca) -> None:
        d = Disenador(biblioteca, runner=RunnerFalso(salida_cli("x")))
        with pytest.raises(ClaudeNoDisponibleError):
            d.turno("   ")
        with pytest.raises(ClaudeNoDisponibleError, match="demasiado largo"):
            d.turno("x" * 10_000)

    def test_sin_claude_instalado_lo_dice_en_llano(
        self, biblioteca: Biblioteca, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(claude_cli.shutil, "which", _ninguno)
        with pytest.raises(ClaudeNoDisponibleError, match="No se encuentra el programa «claude»"):
            Disenador(biblioteca).turno("Hola")

    def test_si_tarda_demasiado_se_corta(
        self, biblioteca: Biblioteca, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        exe = tmp_path / "claude.exe"
        exe.write_bytes(b"")
        monkeypatch.setattr(disenar, "ejecutable", lambda: str(exe))

        def tarda(*_args: object, **_kwargs: object) -> object:
            raise subprocess.TimeoutExpired("claude", disenar.TIMEOUT_SEGUNDOS)

        monkeypatch.setattr(disenar.subprocess, "run", tarda)
        with pytest.raises(ClaudeNoDisponibleError, match="no terminó en 10 minutos"):
            Disenador(biblioteca).turno("Hola")

    def test_la_salida_se_lee_como_utf8_aunque_traiga_basura(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(disenar, "ejecutable", lambda: "claude.exe")

        def responde(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            texto = salida_cli("Más café: ñandú").encode("utf-8") + b"\xff\n"
            return subprocess.CompletedProcess([], 0, texto, b"")

        monkeypatch.setattr(disenar.subprocess, "run", responde)
        salida = leer_salida(disenar.ejecutar_cli(["-p"], "hola", tmp_path))
        assert salida.texto == "Más café: ñandú"


class TestEjecutable:
    def test_en_windows_usa_el_exe_de_detras_del_cmd_de_npm(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cmd = tmp_path / "npm" / "claude.CMD"
        nativo = (
            tmp_path
            / "npm"
            / "node_modules"
            / "@anthropic-ai"
            / "claude-code"
            / "bin"
            / "claude.exe"
        )
        nativo.parent.mkdir(parents=True)
        nativo.write_bytes(b"")
        cmd.write_text("@echo off", encoding="utf-8")
        monkeypatch.setattr(claude_cli.shutil, "which", _siempre(str(cmd)))
        monkeypatch.setattr(claude_cli.sys, "platform", "win32")
        assert claude_cli.ejecutable() == str(nativo)

    def test_si_no_hay_exe_usa_lo_que_haya(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(claude_cli.shutil, "which", _siempre(str(tmp_path / "claude")))
        assert claude_cli.ejecutable() == str(tmp_path / "claude")


def test_leer_salida_sin_resultado_junta_los_textos() -> None:
    texto = "\n".join(
        [
            "basura que no es json",
            linea(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Uno."}]}}
            ),
            linea(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Dos."}]}}
            ),
        ]
    )
    salida = leer_salida(texto)
    assert salida.texto == "Uno.\n\nDos."
    assert salida.error is None
    assert salida.conector_conectado is None


def test_las_horas_de_los_mensajes(biblioteca: Biblioteca) -> None:
    momento = datetime(2026, 10, 17, 12, tzinfo=UTC)
    d = Disenador(biblioteca, runner=RunnerFalso(salida_cli("x")), reloj=lambda: momento)
    assert {m.at for m in d.turno("Hola").historial} == {momento}
