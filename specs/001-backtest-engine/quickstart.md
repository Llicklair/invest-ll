# Quickstart — validar el motor de backtesting

**Feature**: 001-backtest-engine | **Fecha**: 2026-07-25

Cómo comprobar que el motor funciona de verdad. No es un tutorial: es la lista de comprobaciones
que deben pasar para dar la feature por terminada.

---

## Prerrequisitos

```bash
uv sync                 # instala dependencias y Python 3.13 si falta
uv run python -c "import numpy, pandas, exchange_calendars; print('deps OK')"
```

La segunda línea no es decorativa: confirma que las tres dependencias **importan** en 3.13.
Instalado no significa funcional.

---

## Gates del proyecto

Se ejecutan en este orden. Todas deben pasar antes de integrar.

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formato
uv run pyright              # tipos
uv run pytest               # suite completa, sin regresión
```

---

## Validación 1 — el motor mide (US1, P1)

```bash
uv run pytest tests/integration/test_end_to_end.py -v
```

**Qué prueba**: una serie sintética con resultado calculado a mano y una estrategia de cruce de
medias. El informe debe coincidir con el cálculo manual, operación por operación.

**Esperado**: informe con las seis métricas, y `net_result` idéntico al valor esperado.

---

## Validación 2 — el motor no se deja engañar (US2, P2) ★

La comprobación más importante del proyecto.

```bash
uv run pytest tests/integration/test_no_lookahead.py -v
```

**Qué prueba**: una estrategia deliberadamente tramposa que intenta leer precios futuros a través
de la interfaz pública de `MarketView`.

**Esperado**: `LookAheadError`. El test falla si el backtest **completa con éxito** — aquí el
éxito de la estrategia es el fallo del motor.

```bash
uv run pytest tests/integration/test_determinism.py -v
```

**Esperado**: dos ejecuciones idénticas producen informes idénticos campo a campo.

---

## Validación 3 — ejecución al precio correcto

```bash
uv run pytest tests/unit/test_execution_timing.py -v
```

**Esperado**: en el 100% de las órdenes del registro, `execution_timestamp` es la apertura del
periodo siguiente a `signal_timestamp` (SC-008). Ninguna se ejecuta al cierre de su propio periodo.

---

## Validación 4 — los dos mercados sobre el mismo motor

```bash
uv run pytest tests/integration/test_calendars.py -v
```

**Qué prueba**: la misma estrategia, sin modificar, sobre una serie de cripto 24/7 y una serie
bursátil con sesión.

**Esperado**:
- Ambas producen informes con la misma estructura (SC-009).
- Ningún cierre nocturno ni festivo aparece como aviso de dato ausente (SC-010).
- Una vela ausente **dentro** de sesión sí aparece como aviso.
- Ninguna orden se ejecuta con el mercado cerrado.

---

## Validación 5 — las métricas no mienten (US1, escenarios 2–4)

```bash
uv run pytest tests/unit/test_report.py -v
```

**Esperado**:
- Menos de 30 operaciones → `conclusive = False`, **también** cuando el resultado es positivo.
- Cero operaciones → no concluyente, nunca neutro.
- Win rate alto con expectancy negativa → el informe no lo presenta como éxito.
- Un informe no puede construirse sin las seis métricas.

---

## Validación 6 — la fricción pesa (US4, P3)

```bash
uv run pytest tests/unit/test_friction.py -v
```

**Esperado**: la misma estrategia con comisiones más altas da peor resultado neto, proporcional al
número de operaciones. `FrictionConfig` no puede instanciarse sin declarar costes.

---

## Validación 7 — invariantes bajo datos generados

```bash
uv run pytest tests/property -v
```

**Qué prueba**: property tests sobre series generadas. Invariantes: la caja nunca es negativa; el
drawdown máximo nunca es positivo; la suma de `net_pnl` de los trades reconstruye `net_result`
(SC-007); ninguna orden se ejecuta antes de su señal.

---

## Validación 8 — añadir una estrategia no toca el motor (US3, P3)

```bash
uv run pytest tests/integration/test_strategy_swap.py -v
```

**Esperado**: una segunda estrategia distinta se evalúa sobre los mismos datos sin ninguna
modificación en el motor (SC-005), y ambos informes son comparables campo a campo.

---

## Comprobación de rendimiento (SC-001)

```bash
uv run pytest tests/perf/test_throughput.py -v
```

**Esperado**: backtest sobre ~100.000 periodos en menos de 60 segundos.

---

## Ejecución manual

```bash
uv run python -m invest_ll.backtest --help
```

Para inspeccionar un informe a ojo sobre datos propios. No sustituye a las validaciones anteriores.

---

## Criterio de terminación

La feature está lista cuando las ocho validaciones pasan, las cuatro gates están en verde, y la
tabla de Constitution Check del plan sigue en PASS tras el diseño final.

Recordatorio de la constitución: los baselines y snapshots **no** se actualizan para hacer pasar un
test. Si una validación falla, se arregla el motor o se corrige la expectativa con una razón
escrita — nunca se regenera el valor esperado.
