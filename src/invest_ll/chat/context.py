"""Lo que el chat sabe de tu situación antes de responder.

Se reconstruye en cada pregunta desde las fuentes reales (ledger, triggers, históricos), no se
cachea: un chat que responde sobre una cartera de hace una hora es el mismo fallo que el panel
con los módulos cacheados, en peor — porque aquí lo redacta con seguridad un modelo.

Cada dato lleva su fecha. El modelo tiene instrucciones de no presentarlos como de hoy.
"""

from __future__ import annotations

from pathlib import Path

from invest_ll.errors import InvestLLError
from invest_ll.fetch.available import RAIZ_DATOS, discover_assets, market_overview
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.quotes import ultimo_cierre
from invest_ll.portfolio.store import RAIZ as RAIZ_CARTERA
from invest_ll.portfolio.store import ActivityStore
from invest_ll.portfolio.triggers import TriggerStore


def build_context(portfolio_root: Path = RAIZ_CARTERA, data_root: Path = RAIZ_DATOS) -> str:
    """El estado actual, en texto plano para el modelo."""
    partes: list[str] = []

    # -- cartera --
    try:
        cartera = derive_portfolio(ActivityStore(portfolio_root).activities())
    except InvestLLError as error:
        partes.append(f"CARTERA: el ledger tiene un problema y no se pudo derivar: {error}")
        cartera = None

    if cartera is not None:
        if not cartera.open_positions and not cartera.closed_trades:
            partes.append("CARTERA: vacia, sin movimientos registrados.")
        else:
            lineas = ["CARTERA (derivada del ledger; el P&L abierto es valoracion, no hecho):"]
            for p in cartera.open_positions:
                cierre = ultimo_cierre(p.symbol, data_root)
                if cierre is not None:
                    precio, fecha = cierre
                    lineas.append(
                        f"  ABIERTA {p.symbol}: {p.quantity} uds, coste medio {p.avg_cost:.2f}, "
                        f"valor {p.value_at(precio):,.0f} y P&L {p.unrealized_at(precio):,.0f} "
                        f"con el cierre del {fecha.date()}"
                    )
                else:
                    lineas.append(
                        f"  ABIERTA {p.symbol}: {p.quantity} uds, coste medio {p.avg_cost:.2f}, "
                        "sin datos de precio descargados"
                    )
            for t in cartera.closed_trades:
                lineas.append(
                    f"  RETIRADA {t.symbol}: {t.opened_at.date()} a {t.closed_at.date()}, "
                    f"P&L realizado {t.realized_pnl:,.0f}"
                )
            lineas.append(f"  Efectivo derivado: {cartera.cash:,.2f}")
            lineas.extend(f"  AVISO: {a}" for a in cartera.warnings)
            partes.append("\n".join(lineas))

    # -- triggers y pausa --
    store = TriggerStore(portfolio_root)
    armados = store.triggers()
    pausa = store.halted()
    if pausa:
        partes.append(f"PAUSA ACTIVA (no se proponen entradas nuevas): {pausa}")
    if armados:
        partes.append(
            "TRIGGERS ARMADOS (proponen la salida, nunca la ejecutan):\n"
            + "\n".join(f"  {t.trigger_id}: {t.describe()}" for t in armados)
        )
    else:
        partes.append("TRIGGERS: ninguno armado.")

    # -- mercado --
    filas = market_overview(discover_assets(data_root))
    if filas:
        lineas = ["MERCADO (historicos descargados; mira 'datos hasta' antes de fiarte):"]
        for f in filas:
            lineas.append(
                f"  {f['activo']}: ultimo {f['ultimo']}, 1 mes {f.get('1 mes')}%, "
                f"1 anho {f.get('1 año')}%, desde maximo {f.get('desde maximo')}%, "
                f"datos hasta {f.get('datos hasta')}"
            )
        partes.append("\n".join(lineas))
    else:
        partes.append("MERCADO: no hay historicos descargados.")

    return "\n\n".join(partes)
