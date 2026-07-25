# Tareas: Asistente de Inversión

**Feature**: `003-investment-assistant` · **Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md)

**Test-first** (constitución): el test se escribe y falla antes de la implementación. Las cuatro
gates (`ruff check`, `ruff format --check`, `pyright`, `pytest`) pasan antes de integrar nada.

**Orden**: US2 va antes que US1 aunque ambas sean P1. US2 responde a la pregunta que motiva toda la
feature —¿el LLM elige mejor que una regla?— y las demás se construyen sabiendo ya la respuesta.

---

## Fase 1 · Preparación

- [X] T001 Añadir `anthropic>=0.60` a las dependencias en `pyproject.toml` con el comentario de que solo lo usa `src/invest_ll/decision/`
- [X] T002 [P] Crear los paquetes `src/invest_ll/decision/`, `analysis/`, `tracking/` y `live/` con sus `__init__.py`
- [X] T003 [P] Ampliar `.gitignore` con `decisions/` y `ledger/` — decisiones cacheadas y registro de órdenes no se commitean

---

## Fase 2 · Cimientos (bloquean todas las historias)

Sin esto no hay nada que probar. Es la capa que aísla el LLM tras una interfaz.

### Entidades

- [X] T004 [P] Test de `AssetDecision` y `Decision` en `tests/unit/test_decision_entities.py`: pesos fuera de [0,1] rechazados, símbolos repetidos rechazados, suma de pesos > 1 rechazada, razonamiento vacío rechazado
- [X] T005 Implementar `AssetDecision`, `Decision` y `Action` en `src/invest_ll/decision/models.py` — `frozen=True`, `Decimal` para pesos
- [X] T006 [P] Test de `DecisionRequest.cache_key` en `tests/unit/test_decision_cache_key.py`: la clave cambia con el modelo, con las instrucciones y con el instante; **no** cambia con el orden de los símbolos
- [X] T007 Implementar `DecisionRequest` con `cache_key` en `src/invest_ll/decision/models.py`

### Traducción de MarketView a texto

- [X] T008 [P] Test de `render_context()` en `tests/unit/test_decision_prompt.py`: el texto generado **no** contiene fechas reales ni datos posteriores al instante simulado (FR-009, FR-010)
- [X] T009 Implementar `render_context(view, symbols)` en `src/invest_ll/decision/prompt.py` — función pura, sin red, que solo lee de `UniverseView`
- [X] T010 [P] Test de propiedad con hypothesis en `tests/property/test_prompt_no_lookahead.py`: para cualquier cursor, el texto no menciona ningún precio posterior

### Esquema y validación

- [X] T011 [P] Test de `parse_decision()` en `tests/unit/test_decision_schema.py`: JSON válido se convierte; JSON con pesos > 1 lanza `DecisionParseError`; texto libre lanza `DecisionParseError`; **nunca** devuelve una decisión por defecto (FR-011)
- [X] T012 Implementar el esquema JSON y `parse_decision()` en `src/invest_ll/decision/schema.py` — los límites numéricos se validan en código, no en el esquema (research D3)

### Proveedores

- [X] T013 [P] Test de `ScriptedProvider` y `RecordedProvider` en `tests/unit/test_decision_providers.py`: devuelven lo grabado, lanzan `DecisionUnavailableError` si falta, y **no abren un socket**
- [X] T014 Definir el protocolo `DecisionProvider` con `decide()` y `decide_many()` en `src/invest_ll/decision/provider.py` (research D4: los lotes desde el principio)
- [X] T015 Implementar `ScriptedProvider` y `RecordedProvider` en `src/invest_ll/decision/provider.py`
- [X] T016 [P] Test de `CachedProvider` en `tests/unit/test_decision_cachedprovider.py`: la segunda petición idéntica **no** llama al proveedor envuelto; cambiar de modelo **sí** lo llama (FR-045)
- [X] T017 Implementar `CachedProvider` y el almacén en disco en `src/invest_ll/decision/cache.py` — escritura atómica como la 002
- [X] T018 Implementar `AnthropicProvider` en `src/invest_ll/decision/anthropic_provider.py` — `claude-opus-5`, salida estructurada, **sin `temperature`** (research D2), `stop_reason` comprobado antes del contenido
- [X] T019 [P] Test de coste en `tests/unit/test_decision_cost.py`: cuenta las decisiones nuevas, descuenta las cacheadas, marca `needs_confirmation` por encima del umbral (FR-041)
- [X] T020 Implementar `estimate_cost()` en `src/invest_ll/decision/cost.py`

