"""Las métricas de un bot, sacadas de sus operaciones (docs/panel-v5.md §4).

Todo sale de repasar `operaciones.jsonl` en orden, con el mismo coste medio que lleva su cuenta
(`cuenta.Cuenta`): una compra suma lo pagado (comisión incluida) al coste de esa moneda; una venta
se lleva la parte proporcional del coste, y su **resultado** es lo cobrado (menos la comisión)
menos esa parte. Así una venta "gana" o "pierde" igual que la vería quien lleva las cuentas a mano.

Con pocas operaciones cerradas estas cifras dicen poco, y se dice (`aviso`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from invest_ll.bots.cuenta import usdc

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from invest_ll.bots.cuenta import Posicion
    from invest_ll.bots.registro import Operacion

CERO: Final = Decimal(0)
POCAS_CERRADAS: Final = 5
"""Menos ventas cerradas que esto: las métricas de aciertos aún no dicen nada."""


def resultado_venta(
    cantidad_antes: Decimal,
    coste_antes: Decimal,
    vendida: Decimal,
    importe: Decimal,
    comision: Decimal,
) -> Decimal:
    """Lo que ganó o perdió una venta: lo cobrado menos la comisión y la parte del coste que se
    lleva (toda, si vende toda la posición), como `Cuenta.vender`."""
    parte = (
        coste_antes if vendida >= cantidad_antes else usdc(coste_antes * vendida / cantidad_antes)
    )
    return usdc(importe - comision - parte)


def resultados(cronologicas: Sequence[Operacion]) -> list[Decimal | None]:
    """El resultado de cada operación, en el mismo orden: el de cada venta, o None en las compras
    (y en una venta de algo que no constaba comprado)."""
    cantidades: dict[str, Decimal] = {}
    costes: dict[str, Decimal] = {}
    salida: list[Decimal | None] = []
    for o in cronologicas:
        cantidad = cantidades.get(o.coin, CERO)
        coste = costes.get(o.coin, CERO)
        if o.lado == "compra":
            cantidades[o.coin] = cantidad + o.cantidad
            costes[o.coin] = coste + o.importe + o.comision
            salida.append(None)
            continue
        if cantidad <= 0:
            salida.append(None)
            continue
        vendida = min(o.cantidad, cantidad)
        salida.append(resultado_venta(cantidad, coste, vendida, o.importe, o.comision))
        if vendida >= cantidad:
            cantidades.pop(o.coin, None)
            costes.pop(o.coin, None)
        else:
            costes[o.coin] = coste - usdc(coste * vendida / cantidad)
            cantidades[o.coin] = cantidad - vendida
    return salida


def _tiempo_dentro(
    cronologicas: Sequence[Operacion], desde: datetime, ahora: datetime
) -> float | None:
    """La parte del tiempo, desde que arrancó, en que tuvo alguna moneda comprada."""
    total = (ahora - desde).total_seconds()
    if total <= 0:
        return None
    cantidades: dict[str, Decimal] = {}
    dentro = 0.0
    entro: datetime | None = None
    for o in cronologicas:
        antes = any(c > 0 for c in cantidades.values())
        if o.lado == "compra":
            cantidades[o.coin] = cantidades.get(o.coin, CERO) + o.cantidad
        else:
            cantidades[o.coin] = max(CERO, cantidades.get(o.coin, CERO) - o.cantidad)
        despues = any(c > 0 for c in cantidades.values())
        if not antes and despues:
            entro = o.at
        elif antes and not despues and entro is not None:
            dentro += (o.at - entro).total_seconds()
            entro = None
    if entro is not None:
        dentro += (ahora - entro).total_seconds()
    return min(1.0, max(0.0, dentro / total))


@dataclass(frozen=True, slots=True)
class Metricas:
    operaciones: int
    compras: int
    ventas: int
    cerradas: int
    """Ventas con resultado conocido."""
    aciertos: float | None
    """La parte de las cerradas que ganó algo."""
    factor_beneficio: float | None
    """Lo ganado en las ventas que ganaron entre lo perdido en las que perdieron."""
    ganancia_media: Decimal | None
    perdida_media: Decimal | None
    realizada: Decimal
    sin_realizar: Decimal | None
    comisiones: Decimal
    tiempo_dentro: float | None
    operaciones_dia: float | None
    aviso: str | None


def metricas(
    cronologicas: Sequence[Operacion],
    *,
    desde: datetime,
    ahora: datetime,
    posiciones: Mapping[str, Posicion],
    precios: Mapping[str, Decimal],
) -> Metricas:
    """Las métricas de un bot con estas operaciones (de la más antigua a la más reciente)."""
    res = [r for r in resultados(cronologicas) if r is not None]
    ganadas = [r for r in res if r > 0]
    perdidas = [r for r in res if r < 0]
    suma_ganado = sum(ganadas, CERO)
    suma_perdido = -sum(perdidas, CERO)

    sin_realizar: Decimal | None = CERO
    for coin, p in posiciones.items():
        precio = precios.get(coin)
        if precio is None:
            sin_realizar = None
            break
        sin_realizar += p.cantidad * precio - p.coste

    dias = (ahora - desde).total_seconds() / 86_400
    n = len(cronologicas)
    aviso: str | None = None
    if not n:
        aviso = "Aún no ha operado: no hay nada que medir."
    elif len(res) < POCAS_CERRADAS:
        cerradas = (
            "ninguna venta cerrada"
            if not res
            else ("una venta cerrada" if len(res) == 1 else f"{len(res)} ventas cerradas")
        )
        aviso = (
            f"Con {cerradas}, los aciertos y el factor de beneficio aún no dicen nada: es pronto "
            "para sacar conclusiones."
        )
    return Metricas(
        operaciones=n,
        compras=sum(1 for o in cronologicas if o.lado == "compra"),
        ventas=sum(1 for o in cronologicas if o.lado == "venta"),
        cerradas=len(res),
        aciertos=len(ganadas) / len(res) if res else None,
        factor_beneficio=float(suma_ganado / suma_perdido) if suma_perdido > 0 else None,
        ganancia_media=usdc(suma_ganado / len(ganadas)) if ganadas else None,
        perdida_media=usdc(-suma_perdido / len(perdidas)) if perdidas else None,
        realizada=usdc(sum(res, CERO)),
        sin_realizar=usdc(sin_realizar) if sin_realizar is not None else None,
        comisiones=usdc(sum((o.comision for o in cronologicas), CERO)),
        tiempo_dentro=_tiempo_dentro(cronologicas, desde, ahora),
        operaciones_dia=n / dias if dias >= 1 else None,
        aviso=aviso,
    )
