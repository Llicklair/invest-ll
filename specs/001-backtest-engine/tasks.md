---

description: "Task list for 001-backtest-engine"
---

# Tasks: Motor de Backtesting

**Input**: Design documents from `/specs/001-backtest-engine/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **OBLIGATORIOS**. La constitución v1.0.0 exige test-first ("el comportamiento nuevo
empieza por un test que falla") y cobertura explícita de los Principios I, II y III. No es opcional
en este proyecto.

**Organization**: agrupadas por historia de usuario para poder entregar e independientemente
validar cada incremento.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1..US4)
- Todas las rutas son reales y salen de la estructura definida en plan.md

## Path Conventions

Librería única: `src/invest_ll/`, tests en `tests/` en la raíz del repositorio.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dejar el proyecto instalable y las gates ejecutables. Hasta aquí no hay lógica de
negocio.

- [X] T001 Crear `pyproject.toml` con `requires-python = ">=3.13"`, dependencias (`numpy`, `pandas`, `exchange_calendars`) y grupo dev (`pytest`, `hypothesis`, `ruff`, `pyright`)
- [X] T002 Ejecutar `uv sync` y verificar con una ejecución real que `numpy`, `pandas` y `exchange_calendars` importan en Python 3.13; commitear `uv.lock`
- [X] T003 [P] Configurar `ruff` (lint + format) en `pyproject.toml`
- [X] T004 [P] Configurar `pyright` en modo estricto sobre `src/` en `pyproject.toml`
- [X] T005 [P] Configurar `pytest` en `pyproject.toml`: rutas de test, marcadores `perf` y `property`
- [X] T006 Crear el esqueleto de paquetes `src/invest_ll/{data,engine,strategy,report}/__init__.py` y `tests/{unit,integration,property,perf,fixtures}/`
- [X] T007 Verificar que las cuatro gates corren en verde sobre el proyecto vacío: `ruff check .`, `ruff format --check .`, `pyright`, `pytest`

**Checkpoint**: gates ejecutables. Cualquier fallo posterior es del código, no del entorno.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: los cimientos que toda historia necesita, incluida la barrera anti-look-ahead.

**⚠️ CRÍTICO**: ninguna historia puede empezar hasta que esta fase esté completa.

**Nota de diseño**: `MarketView` con su `LookAheadError` va aquí, no en US2, porque el Principio II
es NO NEGOCIABLE y no puede construirse el motor sin él y añadirlo después. US2 es la *verificación
adversarial* de esta barrera, no su construcción.

### Tests (escribir primero, deben fallar)

- [X] T008 [P] Test de `Bar`: validación OHLC (`low ≤ open,close ≤ high`, precios > 0, sin NaN) en `tests/unit/test_bar.py`
- [X] T009 [P] Test de `PriceSeries`: orden cronológico estricto, sin duplicados, alineación al intervalo declarado en `tests/unit/test_series.py`
- [X] T010 [P] Test de `MarketView`: `history(n)` nunca devuelve datos posteriores al cursor; pedir un índice futuro lanza `LookAheadError`; `history(n)` con menos de `n` periodos devuelve los disponibles sin rellenar, en `tests/unit/test_view.py`
- [X] T011 [P] Test de calendarios: `Continuous24x7` siempre abierto; adaptador bursátil cerrado en festivo y fuera de sesión, en `tests/unit/test_calendars.py`
- [X] T012 [P] Test del loader: CSV válido carga; cierre legítimo no genera aviso, vela ausente dentro de sesión sí; serie inválida lanza `InvalidSeriesError`, en `tests/unit/test_loader.py`

### Implementación

- [X] T013 [P] Definir `LookAheadError`, `InvalidSeriesError` e `InsufficientCapitalError` en `src/invest_ll/errors.py`
- [X] T014 [P] Implementar `Bar` (frozen) e `Interval` con validación OHLC en `src/invest_ll/data/bar.py`
- [X] T015 [P] Implementar el protocolo `MarketCalendar`, `Continuous24x7` y `ExchangeCalendarAdapter` en `src/invest_ll/data/calendars.py`
- [X] T016 Implementar `PriceSeries` con validación completa (FR-015, FR-034) en `src/invest_ll/data/series.py` (depende de T014, T015)
- [X] T017 Implementar `MarketView` en `src/invest_ll/engine/view.py`: cursor, interfaz pública de solo-pasado, `LookAheadError` en acceso futuro (FR-002..FR-004) (depende de T016)
- [X] T018 Implementar `load_series` para CSV y Parquet, devolviendo `(PriceSeries, DataWarning[])` y clasificando huecos contra el calendario (FR-016, FR-021) en `src/invest_ll/data/loader.py` (depende de T016)
- [X] T019 [P] Crear fixtures de series sintéticas con resultado calculado a mano (cripto 24/7 y bolsa con sesión) en `tests/fixtures/`

**Checkpoint**: la barrera del Principio II existe y está probada. Puede empezar el motor.

---

## Phase 3: User Story 1 - Medir una estrategia sobre el pasado (Priority: P1) 🎯 MVP

**Goal**: dada una serie y una estrategia, producir un informe con las seis métricas obligatorias.

**Independent Test**: serie sintética + estrategia de cruce de medias → el informe coincide con el
resultado calculado a mano, operación por operación.

### Tests para US1 (escribir primero, deben fallar)

- [X] T020 [P] [US1] Test de contrato de `Strategy`/`Signal` según [contracts/strategy-protocol.md](./contracts/strategy-protocol.md) en `tests/unit/test_strategy_protocol.py`
- [X] T021 [P] [US1] Test de temporización: toda orden se ejecuta a la apertura del periodo siguiente al de la señal, nunca al cierre propio (FR-024, SC-008), en `tests/unit/test_execution_timing.py`
- [X] T022 [P] [US1] Test de métricas: expectancy, drawdown máximo y win rate sobre secuencias de operaciones conocidas, en `tests/unit/test_metrics.py`
- [X] T023 [P] [US1] Test del informe: no se puede construir sin las seis métricas; `conclusive = False` con menos de 30 operaciones aunque el resultado sea positivo; cero operaciones → no concluyente; el win rate no encabeza la salida textual (FR-011..FR-013), en `tests/unit/test_report.py`
- [X] T024 [P] [US1] Test de fricción: `FrictionConfig` no instanciable sin declarar costes; comisión y slippage aplicados a cada orden (FR-007, FR-008), en `tests/unit/test_friction.py`
- [X] T025 [P] [US1] Test de capital: orden que excede la caja se registra como rechazada, no revienta el backtest (FR-010), en `tests/unit/test_portfolio.py`
- [X] T026 [P] [US1] Test end-to-end: cruce de medias sobre fixture sintética → informe idéntico al cálculo manual, en `tests/integration/test_end_to_end.py`

### Implementación para US1

- [X] T027 [P] [US1] Definir el protocolo `Strategy`, `Signal` y `SignalKind` en `src/invest_ll/strategy/protocol.py`
- [X] T028 [P] [US1] Implementar `FrictionConfig` y `RiskConfig` sin valores por defecto en `src/invest_ll/engine/config.py`
- [X] T029 [US1] Implementar `PortfolioState` y `Position`: caja en `Decimal`, curva de equity, una posición a la vez, en `src/invest_ll/engine/portfolio.py` (depende de T028)
- [X] T030 [US1] Implementar `Order`, `Trade` y el motor de ejecución: apertura del periodo siguiente, comisión y slippage, rechazo por capital, ejecución parcial (FR-007..FR-010, FR-024), en `src/invest_ll/engine/execution.py` (depende de T029)
- [X] T031 [P] [US1] Implementar el cálculo de métricas (expectancy, drawdown máximo, win rate, costes totales) en `src/invest_ll/report/metrics.py`
- [X] T032 [US1] Implementar `BacktestReport` con las seis métricas como campos obligatorios, etiqueta `conclusive` y presentación que no encabeza con win rate (FR-011..FR-014), en `src/invest_ll/report/report.py` (depende de T031)
- [X] T033 [US1] Implementar `run_backtest`: bucle secuencial, `MarketView` por paso, dimensionado por fracción del capital (FR-026, FR-027), en `src/invest_ll/engine/backtest.py` (depende de T017, T030, T032)
- [X] T034 [US1] Implementar la estrategia de cruce de medias con parámetros en número de periodos (FR-019, FR-033) en `src/invest_ll/strategy/moving_average.py` (depende de T027)

**Checkpoint**: MVP funcional. El operador ya puede medir una estrategia y obtener un veredicto
honesto.

---

## Phase 4: User Story 2 - Confiar en que el medidor no miente (Priority: P2)

**Goal**: demostrar que la barrera anti-look-ahead construida en Foundational aguanta un intento
deliberado de engaño, y que el motor es reproducible.

**Independent Test**: una estrategia tramposa que intenta leer el futuro provoca `LookAheadError`;
dos ejecuciones idénticas producen informes idénticos.

### Tests para US2 (escribir primero, deben fallar)

- [ ] T035 [P] [US2] Estrategia tramposa que intenta acceder a periodos futuros por la interfaz pública de `MarketView`; el test **falla si el backtest completa con éxito** (SC-003), en `tests/integration/test_no_lookahead.py`
- [ ] T036 [P] [US2] Test de determinismo: dos ejecuciones idénticas producen informes idénticos campo a campo (FR-005, SC-006), en `tests/integration/test_determinism.py`
- [ ] T037 [P] [US2] Property test: ninguna orden tiene `execution_timestamp ≤ signal_timestamp`, sobre series generadas con `hypothesis`, en `tests/property/test_temporal_invariants.py`
- [ ] T038 [P] [US2] Test de borde temporal: señal en el último periodo de la serie no produce operación fantasma; posición abierta al acabar el histórico se valora sin contarla como ganancia realizada, en `tests/unit/test_series_end.py`

### Implementación para US2

- [ ] T039 [US2] Endurecer `MarketView` con los huecos que revelen T035–T037 y documentar en el docstring el límite real de la garantía (interfaz pública, no sandbox) en `src/invest_ll/engine/view.py`
- [ ] T040 [US2] Auditar el motor y eliminar toda fuente de no-determinismo (orden de iteración, aleatoriedad sin semilla, reloj del sistema) en `src/invest_ll/engine/backtest.py`
- [ ] T041 [US2] Implementar el cierre de posiciones abiertas al final de la serie con motivo `END_OF_SERIES` en `src/invest_ll/engine/backtest.py`

**Checkpoint**: el veredicto del motor es creíble y reproducible.

---

## Phase 5: User Story 3 - Comparar estrategias con la misma vara (Priority: P3)

**Goal**: evaluar estrategias de mecanismo distinto sobre los mismos datos y con las mismas
métricas, sin tocar el motor.

**Independent Test**: una segunda estrategia se evalúa sin ninguna modificación en el motor y
ambos informes son comparables campo a campo.

### Tests para US3 (escribir primero, deben fallar)

- [ ] T042 [P] [US3] Test de intercambio: dos estrategias distintas producen informes de la misma estructura sin cambios en el motor (SC-005), en `tests/integration/test_strategy_swap.py`
- [ ] T043 [P] [US3] Test multi-mercado: la misma estrategia, sin modificar, sobre serie cripto 24/7 y serie bursátil con sesión; ningún cierre legítimo se reporta como hueco y ninguna orden se ejecuta con el mercado cerrado (FR-022, SC-009, SC-010), en `tests/integration/test_calendars.py`

### Implementación para US3

- [ ] T044 [P] [US3] Implementar una segunda estrategia de referencia con mecanismo distinto al cruce de medias en `src/invest_ll/strategy/`
- [ ] T045 [US3] Implementar el diferimiento de señales emitidas con el mercado cerrado a la siguiente apertura (FR-022) en `src/invest_ll/engine/backtest.py`
- [ ] T046 [US3] Implementar la aplicación del gap de apertura a las posiciones mantenidas durante el cierre (FR-023) en `src/invest_ll/engine/execution.py`

**Checkpoint**: el motor es una herramienta de decisión, no solo de medición.

---

## Phase 6: User Story 4 - Ver cuánto pesa la fricción (Priority: P3)

**Goal**: hacer visible cuánto se comen los costes y las salidas de protección.

**Independent Test**: la misma estrategia con comisiones más altas da peor resultado neto,
proporcional al número de operaciones.

### Tests para US4 (escribir primero, deben fallar)

- [ ] T047 [P] [US4] Test de sensibilidad a la fricción: mayor comisión → peor resultado neto, proporcional al número de operaciones; los parámetros aplicados aparecen en el informe, en `tests/unit/test_friction_impact.py`
- [ ] T048 [P] [US4] Test de stop/take: nivel tocado dentro del periodo se ejecuta; con stop y take ambos alcanzables en la misma vela se asume el **stop** (FR-029); apertura que atraviesa el stop ejecuta al precio de apertura real, no al nivel (FR-030), en `tests/unit/test_protective_exits.py`
- [ ] T049 [P] [US4] Test de clasificación: el informe distingue cierres por señal, por stop-loss y por take-profit (FR-031), en `tests/unit/test_exit_reasons.py`

### Implementación para US4

- [ ] T050 [US4] Implementar stop-loss y take-profit gestionados por el motor con convención pesimista y gap real (FR-028..FR-030) en `src/invest_ll/engine/execution.py`
- [ ] T051 [US4] Añadir `exit_reason` a `Trade` y su desglose al informe (FR-031) en `src/invest_ll/report/report.py`
- [ ] T052 [US4] Implementar órdenes rechazadas y ejecuciones parciales como estados de primera clase (FR-009) en `src/invest_ll/engine/execution.py`

**Checkpoint**: las cuatro historias funcionan de forma independiente.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T053 [P] Property tests de invariantes económicos: la caja nunca es negativa, el drawdown máximo nunca es positivo, la suma de `net_pnl` reconstruye `net_result` (SC-007), en `tests/property/test_economic_invariants.py`
- [ ] T054 [P] Test de rendimiento: backtest sobre ~100.000 periodos en menos de 60 s (SC-001) en `tests/perf/test_throughput.py`
- [ ] T055 [P] Implementar la CLI de inspección (`python -m invest_ll.backtest`) en `src/invest_ll/cli.py`
- [ ] T056 [P] Escribir `README.md` con el uso del motor y el aviso de que el win rate no es criterio de éxito
- [ ] T057 Ejecutar las ocho validaciones de [quickstart.md](./quickstart.md) de principio a fin y dejar constancia del resultado
- [ ] T058 Ejecutar la cadena completa de gates (`ruff` → `pyright` → `pytest`) sin regresión
- [ ] T059 Crear el workflow de CI en `.github/workflows/ci.yml` que ejecuta las cuatro gates en cada push y PR
- [ ] T060 Activar la branch protection de `main` con el check de CI de T059 y revisión requerida ≥1 — **la ejecuta Marcos en su terminal**, cierra el `TODO(BRANCH_PROTECTION)` de la constitución

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup. **BLOQUEA todas las historias**
- **US1 (Phase 3)**: depende de Foundational. Es el MVP
- **US2 (Phase 4)**: depende de US1 (necesita el motor completo para atacarlo)
- **US3 (Phase 5)**: depende de US1. Independiente de US2
- **US4 (Phase 6)**: depende de US1. Independiente de US2 y US3
- **Polish (Phase 7)**: depende de las historias que se quieran entregar. T059 → T060

### Dentro de cada historia

Tests primero y **deben fallar** antes de implementar (constitución, test-first) → modelos →
motor → informe.

### Parallel Opportunities

- Setup: T003, T004, T005 en paralelo
- Foundational: los cinco tests T008–T012 en paralelo; luego T013, T014, T015 en paralelo
- US1: los siete tests T020–T026 en paralelo; T027, T028, T031 en paralelo
- US2: los cuatro tests T035–T038 en paralelo
- Una vez terminado US1, las fases US2, US3 y US4 pueden avanzar en paralelo

---

## Parallel Example: User Story 1

```bash
# Todos los tests de US1 a la vez (deben fallar antes de implementar):
tests/unit/test_strategy_protocol.py
tests/unit/test_execution_timing.py
tests/unit/test_metrics.py
tests/unit/test_report.py
tests/unit/test_friction.py
tests/unit/test_portfolio.py
tests/integration/test_end_to_end.py

