# Phase 1 — Data Model: Motor de Backtesting

**Feature**: 001-backtest-engine | **Fecha**: 2026-07-25

Entidades derivadas de la spec. Todas son **inmutables** salvo `PortfolioState`, que es el único
estado mutable del motor. La inmutabilidad no es dogma: es lo que hace que una estrategia no pueda
alterar los datos que recibe ni el historial ya registrado.

---

## Bar — observación de un periodo

Unidad mínima de la serie histórica.

| Campo | Tipo | Reglas |
|---|---|---|
| `timestamp` | `datetime` (con zona, UTC) | Obligatorio. Marca el **inicio** del periodo |
| `open` `high` `low` `close` | `float` | Todos > 0 |
| `volume` | `float` | ≥ 0 |

**Validación** (FR-015): `low ≤ open ≤ high`, `low ≤ close ≤ high`, ningún precio ≤ 0, ningún NaN.

---

## PriceSeries — serie histórica

| Campo | Tipo | Reglas |
|---|---|---|
| `symbol` | `str` | Identificador del activo |
| `interval` | `Interval` | Intervalo declarado (FR-032) |
| `calendar` | `MarketCalendar` | Calendario aplicable (FR-021) |
| `bars` | secuencia de `Bar` | Orden cronológico estricto, sin duplicados |

**Validación**:
- Marcas temporales estrictamente crecientes (FR-015).
- Cada marca alineada al `interval` declarado (FR-034).
- Todo hueco se clasifica contra `calendar`: **cierre legítimo** (ignorable) o **dato ausente**
  (se reporta, nunca se rellena — FR-016).

---

## MarketView — ventana temporal segura ★

**La pieza central del Principio II.** Es lo único que una estrategia recibe.

| Campo | Tipo | Reglas |
|---|---|---|
| `_series` | `PriceSeries` | Privado. Nunca expuesto en la interfaz pública |
| `_cursor` | `int` | Índice del último periodo **cerrado** y visible |

**Interfaz pública**: solo permite leer el periodo actual, los N anteriores, o la serie de cierres
hasta el cursor. Ninguna operación acepta un índice futuro.

**Invariantes**:
- Todo acceso a índice `> _cursor` lanza `LookAheadError` (FR-004).
- Los datos devueltos son inmutables: una estrategia no puede modificar el histórico.
- `_cursor` apunta a un periodo **cerrado**. La vela en curso no es visible: es lo que impide
  decidir con un cierre que aún no ha ocurrido (FR-024).

---

## Interval — granularidad

Duración fija de un periodo (1m, 5m, 1h, 1d…). El motor es agnóstico (FR-032); su única función es
validar la alineación de las marcas temporales y traducir "N periodos" a duración real.

---

## MarketCalendar — cuándo opera el mercado

Protocolo con dos preguntas: *¿está abierto en este instante?* y *¿cuál es el siguiente instante
negociable?*

| Implementación | Uso |
|---|---|
| `Continuous24x7` | Cripto. Siempre abierto |
| `ExchangeCalendarAdapter` | Bolsa. Envuelve `exchange_calendars` |

Permite distinguir cierre legítimo de dato ausente (FR-021) y diferir las señales emitidas con el
mercado cerrado (FR-022).

---

## Strategy — protocolo de decisión

Protocolo estructural (FR-017). Recibe un `MarketView` y devuelve una `Signal` o nada.

**Reglas**:
- No recibe capital, posición ni configuración de riesgo: el dimensionado es del motor (FR-027).
- Sus parámetros temporales se expresan en **número de periodos**, nunca en días (FR-033).
- Debe ser determinista: misma vista → misma señal (FR-005).

---

## Signal — intención de operar

| Campo | Tipo | Reglas |
|---|---|---|
| `kind` | `ENTER_LONG` \| `EXIT` | v1 no contempla cortos |
| `stop_loss` `take_profit` | `float` opcional | Niveles de protección (FR-028) |

La señal es una **intención**, no una ejecución: puede diferirse, ejecutarse parcialmente o ser
rechazada.

---

## Order — orden simulada

