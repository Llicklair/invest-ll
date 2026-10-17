"""Conexiones con varios exchanges (docs/panel-v4-real.md §1 y §4).

Generaliza a cualquier exchange lo que `api/conexion.py` hace con Binance (que sigue funcionando
para el plan). Aquí solo se traduce: qué es cada exchange vive en `exchanges.fichas`, sus claves en
`exchanges.credenciales`, los cerrojos y qué red está activa en `exchanges.activacion`, y probar
unas claves en `exchanges.prueba` (con el conector que da `exchanges.registro`).

**Las claves no salen nunca**: ninguna respuesta las lleva, ni enteras ni en parte, ni ningún
mensaje de error (los del exchange se filtran en el conector). Solo se dice si están, de dónde
vienen y qué se supo al probarlas.

Activar una red prueba la conexión antes (lee saldo y permisos; no envía nada), como el cambio de
modo de v2.1: unas claves que el exchange rechaza solo fallarían al operar.
"""

from __future__ import annotations

import json
import sys
import sysconfig
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException

from invest_ll.api.errores import del_dominio, invalido, no_encontrado
from invest_ll.api.schemas_v2 import SaldoMoneda
from invest_ll.api.schemas_v4 import (
    ActivarExchange,
    CampoClave,
    ClavesExchange,
    Conexiones,
    ConfigMcp,
    EstadoExchange,
    EstadoRedExchange,
    ExchangeDisponible,
    MercadoExchange,
    MercadosExchange,
    PruebaExchange,
    RedExchange,
)
from invest_ll.exchanges import activacion, credenciales, prueba, registro
from invest_ll.exchanges.activacion import Comprobacion, ConfigExchanges, huella
from invest_ll.exchanges.conector import ExchangeError
from invest_ll.exchanges.fichas import FICHAS, POR_ID
from invest_ll.nombres import nombre_hyperliquid

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.exchanges.credenciales import ClavesExchange as Claves
    from invest_ll.exchanges.fichas import Ficha

router = APIRouter()

CONFIRMACION_REAL: Final = "DINERO REAL"
EN_LLANO: Final[dict[str, str]] = {"pruebas": "la red de pruebas", "real": "dinero real"}
DE_LA_RED: Final[dict[str, str]] = {"pruebas": "de pruebas", "real": "de dinero real"}

PROGRAMA_MCP: Final = "invest-ll-mcp"
NOMBRE_MCP: Final = "invest-ll"
NOTA_MCP: Final = (
    "Con este conector, Claude (en Claude Code o en Claude Desktop) puede ver tus exchanges y sus "
    "monedas, leer velas, escribir y validar estrategias, probarlas sobre el pasado, guardarlas, "
    "desplegarlas como bots con dinero ficticio, ver cómo van tus bots y pararlos. NO puede "
    "activar el dinero real, pasar un bot a real, subir límites ni tocar tus claves: eso solo se "
    "hace desde este panel, tecleando la confirmación. Para añadirlo: en Claude Desktop, pega el "
    "bloque en su configuración (Ajustes → Desarrollador → Editar configuración); en Claude Code, "
    "en el .mcp.json del proyecto o con «claude mcp add invest-ll -- <comando>»."
)


def _ahora() -> datetime:
    return datetime.now(UTC)


def _ficha(exchange: str) -> Ficha:
    encontrada = POR_ID.get(exchange)
    if encontrada is None:
        raise no_encontrado(
            f"No se conoce el exchange «{exchange}». Los que hay: {', '.join(registro.disponibles())}."
        )
    return encontrada


def _exigir_red(f: Ficha, red: RedExchange) -> None:
    if red == "pruebas" and not f.tiene_pruebas:
        raise invalido(f"{f.nombre} no tiene red de pruebas: solo se usa con dinero real.")


# -- El estado de cada exchange --------------------------------------------------------------------


def _estado(f: Ficha) -> EstadoExchange:
    e = activacion.leer(f)
    activo = activacion.activo_efectivo(e)
    redes: list[EstadoRedExchange] = []
    for red in ("pruebas", "real") if f.tiene_pruebas else ("real",):
        vigente = activacion.comprobacion_vigente(e, red)
        redes.append(
            EstadoRedExchange(
                red=red,
                claves_guardadas=e.claves[red] is not None,
                origen=e.origen[red],
                verificada=e.ordenes[red] > 0,
                puede_retirar=vigente.puede_retirar if vigente is not None else None,
                comprobado=vigente.at if vigente is not None else None,
            )
        )
    return EstadoExchange(
        id=f.id,
        nombre=f.nombre,
        activo=activo,
        redes=redes,
        que_falta_real=[] if activo == "real" else activacion.que_falta(e, "real"),
    )


