"""Motor de rotación entre activos.

Mismas reglas que el motor de un solo activo, porque son las que hacen creíble el resultado:

- La decisión se toma con el periodo cerrado y **se ejecuta en la apertura del siguiente**.
- Cada rotación paga dos veces: se vende uno y se compra otro. Ignorarlo haría que rotar pareciera
  gratis, y es justo lo que más veces ocurre en esta estrategia.
- La estrategia recibe una vista que no expone el futuro de ningún activo.

El benchmark es distinto y tiene que serlo: aquí no basta con comparar contra mantener un activo,
porque elegir *cuál* ya sería hacer trampa a posteriori. Se compara contra **comprar todos a
partes iguales y no tocarlos**, que es lo que consigue quien no quiere decidir nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.benchmark import BuyAndHold
from invest_ll.engine.execution import MOTOR, ExitReason, OrderSide, Trade, build_order
from invest_ll.engine.universe_view import UniverseView
from invest_ll.report.consistency import monthly_consistency
from invest_ll.report.metrics import max_drawdown
from invest_ll.report.report import DEFAULT_MIN_TRADES, BacktestReport, build_report

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from invest_ll.data.universe import Universe
    from invest_ll.engine.config import FrictionConfig, RiskConfig
    from invest_ll.strategy.rotation import RotationStrategy

LOTE_MINIMO = Decimal("0.00000001")


@dataclass(slots=True)
class _Posicion:
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_order: object
    stop: Decimal | None = None


def _salta_el_stop(posicion: _Posicion, bajo: Decimal, apertura: Decimal) -> Decimal | None:
    """El precio al que se sale, o `None` si el stop no se toca.

    Dos reglas heredadas del motor de un activo, ambas pesimistas a propósito:

    1. Se mira el **mínimo** de la vela: si el precio llegó a tocar el nivel, se ejecuta. No se
       supone que el rebote llegó antes.
    2. **Si la vela abre ya por debajo del nivel, se vende en la apertura, no en el nivel.** Un
       stop no protege de un hueco: cuando el mercado abre un 20% más abajo, vendes ahí. Suponer
       lo contrario haría que el stop pareciera una garantía, y no lo es.
    """
    if posicion.stop is None or bajo > posicion.stop:
        return None
    return min(posicion.stop, apertura)


def run_rotation(
    universe: Universe,
    strategy: RotationStrategy,
    *,
    initial_capital: Decimal,
    friction: FrictionConfig,
    risk: RiskConfig,
    min_trades: int = DEFAULT_MIN_TRADES,
) -> BacktestReport:
    """Simula la rotación entre los activos del universo."""
    if initial_capital <= 0:
        raise ValueError(f"el capital inicial debe ser positivo, recibido {initial_capital}")

    cash = initial_capital
    posicion: _Posicion | None = None
    trades: list[Trade] = []
    equity: list[Decimal] = []
    marcas: list[datetime] = []
    ultimo = len(universe) - 1

    # Activo del que acaba de saltar el stop. Sin esto, la estrategia sigue diciendo el mismo
    # nombre en el periodo siguiente y se vuelve a entrar en lo que se acaba de cortar: el stop
    # no protegeria de nada y ademas costaria dos comisiones. Se levanta el veto en cuanto la
    # estrategia cambia de idea, no por tiempo — el criterio de salir es el mismo de volver.
    vetado: str | None = None

    for i in range(len(universe)):
        momento = universe.timestamps[i]

        # El stop se mira ANTES de valorar la cartera: si salta en esta vela, el patrimonio de
        # este periodo es el de haber salido, no el del cierre que nunca llegamos a tener.
        if posicion is not None:
            vela = universe.bar(posicion.symbol, i)
            corte = _salta_el_stop(posicion, Decimal(str(vela.low)), Decimal(str(vela.open)))
            if corte is not None:
                orden_stop = build_order(
                    signal_timestamp=momento,
                    execution_timestamp=momento,
                    side=OrderSide.SELL,
                    reference_price=corte,
                    quantity=posicion.quantity,
                    commission_rate=friction.commission_rate,
                    slippage_rate=friction.slippage_rate,
                )
                cash += orden_stop.notional - orden_stop.commission
                entrada = posicion.entry_order
                trades.append(
                    Trade(
                        entry_order=entrada,  # type: ignore[arg-type]
                        exit_order=orden_stop,
                        exit_reason=ExitReason.STOP_LOSS,
                        gross_pnl=MOTOR.multiply(
                            corte - entrada.reference_price,  # type: ignore[attr-defined]
                            posicion.quantity,
                        ),
                        costs=entrada.costs + orden_stop.costs,  # type: ignore[attr-defined]
                    )
                )
                vetado = posicion.symbol
                posicion = None

        valor = cash
        if posicion is not None:
            valor += MOTOR.multiply(
                posicion.quantity, Decimal(str(universe.bar(posicion.symbol, i).close))
            )
        equity.append(valor)
        marcas.append(momento)

        elegido = strategy.choose(UniverseView(universe, cursor=i))

        if elegido != vetado:
            vetado = None
        elif elegido is not None:
            # Sigue apuntando a lo que acabamos de cortar: fuera hasta que cambie de idea.
            continue

        actual = posicion.symbol if posicion is not None else None
        if elegido == actual or i == ultimo:
            continue

        # Salir de lo que hubiera. La orden se ejecuta en la apertura del periodo siguiente.
        if posicion is not None:
            precio_salida = Decimal(str(universe.bar(posicion.symbol, i + 1).open))
            orden_salida = build_order(
                signal_timestamp=momento,
                execution_timestamp=universe.timestamps[i + 1],
                side=OrderSide.SELL,
                reference_price=precio_salida,
                quantity=posicion.quantity,
                commission_rate=friction.commission_rate,
                slippage_rate=friction.slippage_rate,
            )
            cash += orden_salida.notional - orden_salida.commission

            entrada = posicion.entry_order
            bruto = MOTOR.multiply(
                precio_salida - entrada.reference_price,  # type: ignore[attr-defined]
                posicion.quantity,
            )
            trades.append(
                Trade(
                    entry_order=entrada,  # type: ignore[arg-type]
                    exit_order=orden_salida,
                    exit_reason=ExitReason.SIGNAL,
                    gross_pnl=bruto,
                    costs=entrada.costs + orden_salida.costs,  # type: ignore[attr-defined]
                )
            )
            posicion = None

        # Entrar en el nuevo.
        if elegido is not None:
            precio_entrada = Decimal(str(universe.bar(elegido, i + 1).open))
            presupuesto = cash * risk.position_fraction
            unitario = MOTOR.multiply(
                MOTOR.multiply(precio_entrada, 1 + friction.slippage_rate),
                1 + friction.commission_rate,
            )
            cantidad = MOTOR.divide(presupuesto, unitario).quantize(
                LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
            )
            if cantidad > 0:
                orden = build_order(
                    signal_timestamp=momento,
                    execution_timestamp=universe.timestamps[i + 1],
                    side=OrderSide.BUY,
                    reference_price=precio_entrada,
                    quantity=cantidad,
                    commission_rate=friction.commission_rate,
                    slippage_rate=friction.slippage_rate,
                )
                desembolso = orden.notional + orden.commission
                if desembolso <= cash:
                    cash -= desembolso
                    # El stop se fija sobre el precio REALMENTE pagado (con slippage), no sobre
                    # el de referencia: es de donde se cuenta lo que puedes perder.
                    posicion = _Posicion(
                        symbol=elegido,
                        quantity=cantidad,
                        entry_price=orden.fill_price,
                        entry_order=orden,
                        stop=(
                            MOTOR.multiply(orden.fill_price, 1 - risk.stop_loss_pct)
                            if risk.stop_loss_pct is not None
                            else None
                        ),
                    )

    # Liquidar lo que quede abierto al final, igual que en el motor de un activo.
    if posicion is not None:
        final = Decimal(str(universe.bar(posicion.symbol, ultimo).close))
        orden_final = build_order(
            signal_timestamp=universe.timestamps[ultimo],
            execution_timestamp=universe.timestamps[ultimo],
            side=OrderSide.SELL,
            reference_price=final,
            quantity=posicion.quantity,
            commission_rate=friction.commission_rate,
            slippage_rate=friction.slippage_rate,
        )
        cash += orden_final.notional - orden_final.commission
        entrada = posicion.entry_order
        trades.append(
            Trade(
                entry_order=entrada,  # type: ignore[arg-type]
                exit_order=orden_final,
                exit_reason=ExitReason.END_OF_SERIES,
                gross_pnl=MOTOR.multiply(
                    final - entrada.reference_price,  # type: ignore[attr-defined]
                    posicion.quantity,
                ),
                costs=entrada.costs + orden_final.costs,  # type: ignore[attr-defined]
            )
        )

    return build_report(
        trades=trades,
        equity_curve=equity,
        friction=friction,
        risk=risk,
        symbol=" / ".join(universe.symbols),
        min_trades=min_trades,
        final_cash=cash,
        benchmark=equal_weight_hold(universe, capital=initial_capital, friction=friction),
        consistency=monthly_consistency(equity, marcas),
        equity_timestamps=marcas,
    )


def equal_weight_hold(
    universe: Universe, *, capital: Decimal, friction: FrictionConfig
) -> BuyAndHold:
    """Comprar todos los activos a partes iguales y no tocarlos.

    Es el benchmark honesto para una rotación. Comparar contra mantener **un** activo obligaría a
    elegir cuál, y esa elección se haría sabiendo cuál subió — trampa a posteriori. Repartir a
    partes iguales no exige acertar nada.
    """
    if len(universe) < 2:
        return BuyAndHold(
            net_result=Decimal(0),
            costs=Decimal(0),
            max_drawdown=Decimal(0),
            quantity=Decimal(0),
        )

    por_activo = capital / len(universe.symbols)
    cantidades: dict[str, Decimal] = {}
    costes = Decimal(0)

    for symbol in universe.symbols:
        entrada = Decimal(str(universe.bar(symbol, 1).open))
        compra = MOTOR.multiply(entrada, 1 + friction.slippage_rate)
        unitario = MOTOR.multiply(compra, 1 + friction.commission_rate)
        cantidad = MOTOR.divide(por_activo, unitario).quantize(
            LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
        )
        cantidades[symbol] = cantidad
        costes += MOTOR.multiply(MOTOR.multiply(compra, cantidad), friction.commission_rate)
        costes += MOTOR.multiply(compra - entrada, cantidad)

    bruto = Decimal(0)
    for symbol, cantidad in cantidades.items():
        entrada = Decimal(str(universe.bar(symbol, 1).open))
        salida = Decimal(str(universe.bar(symbol, len(universe) - 1).close))
        venta = MOTOR.multiply(salida, 1 - friction.slippage_rate)
        bruto += MOTOR.multiply(salida - entrada, cantidad)
        costes += MOTOR.multiply(MOTOR.multiply(venta, cantidad), friction.commission_rate)
        costes += MOTOR.multiply(salida - venta, cantidad)

    curva = [
        sum(
            (
                MOTOR.multiply(cantidad, Decimal(str(universe.bar(symbol, i).close)))
                for symbol, cantidad in cantidades.items()
            ),
            start=Decimal(0),
        )
        for i in range(1, len(universe))
    ]

    return BuyAndHold(
        net_result=bruto - costes,
        costs=costes,
        max_drawdown=max_drawdown(curva),
        quantity=sum(cantidades.values(), start=Decimal(0)),
    )
