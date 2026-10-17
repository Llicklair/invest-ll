"""`invest-ll-mcp`: el conector MCP de INVEST LL (docs/panel-v4-real.md §2.1), por stdio.

Lo usa "Diseñar con Claude" del panel (`claude -p --mcp-config …`) y se puede añadir a Claude Code
o Claude Desktop. Once herramientas:

- de datos, sin claves: `exchanges`, `monedas`, `velas`;
- de estrategias a medida, sobre la biblioteca (`medida/`): `esquema`, `validar`, `guardar`,
  `estrategias`, `probar` (sobre el pasado);
- de bots, a través del panel en marcha: `desplegar_ficticio`, `bots`, `parar_bot`.

**Lo que NO tiene, a propósito:** nada para activar dinero real, cambiar límites o tocar claves y
conexiones. Claude puede diseñar, probar y desplegar en FICTICIO; pasar a real es cosa de Marcos,
desde el panel, con confirmación tecleada. `tests/unit/test_mcp_servidor.py` falla si aparece una
herramienta más.

Las herramientas puras usan el dominio directamente; las de bots hablan con el panel por su API
local (`mcp.panel`). Los errores vuelven a Claude en llano (`ToolError`).
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from invest_ll.errors import InvestLLError
from invest_ll.estrategias_custom import formato
from invest_ll.estrategias_custom.biblioteca import Biblioteca
from invest_ll.estrategias_custom.disenar import HERRAMIENTAS, SERVIDOR
from invest_ll.estrategias_custom.interprete import velas_necesarias
from invest_ll.estrategias_custom.prueba import probar as probar_estrategia
from invest_ll.mcp.panel import URL, Panel
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.estrategias_custom.biblioteca import Ficha
    from invest_ll.estrategias_custom.prueba import Resultado
    from invest_ll.exchanges.conector import Conector

INSTRUCCIONES: Final = (
    "Conector de INVEST LL: diseña estrategias a medida en un formato JSON cerrado (no es código), "
    "valídalas, guárdalas, pruébalas sobre el pasado con velas del exchange y despliégalas en un "
    "bot con dinero FICTICIO. No puede activar dinero real, cambiar límites ni tocar claves: eso "
    "lo hace Marcos desde el panel. El pasado no es una promesa; probar muchas versiones y "
    "quedarse con la mejor es sobreajuste."
)
MAX_PARES: Final = 80
MAX_VELAS: Final = 300
MAX_OPERACIONES_RESUMEN: Final = 20

# Los tipos de los parámetros, a nivel de módulo: el SDK los resuelve con los globales del módulo.
Exchange = Annotated[str, Field(description="Id del exchange: 'binance', 'hyperliquid'…")]
IdEstrategia = Annotated[str, Field(description="Id de una estrategia guardada")]
Definicion = Annotated[
    dict[str, Any] | str,
    Field(description="La estrategia en su formato JSON (ver `esquema`)"),
]


def _conector_publico(exchange: str) -> Conector:
    from invest_ll.exchanges import registro

    return registro.conector_publico(exchange)


def _disponibles() -> list[str]:
    from invest_ll.exchanges import registro

    return registro.disponibles()


def _json(datos: object) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1, default=str)


def _pct(x: float) -> str:
    return f"{x * 100:+.1f} %"


def _fecha(texto: str | None, que: str) -> datetime | None:
    if not texto:
        return None
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        raise ToolError(
            f"«{que}» tiene que ser una fecha AAAA-MM-DD, y es «{texto[:30]}»."
        ) from None
    return fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=UTC)


def _definicion(definicion: dict[str, Any] | str) -> object:
    """Claude a veces manda la estrategia como texto JSON: se lee como JSON (nunca se ejecuta)."""
    if isinstance(definicion, str):
        try:
            return json.loads(definicion)
        except json.JSONDecodeError as error:
            raise ToolError(f"La estrategia no es un JSON válido: {error.msg}.") from None
    return definicion


@dataclass(slots=True)
class Herramientas:
    """Lo que hace cada herramienta, sin el protocolo: se prueba directamente."""

    biblioteca: Biblioteca
    panel: Panel
    conector_publico: Callable[[str], Conector] = _conector_publico
    disponibles: Callable[[], list[str]] = _disponibles

    def _conector(self, exchange: str) -> Conector:
        try:
            return self.conector_publico(exchange)
        except NotImplementedError:
            raise ToolError(
                "Esta versión del panel aún no trae los conectores de exchanges."
            ) from None

    # -- Datos --

    def exchanges(self) -> dict[str, Any]:
        try:
            ids = self.disponibles()
        except NotImplementedError:
            raise ToolError(
                "Esta versión del panel aún no trae los conectores de exchanges."
            ) from None
        return {"exchanges": ids}

    def monedas(self, exchange: str, buscar: str = "") -> dict[str, Any]:
        mercados = self._conector(exchange).mercados()
        texto = buscar.strip().upper()
        elegidos = [
            m
            for m in mercados
            if m.cotizada.upper() in ("USDC", "USDT")
            and (not texto or texto in m.base.upper() or texto in m.par.upper())
        ]
        elegidos.sort(key=lambda m: (m.base, m.cotizada))
        return {
            "exchange": exchange,
            "total": len(elegidos),
            "pares": [
                {
                    "moneda": m.base,
                    "par": m.par,
                    "nombre": nombre_hyperliquid(m.base),
                    "comision_tomador": str(m.comision_tomador)
                    if m.comision_tomador is not None
                    else None,
                }
                for m in elegidos[:MAX_PARES]
            ],
            "nota": f"Solo los primeros {MAX_PARES}: usa «buscar» para afinar."
            if len(elegidos) > MAX_PARES
            else None,
        }

    def velas(self, exchange: str, moneda: str, intervalo: str, cuantas: int) -> dict[str, Any]:
        if intervalo not in formato.INTERVALOS:
            raise ToolError(f"«{intervalo}» no vale: usa {', '.join(formato.INTERVALOS)}.")
        cuantas = max(1, min(cuantas, MAX_VELAS))
        from invest_ll.estrategias_custom.prueba import elegir_mercado

        conector = self._conector(exchange)
        mercado = elegir_mercado(conector, moneda)
        desde = datetime.now(UTC) - formato.DURACION[intervalo] * (cuantas + 2)
        velas = [
            v
            for v in conector.velas(mercado.par, intervalo, desde=desde, limite=cuantas + 2)
            if v.cerrada
        ]
        return {
            "par": mercado.par,
            "intervalo": intervalo,
            "columnas": ["inicio", "apertura", "maximo", "minimo", "cierre", "volumen"],
            "velas": [
                [
                    v.inicio.isoformat(),
                    str(v.apertura),
                    str(v.maximo),
                    str(v.minimo),
                    str(v.cierre),
                    str(v.volumen),
                ]
                for v in velas[-cuantas:]
            ],
        }

    # -- Estrategias --

    def esquema(self) -> dict[str, Any]:
        return {
            "explicacion": formato.EXPLICACION,
            "esquema": formato.esquema(),
            "ejemplos": formato.EJEMPLOS,
        }

    def validar(self, definicion: dict[str, Any] | str) -> dict[str, Any]:
        try:
            e = formato.validar(_definicion(definicion))
        except formato.EstrategiaInvalidaError as error:
            return {"valida": False, "errores": error.errores}
        return {
            "valida": True,
            "reglas_en_llano": formato.reglas_en_llano(e),
            "velas_necesarias": velas_necesarias(e),
            "huella": formato.huella(e),
        }

    def guardar(
        self, definicion: dict[str, Any] | str, nota: str, estrategia: str | None
    ) -> dict[str, Any]:
        ficha = self.biblioteca.guardar(
            _definicion(definicion), autor="claude", nota=nota, estrategia_id=estrategia or None
        )
        return {
            "id": ficha.id,
            "version": ficha.ultima.version,
            "estado": ficha.estado,
            "versiones_probadas": len(ficha.probadas),
            "reglas_en_llano": formato.reglas_en_llano(ficha.estrategia),
        }

    def estrategias(self, estrategia: str | None) -> dict[str, Any]:
        if estrategia:
            f = self.biblioteca.ficha(estrategia)
            ultima = self.biblioteca.ultima_prueba(f.id)
            return {
                **self._resumen(f),
                "definicion": f.ultima.definicion,
                "reglas_en_llano": formato.reglas_en_llano(f.estrategia),
                "versiones": [
                    {"version": v.version, "huella": v.huella, "nota": v.nota, "autor": v.autor}
                    for v in f.versiones
                ],
                "ultima_prueba": _resumen_prueba(ultima) if ultima else None,
            }
        return {"estrategias": [self._resumen(f) for f in self.biblioteca.fichas()]}

    @staticmethod
    def _resumen(f: Ficha) -> dict[str, Any]:
        e = f.estrategia
        return {
            "id": f.id,
            "nombre": e.nombre,
            "version": f.ultima.version,
            "estado": f.estado,
            "autor": f.autor,
            "monedas": list(e.monedas),
            "intervalo": e.intervalo,
            "versiones_probadas": len(f.probadas),
        }

    def probar(
        self,
        estrategia: str,
        exchange: str,
        capital: float,
        desde: str | None,
        hasta: str | None,
    ) -> dict[str, Any]:
        try:
            dinero = Decimal(str(capital))
        except InvalidOperation:
            raise ToolError("«capital» tiene que ser un número.") from None
        f = self.biblioteca.ficha(estrategia)
        resultado = probar_estrategia(
            f.estrategia,
            exchange,
            capital=dinero,
            desde=_fecha(desde, "desde"),
            hasta=_fecha(hasta, "hasta"),
            conector_publico=self._conector,
        )
        resultado = self.biblioteca.registrar_prueba(f.id, resultado)
        return {"estrategia": f.id, "version": resultado.version, **_resumen_prueba(resultado)}

    # -- Bots (por el panel) --

    def desplegar_ficticio(self, estrategia: str, nombre: str, capital: float) -> dict[str, Any]:
        f = self.biblioteca.ficha(estrategia)
        try:
            dinero = Decimal(str(capital))
        except InvalidOperation:
            raise ToolError("«capital» tiene que ser un número.") from None
        bot = self.panel.desplegar_ficticio(
            estrategia=f.id,
            nombre=nombre.strip() or f.estrategia.nombre,
            monedas=list(f.estrategia.monedas),
            capital=dinero,
        )
        return {
            "bot": bot.get("id"),
            "nombre": bot.get("nombre"),
            "modo": bot.get("modo", "ficticio"),
            "estado": bot.get("estado"),
            "nota": "Dinero ficticio. Pasarlo a real solo lo puede hacer Marcos desde el panel.",
        }

    def bots(self) -> dict[str, Any]:
        datos = self.panel.bots()
        return {
            "bots": [
                {
                    clave: b.get(clave)
                    for clave in (
                        "id",
                        "nombre",
                        "plantilla",
                        "estrategia",
                        "modo",
                        "exchange",
                        "monedas",
                        "estado",
                        "capital",
                        "valor",
                        "ganancia_pct",
                        "mantener_pct",
                        "operaciones",
                        "aviso",
                    )
                }
                for b in cast("list[dict[str, Any]]", datos.get("bots") or [])
            ],
            "nota": datos.get("nota"),
        }

    def parar_bot(self, bot: str) -> dict[str, Any]:
        datos = self.panel.parar_bot(bot)
        return {"bot": datos.get("id"), "estado": datos.get("estado")}


def _resumen_prueba(r: Resultado) -> dict[str, Any]:
    """Lo que Claude necesita de una prueba, sin las curvas enteras (gastarían su contexto)."""
    return {
        "exchange": r.exchange,
        "monedas": list(r.monedas),
        "intervalo": r.intervalo,
        "desde": r.desde.date().isoformat(),
        "hasta": r.hasta.date().isoformat(),
        "capital": str(r.capital),
        "valor_final": str(r.valor_final),
        "ganancia": _pct(r.ganancia_pct),
        "mantener": _pct(r.mantener_pct),
        "peor_caida": _pct(r.peor_caida),
        "mantener_peor_caida": _pct(r.mantener_peor_caida),
        "operaciones": r.operaciones,
        "comisiones": str(r.comisiones),
        "tiempo_dentro": f"{r.tiempo_dentro * 100:.0f} %",
        "versiones_probadas": r.versiones_probadas,
        "aviso_sobreajuste": r.aviso_sobreajuste,
        "avisos": list(r.avisos),
        "abiertas_al_final": list(r.abiertas),
        "operaciones_detalle": _operaciones(r),
    }


def _operaciones(r: Resultado) -> list[str]:
    """Todas si son pocas; si no, las primeras y las últimas (en el primer turno real, Claude
    echó en falta la última, la que seguía abierta)."""
    lista = [f"{o.at.date().isoformat()} {o.motivo}" for o in r.lista_operaciones]
    if len(lista) > MAX_OPERACIONES_RESUMEN:
        mitad = MAX_OPERACIONES_RESUMEN // 2
        lista = [*lista[:mitad], f"… ({len(lista) - 2 * mitad} más) …", *lista[-mitad:]]
    if r.operaciones > len(r.lista_operaciones):
        lista.append(
            f"(la prueba solo guarda las primeras {len(r.lista_operaciones)} de "
            f"{r.operaciones} operaciones)"
        )
    return lista


def _llamar(fn: Callable[[], dict[str, Any]]) -> str:
    """Los errores del dominio vuelven a Claude como texto en llano, no como un fallo opaco."""
    try:
        return _json(fn())
    except ToolError:
        raise
    except formato.EstrategiaInvalidaError as error:
        raise ToolError(str(error)) from None
    except (InvestLLError, ValueError) as error:
        raise ToolError(str(error)) from None


def crear_servidor(h: Herramientas) -> MCPServer:
    """El servidor con sus once herramientas (y ninguna más)."""
    s: MCPServer = MCPServer(SERVIDOR, instructions=INSTRUCCIONES, log_level="WARNING")

    @s.tool(
        description="Los exchanges con que puede hablar INVEST LL (ids para monedas, velas y probar).",
        structured_output=False,
    )
    def exchanges() -> str:
        return _llamar(h.exchanges)

    @s.tool(
        description=(
            "Los pares de contado (contra USDC o USDT) de un exchange, con su comisión de tomador "
            "si se sabe. Datos públicos, sin claves."
        ),
        structured_output=False,
    )
    def monedas(
        exchange: Exchange,
        buscar: Annotated[str, Field(description="Filtra por texto: 'BTC', 'SOL'…")] = "",
    ) -> str:
        return _llamar(lambda: h.monedas(exchange, buscar))

    @s.tool(
        description=(
            "Las últimas velas CERRADAS de una moneda en un exchange (inicio, apertura, máximo, "
            f"mínimo, cierre, volumen). Como mucho {MAX_VELAS}."
        ),
        structured_output=False,
    )
    def velas(
        exchange: Exchange,
        moneda: Annotated[str, Field(description="BTC, ETH, SOL…")],
        intervalo: Annotated[
            str, Field(description="15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d o 1w")
        ] = "1d",
        cuantas: Annotated[int, Field(description="Cuántas velas")] = 60,
    ) -> str:
        return _llamar(lambda: h.velas(exchange, moneda, intervalo, cuantas))

    @s.tool(
        description=(
            "El formato de las estrategias a medida: explicación, JSON Schema y ejemplos. Una "
            "estrategia NO es código: es un JSON cerrado que el motor interpreta."
        ),
        structured_output=False,
    )
    def esquema() -> str:
        return _llamar(h.esquema)

    @s.tool(
        description=(
            "Comprueba una estrategia sin guardarla: si vale, sus reglas en llano y cuántas velas "
            "necesita; si no, cada problema en llano."
        ),
        structured_output=False,
    )
    def validar(definicion: Definicion) -> str:
        return _llamar(lambda: h.validar(definicion))

    @s.tool(
        description=(
            "Valida y guarda una estrategia en la biblioteca (autor: Claude). Sin `estrategia`, "
            "crea una nueva; con el id de una existente, guarda una VERSIÓN NUEVA de esa (úsalo "
            "siempre que cambies una estrategia: así se cuentan las versiones probadas)."
        ),
        structured_output=False,
    )
    def guardar(
        definicion: Definicion,
        nota: Annotated[str, Field(description="Qué cambia respecto a la versión anterior")] = "",
        estrategia: Annotated[
            str | None, Field(description="Id de la estrategia, para guardar una versión nueva")
        ] = None,
    ) -> str:
        return _llamar(lambda: h.guardar(definicion, nota, estrategia))

    @s.tool(
        description=(
            "Las estrategias de la biblioteca (id, nombre, versión, estado). Con `estrategia`, "
            "la ficha de una: su definición, sus reglas en llano, sus versiones y su última prueba."
        ),
        structured_output=False,
    )
    def estrategias(
        estrategia: Annotated[str | None, Field(description="Id, para ver una entera")] = None,
    ) -> str:
        return _llamar(lambda: h.estrategias(estrategia))

    @s.tool(
        description=(
            "Prueba la última versión de una estrategia GUARDADA sobre el pasado, con velas del "
            "exchange, comisiones y deslizamiento, frente a mantener. Por defecto, el último año. "
            "Cuenta las versiones probadas: a partir de 3 avisa de sobreajuste. El pasado no es "
            "una promesa."
        ),
        structured_output=False,
    )
    def probar(
        estrategia: IdEstrategia,
        exchange: Exchange = "binance",
        capital: Annotated[float, Field(description="USDC de partida", gt=0)] = 1000,
        desde: Annotated[
            str | None, Field(description="AAAA-MM-DD (por defecto, hace un año)")
        ] = None,
        hasta: Annotated[str | None, Field(description="AAAA-MM-DD (por defecto, hoy)")] = None,
    ) -> str:
        return _llamar(lambda: h.probar(estrategia, exchange, capital, desde, hasta))

    @s.tool(
        description=(
            "Crea un bot con DINERO FICTICIO que ejecuta una estrategia guardada (necesita el panel "
            "abierto). Solo ficticio: pasar un bot a dinero real lo hace Marcos desde el panel. "
            "Úsala solo si Marcos lo pide."
        ),
        structured_output=False,
    )
    def desplegar_ficticio(
        estrategia: IdEstrategia,
        nombre: Annotated[str, Field(description="Nombre del bot")] = "",
        capital: Annotated[float, Field(description="USDC ficticios", gt=0)] = 1000,
    ) -> str:
        return _llamar(lambda: h.desplegar_ficticio(estrategia, nombre, capital))

    @s.tool(
        description="Los bots del panel y cómo van (necesita el panel abierto).",
        structured_output=False,
    )
    def bots() -> str:
        return _llamar(h.bots)

    @s.tool(
        description=(
            "Para un bot: deja de operar y conserva sus posiciones (necesita el panel abierto)."
        ),
        structured_output=False,
    )
    def parar_bot(bot: Annotated[str, Field(description="Id del bot")]) -> str:
        return _llamar(lambda: h.parar_bot(bot))

    hechas = (exchanges, monedas, velas, esquema, validar, guardar, estrategias, probar)
    hechas += (desplegar_ficticio, bots, parar_bot)
    if {f.__name__ for f in hechas} != set(HERRAMIENTAS):  # pragma: no cover - un descuido
        raise RuntimeError("las herramientas del conector no son las de disenar.HERRAMIENTAS")
    return s


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="invest-ll-mcp",
        description="El conector MCP de INVEST LL (stdio). No puede activar dinero real.",
    )
    parser.add_argument(
        "--raiz",
        type=Path,
        default=None,
        help="La carpeta del panel (donde están medida/, bots/…). Por defecto, la actual.",
    )
    parser.add_argument(
        "--medida",
        type=Path,
        default=None,
        help="La biblioteca de estrategias. Por defecto, medida/ dentro de la raíz.",
    )
    parser.add_argument("--panel", default=URL, help=f"La API del panel (por defecto {URL})")
    args = parser.parse_args(argv)
    if args.raiz is not None:
        os.chdir(args.raiz)
    biblioteca = Biblioteca(args.medida) if args.medida is not None else Biblioteca()
    herramientas = Herramientas(biblioteca=biblioteca, panel=Panel(args.panel))
    crear_servidor(herramientas).run("stdio")
