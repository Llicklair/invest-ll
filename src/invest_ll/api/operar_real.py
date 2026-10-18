"""Operar de verdad en un exchange desde el panel (docs/panel-v5.md: Operar → Hyperliquid).

Órdenes manuales de contado con la cuenta conectada en Conexiones, cada una confirmada tecleando
la cantidad (como las de Invertir desde v2). Lo que protege cada orden:

- va a la red **activa** del exchange (pruebas o real, la de Conexiones), y la petición dice cuál
  estaba viendo quien confirmó: si no coincide, no se envía (409);
- la cantidad tecleada tiene que ser la de la orden (422 si no);
- el conector se pide a `exchanges.registro.conector`, que vuelve a comprobar los cerrojos de
  activación en ese momento (claves probadas, evidencia de pruebas para real, permisos sin
  retirar);
- un id de cliente por orden: un reintento no la duplica; si se corta a medias, se dice que no se
  sabe si se ejecutó (nunca se adivina);
- toda orden resuelta se anota en el registro (`ledger/`) con su modo y su exchange: en pruebas,
  esa es la evidencia que pide activar el dinero real.

Ninguna IA llega aquí: el conector MCP no tiene herramientas de órdenes. Lo que sale a la red, por
`_conector`, que los tests sustituyen.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from fastapi import APIRouter

from invest_ll import llano
from invest_ll.api.errores import conflicto, invalido, no_encontrado
from invest_ll.api.schemas_v5 import (
    EstadoOperarReal,
    MercadoReal,
    NuevaOrdenReal,
    OrdenAbiertaReal,
    ResultadoOrdenReal,
    SaldoReal,
)
from invest_ll.exchanges import activacion, registro
from invest_ll.exchanges.anotar import anotar
from invest_ll.exchanges.conector import EstadoDesconocidoError, ExchangeError
from invest_ll.exchanges.mercados import mercado_de

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.exchanges.conector import Conector, Mercado, OrdenExchange, Red
    from invest_ll.exchanges.fichas import Ficha

router = APIRouter()

# -- Lo que sale a la red (sustituible en los tests) ----------------------------------------------


def _red_activa(f: Ficha) -> Red | None:
    """La red en que está activo el exchange (lo que se cumple ahora), o None."""
    activo = activacion.activo_efectivo(activacion.leer(f))
    return None if activo == "sin_conectar" else activo


def _que_falta(f: Ficha) -> list[str]:
    return activacion.por_que_no(activacion.leer(f), "pruebas")


def _conector(exchange: str, red: Red) -> Conector:
    return registro.conector(exchange, red)


# -- Por dentro ----------------------------------------------------------------------------------


def _ficha(exchange: str) -> Ficha:
    try:
        return registro.ficha(exchange)
    except ExchangeError as error:
        raise no_encontrado(str(error)) from error


def leer_tecleado(texto: str) -> Decimal | None:
    """Lo tecleado como número, en castellano o no: '0,095', '0.095', '1.234,5'. None si no es uno.

    Se compara el valor y no la escritura (como en Invertir): '0,0950' y '0,095' son lo mismo."""
    t = texto.strip().replace(" ", "").replace(chr(0xA0), "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(t)
    except (InvalidOperation, ValueError):
        return None
    return valor if valor.is_finite() else None


def _mercado(m: Mercado) -> MercadoReal:
    return MercadoReal(
        par=m.par,
        base=m.base,
        cotizada=m.cotizada,
        minimo_importe=m.minimo_importe,
        minimo_cantidad=m.minimo_cantidad,
        paso_cantidad=m.paso_cantidad,
        paso_precio=m.paso_precio,
        comision_tomador=m.comision_tomador,
    )


def _abierta(o: OrdenExchange) -> OrdenAbiertaReal:
    return OrdenAbiertaReal(
        id_cliente=o.id_cliente,
        par=o.par,
        lado=o.lado,
        tipo=o.tipo,
        cantidad=o.cantidad,
        ejecutada=o.ejecutada,
        precio=o.precio_medio,
        at=o.at,
    )


def _sin_mercado(nombre: str, coin: str, red: Red) -> str:
    donde = "en su red de pruebas" if red == "pruebas" else "al contado"
    return (
        f"{nombre} no tiene mercado de contado de {coin} {donde}: aquí solo se opera al contado "
        "(sin apalancamiento). Elige otra moneda."
        + (" En la red de pruebas, PURR suele tener libro." if red == "pruebas" else "")
    )


def _texto(o: OrdenExchange, red: Red, nombre: str) -> str:
    base = o.par.split("/")[0]
    cotizada = o.par.split("/")[-1]
    donde = " (red de pruebas)" if red == "pruebas" else ""
    verbo = "Compraste" if o.lado == "compra" else "Vendiste"
    if o.estado == "rechazada" or (o.estado == "cancelada" and o.ejecutada <= 0):
        return f"{nombre} no la ejecutó{donde}: no se ha {'comprado' if o.lado == 'compra' else 'vendido'} nada."
    if o.estado == "abierta":
        precio = (
            f" a {llano.cantidad(o.precio_medio or Decimal(0))} {cotizada}"
            if o.tipo == "limite"
            else ""
        )
        return (
            f"Orden puesta en {nombre}{donde}: {'comprar' if o.lado == 'compra' else 'vender'} "
            f"{llano.cantidad(o.cantidad)} {base}{precio}. Sigue abierta hasta que se ejecute o la canceles."
        )
    a = f" a {llano.cantidad(o.precio_medio)} {cotizada}" if o.precio_medio else ""
    comision = (
        f" Comisión: {llano.cantidad(o.comision)} {o.comision_moneda or cotizada}."
        if o.comision is not None
        else ""
    )
    if o.ejecutada < o.cantidad:
        return (
            f"Solo se ejecutó una parte{donde}: {verbo.lower()} {llano.cantidad(o.ejecutada)} de "
            f"{llano.cantidad(o.cantidad)} {base}{a}.{comision}"
        )
    return f"{verbo} {llano.cantidad(o.ejecutada)} {base}{a}{donde}.{comision}"


def _resultado(o: OrdenExchange, red: Red, nombre: str, exchange: str) -> ResultadoOrdenReal:
    anotada = False
    texto = _texto(o, red, nombre)
    if o.estado != "abierta":
        try:
            anotar(o, exchange=exchange, red=red)
            anotada = True
        except Exception as error:  # la orden ya salió: el fallo de anotarla no la deshace
            texto += f" No se pudo anotar en el registro de órdenes: {error}"
    return ResultadoOrdenReal(
        estado=o.estado,
        texto=texto,
        id_cliente=o.id_cliente,
        par=o.par,
        lado=o.lado,
        red=red,
        cantidad=o.cantidad,
        ejecutada=o.ejecutada,
        precio_medio=o.precio_medio,
        comision=o.comision,
        comision_moneda=o.comision_moneda,
        anotada=anotada,
    )


# -- Las rutas -------------------------------------------------------------------------------------


@router.get("/operar/{exchange}", tags=["operar"])
def estado(exchange: str, coin: str) -> EstadoOperarReal:
    """Si se puede operar de verdad con esa moneda, en qué red, con qué saldo y qué órdenes hay
    abiertas. Sin conectar no es un error: `conectado` false y `que_falta` en llano."""
    f = _ficha(exchange)
    ahora = datetime.now(UTC)
    red = _red_activa(f)
    vacio = EstadoOperarReal(
        exchange=f.id,
        nombre=f.nombre,
        red=red,
        conectado=False,
        que_falta=[],
        coin=coin,
        mercado=None,
        aviso=None,
        saldo=[],
        ordenes_abiertas=[],
        at=ahora,
    )
    if red is None:
        return vacio.model_copy(
            update={"que_falta": _que_falta(f) or [f"{f.nombre} no está conectado."]}
        )
    try:
        c = _conector(f.id, red)
        m = mercado_de(c, coin)
        saldo = c.saldo()
        abiertas = c.ordenes_abiertas(m.par if m is not None else None)
    except ExchangeError as error:
        return vacio.model_copy(update={"conectado": True, "aviso": str(error)})
    return vacio.model_copy(
        update={
            "conectado": True,
            "mercado": _mercado(m) if m is not None else None,
            "aviso": None if m is not None else _sin_mercado(f.nombre, coin, red),
            "saldo": [SaldoReal(moneda=k, cantidad=v) for k, v in sorted(saldo.items()) if v > 0],
            "ordenes_abiertas": [_abierta(o) for o in abiertas],
        }
    )


@router.post("/operar/{exchange}/ordenes", tags=["operar"])
def enviar(exchange: str, peticion: NuevaOrdenReal) -> ResultadoOrdenReal:
    """Envía UNA orden de contado de verdad, con la cantidad tecleada. 409 si el exchange no está
    conectado o no está en la red que se veía; 422 si lo tecleado no coincide o el exchange la
    rechaza. Si se corta a medias: `estado` 'desconocido' (no se sabe si se ejecutó)."""
    f = _ficha(exchange)
    red = _red_activa(f)
    if red is None:
        raise conflicto(f"{f.nombre} no está conectado: conéctalo en Conexiones antes de operar.")
    if peticion.red != red:
        otra = "la red de pruebas" if red == "pruebas" else "dinero real"
        raise conflicto(
            f"La pantalla mostraba {'la red de pruebas' if peticion.red == 'pruebas' else 'dinero real'}, "
            f"pero {f.nombre} está ahora en {otra}: no se ha enviado nada. Recarga y vuelve a mirar."
        )
    tecleado = leer_tecleado(peticion.escrito)
    if tecleado is None or tecleado != peticion.cantidad:
        raise invalido(
            f"Lo escrito ({peticion.escrito.strip() or 'nada'}) no coincide con la cantidad "
            f"({llano.cantidad(peticion.cantidad)}): no se ha enviado nada."
        )
    if peticion.tipo == "limite" and peticion.precio is None:
        raise invalido("Una orden límite necesita su precio.")
    try:
        c = _conector(f.id, red)
    except ExchangeError as error:
        raise conflicto(str(error)) from error
    m = mercado_de(c, peticion.coin)
    if m is None:
        raise invalido(_sin_mercado(f.nombre, peticion.coin, red))
    id_cliente = f"ill{secrets.token_hex(12)}"
    try:
        orden = c.enviar(
            m.par,
            peticion.lado,
            peticion.cantidad,
            id_cliente=id_cliente,
            tipo=peticion.tipo,
            precio=peticion.precio if peticion.tipo == "limite" else None,
        )
    except EstadoDesconocidoError:
        return ResultadoOrdenReal(
            estado="desconocido",
            texto=(
                f"Se envió a {f.nombre} y se perdió la conexión: no se sabe si se ejecutó. Mira tus "
                f"órdenes y tu saldo en {f.nombre} antes de repetirla."
            ),
            id_cliente=id_cliente,
            par=m.par,
            lado=peticion.lado,
            red=red,
            cantidad=peticion.cantidad,
            ejecutada=Decimal(0),
            precio_medio=None,
            comision=None,
            comision_moneda=None,
            anotada=False,
        )
    except ExchangeError as error:
        raise invalido(f"{f.nombre} no la aceptó: {error}") from error
    return _resultado(orden, red, f.nombre, f.id)


@router.delete("/operar/{exchange}/ordenes/{id_cliente}", tags=["operar"])
def cancelar(exchange: str, id_cliente: str, coin: str) -> ResultadoOrdenReal:
    """Cancela una orden abierta (lo ya ejecutado de ella, se queda). 404 si no está."""
    f = _ficha(exchange)
    red = _red_activa(f)
    if red is None:
        raise conflicto(f"{f.nombre} no está conectado.")
    try:
        c = _conector(f.id, red)
        m = mercado_de(c, coin)
        if m is None:
            raise invalido(_sin_mercado(f.nombre, coin, red))
        orden = c.cancelar(m.par, id_cliente=id_cliente)
    except ExchangeError as error:
        raise invalido(f"{f.nombre} no la canceló: {error}") from error
    if orden is None:
        raise no_encontrado(f"No hay ninguna orden «{id_cliente}» en {f.nombre}.")
    return _resultado(orden, red, f.nombre, f.id)