| Campo | Tipo | Notas |
|---|---|---|
| `signal_timestamp` | `datetime` | Instante de la decisión |
| `execution_timestamp` | `datetime` | Apertura del periodo siguiente (FR-024) |
| `requested_quantity` / `filled_quantity` | `float` | Distintos si hay ejecución parcial |
| `fill_price` | `float` | Precio efectivo, con slippage aplicado |
| `status` | `FILLED` \| `PARTIAL` \| `REJECTED` | FR-009 |
| `rejection_reason` | `str` opcional | Capital insuficiente, mercado cerrado, sin periodo siguiente |

**Invariante clave**: `execution_timestamp` es **siempre** posterior a `signal_timestamp`. Es la
representación en datos del Principio II — y es verificable a posteriori sobre el informe (SC-008).

---

## Trade — operación completa

Ciclo cerrado de entrada y salida.

| Campo | Tipo | Notas |
|---|---|---|
| `entry_order` / `exit_order` | `Order` | |
| `exit_reason` | `SIGNAL` \| `STOP_LOSS` \| `TAKE_PROFIT` \| `END_OF_SERIES` | FR-031 |
| `gross_pnl` / `costs` / `net_pnl` | `Decimal` | `net_pnl = gross_pnl − costs` |

**Invariante**: `net_pnl` de cada trade suma exactamente el resultado neto del informe (SC-007).

---

## PortfolioState — estado mutable del motor

Único estado que evoluciona. **Nunca visible para la estrategia**: dársela permitiría condicionar
la decisión al capital, rompiendo la comparabilidad del Principio V.

| Campo | Tipo |
|---|---|
| `cash` | `Decimal` |
| `open_position` | `Position` opcional (una a la vez en v1) |
| `equity_curve` | serie de `Decimal` |

---

## FrictionConfig / RiskConfig — configuración

**FrictionConfig** (FR-007, FR-008): comisión, slippage y regla de rechazo. **Sin valores por
defecto**: instanciarla exige declarar los costes, de forma que "cero comisiones" solo puede ser
una decisión escrita, nunca un descuido.

**RiskConfig** (FR-026): fracción del capital por entrada (0 < f ≤ 1), y stop-loss / take-profit
por defecto opcionales.

Ambas aparecen íntegras en el informe.

---

## BacktestReport — el veredicto

| Campo | Notas |
|---|---|
| `net_result` `expectancy` `max_drawdown` `trade_count` `total_costs` `win_rate` | Las seis obligatorias (FR-011) |
| `conclusive` | `False` si `trade_count < min_trades` (FR-013) |
| `inconclusive_reason` | Por qué no concluye |
| `trades` | Registro completo, auditable (FR-014) |
| `friction` / `risk` / `series_metadata` | Parámetros aplicados (FR-008) |
| `data_warnings` | Huecos detectados (FR-016) |

**Invariantes**:
- Las seis métricas están **siempre** presentes: el informe no puede construirse sin ellas
  (SC-002).
- `win_rate` nunca se presenta solo ni encabeza la representación textual (FR-012).
- `conclusive = False` con menos de 30 operaciones, **aunque el resultado sea excelente**.

---

## Errores del dominio

| Error | Cuándo |
|---|---|
| `LookAheadError` | Acceso a datos futuros (FR-004) |
| `InvalidSeriesError` | Serie que no pasa validación (FR-015, FR-034) |
| `InsufficientCapitalError` | Orden que excede la caja (FR-010) |

---

## Flujo de un paso de simulación

```
periodo N cierra
  → MarketView(cursor = N)
  → Strategy.decide(view) → Signal | None
  → si hay señal: Order(execution = apertura de N+1)
      → mercado cerrado en N+1 → diferir a la siguiente apertura (FR-022)
      → no existe N+1 → rechazar, sin operación fantasma
  → aplicar fricción → actualizar PortfolioState
  → comprobar stop/take sobre el rango del periodo, con convención pesimista (FR-029)
```

La estrategia nunca ve `PortfolioState`, ni `Order`, ni el periodo N+1. Solo `MarketView`.