**Punto de control**: `uv run pytest tests/unit/test_decision_*.py` en verde y la suite entera sigue pasando sin red.

---

## Fase 3 · US2 · Que el LLM elija, y saber si acierta (P1)

**La fase que responde a la pregunta.** Entregable por sí sola: se puede comparar el LLM contra una
regla fija con las mismas métricas.

- [X] T021 [P] [US2] Test en `tests/unit/test_llm_strategy.py`: `LLMStrategy` cumple el protocolo `RotationStrategy` y `run_rotation()` la acepta sin distinguirla (FR-006, Principio V)
- [X] T022 [P] [US2] Test en `tests/unit/test_llm_strategy.py`: entre puntos de decisión reutiliza la vigente y **no** consulta al proveedor en cada vela (FR-042)
- [X] T023 [P] [US2] Test en `tests/unit/test_llm_strategy.py`: un fallo del proveedor **detiene** el backtest en vez de sustituirlo por "mantener" (contrato de `LLMStrategy`)
- [X] T024 [US2] Implementar `LLMStrategy` en `src/invest_ll/strategy/llm.py` con `frequency` configurable, mensual por defecto (FR-040)
- [X] T025 [P] [US2] Test en `tests/unit/test_llm_report_parity.py`: el informe del LLM tiene **exactamente** las mismas métricas que el de `RelativeMomentum` — mismo orden, win rate el último con su coletilla (FR-007, Principio III)
- [X] T026 [P] [US2] Test en `tests/unit/test_llm_lookahead.py`: `LLMStrategy` no puede acceder a datos futuros — el mismo test que ya protege a las reglas fijas, aplicado al LLM (FR-009, Principio II)
- [X] T027 [P] [US2] Test en `tests/unit/test_llm_reasoning.py`: el razonamiento de cada decisión queda registrado y es recuperable (FR-012)
- [X] T028 [US2] Implementar el registro del razonamiento junto a la decisión en `src/invest_ll/decision/cache.py`
- [X] T029 [P] [US2] Test en `tests/unit/test_llm_no_prediction_claims.py`: ningún texto generado afirma capacidad de predicción; se comprueba contra una lista de expresiones prohibidas (FR-013)
- [X] T030 [US2] Añadir la advertencia de contaminación de conocimiento al informe del LLM en `src/invest_ll/report/report.py` (FR-010) — el modelo sabe qué pasó después del periodo simulado y eso no tiene arreglo
- [X] T031 [US2] Comando `invest-ll-compare` en `src/invest_ll/cli/compare.py`: varias estrategias, mismo universo, mismo split, tabla comparativa
- [X] T032 [P] [US2] Test del comando en `tests/integration/test_compare_cli.py` con proveedor grabado, sin red

**Punto de control** (escenarios E1 y E2 del quickstart): se puede ejecutar la comparación y repetirla obteniendo lo mismo sin gastar una llamada.

---

## Fase 4 · US1 · Pedir una propuesta y ver qué habría pasado (P1)

- [X] T033 [P] [US1] Test en `tests/unit/test_proposal.py`: con importe y periodicidad devuelve una cartera concreta con cantidades (FR-001)
- [X] T034 [US1] Implementar `propose_portfolio()` en `src/invest_ll/proposal/builder.py`
- [X] T035 [P] [US1] Test en `tests/unit/test_proposal.py`: toda propuesta trae su simulación con las seis métricas y la comparación contra no hacer nada (FR-002, FR-003)
- [X] T036 [US1] Conectar la propuesta con `run_dca()` y `analyze_portfolio()` — reutiliza lo que ya existe
- [X] T037 [P] [US1] Test en `tests/unit/test_proposal_explanations.py`: cada activo trae su explicación en lenguaje llano (FR-004)
- [X] T038 [P] [US1] Test en `tests/unit/test_proposal.py`: no se exige elegir estrategia ni parámetros (FR-005) — la firma solo pide importe y periodicidad
- [X] T039 [US1] Comando `invest-ll-propose` en `src/invest_ll/cli/propose.py`
- [X] T040 [P] [US1] Test del comando en `tests/integration/test_propose_cli.py`

**Punto de control** (E4): `invest-ll-propose --amount 500 --frequency monthly` da una cartera con su simulación.

---

## Fase 5 · US3 · Saber qué hay detrás de cada activo (P2)

