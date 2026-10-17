"""Diseñar con Claude (docs/panel-v4-real.md §2): una conversación en la que Claude escribe,
valida, prueba y, si Marcos lo pide, despliega en ficticio una estrategia a medida.

Cada turno es UNA llamada al CLI `claude -p` (la suscripción de Marcos, como el chat; gasta cuota)
con el conector MCP de INVEST LL (`invest-ll-mcp`) como única caja de herramientas:

- `--mcp-config` con solo ese servidor y `--strict-mcp-config` (ningún otro MCP configurado);
- `--tools ""`: sin las herramientas propias del CLI (ni terminal, ni ficheros, ni web);
- `--allowedTools` con las once herramientas del conector y `--permission-mode dontAsk`: lo que
  no esté en la lista se deniega sin preguntar a nadie;
- un prompt de sistema con el formato, las reglas de la casa (no prometer, el pasado no es una
  promesa, enseñar las pegas, el sobreajuste) y que NO puede activar dinero real. El conector,
  además, no tiene herramientas para eso: aunque lo intente, no hay con qué.

**La conversación sigue** con la sesión del propio CLI (`--session-id` en el primer turno,
`--resume` en los siguientes) y queda guardada, con lo que dijo cada uno, en
`medida/sesiones/<sesion>.json`. Una sesión cuyo primer turno falla no se guarda.

**Qué estrategia creó o cambió** se sabe mirando la biblioteca antes y después del turno: el
conector guarda en el mismo `medida/`.

El que ejecuta el CLI (`runner`) se inyecta: los tests no gastan cuota.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.errors import InvestLLError
from invest_ll.estrategias_custom.formato import EXPLICACION
from invest_ll.fetch.atomic_write import replace_atomically

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from invest_ll.estrategias_custom.biblioteca import Biblioteca

EJECUTABLE: Final = "claude"
TIMEOUT_SEGUNDOS: Final = 600
"""Diez minutos: un turno con varias pruebas sobre el pasado tarda unos pocos."""
MODELO: Final = "opus"
"""El alias del CLI para el Opus más reciente: no se queda viejo como un nombre fijo."""
SERVIDOR: Final = "invest-ll"
HERRAMIENTAS: Final = (
    "exchanges",
    "monedas",
    "velas",
    "esquema",
    "validar",
    "probar",
    "guardar",
    "estrategias",
    "desplegar_ficticio",
    "bots",
    "parar_bot",
)
"""Las del conector MCP, y las únicas que puede usar Claude en un turno. Ninguna activa dinero
real, cambia límites ni toca claves (`tests/unit/test_mcp_servidor.py` lo vigila)."""
SESIONES: Final = "sesiones"
MAX_MENSAJE: Final = 8000
_SESION: Final = re.compile(r"^[a-f0-9]{16}$")

PROMPT_SISTEMA: Final = (
    """\
Eres quien disena estrategias a medida en INVEST LL, la aplicacion de inversion de Marcos. Marcos
no es experto en inversion. Respondes en espanol, claro y breve, en Markdown.

Tienes UNA caja de herramientas, el conector de INVEST LL (mcp__invest-ll__*): exchanges, monedas,
velas, esquema, validar, probar, guardar, estrategias, desplegar_ficticio, bots y parar_bot. No
tienes terminal, ni ficheros, ni web.

Como trabajas:
1. Escribe la estrategia en el formato de abajo (si dudas, `esquema` trae el JSON Schema y
   ejemplos), compruebala con `validar` y guardala con `guardar` (autor: Claude).
2. Pruebala sobre el pasado con `probar` (por defecto Binance y el ultimo ano, salvo que Marcos
   diga otra cosa).
3. Ensena el resultado CON SUS PEGAS: ganancia frente a mantener, peor caida, cuantas operaciones,
   comisiones, tiempo dentro, y los avisos que devuelve la prueba.
4. Si cambias una estrategia ya guardada, guardala como version nueva de la MISMA (`guardar` con
   su id), nunca como una nueva: asi se cuentan las versiones probadas.
5. Solo si Marcos lo pide, `desplegar_ficticio` (dinero ficticio).

Reglas que no se negocian:
- NUNCA puedes activar dinero real, subir limites ni tocar claves: no hay herramientas para eso y
  no las busques. Si Marcos lo pide, dile que se hace desde el panel (Bots), por el, con
  confirmacion tecleada, y que antes conviene una semana en ficticio.