def configuracion_mcp() -> ConfigMcp:
    """El bloque para Claude Code / Desktop: el programa `invest-ll-mcp` del entorno del proyecto,
    con su ruta absoluta (Claude Desktop no hereda el PATH de la terminal del proyecto)."""
    nombre = f"{PROGRAMA_MCP}.exe" if sys.platform == "win32" else PROGRAMA_MCP
    comando = str(Path(sysconfig.get_path("scripts")).absolute() / nombre)
    argumentos: list[str] = []
    bloque = {"mcpServers": {NOMBRE_MCP: {"command": comando, "args": argumentos}}}
    nota = NOTA_MCP
    if not Path(comando).exists():
        nota += (
            " (Ese programa aún no está instalado: ejecuta «uv sync» en la carpeta del proyecto.)"
        )
    return ConfigMcp(
        comando=comando,
        argumentos=argumentos,
        bloque_json=json.dumps(bloque, ensure_ascii=False, indent=2),
        nota=nota,
    )


# -- Probar unas claves --------------------------------------------------------------------------


def _probar(f: Ficha, red: RedExchange, claves: Claves) -> prueba.Prueba:
    """Lee saldo y permisos (no envía nada) y, si sale bien, lo apunta como comprobación."""
    try:
        conector = registro.con_claves(f.id, red, claves)
    except ExchangeError as error:
        return prueba.Prueba(ok=False, detalle=str(error))
    resultado = prueba.probar(f, red, conector)
    if resultado.ok:
        permisos = resultado.permisos
        ConfigExchanges().guardar_comprobacion(
            f.id,
            red,
            Comprobacion(
                at=_ahora(),
                huella=huella(f, red, claves),
                puede_operar=permisos.operar if permisos is not None else None,
                puede_retirar=permisos.retirar if permisos is not None else None,
                permisos=permisos.texto if permisos is not None else "",
            ),
        )
    return resultado


# -- Las rutas -------------------------------------------------------------------------------------


@router.get("/conexiones", tags=["conexiones"])
def conexiones() -> Conexiones:
    """Cada exchange con su estado, y la configuración del conector MCP para Claude."""
    return Conexiones(exchanges=[_estado(f) for f in FICHAS], mcp=configuracion_mcp())


@router.get("/conexiones/disponibles", tags=["conexiones"])
def disponibles() -> list[ExchangeDisponible]:
    """Los exchanges que se pueden conectar, con los campos de sus claves y cómo conseguirlas."""
    return [
        ExchangeDisponible(
            id=f.id,
            nombre=f.nombre,
            tiene_pruebas=f.tiene_pruebas,
            campos=[
                CampoClave(clave=c.clave, nombre=c.nombre, secreto=c.secreto, ayuda=c.ayuda)
                for c in f.campos
            ],
            como_conseguir_pruebas=list(f.como_conseguir_pruebas),
            como_conseguir_real=list(f.como_conseguir_real),
            aviso=f.aviso,
        )
        for f in FICHAS
    ]


@router.put("/conexiones/{exchange}/claves/{red}", tags=["conexiones"], status_code=204)
def guardar_claves(exchange: str, red: RedExchange, claves: ClavesExchange) -> None:
    """Al almacén de credenciales de Windows. Nunca se devuelven. 422 en llano si falta algún campo
    o si las reales coinciden con las de pruebas."""
    # También: 404 si el exchange no existe, 422 si no tiene red de pruebas y 409 si las claves de
    # esa red las pone el entorno (Binance, como en v2: mandan ellas).
    f = _ficha(exchange)
    _exigir_red(f, red)
    estado = activacion.leer(f)
    if estado.origen[red] == "entorno":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Las claves {DE_LA_RED[red]} de {f.nombre} vienen del entorno: mandan ellas. "
                "Cámbialas allí."
            ),
        )
    with del_dominio():
        nuevas = credenciales.normalizar(f, claves.valores)
    otra: RedExchange = "real" if red == "pruebas" else "pruebas"
    de_la_otra = estado.claves[otra]
    if de_la_otra is not None and de_la_otra.mismas_que(nuevas):
        raise invalido(
            "Las claves de dinero real tienen que ser distintas de las de pruebas: si son las "
            "mismas, no hay separación entre las dos redes."
        )
    if estado.claves[red] == nuevas:
        return
    credenciales.guardar(f, red, nuevas)
    # Otras claves: lo que se probó con las de antes ya no vale (y si esa red estaba activa, se
    # desconecta hasta volver a activarla, que las prueba).
    ConfigExchanges().olvidar(f.id, red, at=_ahora())


