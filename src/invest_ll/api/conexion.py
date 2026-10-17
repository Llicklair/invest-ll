"""Conexión con Binance y modo de operación desde el panel (docs/panel-v2.md, 4.6).

Los cuatro cerrojos de `live/mode.py` no se tocan: el panel solo cambia DE DÓNDE salen el modo y
las claves (el almacén de credenciales de Windows y `config/panel.json`, fuera de git) cuando no
están en el entorno. Si el entorno los define, mandan ellos. La lógica vive en `live.modo_panel`
(qué modo, de dónde, con qué evidencia), `live.credenciales` (el almacén) y
`live.prueba_conexion` (leer el saldo y explicar los fallos); aquí solo se traduce.

**Las claves no salen nunca**: ninguna respuesta las lleva, ni enteras ni en parte, y ningún
mensaje de error tampoco. Solo se dice si están y de dónde vienen.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter, HTTPException

from invest_ll.api import cartera as rutas_cartera
from invest_ll.api.errores import invalido, no_encontrado
from invest_ll.api.modo import modo_efectivo
from invest_ll.api.schemas_v2 import (
    CambioModo,
    Cerrojo,
    Conexion,
    EstadoRed,
    ModoDisponible,
    NuevasClaves,
    PruebaConexion,
    Red,
    Saldo,
    SaldoMoneda,
)
from invest_ll.errors import InvestLLError
from invest_ll.live import credenciales, prueba_conexion
from invest_ll.live.mode import VAR_MODO, VAR_TESTNET_HECHA, Simulation
from invest_ll.live.modo_panel import (
    MODOS,
    ConfigPanel,
    Fuentes,
    ModoPanel,
    claves_efectivas,
    entorno_efectivo,
    fuentes_actuales,
    modo_del_panel,
    origen_de_las_claves,
    origen_del_modo,
    resolver,
)

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.credenciales import Claves

router = APIRouter()

CONFIRMACION_REAL: Final = "DINERO REAL"
LO_FIJA_EL_ENTORNO: Final = (
    f"El modo lo fija {VAR_MODO} en el entorno: quítalo de ahí para elegirlo desde el panel."
)
NOMBRE_RED: Final[dict[Red, str]] = {"pruebas": "la red de pruebas", "real": "dinero real"}
EN_LLANO: Final[dict[ModoPanel, str]] = {
    "simulacion": "simulación",
    "pruebas": "la red de pruebas",
    "real": "dinero real",
}
MODO_PEDIDO_EN_EL_ENTORNO: Final[dict[str, ModoPanel]] = {"testnet": "pruebas", "real": "real"}


def leer_saldo(red: Red, claves: Claves) -> dict[str, Decimal]:
    """Habla con el exchange. Los tests la sustituyen: la suite corre sin red."""
    return prueba_conexion.leer_saldo(red, claves)


def _verificada_en_pruebas(f: Fuentes) -> bool:
    valor = entorno_efectivo(f).get(VAR_TESTNET_HECHA, "").strip().lower()
    return valor in ("1", "true", "si", "yes")


def _claves_distintas(f: Fuentes) -> bool | None:
    """`None` si faltan las reales (no hay nada que comparar)."""
    reales = claves_efectivas(f, "real")
    if reales is None:
        return None
    pruebas = claves_efectivas(f, "pruebas")
    return pruebas is None or pruebas.clave != reales.clave


def que_falta(f: Fuentes, modo: ModoPanel) -> list[str]:
    """Lo que falta para poder pasar a ese modo, en llano. Vacío si se puede."""
    faltan: list[str] = []
    if modo == "pruebas" and claves_efectivas(f, "pruebas") is None:
        faltan.append(
            "Guarda las claves de la red de pruebas (testnet.binance.vision, tipo HMAC-SHA256)."
        )
    if modo == "real":
        if claves_efectivas(f, "real") is None:
            faltan.append(
                "Guarda las claves de dinero real (con permiso de lectura y spot, nunca de "
                "retirada)."
            )
        if not _verificada_en_pruebas(f):
            faltan.append(
                "Haz al menos una orden en la red de pruebas que se ejecute: es la prueba de que "
                "esa etapa está hecha."
            )
        if _claves_distintas(f) is False:
            faltan.append("Las claves de dinero real tienen que ser distintas de las de pruebas.")
    return faltan


def _modo_actual(f: Fuentes) -> tuple[ModoPanel, str | None]:
    """El modo efectivo y, si no se pudo activar el pedido, por qué."""
    try:
        efectivo = resolver(f)
    except InvestLLError as error:
        # El entorno pide un modo que no se puede activar: se dice cuál y por qué, sin fingir
        # que se está en otro.
        pedido = f.entorno.get(VAR_MODO, "").strip().lower()
        return MODO_PEDIDO_EN_EL_ENTORNO.get(pedido, "simulacion"), str(error)
    return modo_del_panel(efectivo.modo), efectivo.aviso


def _cerrojos(f: Fuentes, actual: ModoPanel) -> list[Cerrojo]:
    origen_real = origen_de_las_claves(f, "real")
    distintas = _claves_distintas(f)
    verificada = _verificada_en_pruebas(f)
    return [
        Cerrojo(
            nombre="Elegir dinero real",
            ok=actual == "real",
            detalle=(
                "Activo: las órdenes mueven dinero de verdad."
                if actual == "real"
                else f"Ahora estás en {EN_LLANO[actual]}. Se activa escribiendo {CONFIRMACION_REAL}."
            ),
        ),
        Cerrojo(
            nombre="Claves de dinero real",
            ok=origen_real != "ninguno",
            detalle={
                "panel": "Guardadas en el almacén de credenciales de Windows.",
                "entorno": "Puestas en el entorno (INVEST_LL_LIVE_KEY).",
                "ninguno": "Faltan: pégalas en este mismo paso.",
            }[origen_real],
        ),
        Cerrojo(
            nombre="Haber operado en la red de pruebas",
            ok=verificada,
            detalle=(
                f"{f.ordenes_de_pruebas} orden(es) de pruebas ejecutadas en tu registro."
                if f.ordenes_de_pruebas
                else "Declarado en el entorno (INVEST_LL_TESTNET_VERIFIED)."
                if verificada
                else "Todavía no hay ninguna orden de pruebas ejecutada en tu registro."
            ),
        ),
        Cerrojo(
            nombre="Claves reales distintas de las de pruebas",
            ok=distintas is True,
            detalle=(
                "Son distintas."
                if distintas
                else "Coinciden con las de pruebas: tienen que ser otras."
                if distintas is False
                else "Faltan las claves de dinero real."
            ),
        ),
    ]


def _estado(f: Fuentes | None = None) -> Conexion:
    fuentes = f or fuentes_actuales()
    actual, aviso = _modo_actual(fuentes)
    origen = origen_del_modo(fuentes.entorno)
    redes = [
        EstadoRed(
            red=red,
            claves_guardadas=origen_de_las_claves(fuentes, red) != "ninguno",
            origen=origen_de_las_claves(fuentes, red),
            verificada=(
                fuentes.ordenes_de_pruebas > 0 if red == "pruebas" else fuentes.ordenes_reales > 0
            ),
        )
        for red in credenciales.REDES
    ]
    modos: list[ModoDisponible] = []
    for modo in MODOS:
        faltan = que_falta(fuentes, modo)
        if origen == "entorno" and modo != actual:
            faltan.insert(0, LO_FIJA_EL_ENTORNO)
        # Por qué no se activó el modo pedido: va con ESE modo (el del panel o el del entorno),
        # no con el de simulación al que se volvió.
        pedido = actual if origen == "entorno" or fuentes.modo_panel is None else fuentes.modo_panel
        if modo == pedido and aviso is not None and aviso not in faltan:
            faltan.append(aviso)
        modos.append(ModoDisponible(modo=modo, disponible=not faltan, que_falta=faltan))
    return Conexion(
        modo=actual,
        modo_origen=origen,
        redes=redes,
        modos=modos,
        cerrojos_real=_cerrojos(fuentes, actual),
    )


@router.get("/conexion", tags=["conexion"])
def conexion() -> Conexion:
    return _estado()


@router.put("/conexion/claves/{red}", tags=["conexion"], status_code=204)
def guardar_claves(red: Red, claves: NuevasClaves) -> None:
    """Guarda las claves en el almacén de credenciales. 422 si las reales coinciden con las de
    pruebas. Nunca se devuelven por ninguna ruta."""
    try:
        nuevas = credenciales.Claves(clave=claves.clave.strip(), secreto=claves.secreto.strip())
    except ValueError:
        raise invalido("La clave y el secreto no pueden estar vacíos.") from None
    otra: Red = "real" if red == "pruebas" else "pruebas"
    de_la_otra = claves_efectivas(fuentes_actuales(), otra)
    if de_la_otra is not None and de_la_otra.clave == nuevas.clave:
        raise invalido(
            "Las claves de dinero real tienen que ser distintas de las de pruebas: si son la "
            "misma, no hay separación entre modos."
        )
    credenciales.guardar(red, nuevas)


@router.delete("/conexion/claves/{red}", tags=["conexion"], status_code=204)
def borrar_claves(red: Red) -> None:
    """404 si no había claves guardadas para esa red."""
    if not credenciales.borrar(red):
        raise no_encontrado(f"no había claves de {NOMBRE_RED[red]} guardadas en el panel")
    config = ConfigPanel()
    # Sin claves, el modo elegido en el panel ya no se puede activar: se vuelve a simulación a
    # propósito, en vez de dejar un modo pedido que nunca se cumple.
    if config.modo() == red:
        config.guardar_modo("simulacion")


@router.post("/conexion/probar/{red}", tags=["conexion"])
def probar(red: Red) -> PruebaConexion:
    """Lee el saldo con esas claves. No envía ninguna orden."""
    prueba = prueba_conexion.probar(red, claves_efectivas(fuentes_actuales(), red), leer_saldo)
    return PruebaConexion(
        ok=prueba.ok,
        detalle=prueba.detalle,
        saldo=[SaldoMoneda(moneda=m, cantidad=c) for m, c in prueba.saldo],
    )


@router.put("/conexion/modo", tags=["conexion"])
def cambiar_modo(cambio: CambioModo) -> Conexion:
    """422 si faltan condiciones (dice cuáles) o, para real, la confirmación 'DINERO REAL'.
    409 si el modo lo fija el entorno."""
    f = fuentes_actuales()
    if origen_del_modo(f.entorno) == "entorno":
        raise HTTPException(status_code=409, detail=LO_FIJA_EL_ENTORNO)
    if cambio.modo == "real" and (cambio.confirmacion or "").strip() != CONFIRMACION_REAL:
        raise invalido(f"Para pasar a dinero real escribe exactamente {CONFIRMACION_REAL}.")
    faltan = que_falta(f, cambio.modo)
    if faltan:
        raise invalido("Todavía no se puede: " + " ".join(faltan))
    # La última palabra la tienen los cerrojos de live/mode.py, con el entorno que quedaría.
    pedido = replace(f, modo_panel=cambio.modo)
    resultado = resolver(pedido)
    if modo_del_panel(resultado.modo) != cambio.modo:
        raise invalido(resultado.aviso or "Ese modo no se puede activar ahora.")
    ConfigPanel().guardar_modo(cambio.modo)
    return _estado(pedido)


@router.get("/saldo", tags=["conexion"])
def saldo() -> Saldo:
    """Saldo del exchange en el modo activo. 409 en simulación."""
    modo = modo_efectivo().modo
    if isinstance(modo, Simulation):
        raise HTTPException(
            status_code=409,
            detail="En simulación no hay exchange: no hay saldo que leer. Conecta Binance primero.",
        )
    try:
        libres = rutas_cartera.broker_para(modo).balance()
    except InvestLLError as error:
        # Lo mismo que Probar la conexión: el JSON de Binance no se le enseña a nadie.
        red: credenciales.Red = "pruebas" if modo_del_panel(modo) == "pruebas" else "real"
        raise invalido(prueba_conexion.explicar_fallo(error, red)) from None
    return Saldo(
        modo=modo_del_panel(modo),
        saldo=[SaldoMoneda(moneda=m, cantidad=c) for m, c in prueba_conexion.ordenar_saldo(libres)],
        at=datetime.now(UTC),
    )