- [X] T041 [P] [US3] Test en `tests/unit/test_asset_analysis.py`: un `Fact` sin `source` o sin `as_of` **no se construye** (FR-017)
- [X] T042 [US3] Implementar `Fact` y `AssetAnalysis` en `src/invest_ll/analysis/models.py`
- [X] T043 [P] [US3] Test en `tests/unit/test_asset_analysis.py`: los hechos verificables y la interpretación del LLM viven en campos separados (FR-049)
- [X] T044 [US3] Implementar `YFinanceResearcher` en `src/invest_ll/analysis/yfinance_researcher.py` — sector, tamaño, deuda, márgenes
- [X] T045 [P] [US3] Test en `tests/unit/test_asset_analysis.py`: un activo sin entidad detrás (oro, un índice) se explica sin inventarle una empresa (FR-019)
- [X] T046 [P] [US3] Test en `tests/unit/test_asset_analysis.py`: los escenarios se presentan como escenarios, nunca como predicciones (FR-018)
- [X] T047 [US3] Añadir en `src/invest_ll/analysis/models.py` la advertencia de que los datos son actuales y **no sirven** para analizar el pasado (FR-051)
- [X] T048 [US3] Comando `invest-ll-analyze` en `src/invest_ll/cli/analyze.py`

**Punto de control** (E5): el informe distingue visiblemente dato de interpretación.

---

## Fase 6 · US4 · Comparar lo estimado con lo que pasó (P2)

**La única evidencia no contaminada que vamos a tener.**

- [X] T049 [P] [US4] Test en `tests/unit/test_forecast.py`: una estimación registrada **no se puede modificar** (FR-021)
- [X] T050 [US4] Implementar `Forecast` y `Outcome` en `src/invest_ll/tracking/models.py`
- [X] T051 [P] [US4] Test en `tests/unit/test_forecast_store.py`: el almacén **solo añade**; reescribir el histórico falla
- [X] T052 [US4] Implementar `ForecastStore` en `src/invest_ll/tracking/store.py` — escritura atómica, solo-añadir
- [X] T053 [P] [US4] Test en `tests/unit/test_forecast_evaluation.py`: comparar una estimación con datos posteriores da la diferencia (FR-022)
- [X] T054 [US4] Implementar `evaluate_forecast()` en `src/invest_ll/tracking/forecast.py`
- [X] T055 [P] [US4] Test en `tests/unit/test_forecast_evaluation.py`: el histórico conserva los fallos y muestra si el sistema tiende a pasarse o quedarse corto (FR-023, FR-024)
- [X] T056 [US4] Comando `invest-ll-track` en `src/invest_ll/cli/track.py` con `--list` y `--evaluate`

**Punto de control** (E6): una estimación que salió mal sigue en la lista.

---

## Fase 7 · US5 · Pasar a dinero real (P3)

**La fase con más tests de cosas que NO deben poder pasar.** Va la última a propósito.

### Modos como tipos

- [X] T057 [P] [US5] Test en `tests/unit/test_operating_mode.py`: el modo por defecto **es** `Simulation` sin configurar nada (FR-025)
- [X] T058 [US5] Implementar `Simulation`, `Testnet` y `Real` como tipos distintos en `src/invest_ll/live/mode.py` — no un booleano ni un enum con un flag
- [X] T059 [P] [US5] Test en `tests/unit/test_operating_mode.py`: el modo real exige acción explícita **y** credenciales separadas; ninguna de las dos por sí sola basta (FR-026)
- [X] T060 [P] [US5] Test en `tests/unit/test_operating_mode.py`: el modo real **no** se activa por configuración heredada ni por un valor por defecto (FR-027)

### El broker

