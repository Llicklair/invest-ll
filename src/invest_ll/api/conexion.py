"""Conexión con Binance y modo de operación desde el panel (docs/panel-v2.md, 4.6).

ESQUELETO DEL CONTRATO v2: rutas y modelos fijados; los cuerpos, pendientes.

Los cuatro cerrojos de `live/mode.py` no se tocan: el panel solo cambia DE DÓNDE salen el modo y
las claves (el almacén de credenciales de Windows y `config/panel.json`, fuera de git) cuando no
están en el entorno. Si el entorno los define, mandan ellos.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.schemas_v2 import (
    CambioModo,
    Conexion,
    NuevasClaves,
    PruebaConexion,
    Red,
    Saldo,
)

router = APIRouter()

PENDIENTE = "pendiente de implementar"


@router.get("/conexion", tags=["conexion"])
def conexion() -> Conexion:
    raise NotImplementedError(PENDIENTE)


@router.put("/conexion/claves/{red}", tags=["conexion"], status_code=204)
def guardar_claves(red: Red, claves: NuevasClaves) -> None:
    """Guarda las claves en el almacén de credenciales. 422 si las reales coinciden con las de
    pruebas. Nunca se devuelven por ninguna ruta."""
    raise NotImplementedError(PENDIENTE)


@router.delete("/conexion/claves/{red}", tags=["conexion"], status_code=204)
def borrar_claves(red: Red) -> None:
    """404 si no había claves guardadas para esa red."""
    raise NotImplementedError(PENDIENTE)


@router.post("/conexion/probar/{red}", tags=["conexion"])
def probar(red: Red) -> PruebaConexion:
    """Lee el saldo con esas claves. No envía ninguna orden."""
    raise NotImplementedError(PENDIENTE)


@router.put("/conexion/modo", tags=["conexion"])
def cambiar_modo(cambio: CambioModo) -> Conexion:
    """422 si faltan condiciones (dice cuáles) o, para real, la confirmación 'DINERO REAL'.
    409 si el modo lo fija el entorno."""
    raise NotImplementedError(PENDIENTE)


@router.get("/saldo", tags=["conexion"])
def saldo() -> Saldo:
    """Saldo del exchange en el modo activo. 409 en simulación."""
    raise NotImplementedError(PENDIENTE)
