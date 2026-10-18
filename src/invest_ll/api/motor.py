"""El motor de los bots, visto desde el panel (docs/panel-v5.md: siempre encendido).

Los bots viven en su servicio aparte (`bots.servicio`, 127.0.0.1:8602), que sigue aunque cierres el
panel. Desde aquí: si está en marcha y desde cuándo, arrancarlo, reiniciarlo para traer código
nuevo (los bots se paran unos segundos y lo apuntan como hueco), y sus opciones: arrancar con
Windows (un .vbs en la carpeta Inicio) y que Windows no se duerma mientras haya bots en marcha.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter

from invest_ll.api.errores import invalido
from invest_ll.api.schemas_v5 import EstadoMotor, OpcionesMotor
from invest_ll.bots import servicio

router = APIRouter()


def _estado() -> EstadoMotor:
    salud = servicio.en_marcha()
    opciones = servicio.leer_opciones()
    con_windows = servicio.inicio_instalado()
    if salud is None:
        return EstadoMotor(
            en_marcha=False,
            pid=None,
            desde=None,
            bots=0,
            bots_en_marcha=0,
            codigo_nuevo=False,
            arranca_con_windows=con_windows,
            mantener_despierto=opciones.mantener_despierto,
            texto="El motor de los bots está parado: ningún bot opera hasta que lo arranques.",
        )
    desde = salud.get("desde")
    version = salud.get("version")
    nuevo = isinstance(version, int | float) and servicio.version_del_codigo() > float(version) + 1
    bots, en_marcha = int(salud.get("bots") or 0), int(salud.get("en_marcha") or 0)
    return EstadoMotor(
        en_marcha=True,
        pid=salud.get("pid"),
        desde=datetime.fromisoformat(desde) if isinstance(desde, str) else None,
        bots=bots,
        bots_en_marcha=en_marcha,
        codigo_nuevo=nuevo,
        arranca_con_windows=con_windows,
        mantener_despierto=opciones.mantener_despierto,
        texto=(
            f"En marcha aparte del panel: {en_marcha} de {bots} bots operan aunque cierres esta "
            "ventana, mientras el ordenador esté encendido."
        ),
    )


@router.get("/motor", tags=["motor"])
def estado() -> EstadoMotor:
    return _estado()


@router.post("/motor/arrancar", tags=["motor"])
async def arrancar() -> EstadoMotor:
    """Lo arranca si está parado y espera a que conteste (como mucho 20 s)."""
    if await asyncio.to_thread(servicio.en_marcha) is None:
        await asyncio.to_thread(servicio.arrancar_en_segundo_plano)
        if await asyncio.to_thread(servicio.esperar_en_marcha) is None:
            raise invalido("El motor de los bots no arrancó: mira bots/motor.log.")
    return await asyncio.to_thread(_estado)


@router.post("/motor/reiniciar", tags=["motor"])
async def reiniciar() -> EstadoMotor:
    """Lo para con calma (guarda cada bot) y lo vuelve a arrancar con el código de ahora."""
    if await asyncio.to_thread(servicio.apagar):
        for _ in range(40):
            if await asyncio.to_thread(servicio.en_marcha) is None:
                break
            await asyncio.sleep(0.25)
    return await arrancar()


@router.put("/motor/opciones", tags=["motor"])
def opciones(cambio: OpcionesMotor) -> EstadoMotor:
    if cambio.arranca_con_windows is not None:
        if cambio.arranca_con_windows:
            servicio.instalar_inicio()
        else:
            servicio.quitar_inicio()
    if cambio.mantener_despierto is not None:
        servicio.guardar_opciones(servicio.Opciones(mantener_despierto=cambio.mantener_despierto))
    return _estado()