- [X] T061 [P] [US5] Test en `tests/unit/test_broker_contract.py`: `submit()` **no se puede llamar** sin construir una `Confirmation` para esa orden concreta (FR-028)
- [X] T062 [US5] Definir el protocolo `Broker` y `Confirmation` en `src/invest_ll/live/broker.py` — `confirmation` sin valor por defecto
- [X] T063 [P] [US5] Test en `tests/unit/test_live_safety.py`: `SimulatedBroker` **nunca** produce una orden real, con ninguna confirmación (FR-038)
- [X] T064 [US5] Implementar `SimulatedBroker` en `src/invest_ll/live/simulated_broker.py`
- [ ] T065 [P] [US5] Test en `tests/unit/test_ccxt_broker.py` con doble: el modo se comprueba **al enviar**, no al construir (FR-032)
- [ ] T066 [US5] Implementar `CcxtBroker` en `src/invest_ll/live/ccxt_broker.py` — credenciales del entorno (FR-033)
- [X] T067 [P] [US5] Test en `tests/unit/test_live_safety.py`: las credenciales de pruebas y las reales no son intercambiables; usarlas cruzadas **falla visiblemente** (FR-048)
- [X] T068 [P] [US5] Test en `tests/unit/test_live_safety.py`: ningún mensaje de error, registro ni informe contiene una credencial (FR-034)
- [X] T069 [P] [US5] Test en `tests/unit/test_ccxt_broker.py`: perder la conexión con una orden enviada da `UNKNOWN`, nunca `FILLED` ni `REJECTED` (FR-035)

### Registro y testnet obligatoria

- [X] T070 [P] [US5] Test en `tests/unit/test_execution_ledger.py`: cada orden queda registrada con lo pedido, lo ejecutado **y el modo** (FR-030)
- [X] T071 [US5] Implementar `ExecutionLedger` en `src/invest_ll/live/ledger.py` — solo añadir
- [X] T072 [P] [US5] Test en `tests/unit/test_execution_ledger.py`: una diferencia entre lo pedido y lo ejecutado se comunica, no se da por buena (FR-031)
- [X] T073 [P] [US5] Test en `tests/unit/test_live_safety.py`: sin haber operado antes en testnet, el modo real se **rechaza** (FR-047)
- [X] T074 [US5] Implementar la comprobación de testnet previa en `src/invest_ll/live/mode.py`
- [ ] T075 [US5] Comando `invest-ll-execute` en `src/invest_ll/cli/execute.py` con confirmación interactiva por orden
- [ ] T076 [P] [US5] Test de integración en `tests/integration/test_execute_cli.py`: los cuatro negativos del escenario E7 se comportan como se describe

**Punto de control** (E7): las cuatro cosas que no deben poder pasar, no pasan.

---

## Fase 8 · Cierre

- [X] T077 [P] Ampliar `tests/unit/test_engine_isolation.py`: el motor no importa `decision`, `live`, `analysis` ni `anthropic`
- [ ] T078 [P] Test en `tests/unit/test_no_network_in_suite.py`: la suite entera pasa con los sockets bloqueados y **sin una sola llamada al modelo** (FR-036, SC-011)
- [ ] T079 [P] Añadir al panel la pestaña de comparación LLM vs reglas en `src/invest_ll/dashboard/app.py`
- [ ] T080 [P] Añadir al panel la vista de estimado contra real en `src/invest_ll/dashboard/app.py`
- [ ] T081 [P] Actualizar `README.md` con los comandos nuevos y la advertencia sobre el modo real
- [ ] T082 Ejecutar los 8 escenarios de [quickstart.md](quickstart.md) y dejar constancia del resultado
- [ ] T083 Las cuatro gates en verde: `ruff check` · `ruff format --check` · `pyright` · `pytest`

---

## Dependencias

```
Fase 1 (preparación)
   └─> Fase 2 (cimientos) ─── bloquea todo lo demás
          ├─> Fase 3 · US2 ← empezar aquí: responde la pregunta
          ├─> Fase 4 · US1 (necesita US2 para simular la propuesta)
          ├─> Fase 5 · US3 (independiente de US1/US2)
          ├─> Fase 6 · US4 (independiente)
          └─> Fase 7 · US5 (independiente; va la última por criterio, no por dependencia)
                 └─> Fase 8 (cierre)
```

**US3, US4 y US5 son independientes entre sí**: se pueden abordar en cualquier orden una vez están
los cimientos. US1 depende de US2 porque su simulación usa la estrategia.

## Paralelismo

Las tareas marcadas `[P]` tocan ficheros distintos y no dependen de tareas incompletas. Dentro de
cada fase, todos los tests `[P]` se pueden escribir a la vez antes de implementar nada — que es
justo lo que pide el test-first.

## Alcance mínimo útil

**Fases 1 + 2 + 3.** Con eso ya se puede responder a la pregunta que motiva la feature: *¿el LLM
elige mejor que una regla fija?* Si la respuesta es que no —y los 40 barridos de estrategias
apuntan a que puede serlo— eso cambia qué merece la pena construir después.

Total: **83 tareas** · US2 · 12 · US1 · 8 · US3 · 8 · US4 · 8 · US5 · 20
