"""Un exchange en memoria, para las pruebas de todos (bots reales, estrategias, Conexiones).

Hace lo que promete el protocolo `Conector`, sin red: mercados con sus pasos y mínimos, precios,
libro, velas, saldo y órdenes (con id de cliente: un reintento no duplica). Y deja **provocar** lo
que en un exchange de verdad pasa sin avisar:

- `rechazar_siguiente(texto)`: la próxima orden la rechaza el exchange (`ExchangeError`).
- `cortar_siguiente(ejecutada=...)`: la próxima orden se envía y se corta la comunicación
  (`EstadoDesconocidoError`). Con `ejecutada=True` el exchange sí la ejecutó, y `orden()` lo dice
  después; con `False`, no llegó.
- `caer(texto)` / `levantar()`: no se puede hablar con él (todo da `ExchangeError`).
- `poner_precio(par, precio)` + `casar(par)`: mover el mercado y ejecutar las órdenes límite que
  crucen.

Las comisiones se cobran en la moneda cotizada (`comision` por uno del importe), como hace Binance
sin BNB. Se usa así:

    falso = ConectorFalso("binance", "pruebas", saldo_inicial={"USDT": Decimal(1000)})
    falso.poner_precio("BTC/USDT", Decimal(60000))
    with registro.inyectados({"binance": falso}): ...

(o, sin pasar por el registro, dárselo directamente a quien lo use).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Final, Literal

from invest_ll.exchanges.conector import (
    EstadoDesconocidoError,
    ExchangeError,
    Lado,
    Mercado,
    OrdenExchange,
    Permisos,
    Red,
)
from invest_ll.vivo.fuente import Libro, Vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Iterable

COMISION: Final = Decimal("0.001")


def mercado_falso(
    base: str,
    cotizada: str = "USDT",
    *,
    paso_cantidad: str = "0.00001",
    paso_precio: str = "0.01",
    minimo_importe: str | None = "5",
    minimo_cantidad: str | None = None,
) -> Mercado:
    return Mercado(
        par=f"{base}/{cotizada}",
        base=base,
        cotizada=cotizada,
        minimo_importe=Decimal(minimo_importe) if minimo_importe is not None else None,
        minimo_cantidad=Decimal(minimo_cantidad) if minimo_cantidad is not None else None,
        paso_cantidad=Decimal(paso_cantidad),
        paso_precio=Decimal(paso_precio),
        comision_tomador=COMISION,
        comision_creador=COMISION,
    )


MERCADOS_DE_SERIE: Final = (
    mercado_falso("BTC"),
    mercado_falso("ETH", paso_cantidad="0.0001"),
    mercado_falso("SOL", paso_cantidad="0.001"),
)


def redondear_abajo(valor: Decimal, paso: Decimal | None) -> Decimal:
    """Al paso del mercado, hacia abajo (como `amount_to_precision` de ccxt: nunca de más)."""
    if paso is None or paso <= 0:
        return valor
    return (valor / paso).to_integral_value(rounding=ROUND_DOWN) * paso


@dataclass
class ConectorFalso:
    """Ver el docstring del módulo."""

    exchange_: str = "falso"
    red_: Red = "pruebas"
    saldo_inicial: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    mercados_: tuple[Mercado, ...] = MERCADOS_DE_SERIE
    comision: Decimal = COMISION
    permisos_: Permisos = field(
        default_factory=lambda: Permisos(
            operar=True, retirar=False, texto="Puede operar en contado y no puede retirar."
        )
    )
    reloj: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    precios: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    libros: dict[str, Libro] = field(default_factory=dict[str, Libro])
    series: dict[tuple[str, str], list[Vela]] = field(
        default_factory=dict[tuple[str, str], list[Vela]]
    )
    saldos: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    ordenes: dict[str, OrdenExchange] = field(default_factory=dict[str, OrdenExchange])
    """Por id de cliente: lo que el exchange sabe de cada orden."""
    creadas: list[OrdenExchange] = field(default_factory=list[OrdenExchange])
    """Cada orden que llegó al exchange (un reintento que no duplica no añade nada)."""
    caido: str | None = None
    _rechazos: list[str] = field(default_factory=list[str], init=False)
    _cortes: list[bool] = field(default_factory=list[bool], init=False)

    def __post_init__(self) -> None:
        self.saldos = {**self.saldo_inicial, **self.saldos}

    # -- provocar ---------------------------------------------------------------------------------

    def rechazar_siguiente(self, texto: str = "El exchange rechaza la orden.") -> None:
        self._rechazos.append(texto)

    def cortar_siguiente(self, *, ejecutada: bool) -> None:
        self._cortes.append(ejecutada)

    def caer(self, texto: str = "No hay conexión con el exchange (falso).") -> None:
        self.caido = texto

    def levantar(self) -> None:
        self.caido = None

    def poner_precio(self, par: str, precio: Decimal) -> None:
        self.precios[par] = precio

    def casar(self, par: str) -> list[OrdenExchange]:
        """Ejecuta las órdenes límite de `par` que crucen el precio de ahora. Las devuelve."""
        actual = self.precio(par)
        hechas: list[OrdenExchange] = []
        if actual is None:
            return hechas
        for orden in list(self.ordenes.values()):
            if orden.par != par or orden.estado != "abierta" or orden.precio_medio is None:
                continue
            cruza = (
                actual <= orden.precio_medio
                if orden.lado == "compra"
                else actual >= orden.precio_medio
            )
            if cruza:
                hecha = self._ejecutar(orden, orden.precio_medio)
                self.ordenes[orden.id_cliente] = hecha
                hechas.append(hecha)
        return hechas

    # -- el protocolo -----------------------------------------------------------------------------

    @property
    def exchange(self) -> str:
        return self.exchange_

    @property
    def red(self) -> Red:
        return self.red_

    def _vivo(self) -> None:
        if self.caido is not None:
            raise ExchangeError(self.caido)

    def mercados(self) -> list[Mercado]:
        self._vivo()
        return sorted(self.mercados_, key=lambda m: m.par)

    def mercado(self, par: str) -> Mercado:
        self._vivo()
        for m in self.mercados_:
            if m.par == par:
                return m
        raise ExchangeError(f"{self.exchange_} no tiene el par {par} de contado.")

    def precio(self, par: str) -> Decimal | None:
        self.mercado(par)
        if par in self.precios:
            return self.precios[par]
        libro = self.libros.get(par)
        return libro.medio if libro is not None else None

    def libro(self, par: str, niveles: int = 20) -> Libro | None:
        self.mercado(par)
        libro = self.libros.get(par)
        if libro is None:
            return None
        return replace(libro, compras=libro.compras[:niveles], ventas=libro.ventas[:niveles])

    def velas(
        self, par: str, intervalo: str, desde: datetime | None = None, limite: int = 1000
    ) -> list[Vela]:
        self.mercado(par)
        serie = [
            v for v in self.series.get((par, intervalo), []) if desde is None or v.inicio >= desde
        ]
        return serie[:limite] if desde is not None else serie[-limite:]

    def saldo(self) -> dict[str, Decimal]:
        self._vivo()
        return {m: c for m, c in self.saldos.items() if c > 0}

    def permisos(self) -> Permisos:
        self._vivo()
        return self.permisos_

    def enviar(
        self,
        par: str,
        lado: Lado,
        cantidad: Decimal,
        *,
        id_cliente: str,
        tipo: Literal["mercado", "limite"] = "mercado",
        precio: Decimal | None = None,
    ) -> OrdenExchange:
        self._vivo()
        if not id_cliente.strip():
            raise ExchangeError(
                "Una orden necesita un id de cliente: sin él, un reintento la duplica."
            )
        previa = self.ordenes.get(id_cliente)
        if previa is not None:
            if previa.par != par or previa.lado != lado:
                raise ExchangeError(
                    f"El id de cliente {id_cliente} ya se usó para otra orden: cada orden necesita "
                    "el suyo."
                )
            return previa
        m = self.mercado(par)
        cant = redondear_abajo(cantidad, m.paso_cantidad)
        if cant <= 0:
            raise ExchangeError(f"La cantidad {cantidad} {m.base} se queda en cero al redondearla.")
        if m.minimo_cantidad is not None and cant < m.minimo_cantidad:
            raise ExchangeError(f"La cantidad mínima de {par} es {m.minimo_cantidad} {m.base}.")
        if tipo == "limite":
            if precio is None or precio <= 0:
                raise ExchangeError("Una orden límite necesita un precio mayor que cero.")
            precio = redondear_abajo(precio, m.paso_precio)
        referencia = precio if tipo == "limite" else self.precio(par)
        if referencia is None:
            raise ExchangeError(f"No hay precio de {par}: no se ha enviado nada.")
        if m.minimo_importe is not None and cant * referencia < m.minimo_importe:
            raise ExchangeError(
                f"El importe mínimo de una orden de {par} es {m.minimo_importe} {m.cotizada}."
            )
        if self._rechazos:
            raise ExchangeError(self._rechazos.pop(0))
        orden = OrdenExchange(
            id_exchange=f"F{len(self.creadas) + 1}",
            id_cliente=id_cliente,
            par=par,
            lado=lado,
            tipo=tipo,
            cantidad=cant,
            ejecutada=Decimal(0),
            precio_medio=precio if tipo == "limite" else None,
            comision=None,
            comision_moneda=None,
            estado="abierta",
            at=self.reloj(),
        )
        cortada = self._cortes.pop(0) if self._cortes else None
        if cortada is False:
            raise EstadoDesconocidoError(
                f"Se envió la orden {id_cliente} y se cortó la comunicación: NO se sabe si se "
                "ejecutó."
            )
        actual = self.precio(par)
        if tipo == "mercado":
            cruza = True
        else:
            cruza = (
                actual is not None
                and precio is not None
                and (precio >= actual if lado == "compra" else precio <= actual)
            )
        if cruza:
            orden = self._ejecutar(orden, actual if actual is not None else referencia)
        self.ordenes[id_cliente] = orden
        self.creadas.append(orden)
        if cortada is True:
            raise EstadoDesconocidoError(
                f"Se envió la orden {id_cliente} y se cortó la comunicación: NO se sabe si se "
                "ejecutó."
            )
        return orden

    def _ejecutar(self, orden: OrdenExchange, precio: Decimal) -> OrdenExchange:
        m = self.mercado(orden.par)
        importe = orden.cantidad * precio
        comision = importe * self.comision
        if orden.lado == "compra":
            if self.saldos.get(m.cotizada, Decimal(0)) < importe + comision:
                return replace(orden, estado="rechazada")
            self.saldos[m.cotizada] = self.saldos.get(m.cotizada, Decimal(0)) - importe - comision
            self.saldos[m.base] = self.saldos.get(m.base, Decimal(0)) + orden.cantidad
        else:
            if self.saldos.get(m.base, Decimal(0)) < orden.cantidad:
                return replace(orden, estado="rechazada")
            self.saldos[m.base] = self.saldos.get(m.base, Decimal(0)) - orden.cantidad
            self.saldos[m.cotizada] = self.saldos.get(m.cotizada, Decimal(0)) + importe - comision
        return replace(
            orden,
            ejecutada=orden.cantidad,
            precio_medio=precio,
            comision=comision,
            comision_moneda=m.cotizada,
            estado="ejecutada",
            at=self.reloj(),
        )

    def orden(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        self._vivo()
        orden = self.ordenes.get(id_cliente)
        return orden if orden is not None and orden.par == par else None

    def cancelar(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        orden = self.orden(par, id_cliente=id_cliente)
        if orden is None or orden.estado not in ("abierta", "parcial"):
            return orden
        cancelada = replace(orden, estado="cancelada" if orden.ejecutada == 0 else "parcial")
        self.ordenes[id_cliente] = cancelada
        return cancelada

    def ordenes_abiertas(self, par: str | None = None) -> list[OrdenExchange]:
        self._vivo()
        return [
            o
            for o in self.ordenes.values()
            if o.estado in ("abierta", "parcial") and (par is None or o.par == par)
        ]


def con_velas(falso: ConectorFalso, velas: Iterable[Vela]) -> ConectorFalso:
    """Pone las velas en el conector falso, por par e intervalo."""
    for vela in velas:
        falso.series.setdefault((vela.coin, vela.intervalo), []).append(vela)
    for serie in falso.series.values():
        serie.sort(key=lambda v: v.inicio)
    return falso
