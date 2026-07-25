# Implementation Plan: Motor de Backtesting

**Branch**: `001-backtest-engine` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-backtest-engine/spec.md`

## Summary

Motor que simula la ejecución de una estrategia sobre una serie histórica y emite un veredicto
honesto sobre si habría ganado o perdido dinero. Es la primera feature del proyecto porque los
Principios II, III y IV de la constitución son propiedades de este componente: sin un medidor
fiable, ninguna estrategia posterior puede evaluarse.

**Enfoque técnico**: bucle secuencial sobre arrays numpy, donde la estrategia solo recibe un
`MarketView` — una ventana que envuelve la serie con un índice de corte y cuya interfaz pública no
puede devolver datos futuros. Esa pieza es la que convierte el Principio II de convención en
propiedad del diseño. La contabilidad usa `Decimal`; los indicadores, `float`. El calendario de
mercado se abstrae tras un protocolo propio con dos implementaciones (cripto 24/7 y bolsa vía
`exchange_calendars`), de forma que el mismo motor sirva para ambos mercados sin saber cuál está
simulando.

Decisiones y alternativas descartadas: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.13 (gestionado con `uv`; la máquina tiene 3.11.9 y 3.14.0 — ver R8)

**Primary Dependencies**: `numpy` (núcleo del bucle), `pandas` (carga y validación, solo en la
frontera), `exchange_calendars` (festivos bursátiles, tras adaptador propio)

**Storage**: ficheros de histórico en CSV (obligatorio) y Parquet (opcional). Sin base de datos:
las series son inmutables

**Testing**: `pytest` + `hypothesis` (invariantes del motor). `mutmut` **no aplica** en esta
máquina — Windows nativo lo instala pero no lo ejecuta; requiere WSL o contenedor y queda fuera
del bucle de esta feature

**Target Platform**: Windows 10 nativo (desarrollo). Sin dependencias específicas de plataforma;
el código debe correr igual en Linux

**Project Type**: librería Python con CLI de inspección

**Performance Goals**: veredicto completo sobre ~100.000 periodos en menos de 60 s (SC-001)

**Constraints**: sin E/S de red en el motor (FR-006); determinismo estricto — sin aleatoriedad sin
semilla, sin reloj del sistema, sin concurrencia en el bucle (FR-005)

**Scale/Scope**: un activo por backtest, un mercado por serie, una posición abierta a la vez, solo
posiciones largas (v1)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Derived from `.specify/memory/constitution.md` v1.0.0.

**Evaluación inicial (pre-Phase 0): PASS** — la feature es simulación pura y no toca ejecución
real.

**Re-evaluación post-Phase 1 (diseño completo)**:

| # | Gate | Estado | Evidencia en el diseño |
|---|------|--------|------------------------|
| I | Seguridad del capital (NO NEGOCIABLE) | **PASS** | El motor no importa ningún cliente de red ni SDK de broker (FR-006). No existe camino de código hacia una orden real: no hay modo "real" que activar en esta feature. Sin secretos: las series son ficheros locales |
| II | Sin look-ahead (NO NEGOCIABLE) | **PASS** | `MarketView` no expone públicamente ningún periodo posterior al cursor; el intento lanza `LookAheadError` (FR-004). La ejecución va a la apertura del periodo siguiente (FR-024) y el modo "ejecutar al cierre propio" está **prohibido por diseño** (FR-025). Verificado por el test de la estrategia tramposa (SC-003) |
| III | Métricas honestas | **PASS** | Las seis métricas son campos obligatorios de `BacktestReport`: un informe incompleto no llega a construirse (SC-002). `conclusive = False` por debajo de 30 operaciones aunque el resultado sea bueno (FR-013). El win rate no puede encabezar la representación textual (FR-012) |
| IV | Fricción realista | **PASS** | `FrictionConfig` es parámetro obligatorio sin valor por defecto en `run_backtest`: no se puede lanzar un backtest sin declarar costes. Órdenes rechazadas y parciales modeladas (FR-009). Convención pesimista cuando stop y take caben en la misma vela (FR-029) |
| V | Estrategias comparables | **PASS** | `Strategy` es un `Protocol` estructural: no exige herencia y admite igual una regla fija o un envoltorio de IA (FR-017). El dimensionado es competencia del motor, no de la estrategia (FR-027), de modo que dos estrategias con la misma configuración son comparables. Añadir una no toca el motor (FR-018, SC-005) |
| — | Gates técnicas | **PASS** | `ruff` → `pyright` → `pytest` documentadas en [quickstart.md](./quickstart.md). Sin actualización automática de baselines |

**Sin violaciones. La tabla de Complexity Tracking queda vacía.**

**Salvedad declarada, no violación** (R1): la garantía del Principio II es *estructural en la
interfaz pública*, no un sandbox — Python no ofrece encapsulación real y una estrategia decidida a
hacer trampa podría alcanzar el atributo privado por introspección. Por eso el diseño no descansa
solo en la barrera de tipos: SC-003 exige el test de la estrategia tramposa como verificación
independiente. Se documenta aquí para no afirmar más protección de la que existe.

## Project Structure

### Documentation (this feature)

```text
specs/001-backtest-engine/
├── plan.md              # Este fichero
├── spec.md              # Especificación (34 FR, 10 SC)
├── research.md          # Phase 0 — 8 decisiones técnicas
├── data-model.md        # Phase 1 — entidades e invariantes
├── quickstart.md        # Phase 1 — 8 validaciones ejecutables
├── contracts/
│   └── strategy-protocol.md   # Phase 1 — interfaz pública estable
├── checklists/
│   └── requirements.md  # Calidad de la spec (16/16)
└── tasks.md             # Phase 2 — lo genera /speckit-tasks
```

### Source Code (repository root)

```text
src/invest_ll/
├── data/
│   ├── bar.py            # Bar, Interval
│   ├── series.py         # PriceSeries + validación (FR-015, FR-034)
│   ├── loader.py         # CSV/Parquet → PriceSeries + DataWarning
│   └── calendars.py      # MarketCalendar, Continuous24x7, ExchangeCalendarAdapter
├── engine/
│   ├── view.py           # MarketView ★ el corazón del Principio II
│   ├── portfolio.py      # PortfolioState, Position
│   ├── execution.py      # Order, fricción, stop/take, convención pesimista
│   └── backtest.py       # run_backtest — el bucle
├── strategy/
│   ├── protocol.py       # Strategy (Protocol), Signal
│   └── moving_average.py # Estrategia de referencia (FR-019)
├── report/
│   ├── metrics.py        # expectancy, drawdown, win rate
│   └── report.py         # BacktestReport + presentación honesta (FR-012)
├── errors.py             # LookAheadError, InvalidSeriesError, InsufficientCapitalError
└── cli.py                # Inspección manual

tests/
├── unit/                 # execution_timing, report, friction, metrics, view
├── integration/          # end_to_end, no_lookahead ★, determinism, calendars, strategy_swap
├── property/             # invariantes con hypothesis
├── perf/                 # throughput (SC-001)
└── fixtures/             # series sintéticas con resultado calculado a mano

pyproject.toml            # deps, ruff, pyright, pytest
uv.lock                   # commiteado — reproducibilidad más allá del código
```

**Structure Decision**: librería única bajo `src/invest_ll/`, dividida en cuatro capas con una
dependencia estrictamente unidireccional: `data` → `engine` → `report`, con `strategy` dependiendo
solo del protocolo. El motor **no** conoce a las estrategias concretas (FR-018) ni la capa de datos
conoce al motor.

La separación `data` / `engine` es la que permite soportar cripto y bolsa sobre el mismo motor: las
diferencias de calendario viven enteras en `data/calendars.py` y el bucle de `engine/backtest.py`
no sabe qué mercado está simulando.

`engine/view.py` es el fichero más importante del proyecto. Es pequeño a propósito: cuanto menos
código tenga, más fácil es verificar que el Principio II se cumple.

## Complexity Tracking

> Sin violaciones de la constitución. Nada que justificar.
