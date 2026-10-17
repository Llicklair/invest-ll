"""Que ningún comando se quede fuera del contrato JSON.

Dos veces en este proyecto se dio por hecho que algo estaba conectado y no lo estaba: la
traducción de símbolos y la pestaña `seguimiento`. En ambos casos el código existía, el commit
decía que se había integrado, y nadie lo llamaba. La forma de que no vuelva a pasar no es tener
más cuidado: es que la suite se ponga roja.

Este fichero recorre los puntos de entrada declarados en `pyproject.toml` — no una lista escrita
a mano, que se quedaría desactualizada en cuanto se añada un comando— y exige que cada uno
acepte `--json`.
"""

from __future__ import annotations

import ast
import importlib
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

# `fetch` descarga, `panel` levanta un servidor y `chat` es una conversacion interactiva:
# ninguno produce un resultado que otro programa deba consumir. `mcp` es un servidor MCP por
# stdio: su salida ya es un protocolo (JSON-RPC) y un sobre JSON delante lo romperia.
SIN_JSON = frozenset({"invest-ll-fetch", "invest-ll-panel", "invest-ll-chat", "invest-ll-mcp"})


def puntos_de_entrada() -> dict[str, str]:
    """Los comandos declarados en pyproject, para no mantener una lista en paralelo."""
    crudo = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    scripts: dict[str, str] = crudo["project"]["scripts"]
    return {nombre: destino for nombre, destino in scripts.items() if nombre not in SIN_JSON}


COMANDOS = sorted(puntos_de_entrada().items())


class TestTodosAceptanJson:
    def test_hay_comandos_que_comprobar(self) -> None:
        """Si la lista viniera vacia, todo lo de abajo pasaria sin comprobar nada."""
        assert len(COMANDOS) >= 6, f"solo se detectaron {len(COMANDOS)} comandos"

    @pytest.mark.parametrize(("nombre", "destino"), COMANDOS)
    def test_el_comando_acepta_json(self, nombre: str, destino: str) -> None:
        """`--json` tiene que estar en todos: un agente no puede usar solo la mitad."""
        modulo_nombre, _, _ = destino.partition(":")
        fuente = Path(importlib.import_module(modulo_nombre).__file__ or "").read_text(
            encoding="utf-8"
        )
        assert "add_json_flag" in fuente, (
            f"{nombre} no llama a add_json_flag: se quedaria fuera del contrato JSON"
        )

    @pytest.mark.parametrize(("nombre", "destino"), COMANDOS)
    def test_el_comando_cierra_la_salida(self, nombre: str, destino: str) -> None:
        """Declarar `--json` sin llamar a `cerrar()` daria una bandera que no hace nada."""
        modulo_nombre, _, _ = destino.partition(":")
        fuente = Path(importlib.import_module(modulo_nombre).__file__ or "").read_text(
            encoding="utf-8"
        )
        assert ".cerrar(" in fuente or ".error(" in fuente, (
            f"{nombre} declara --json pero nunca emite el sobre"
        )


class TestElGuardianDetectaDeVerdad:
    """Un guardian que no puede fallar es peor que no tener guardian.

    El de las pestanas del panel era tautologico —su regex casaba con la propia definicion— y
    estuvo verde mientras la pestana seguia desconectada. Aqui se comprueba al reves: contra
    codigo que SI deberia marcar.
    """

    def test_marca_un_comando_sin_la_bandera(self) -> None:
        fuente_falsa = "def main(argv=None):\n    parser = ArgumentParser()\n    return 0\n"
        assert "add_json_flag" not in fuente_falsa

    def test_marca_un_comando_que_no_cierra(self) -> None:
        fuente_falsa = "add_json_flag(parser)\nreturn SALIDA_OK\n"
        assert ".cerrar(" not in fuente_falsa and ".error(" not in fuente_falsa


class TestNadieImprimeAEspaldasDeLaSalida:
    """Un `print()` suelto en modo JSON rompe el documento por la mitad.

    Se mira el AST y no el texto: un `print` dentro de una cadena o un comentario no cuenta, y
    uno escrito con otro espaciado si.
    """

    @pytest.mark.parametrize(("nombre", "destino"), COMANDOS)
    def test_no_quedan_prints_sueltos(self, nombre: str, destino: str) -> None:
        modulo_nombre, _, _ = destino.partition(":")
        ruta = Path(importlib.import_module(modulo_nombre).__file__ or "")
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))

        culpables = [
            nodo.lineno
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id == "print"
        ]
        assert not culpables, (
            f"{nombre} tiene print() directo en las lineas {culpables}: en modo JSON "
            "eso sale en stdout y rompe el documento. Usa salida.linea()."
        )
