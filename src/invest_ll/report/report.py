"""El veredicto (T032).

Las seis métricas son campos obligatorios del tipo: un informe incompleto no llega a construirse
(SC-002). Y la presentación está ordenada para que lo importante se lea primero y lo engañoso al
final (FR-012).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.execution import ExitReason, Order

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator, Sequence
    from datetime import datetime

    from invest_ll.data.loader import DataWarning
    from invest_ll.engine.benchmark import BuyAndHold
    from invest_ll.engine.config import FrictionConfig, RiskConfig
    from invest_ll.engine.execution import Trade
    from invest_ll.report.consistency import Consistency

# Por debajo de esta cifra, el resultado no distingue habilidad de suerte.
DEFAULT_MIN_TRADES = 30


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Resultado completo y auditable de un backtest."""

    # Las seis obligatorias (FR-011)
    net_result: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    trade_count: int
    total_costs: Decimal
    win_rate: float

    # Auditoría y contexto
    trades: tuple[Trade, ...]
    friction: FrictionConfig
    risk: RiskConfig
    symbol: str
    min_trades: int = DEFAULT_MIN_TRADES
    data_warnings: tuple[DataWarning, ...] = ()
    final_cash: Decimal = Decimal(0)
    rejected_orders: tuple[Order, ...] = ()
    buy_and_hold: BuyAndHold | None = None
    consistency: Consistency | None = None
    equity_curve: tuple[Decimal, ...] = ()
    equity_timestamps: tuple[datetime, ...] = ()

    @property
    def excess_return(self) -> Decimal:
        """Cuánto añade la estrategia sobre no hacer nada.

        Negativo significa que todo el riesgo asumido y todas las comisiones pagadas han servido
        para quedarse por debajo de comprar y olvidarse.
        """
        if self.buy_and_hold is None:
            return Decimal(0)
        return self.net_result - self.buy_and_hold.net_result

    @property
    def beats_market(self) -> bool:
        return self.excess_return > 0

    @property
    def conclusive(self) -> bool:
        """FR-013: por debajo del umbral, el resultado no concluye — gane o pierda."""
        return self.trade_count >= self.min_trades

    @property
    def inconclusive_reason(self) -> str | None:
        if self.conclusive:
            return None
        # Sin acentos: este texto se imprime en consola, y en Windows (cp1252) un acento en el
        # aviso bastaria para que el informe no llegara a verse.
        if self.trade_count == 0:
            return (
                "la estrategia no opero ninguna vez: no hay nada que evaluar. "
                "Esto no es un resultado neutro, es ausencia de resultado"
            )
        return (
            f"solo {self.trade_count} operaciones, por debajo del minimo de {self.min_trades}. "
            "Con esta muestra no se distingue la habilidad de la suerte"
        )

    def all_orders(self) -> Iterator[Order]:
        """Todas las órdenes emitidas, ejecutadas o no. Base de la auditoría (FR-014)."""
        for trade in self.trades:
            yield trade.entry_order
            if trade.exit_order is not None:
                yield trade.exit_order
        yield from self.rejected_orders

    def exits_by_reason(self) -> dict[ExitReason, int]:
        """Desglose de cierres por motivo (FR-031)."""
        conteo = dict.fromkeys(ExitReason, 0)
        for trade in self.trades:
            conteo[trade.exit_reason] += 1
        return conteo

    def render(self) -> str:
        """Representación textual del veredicto.

        El orden no es estético. Si el resultado no concluye, eso va **antes** que cualquier
        cifra, para que no pueda leerse como bueno de un vistazo. Y el win rate va el último,
        detrás de la expectancy, porque leído primero engaña (FR-012).
        """
        # Solo ASCII: la consola de Windows usa cp1252 por defecto y un simple símbolo de aviso
        # bastaría para que imprimir el informe lanzara UnicodeEncodeError. Un veredicto que no
        # se puede imprimir no sirve de nada.
        lineas: list[str] = [f"Backtest - {self.symbol}", "=" * 46]

        if not self.conclusive:
            lineas += [f"[!] NO CONCLUYENTE: {self.inconclusive_reason}", ""]

        lineas += [
            f"  Resultado neto      {self.net_result:>16.2f}",
            f"  Expectancy/oper.    {self.expectancy:>16.2f}",
            f"  Drawdown maximo     {self.max_drawdown:>16.2f}",
            f"  Operaciones         {self.trade_count:>16}",
            f"  Costes totales      {self.total_costs:>16.2f}",
            f"  Win rate            {self.win_rate:>15.1%}  (no es criterio de exito)",
            "",
            f"  Friccion aplicada   {self.friction.describe()}",
            f"  Riesgo aplicado     {self.risk.describe()}",
        ]

        lineas += self._render_benchmark()
        lineas += self._render_consistency()

        desglose = self.exits_by_reason()
        if self.trade_count:
            lineas += [
                "",
                "  Cierres por motivo",
                f"    senal          {desglose[ExitReason.SIGNAL]:>6}",
                f"    stop-loss      {desglose[ExitReason.STOP_LOSS]:>6}",
                f"    take-profit    {desglose[ExitReason.TAKE_PROFIT]:>6}",
                f"    fin de serie   {desglose[ExitReason.END_OF_SERIES]:>6}",
            ]

        liquidadas = desglose[ExitReason.END_OF_SERIES]
        if liquidadas:
            lineas += [
                "",
                f"  [!] {liquidadas} posicion(es) seguian abiertas al agotarse el historico y se",
                "      valoraron al ultimo cierre. Ese resultado no lo realizo la estrategia:",
                "      depende de donde termina la serie, no de una decision de salida.",
            ]

        if self.data_warnings:
            lineas += ["", f"  [!] {len(self.data_warnings)} aviso(s) en los datos:"]
            lineas += [f"      - {aviso.message}" for aviso in self.data_warnings[:5]]

        return "\n".join(lineas)

    def _render_benchmark(self) -> list[str]:
        """La comparación que decide si la estrategia merece la pena.

        Va después de las métricas y antes de los avisos porque es la conclusión, no un detalle.
        Se dice en palabras además de en cifras: "no bate al mercado" no se malinterpreta.
        """
        if self.buy_and_hold is None or self.buy_and_hold.did_nothing:
            return []

        bh = self.buy_and_hold
        lineas = [
            "",
            "  Frente a comprar y mantener",
            f"    esta estrategia   {self.net_result:>16.2f}   (drawdown {self.max_drawdown:.2f})",
            f"    comprar y esperar {bh.net_result:>16.2f}   (drawdown {bh.max_drawdown:.2f})",
            f"    diferencia        {self.excess_return:>16.2f}",
        ]

        if self.beats_market:
            lineas.append("    -> la estrategia BATE a comprar y mantener")
        else:
            lineas.append(
                "    -> la estrategia NO bate a comprar y mantener: todo el riesgo asumido"
            )
            lineas.append("       y las comisiones pagadas quedaron por debajo de no hacer nada")

        # Ganar menos sufriendo mucho menos es un resultado legitimo, y merece decirse.
        if not self.beats_market and self.max_drawdown > bh.max_drawdown:
            lineas.append(
                "       (aunque su caida maxima fue menor: gano menos, pero sufrio menos)"
            )

        return lineas

    def _render_consistency(self) -> list[str]:
        """Como de regular fue el camino.

        El porcentaje de meses en verde NUNCA aparece solo: va pegado al peor mes y a la
        asimetria. Un 90% de meses positivos con un mes que se come veinte es el perfil de las
        estrategias que arruinan a quien las usa, y leido a solas parece excelente.
        """
        c = self.consistency
        if c is None or c.periods == 0:
            return []

        lineas = [
            "",
            "  Regularidad del camino",
            f"    meses en verde    {c.positive_periods}/{c.periods}  ({c.positive_ratio:.0%})",
            f"    mejor mes         {c.best_period:>12.2f}",
            f"    peor mes          {c.worst_period:>12.2f}",
            f"    racha en rojo     {c.longest_losing_streak} mes(es) seguidos",
        ]

        if c.positive_ratio >= 0.7 and c.asymmetry > 3:
            lineas += [
                f"    [!] {c.positive_ratio:.0%} de meses en verde, pero el peor mes se come",
                f"        {c.asymmetry:.1f} meses buenos. Ese perfil aguanta anos y luego lo",
                "        devuelve de golpe: mira la asimetria, no el porcentaje.",
            ]

        return lineas

    def __str__(self) -> str:
        return self.render()


