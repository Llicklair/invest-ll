"""Los ids de activo de la API: construirlos y resolverlos, en un único sitio.

Un id es `proveedor:símbolo:intervalo` (`yfinance:GLD:DAY_1`, `ccxt-binance:BTC/USDT:DAY_1`). El
símbolo puede llevar "/" y, en teoría, ":"; por eso el proveedor se corta por el PRIMER ":" y el
intervalo por el ÚLTIMO, y lo que queda en medio es el símbolo tal cual. Aun así no se descompone
para buscar: se resuelve comparando contra los ids de lo que hay descargado, que es la única
fuente de verdad. Un id que no corresponde a ningún histórico es un 404, no un activo vacío.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.api.errores import del_dominio, no_encontrado
from invest_ll.api.schemas import Activo
from invest_ll.dashboard.data import AvailableAsset, discover_assets
from invest_ll.engine.config import FrictionConfig
from invest_ll.errors import InvestLLError
from invest_ll.nombres import moneda_de, nombre_llano

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.api.schemas import Friccion
    from invest_ll.data.series import PriceSeries

SEPARADOR = ":"

ILEGIBLE = (InvestLLError, ValueError, OSError, KeyError)
"""Lo que puede lanzar leer un histórico corrupto. Las mesas lo saltan, como hacía el panel."""


def id_de(activo: AvailableAsset) -> str:
    return SEPARADOR.join((activo.provider, activo.symbol, activo.interval.name))


def partes_de(id_activo: str) -> tuple[str, str, str]:
    """(proveedor, símbolo, intervalo). `ValueError` si no tiene la forma de un id."""
    proveedor, _, resto = id_activo.partition(SEPARADOR)
    simbolo, _, intervalo = resto.rpartition(SEPARADOR)
    if not (proveedor and simbolo and intervalo):
        raise ValueError(
            f"id de activo mal formado: {id_activo!r}. La forma es proveedor:simbolo:intervalo, "
            "p.ej. 'yfinance:GLD:DAY_1'"
        )
    return proveedor, simbolo, intervalo


def descargados() -> list[AvailableAsset]:
    return discover_assets()


def resolver(id_activo: str, activos: Sequence[AvailableAsset] | None = None) -> AvailableAsset:
    """El histórico de ese id. 404 si no hay ninguno descargado con él."""
    with del_dominio():
        partes_de(id_activo)
    for activo in descargados() if activos is None else activos:
        if id_de(activo) == id_activo:
            return activo
    raise no_encontrado(f"no hay ningun historico descargado con id {id_activo!r}")


def resolver_varios(ids: Sequence[str]) -> list[AvailableAsset]:
    """Varios ids, en el orden pedido y sin repetir. 404 en cuanto uno no exista."""
    activos = descargados()
    elegidos: list[AvailableAsset] = []
    for id_activo in dict.fromkeys(ids):
        elegidos.append(resolver(id_activo, activos))
    return elegidos


def por_simbolo(simbolo: str, activos: Sequence[AvailableAsset] | None = None) -> AvailableAsset:
    """El primer histórico de ese símbolo, como hacía la gráfica del panel. 404 si no hay."""
    buscado = simbolo.strip().upper()
    for activo in descargados() if activos is None else activos:
        if activo.symbol.upper() == buscado:
            return activo
    raise no_encontrado(f"no hay historico descargado de {simbolo!r}")


def serie_completa(activo: AvailableAsset) -> PriceSeries:
    """Todo el histórico, para MIRAR. 422 con el motivo si el fichero no se puede leer."""
    with del_dominio(f"No se pudo cargar {activo.symbol}: "):
        return activo.load_completa()


def series_para_medir(activos: Sequence[AvailableAsset]) -> list[PriceSeries]:
    """Las series recortadas por la reserva, para MEDIR (backtests y propuestas)."""
    return [activo.load() for activo in activos]


def como_activo(activo: AvailableAsset) -> Activo | None:
    """El activo para la cabecera, con sus fechas. `None` si el fichero no se puede leer."""
    try:
        serie = activo.load_completa()
    except ILEGIBLE:
        return None
    return Activo(
        id=id_de(activo),
        symbol=activo.symbol,
        nombre=nombre_llano(activo.symbol),
        moneda=moneda_de(activo.symbol),
        provider=activo.provider,
        interval=activo.interval.name,
        is_crypto=activo.is_crypto,
        label=activo.label,
        desde=serie.bars[0].timestamp.date(),
        hasta=serie.bars[-1].timestamp.date(),
    )


def costes(peticion: Friccion) -> FrictionConfig:
    """Los costes de la petición, que son obligatorios (Principio IV)."""
    return FrictionConfig(commission_rate=peticion.comision, slippage_rate=peticion.slippage)
