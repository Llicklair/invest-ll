"""Salida legible por una máquina, sin que deje de serlo por una persona.

La CLI es la superficie de control de este proyecto: nueve comandos que ya hacen todo lo que hace
el sistema. Lo que les faltaba es hablar en un formato que otra cosa —un agente, un script, el
panel— pueda leer sin adivinar dónde acaba una columna.

**La decisión de diseño que sostiene este módulo**: un aviso mostrado a una persona SIEMPRE viaja
también en el JSON. Por eso `Salida.aviso()` hace las dos cosas a la vez y no hay forma de emitir
uno sin el otro. Si el modo JSON entregara los números sin las advertencias, un agente leería
"el LLM ganó" sin leer "el modelo fue entrenado con datos posteriores al periodo simulado" — y
este proyecto entero existe para que esas dos frases no se separen.

`tests/unit/test_cli_emit.py::test_un_aviso_siempre_viaja_en_los_dos_modos` es lo que impide que
esa garantía se erosione.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Mapping

VERSION_FORMATO = 1

# Códigos de aviso. Son parte del contrato con quien consuma la salida: el texto puede cambiar,
# el código no. Un agente debería ramificar por código, nunca por la redacción.
AVISO_CONTAMINACION = "llm_contamination"
AVISO_SIN_VENTAJA = "no_advantage_over_holding"
AVISO_NO_CONCLUYENTE = "inconclusive"
AVISO_SOBREAJUSTE = "overfitting_attempts"
AVISO_WIN_RATE = "win_rate_not_success"
AVISO_SOLO_SIMULACION = "simulation_only"
AVISO_NO_ES_PREVISION = "not_a_prediction"
AVISO_VENCIDAS = "forecasts_overdue"
AVISO_FALLOS_GENERACION = "generation_failures"
AVISO_ORDEN_REVISAR = "order_needs_attention"
AVISO_DINERO_REAL = "real_money"


def add_json_flag(parser: argparse.ArgumentParser, *, hereda: bool = False) -> None:
    """Añade `--json` con la misma redacción en todos los comandos.

    `hereda=True` es para los **subcomandos**. Argparse tiene aquí una trampa: si el subparser
    declara `--json` con el default normal, `track --json list` termina en `json=False` porque el
    subparser sobrescribe con su propio default al no ver la bandera. Con `SUPPRESS` el atributo
    simplemente no se toca, y el valor que puso el padre sobrevive.

    Así `track --json list` y `track list --json` significan lo mismo, que es lo que cualquiera
    espera al escribirlos.
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if hereda else False,
        help="Emite el resultado como JSON en stdout, para consumirlo desde otro programa.",
    )


def _plano(valor: object) -> object:
    """Convierte a algo que `json.dumps` acepte, sin perder exactitud en el dinero.

    `Decimal` sale como cadena y NO como `float` a propósito: el proyecto usa `Decimal` para el
    dinero justamente porque `float` pierde céntimos. Serializarlo como número lo desharía en la
    frontera, que es donde menos se nota y más duele.
    """
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, Enum):
        return _plano(valor.value)
    if isinstance(valor, dict):
        crudo = cast("dict[object, object]", valor)
        return {str(clave): _plano(v) for clave, v in crudo.items()}
    if isinstance(valor, list | tuple | set | frozenset):
        secuencia = cast("Iterable[object]", valor)
        return [_plano(v) for v in secuencia]
    if valor is None or isinstance(valor, str | int | float | bool):
        return valor
    return str(valor)


@dataclass(frozen=True, slots=True)
class Aviso:
    """Una advertencia, con un código estable y su texto para leer."""

    code: str
    message: str


@dataclass(slots=True)
class Salida:
    """Lo que el comando comunica, en el formato que toque.

    Se usa igual en los dos modos: el comando llama a `linea`, `aviso` y `dato` sin saber cuál
    está activo, y `cerrar` decide la forma final.
    """

    command: str
    json_mode: bool = False
    datos: dict[str, object] = field(default_factory=dict[str, object])
    avisos: list[Aviso] = field(default_factory=list["Aviso"])
    _error: str | None = None

    def linea(self, texto: str = "") -> None:
        """Texto solo para una persona. En modo JSON no sale: no es dato, es presentación."""
        if not self.json_mode:
            print(texto)

    def aviso(self, code: str, texto: str, *, mostrar: bool = True) -> None:
        """Una advertencia. Va SIEMPRE al JSON, y al texto salvo que ya se haya escrito aparte.

        `mostrar=False` es para cuando el texto ya se imprimió con formato propio (una tabla, un
        bloque de varias líneas): el aviso se registra igual, solo se evita repetirlo.
        """
        self.avisos.append(Aviso(code=code, message=texto))
        if mostrar and not self.json_mode:
            print(texto)

    def dato(self, **campos: object) -> None:
        """Añade campos al cuerpo del JSON. En modo texto no hace nada visible."""
        self.datos.update(campos)

    def pregunta(self, texto: str) -> str:
        """Pide algo por teclado sin ensuciar stdout.

        En modo JSON la pregunta sale por **stderr**, para que stdout siga siendo un único
        documento parseable. Lo que NO hace es saltarse la pregunta: `--json` es un formato de
        salida, nunca un permiso para actuar sin que un humano conteste.
        """
        if self.json_mode:
            print(texto, end="", file=sys.stderr, flush=True)
            return input()
        return input(texto)

    def error(self, mensaje: str, codigo: int) -> int:
        """Registra el fallo y devuelve el código de salida, listo para `return`."""
        self._error = mensaje
        if not self.json_mode:
            print(f"Error: {mensaje}", file=sys.stderr)
        return self.cerrar(codigo)

    def cerrar(self, codigo: int) -> int:
        """Emite el JSON si toca y devuelve el mismo código que le pasaron.

        **`ok` significa "el comando funcionó", no "el resultado te gusta".** La primera versión
        lo ataba a `exit_code == 0` y se cayó en cuanto `invest-ll-alerts` encontró tres alertas:
        salía `ok: false` cuando el comando había hecho exactamente su trabajo. Eran dos preguntas
        distintas metidas en un campo.

        Ahora se separan:

        - `ok`      -> ¿se pudo calcular? Falso solo si hubo un error.
        - `exit_code` -> ¿hay algo que mirar? 0 limpio; 3 no concluyente; 6 alertas que revisar.

        Un agente que quiera "corrió sin romperse" mira `ok`; uno que quiera "y ademas no hay nada
        que revisar" mira `exit_code == 0`. Y un resultado no concluyente sigue llevando su aviso
        en `warnings`, que es lo que impide leer la cifra sin la coletilla.
        """
        if not self.json_mode:
            return codigo

        sobre: dict[str, object] = {
            "format_version": VERSION_FORMATO,
            "command": self.command,
            "ok": self._error is None,
            "exit_code": codigo,
            "data": _plano(self.datos),
            "warnings": [{"code": a.code, "message": a.message} for a in self.avisos],
        }
        if self._error is not None:
            sobre["error"] = self._error

        print(json.dumps(sobre, ensure_ascii=False, indent=2))
        return codigo


def salida_de(args: object, command: str) -> Salida:
    """Construye la `Salida` mirando si el comando recibió `--json`."""
    return Salida(command=command, json_mode=bool(getattr(args, "json", False)))


def como_dict(objeto: object, campos: Mapping[str, str]) -> dict[str, object]:
    """Extrae atributos de un objeto a un dict, renombrándolos.

    `campos` va `{nombre_en_json: nombre_del_atributo}`.
    """
    return {clave: _plano(getattr(objeto, atributo, None)) for clave, atributo in campos.items()}