def build_report(
    *,
    trades: Sequence[Trade],
    equity_curve: Sequence[Decimal],
    friction: FrictionConfig,
    risk: RiskConfig,
    symbol: str,
    min_trades: int,
    data_warnings: Sequence[DataWarning] = (),
    final_cash: Decimal = Decimal(0),
    rejected_orders: Sequence[Order] = (),
    benchmark: BuyAndHold | None = None,
    consistency: Consistency | None = None,
    equity_timestamps: Sequence[datetime] = (),
) -> BacktestReport:
    """Ensambla el informe a partir del registro de operaciones."""
    from invest_ll.report.metrics import expectancy, max_drawdown, win_rate

    resultados = [t.net_pnl for t in trades]

    return BacktestReport(
        net_result=sum(resultados, start=Decimal(0)),
        expectancy=expectancy(resultados),
        max_drawdown=max_drawdown(equity_curve),
        trade_count=len(trades),
        total_costs=sum((t.costs for t in trades), start=Decimal(0)),
        win_rate=win_rate(resultados),
        trades=tuple(trades),
        friction=friction,
        risk=risk,
        symbol=symbol,
        min_trades=min_trades,
        data_warnings=tuple(data_warnings),
        final_cash=final_cash,
        rejected_orders=tuple(rejected_orders),
        buy_and_hold=benchmark,
        consistency=consistency,
        equity_curve=tuple(equity_curve),
        equity_timestamps=tuple(equity_timestamps),
    )