# Componentes sin dependencias entre sí:
src/invest_ll/strategy/protocol.py
src/invest_ll/engine/config.py
src/invest_ll/report/metrics.py
```

---

## Implementation Strategy

### MVP (solo US1)

1. Phase 1: Setup
2. Phase 2: Foundational — **crítico**, incluye la barrera del Principio II
3. Phase 3: US1
4. **PARAR Y VALIDAR**: el informe coincide con el cálculo manual
5. En este punto el operador ya puede medir estrategias

### Entrega incremental

1. Setup + Foundational → cimientos
2. + US1 → **MVP**: se puede medir
3. + US2 → se puede *confiar* en lo que se mide
4. + US3 → se pueden comparar estrategias y mercados
5. + US4 → se ve el peso de la fricción y las protecciones

**Recomendación**: no saltarse US2 aunque el MVP ya "funcione". Un medidor en el que no se confía
produce decisiones peores que no tener medidor, porque da confianza injustificada.

---

## Notes

- 60 tareas: 7 setup · 12 foundational · 15 US1 · 7 US2 · 5 US3 · 6 US4 · 8 polish
- Los tests deben **fallar** antes de implementar. Un test que pasa a la primera no está probando
  lo que crees
- Prohibido actualizar baselines o snapshots para hacer pasar un test (constitución)
- Commit por tarea o grupo lógico. Los loops autónomos nunca mergean
- T060 es la única tarea que **no** ejecuta el agente: cambia ajustes de un repo remoto y la
  ejecuta Marcos