- Nada de promesas ni predicciones. El pasado no es una promesa: una prueba sobre el pasado sirve
  para descartar ideas malas, no para confirmar buenas.
- Sobreajuste: elegir la mejor de muchas pruebas sobre el pasado se parece a hacer trampa. No
  retoques parametros para que el pasado salga bonito; si la prueba avisa de sobreajuste, dilo.
  Prefiere reglas simples y pocas.
- En este proyecto, operar menos gano a operar mas y ninguna estrategia probada batio a comprar y
  mantener. Cada operacion paga comision. Dilo si la estrategia opera mucho.
- Si algo falla o no lo sabes, dilo. No inventes datos.

Al terminar un turno, resume: que hace la estrategia (sus reglas en llano), su id, como salio
frente a mantener y sus pegas.

El formato de una estrategia:
"""
    + EXPLICACION
)


class ClaudeNoDisponibleError(InvestLLError):
    """No se pudo hablar con el CLI de claude. El texto, en llano."""


class SesionNoEncontradaError(InvestLLError):
    """No existe esa conversación."""


@dataclass(frozen=True, slots=True)
class Mensaje:
    autor: Literal["marcos", "claude"]
    texto: str
    at: datetime
    herramientas: tuple[str, ...] = ()
    estrategia: str | None = None


@dataclass(frozen=True, slots=True)
class Turno:
    sesion: str
    respuesta: str
    estrategia: str | None
    herramientas: tuple[str, ...]
    historial: tuple[Mensaje, ...]


@dataclass(frozen=True, slots=True)
class Salida:
    """Lo que se saca de la salida `stream-json` del CLI."""

    texto: str
    herramientas: tuple[str, ...]
    conector_conectado: bool | None
    error: str | None


type Runner = Callable[[Sequence[str], str, Path], str]
"""(argumentos sin el ejecutable, lo que se escribe por la entrada, directorio) -> salida."""


# -- El CLI ----------------------------------------------------------------------------------------


def ejecutable() -> str | None:
    """El `claude` de verdad. En Windows, npm deja un `claude.cmd` que llama a un `claude.exe`:
    se usa el .exe directamente, porque cmd.exe estropea los argumentos con comillas y saltos de
    línea (el prompt de sistema los lleva)."""
    ruta = shutil.which(EJECUTABLE)
    if ruta is None:
        return None
    p = Path(ruta)
    if sys.platform == "win32" and p.suffix.lower() != ".exe":
        nativo = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if nativo.is_file():
            return str(nativo)
    return ruta


def ejecutar_cli(argumentos: Sequence[str], entrada: str, cwd: Path) -> str:
    """Lanza `claude` y devuelve su salida. Errores en llano."""
    exe = ejecutable()
    if exe is None:
        raise ClaudeNoDisponibleError(
            "No se encuentra el programa «claude» (Claude Code) en este equipo. Diseñar con Claude "
            "usa tu suscripción a través de él: instálalo con «npm install -g "
            "@anthropic-ai/claude-code» e inicia sesión con «claude»."
        )
    try:
        proceso = subprocess.run(
            [exe, *argumentos],
            input=entrada.encode("utf-8"),
            capture_output=True,
            cwd=cwd,
            timeout=TIMEOUT_SEGUNDOS,
            check=False,
        )
    except FileNotFoundError as error:
        raise ClaudeNoDisponibleError(f"No se pudo lanzar «{exe}»: {error}.") from error
    except subprocess.TimeoutExpired as error:
        raise ClaudeNoDisponibleError(
            f"Claude no terminó en {TIMEOUT_SEGUNDOS // 60} minutos y se ha cortado el turno. "
            "Prueba con una petición más sencilla."
        ) from error
    salida = proceso.stdout.decode("utf-8", errors="replace")
    if proceso.returncode != 0 and not salida.strip():
        detalle = proceso.stderr.decode("utf-8", errors="replace").strip() or "sin mensaje"
        raise ClaudeNoDisponibleError(f"Claude devolvió un error: {detalle[:400]}")
    return salida


def leer_salida(texto: str) -> Salida:
    """La respuesta final, las herramientas del conector usadas (en orden) y si el conector
    arrancó, de las líneas JSON de `--output-format stream-json`."""
    prefijo = f"mcp__{SERVIDOR}__"
    herramientas: list[str] = []
    textos: list[str] = []
    final: str | None = None
    error: str | None = None
    conectado: bool | None = None
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if not isinstance(evento, dict):
            continue
        e = cast("dict[str, Any]", evento)
        tipo = e.get("type")
        if tipo == "system" and e.get("subtype") == "init":
            for servidor in cast("list[dict[str, Any]]", e.get("mcp_servers") or []):
                if servidor.get("name") == SERVIDOR:
                    conectado = servidor.get("status") == "connected"
        elif tipo == "assistant":
            mensaje = cast("dict[str, Any]", e.get("message") or {})
            for bloque in cast("list[dict[str, Any]]", mensaje.get("content") or []):
                if bloque.get("type") == "tool_use":
                    nombre = str(bloque.get("name", ""))
                    herramientas.append(nombre.removeprefix(prefijo))
                elif bloque.get("type") == "text":
                    textos.append(str(bloque.get("text", "")))
        elif tipo == "result":
            if e.get("is_error") or e.get("subtype") not in (None, "success"):
                error = str(e.get("result") or e.get("subtype") or "error")
            elif isinstance(e.get("result"), str):
                final = str(e["result"])
    respuesta = final if final is not None else "\n\n".join(t for t in textos if t.strip())
    return Salida(respuesta.strip(), tuple(herramientas), conectado, error)


def comando_mcp(medida: Path) -> tuple[str, list[str]]:
    """Cómo lanza el CLI el conector: con el Python de este panel y sobre su biblioteca."""
    return sys.executable, ["-m", "invest_ll.mcp", "--medida", str(medida.resolve())]


def argumentos(
    *, mcp_config: Path, sesion_cli: str, nueva: bool, modelo: str = MODELO
) -> list[str]:
    """Los argumentos de un turno: solo el conector de INVEST LL, nada más."""
    permitidas = ",".join(f"mcp__{SERVIDOR}__{h}" for h in HERRAMIENTAS)
    return [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        modelo,
        "--mcp-config",
        str(mcp_config),
        "--strict-mcp-config",
        "--tools",
        "",
        "--allowedTools",
        permitidas,
        "--permission-mode",
        "dontAsk",
        "--disable-slash-commands",
        "--system-prompt",
        PROMPT_SISTEMA,
        *(["--session-id", sesion_cli] if nueva else ["--resume", sesion_cli]),
    ]


# -- Las conversaciones ----------------------------------------------------------------------------


def _mensaje_a_json(m: Mensaje) -> dict[str, Any]:
    return {
        "autor": m.autor,
        "texto": m.texto,
        "at": m.at.isoformat(),
        "herramientas": list(m.herramientas),
        "estrategia": m.estrategia,
    }


def _mensaje_de_json(d: dict[str, Any]) -> Mensaje:
    return Mensaje(
        autor="claude" if d.get("autor") == "claude" else "marcos",
        texto=str(d.get("texto", "")),
        at=datetime.fromisoformat(str(d["at"])),
        herramientas=tuple(str(h) for h in cast("list[object]", d.get("herramientas") or [])),
        estrategia=str(d["estrategia"]) if d.get("estrategia") else None,
    )


class Disenador:
    """Las conversaciones de "Diseñar con Claude" sobre una biblioteca."""

    def __init__(
        self,
        biblioteca: Biblioteca,
        *,
        runner: Runner | None = None,
        cwd: Path | None = None,
        modelo: str = MODELO,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self.biblioteca = biblioteca
        self._runner = runner or ejecutar_cli
        self._cwd = cwd or Path.cwd()
        self._modelo = modelo
        self._reloj = reloj or (lambda: datetime.now(UTC))
        self._cerrojos: dict[str, threading.Lock] = {}
        self._cerrojo = threading.Lock()

    @property
    def carpeta(self) -> Path:
        return self.biblioteca.raiz / SESIONES

    def _ruta(self, sesion: str) -> Path:
        if not _SESION.match(sesion):
            raise SesionNoEncontradaError(f"No hay ninguna conversación «{sesion[:40]}».")
        return self.carpeta / f"{sesion}.json"

    def _leer(self, sesion: str) -> dict[str, Any]:
        try:
            texto = self._ruta(sesion).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SesionNoEncontradaError(
                f"No hay ninguna conversación «{sesion}»: empieza una nueva sin sesión."
            ) from None
        return cast("dict[str, Any]", json.loads(texto))

    def _escribir(self, sesion: str, datos: dict[str, Any]) -> None:
        texto = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
        destino = self._ruta(sesion)
        destino.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(
            destino, lambda tmp: tmp.write_text(texto, encoding="utf-8", newline="\n")
        )

    def _cerrojo_de(self, sesion: str) -> threading.Lock:
        with self._cerrojo:
            return self._cerrojos.setdefault(sesion, threading.Lock())

    def _foto(self) -> dict[str, int]:
        """Cada estrategia con su número de versiones: para ver cuál cambió en el turno."""
        return {f.id: len(f.versiones) for f in self.biblioteca.fichas()}

    def conversacion(self, sesion: str) -> Turno:
        datos = self._leer(sesion)
        historial = tuple(
            _mensaje_de_json(m) for m in cast("list[dict[str, Any]]", datos.get("historial", []))
        )
        ultima = next((m for m in reversed(historial) if m.autor == "claude"), None)
        return Turno(
            sesion=sesion,
            respuesta=ultima.texto if ultima else "",
            estrategia=ultima.estrategia if ultima else None,
            herramientas=ultima.herramientas if ultima else (),
            historial=historial,
        )

    def turno(self, mensaje: str, sesion: str | None = None) -> Turno:
        """Un mensaje de Marcos y la respuesta de Claude. Puede tardar varios minutos."""
        mensaje = mensaje.strip()
        if not mensaje:
            raise ClaudeNoDisponibleError("Escribe qué estrategia quieres.")
        if len(mensaje) > MAX_MENSAJE:
            raise ClaudeNoDisponibleError(
                f"El mensaje es demasiado largo: como mucho {MAX_MENSAJE} caracteres."
            )
        if sesion is None:
            sesion = secrets.token_hex(8)
            datos: dict[str, Any] = {
                "sesion": sesion,
                "sesion_cli": str(uuid.uuid4()),
                "creada": self._reloj().isoformat(),
                "historial": [],
            }
            nueva = True
        else:
            datos = self._leer(sesion)
            nueva = False

        with self._cerrojo_de(sesion):
            if not nueva:
                datos = self._leer(sesion)  # lo último, por si otro turno acaba de terminar
            pregunta = Mensaje("marcos", mensaje, self._reloj())
            antes = self._foto()
            config = self.carpeta / f"{sesion}.mcp.json"
            comando, args = comando_mcp(self.biblioteca.raiz)
            self._escribir_config(config, comando, args)
            try:
                salida = leer_salida(
                    self._runner(
                        argumentos(
                            mcp_config=config,
                            sesion_cli=str(datos["sesion_cli"]),
                            nueva=nueva,
                            modelo=self._modelo,
                        ),
                        mensaje,
                        self._cwd,
                    )
                )
                if salida.error is not None and not salida.texto:
                    raise ClaudeNoDisponibleError(f"Claude no pudo responder: {salida.error[:400]}")
            except Exception:
                if nueva:  # una conversación que no llegó a empezar no se guarda
                    config.unlink(missing_ok=True)
                raise
            texto = salida.texto or "(Claude no ha escrito nada en este turno.)"
            if salida.conector_conectado is False:
                texto += (
                    "\n\n> El conector de INVEST LL no arrancó en este turno: Claude no ha podido "
                    "usar sus herramientas (validar, probar, guardar…)."
                )
            despues = self._foto()
            cambiadas = [i for i, n in despues.items() if antes.get(i) != n]
            estrategia = self._mas_reciente(cambiadas)
            respuesta = Mensaje("claude", texto, self._reloj(), salida.herramientas, estrategia)
            historial = [
                *cast("list[dict[str, Any]]", datos.get("historial", [])),
                _mensaje_a_json(pregunta),
                _mensaje_a_json(respuesta),
            ]
            datos["historial"] = historial
            self._escribir(sesion, datos)
        return self.conversacion(sesion)

    def _mas_reciente(self, ids: list[str]) -> str | None:
        if not ids:
            return None
        fichas = [self.biblioteca.ficha(i) for i in ids]
        return max(fichas, key=lambda f: f.actualizada).id

    @staticmethod
    def _escribir_config(destino: Path, comando: str, args: list[str]) -> None:
        texto = json.dumps(
            {"mcpServers": {SERVIDOR: {"type": "stdio", "command": comando, "args": args}}},
            ensure_ascii=False,
            indent=2,
        )
        destino.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(destino, lambda tmp: tmp.write_text(texto, encoding="utf-8"))
