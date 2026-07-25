"""El bucle de simulación (T033).

Estructura de un paso, y el orden importa:

    periodo i cierra
      → MarketView(cursor=i)              la estrategia solo ve hasta aquí
      → strategy.decide(view)             intención, sin tamaño ni precio
      → la orden se ejecuta en la APERTURA de i+1   nunca al cierre de i

Ejecutar al cierre del propio periodo de la señal sería asumir un precio que no se conocía al
decidir. Es la forma más común de inflar un backtest, y aquí no existe como opción (FR-025).

**Determinismo (FR-005)** — auditado en T040. El bucle no usa ninguna de las fuentes habituales
de irreproducibilidad: sin `random`, sin reloj del sistema, sin concurrencia, sin iteración sobre
conjuntos o diccionarios cuyo orden dependa del `hash` del proceso. El único orden que existe es
el cronológico de la serie. La contabilidad va en `Decimal`, así que tampoco hay acumulación de
error que dependa del orden de las sumas.

Si algún día entra aquí una fuente de azar, debe recibir una semilla explícita que forme parte
del informe. Un backtest que no se puede repetir no permite comparar nada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.benchmark import buy_and_hold
from invest_ll.engine.execution import (
    MOTOR,
    ExitReason,
    Order,
    OrderSide,
    Trade,
    build_order,
    rejected_order,
)
from invest_ll.engine.portfolio import PortfolioState, Position
from invest_ll.engine.view import MarketView
from invest_ll.report.report import DEFAULT_MIN_TRADES, build_report
from invest_ll.strategy.protocol import SignalKind

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence
    from datetime import datetime

    from invest_ll.data.bar import Bar
    from invest_ll.data.loader import DataWarning
    from invest_ll.data.series import PriceSeries
    from invest_ll.engine.config import FrictionConfig, RiskConfig
    from invest_ll.report.report import BacktestReport
    from invest_ll.strategy.protocol import Strategy

# Granularidad mínima de una posición. Ocho decimales cubren activos fraccionables como cripto.
LOTE_MINIMO = Decimal("0.00000001")

# A partir de esta duración, una vela representa una sesión entera y no un instante.
UN_DIA = timedelta(days=1)


def run_backtest(
    series: PriceSeries,
    strategy: Strategy,
    *,
    initial_capital: Decimal,
    friction: FrictionConfig,
    risk: RiskConfig,
    min_trades: int = DEFAULT_MIN_TRADES,
    data_warnings: Sequence[DataWarning] = (),
) -> BacktestReport:
    """Simula la estrategia sobre la serie y devuelve el veredicto.

    `friction` y `risk` no tienen valor por defecto a propósito: no se puede lanzar un backtest
    sin declarar los costes ni el tamaño de posición (Principio IV).

    No realiza ninguna E/S de red y no conoce ningún broker. Es simulación pura (FR-006).
    """
    if initial_capital <= 0:
        raise ValueError(f"el capital inicial debe ser positivo, recibido {initial_capital}")

    portfolio = PortfolioState(cash=initial_capital)
    trades: list[Trade] = []
    rejected: list[Order] = []
    last_index = len(series) - 1

    for i in range(len(series)):
        bar = series.bars[i]

        # Las salidas de protección se comprueban ANTES de pedir decisión a la estrategia: un
        # stop es una orden que ya está puesta en el mercado y salta sola cuando el precio la
        # toca, sin que nadie tenga que decidir nada. No es look-ahead: se resuelve dentro del
        # rango de la propia vela, no con datos posteriores.
        if portfolio.is_open:
            proteccion = _check_protective_exit(portfolio, bar)
            if proteccion is not None:
                reason, precio = proteccion
                trades.append(
                    _close_position(
                        portfolio,
                        signal_timestamp=bar.timestamp,
                        execution_timestamp=bar.timestamp,
                        reference=precio,
                        friction=friction,
                        reason=reason,
                    )
                )

        portfolio.record_equity(bar.timestamp, Decimal(str(bar.close)))

        signal = strategy.decide(MarketView(series, cursor=i))
        if signal is None:
            continue

        # La ejecución vive en el periodo siguiente. Si no existe, no hay operación: una señal
        # en la última vela no puede producir una entrada fantasma.
        if i == last_index:
            continue

        # FR-022: la orden va al siguiente periodo con el mercado abierto. Descartar la señal
        # sin más borraría operaciones que en la realidad sí habrían ocurrido a la apertura
        # siguiente; ejecutarla con el mercado cerrado sería inventarlas.
        next_index = _next_open_index(series, i + 1)
        if next_index is None:
            continue

        next_bar = series.bars[next_index]
        reference = Decimal(str(next_bar.open))

        if signal.kind is SignalKind.ENTER_LONG and not portfolio.is_open:
            _open_position(
                portfolio,
                rejected,
                signal_timestamp=bar.timestamp,
                execution_timestamp=next_bar.timestamp,
                reference=reference,
                friction=friction,
                risk=risk,
                signal_stop=signal.stop_loss,
                signal_take=signal.take_profit,
            )

        elif signal.kind is SignalKind.EXIT and portfolio.is_open:
            trades.append(
                _close_position(
                    portfolio,
                    signal_timestamp=bar.timestamp,
                    execution_timestamp=next_bar.timestamp,
                    reference=reference,
                    friction=friction,
                    reason=ExitReason.SIGNAL,
                )
            )

    # Una posición todavía abierta al agotarse el histórico se liquida al último cierre. No
    # hacerlo dejaría fuera del veredicto una ganancia o pérdida que el operador sí tendría.
    if portfolio.is_open:
        final_bar = series.bars[-1]
        trades.append(
            _close_position(
                portfolio,
                signal_timestamp=final_bar.timestamp,
                execution_timestamp=final_bar.timestamp,
                reference=Decimal(str(final_bar.close)),
                friction=friction,
                reason=ExitReason.END_OF_SERIES,
            )
        )

    return build_report(
        benchmark=buy_and_hold(series, capital=initial_capital, friction=friction),
        trades=trades,
        equity_curve=portfolio.equity_curve,
        friction=friction,
        risk=risk,
        symbol=series.symbol,
        min_trades=min_trades,
        data_warnings=data_warnings,
        final_cash=portfolio.cash,
        rejected_orders=rejected,
    )


def _check_protective_exit(
    portfolio: PortfolioState, bar: Bar
) -> tuple[ExitReason, Decimal] | None:
    """¿Salta el stop o el take dentro de esta vela? (FR-029, FR-030).

    Dos reglas, ambas deliberadamente conservadoras:

    1. **Si el stop y el take caben los dos en la misma vela, gana el stop.** No sabemos en qué
       orden se movió el precio dentro del periodo; quedarnos con la versión buena de una
       historia que desconocemos es justo la clase de optimismo que arruina un backtest.
    2. **Si la vela abre ya atravesando el nivel, se ejecuta a la apertura, no al nivel.** Un
       stop no protege de un hueco: cuando el mercado abre 20 puntos por debajo, vendes ahí, no
       donde te habría gustado.
    """
    position = portfolio.position
    if position is None:  # pragma: no cover - el llamante ya lo comprueba
        return None

    apertura = Decimal(str(bar.open))
    minimo = Decimal(str(bar.low))
    maximo = Decimal(str(bar.high))

    stop = position.stop_loss
    take = position.take_profit

    if stop is not None and minimo <= stop:
        # Si abrió por debajo del stop, el hueco ya se comió la protección.
        return ExitReason.STOP_LOSS, min(stop, apertura)

    if take is not None and maximo >= take:
        # Simétrico: si abrió por encima del objetivo, el precio real fue mejor.
        return ExitReason.TAKE_PROFIT, max(take, apertura)

    return None


def _tradeable(series: PriceSeries, moment: datetime) -> bool:
    """¿Se puede operar en el periodo que empieza en `moment`?

    La pregunta depende de la granularidad, y confundirlas cuesta caro. Una vela diaria suele
    fecharse a medianoche, hora a la que ningún mercado con horario está abierto: preguntar
    `is_open` sobre ella responde siempre que no, y el motor no ejecuta una sola orden en todo el
    backtest. Sin error, sin aviso, con cero operaciones y aspecto de resultado válido.

    Para velas de un día o más la pregunta correcta es si ese día hubo sesión.
    """
    if series.interval.duration >= UN_DIA:
        return series.calendar.is_session(moment)
    return series.calendar.is_open(moment)


def _next_open_index(series: PriceSeries, start: int) -> int | None:
    """Primer periodo negociable desde `start`, o `None` si no queda ninguno.

    En un mercado continuo devuelve `start` siempre. En bolsa salta los días sin sesión: una
    señal emitida al cierre del viernes se ejecuta en la apertura del lunes, que es lo que
    ocurriría de verdad.
    """
    for index in range(start, len(series)):
        if _tradeable(series, series.bars[index].timestamp):
            return index
    return None


def _open_position(
    portfolio: PortfolioState,
    rejected: list[Order],
    *,
    signal_timestamp: datetime,
    execution_timestamp: datetime,
    reference: Decimal,
    friction: FrictionConfig,
    risk: RiskConfig,
    signal_stop: float | None,
    signal_take: float | None,
) -> None:
    """Abre posición con la fracción configurada del capital (FR-026)."""
    presupuesto = portfolio.cash * risk.position_fraction
    fill_estimado = reference * (1 + friction.slippage_rate)
    coste_unitario = fill_estimado * (1 + friction.commission_rate)

    # ROUND_DOWN, no el redondeo por defecto: redondear hacia arriba haría que el desembolso
    # superase la caja por una fracción ínfima y la orden se rechazaría siempre que se invierta
    # el capital completo. Comprometer de menos es aceptable; de más, nunca.
    quantity = MOTOR.divide(presupuesto, coste_unitario).quantize(
        LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
    )

    if quantity <= 0:
        rejected.append(
            rejected_order(
                signal_timestamp=signal_timestamp,
                execution_timestamp=execution_timestamp,
                side=OrderSide.BUY,
                reference_price=reference,
                requested_quantity=quantity,
                reason=(
                    f"capital insuficiente: {portfolio.cash} disponible no alcanza "
                    f"para una unidad a {reference}"
                ),
            )
        )
        return

    order = build_order(
        signal_timestamp=signal_timestamp,
        execution_timestamp=execution_timestamp,
        side=OrderSide.BUY,
        reference_price=reference,
        quantity=quantity,
        commission_rate=friction.commission_rate,
        slippage_rate=friction.slippage_rate,
    )

    desembolso = order.notional + order.commission
    if desembolso > portfolio.cash:
        rejected.append(
            rejected_order(
                signal_timestamp=signal_timestamp,
                execution_timestamp=execution_timestamp,
                side=OrderSide.BUY,
                reference_price=reference,
                requested_quantity=quantity,
                reason=f"desembolso {desembolso} supera la caja {portfolio.cash}",
            )
        )
        return

    portfolio.cash -= desembolso
    portfolio.position = Position(
        entry_order=order,
        quantity=order.filled_quantity,
        entry_price=order.fill_price,
        stop_loss=Decimal(str(signal_stop)) if signal_stop is not None else None,
        take_profit=Decimal(str(signal_take)) if signal_take is not None else None,
    )


def _close_position(
    portfolio: PortfolioState,
    *,
    signal_timestamp: datetime,
    execution_timestamp: datetime,
    reference: Decimal,
    friction: FrictionConfig,
    reason: ExitReason,
) -> Trade:
    """Cierra la posición abierta y construye la operación completa."""
    position = portfolio.position
    if position is None:  # pragma: no cover - el llamante ya lo comprueba
        raise RuntimeError("no hay posición que cerrar")

    order = build_order(
        signal_timestamp=signal_timestamp,
        execution_timestamp=execution_timestamp,
        side=OrderSide.SELL,
        reference_price=reference,
        quantity=position.quantity,
        commission_rate=friction.commission_rate,
        slippage_rate=friction.slippage_rate,
    )

    portfolio.cash += order.notional - order.commission
    portfolio.position = None

    # El bruto se mide contra los precios de referencia (sin fricción) y los costes se suman
    # aparte. Así el informe puede decir cuánto se llevó el mercado y cuánto los costes.
    gross = (reference - position.entry_order.reference_price) * position.quantity
    costs = position.entry_order.costs + order.costs

    return Trade(
        entry_order=position.entry_order,
        exit_order=order,
        exit_reason=reason,
        gross_pnl=gross,
        costs=costs,
    )