@router.delete("/conexiones/{exchange}/claves/{red}", tags=["conexiones"], status_code=204)
def borrar_claves(exchange: str, red: RedExchange) -> None:
    # 404 si no había claves guardadas; 409 si las pone el entorno (el panel no las puede borrar).
    f = _ficha(exchange)
    if activacion.leer(f).origen[red] == "entorno":
        raise HTTPException(
            status_code=409,
            detail="Esas claves vienen del entorno: el panel no las puede borrar. Quítalas de allí.",
        )
    if not credenciales.borrar(f, red):
        raise no_encontrado(f"No había claves {DE_LA_RED[red]} de {f.nombre} guardadas.")
    ConfigExchanges().olvidar(f.id, red, at=_ahora())


@router.post("/conexiones/{exchange}/probar/{red}", tags=["conexiones"])
def probar(exchange: str, red: RedExchange) -> PruebaExchange:
    """Lee saldo y permisos con esas claves. No envía ninguna orden."""
    # 404 si no hay claves de esa red: no hay nada que probar.
    f = _ficha(exchange)
    _exigir_red(f, red)
    claves = activacion.leer(f).claves[red]
    if claves is None:
        raise no_encontrado(
            f"No hay claves {DE_LA_RED[red]} de {f.nombre} guardadas: pégalas primero."
        )
    resultado = _probar(f, red, claves)
    return PruebaExchange(
        ok=resultado.ok,
        detalle=resultado.detalle,
        saldo=[SaldoMoneda(moneda=m, cantidad=c) for m, c in resultado.saldo],
        permisos=resultado.permisos.texto if resultado.permisos is not None else None,
    )


@router.post("/conexiones/{exchange}/activar", tags=["conexiones"])
def activar(exchange: str, peticion: ActivarExchange) -> EstadoExchange:
    """Usa ese exchange en pruebas o en real. Real exige claves distintas, evidencia de pruebas
    (si el exchange tiene red de pruebas), que la clave no pueda retirar si se sabe, y 'DINERO
    REAL'. 422 en llano con lo que falte."""
    f = _ficha(exchange)
    red = peticion.red
    _exigir_red(f, red)
    if red == "real" and (peticion.confirmacion or "").strip() != CONFIRMACION_REAL:
        raise invalido(f"Para usar dinero real escribe exactamente {CONFIRMACION_REAL}.")
    estado = activacion.leer(f)
    faltan = activacion.que_falta(estado, red)
    if faltan:
        raise invalido(
            f"Todavía no se puede usar {EN_LLANO[red]} en {f.nombre}: " + " ".join(faltan)
        )
    claves = estado.claves[red]
    if claves is None:  # pragma: no cover - que_falta ya lo exige
        raise invalido(f"Faltan las claves {DE_LA_RED[red]} de {f.nombre}.")
    resultado = _probar(f, red, claves)
    if not resultado.ok:
        raise invalido(f"No se activa {EN_LLANO[red]} en {f.nombre}: {resultado.detalle}")
    retirar = resultado.permisos.retirar if resultado.permisos is not None else None
    problema = activacion.problema_de_permisos(f, red, retirar)
    if problema is not None:
        raise invalido(problema)
    ConfigExchanges().guardar_activo(f.id, red, at=_ahora())
    return _estado(f)


@router.get("/conexiones/{exchange}/mercados", tags=["conexiones"])
def mercados(exchange: str, red: RedExchange = "real") -> MercadosExchange:
    """Los pares de contado del exchange (datos públicos: no necesita claves)."""
    f = _ficha(exchange)
    _exigir_red(f, red)
    with del_dominio():
        lista = registro.conector_publico(f.id, red).mercados()
    return MercadosExchange(
        exchange=f.id,
        red=red,
        mercados=[
            MercadoExchange(
                par=m.par,
                base=m.base,
                cotizada=m.cotizada,
                nombre=nombre_hyperliquid(m.base),
                minimo_importe=m.minimo_importe,
                paso_cantidad=m.paso_cantidad,
            )
            for m in lista
        ],
    )
