"""Cuenta de práctica: comprar y vender con dinero ficticio a precios reales (docs/panel-v3-vivo.md §2).

Nada sale al exterior: las órdenes se ejecutan con `invest_ll.vivo.ejecucion` contra el libro real
del momento. Las reglas (saldo, lo que tienes, órdenes con límite, el registro en `practica/`) están
en `invest_ll.vivo.practica`; aquí solo se traducen al contrato y se valora a precios de ahora.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import APIRouter

from invest_ll.api.errores import del_dominio, invalido, no_encontrado
from invest_ll.api.schemas_v3 import (
    CuentaPractica,
    EjecucionPractica,
    NuevaOrdenPractica,
    OrdenPractica,
    PosicionPractica,
    ReinicioPractica,
    ResultadoPractica,
)
from invest_ll.nombres import nombre_hyperliquid
from invest_ll.vivo import servicio
from invest_ll.vivo.practica import (
    DECIMALES_USDC,
    OrdenNoEncontradaError,
    Resultado,
    limpio,
    recortar,
)

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.vivo.fuente import FuentePrecios
    from invest_ll.vivo.practica import CuentaDePractica, Ejecutada, Orden, Posicion

router = APIRouter()


@router.get("/practica", tags=["practica"])
def cuenta() -> CuentaPractica:
    """La cuenta de práctica valorada a precios de ahora."""
    return valorar(servicio.cuenta(), servicio.fuente())


@router.post("/practica/ordenes", tags=["practica"])
def nueva_orden(orden: NuevaOrdenPractica) -> ResultadoPractica:
    """A mercado se ejecuta ya contra el libro; con límite queda pendiente. 422 en llano si no hay
    saldo, si no tienes esa moneda o si el libro no da para tanto."""
    mercado = servicio.mercado()
    coin = mercado.canonica(orden.coin)
    if mercado.existe(coin) is False:
        raise invalido(f"Hyperliquid no tiene ninguna moneda llamada «{orden.coin}».")
    practica = servicio.cuenta()
    decimales = mercado.decimales(coin)
    with del_dominio():
        if orden.tipo == "mercado":
            if orden.precio_limite is not None:
                raise invalido(
                    "Una orden a mercado no lleva precio límite: quítalo o elige «Con límite»."
                )
            resultado = practica.a_mercado(
                mercado,
                coin,
                orden.lado,
                cantidad=orden.cantidad,
                importe=orden.importe,
                decimales=decimales,
            )
        else:
            if orden.importe is not None:
                raise invalido(
                    "Una orden con límite se da en cantidad de la moneda, no en importe: "
                    "pon la cantidad."
                )
            if orden.cantidad is None or orden.precio_limite is None:
                raise invalido("Una orden con límite necesita la cantidad y el precio límite.")
            resultado = practica.con_limite(
                mercado,
                coin,
                orden.lado,
                cantidad=orden.cantidad,
                precio_limite=orden.precio_limite,
                decimales=decimales,
            )
    return _resultado(resultado, practica, mercado)


@router.delete("/practica/ordenes/{orden_id}", tags=["practica"])
def cancelar(orden_id: str) -> CuentaPractica:
    """Cancela una orden con límite pendiente. 404 si no existe."""
    practica = servicio.cuenta()
    try:
        practica.cancelar(orden_id)
    except OrdenNoEncontradaError:
        raise no_encontrado(
            "No hay ninguna orden pendiente con ese número: quizá ya se ha ejecutado o cancelado."
        ) from None
    return valorar(practica, servicio.fuente())


@router.post("/practica/reiniciar", tags=["practica"])
def reiniciar(reinicio: ReinicioPractica) -> CuentaPractica:
    """Empieza de cero con ese saldo ficticio (el historial anterior se guarda aparte)."""
    practica = servicio.cuenta()
    with del_dominio():
        practica.reiniciar(reinicio.inicial)
    return valorar(practica, servicio.fuente())


# -- Del dominio al contrato -------------------------------------------------------------------------


def valorar(practica: CuentaDePractica, fuente: FuentePrecios) -> CuentaPractica:
    """La cuenta a precios de ahora (el medio del libro o de la lista de Hyperliquid). Si falta el
    precio de alguna posición, el valor total y la ganancia quedan sin cifra: no se inventa."""
    foto = practica.foto()
    posiciones = [_posicion(p, fuente.precio(p.coin)) for p in foto.posiciones]
    valor_total: Decimal | None = foto.saldo + foto.reservado
    for posicion in posiciones:
        valor_total = (
            None if valor_total is None or posicion.valor is None else valor_total + posicion.valor
        )
    ganancia = None if valor_total is None else valor_total - foto.inicial
    return CuentaPractica(
        inicial=limpio(foto.inicial),
        saldo=limpio(foto.saldo),
        reservado=limpio(foto.reservado),
        valor_total=None if valor_total is None else limpio(valor_total),
        ganancia=None if ganancia is None else limpio(ganancia),
        ganancia_pct=None if ganancia is None else float(ganancia / foto.inicial),
        posiciones=posiciones,
        ordenes=[_orden(o) for o in foto.ordenes],
        historial=[_ejecucion(e) for e in foto.historial],
        at=servicio.ahora(),
    )


def _posicion(p: Posicion, precio: Decimal | None) -> PosicionPractica:
    valor = None if precio is None else recortar(p.cantidad * precio, DECIMALES_USDC)
    ganancia = None if valor is None else recortar(valor - p.coste, DECIMALES_USDC)
    return PosicionPractica(
        coin=p.coin,
        nombre=nombre_hyperliquid(p.coin),
        cantidad=limpio(p.cantidad),
        precio_medio=p.precio_medio,
        precio=None if precio is None else limpio(precio),
        valor=valor,
        ganancia=ganancia,
        ganancia_pct=None if ganancia is None or not p.coste else float(ganancia / p.coste),
    )


def _orden(o: Orden) -> OrdenPractica:
    return OrdenPractica(
        id=o.id,
        coin=o.coin,
        nombre=nombre_hyperliquid(o.coin),
        lado=o.lado,
        cantidad=limpio(o.cantidad),
        precio_limite=limpio(o.precio_limite),
        creada=o.creada,
    )


def _ejecucion(e: Ejecutada) -> EjecucionPractica:
    return EjecucionPractica(
        id=e.id,
        coin=e.coin,
        nombre=nombre_hyperliquid(e.coin),
        lado=e.lado,
        tipo=e.tipo,
        cantidad=limpio(e.cantidad),
        precio=limpio(e.precio),
        importe=limpio(e.importe),
        comision=limpio(e.comision),
        at=e.at,
    )


def _resultado(
    resultado: Resultado, practica: CuentaDePractica, fuente: FuentePrecios
) -> ResultadoPractica:
    return ResultadoPractica(
        resumen=resultado.resumen,
        ejecucion=None if resultado.ejecutada is None else _ejecucion(resultado.ejecutada),
        orden=None if resultado.orden is None else _orden(resultado.orden),
        cuenta=valorar(practica, fuente),
    )
