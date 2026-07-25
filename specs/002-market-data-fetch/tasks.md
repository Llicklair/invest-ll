---

description: "Task list for 002-market-data-fetch"
---

# Tasks: Descarga de Histórico Real de Mercado

**Input**: Design documents from `/specs/002-market-data-fetch/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **OBLIGATORIOS**. La constitución v1.0.0 exige test-first. Aquí además son la única
garantía de dos cosas que ningún humano puede vigilar de forma continua: que el motor no adquiera
red, y que la fusión de rangos no corrompa un histórico en silencio.

**Organization**: agrupadas por historia de usuario.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1..US4)
- Todas las rutas salen de la estructura definida en plan.md

## Path Conventions

Paquete nuevo `src/invest_ll/fetch/`, hermano del motor. Tests en `tests/` en la raíz.

---

## Phase 1: Setup

**Purpose**: dependencias nuevas y bloqueo global de red en la suite.

- [X] T001 Añadir `ccxt` y `yfinance` a las dependencias en `pyproject.toml`
- [X] T002 Ejecutar `uv sync` y verificar con una ejecución real que `ccxt` y `yfinance` importan en Python 3.14; actualizar `uv.lock`
- [X] T003 Crear el esqueleto `src/invest_ll/fetch/` y `src/invest_ll/fetch/providers/` con sus `__init__.py`
- [X] T004 Configurar en `tests/conftest.py` un fixture autouse que **bloquea `socket.socket`** durante toda la suite (FR-024, SC-002)
- [X] T005 [P] Verificar que la suite existente de la feature 001 sigue en verde con la red bloqueada — si algo falla, la 001 tenía una dependencia de red que nadie había visto
- [X] T006 [P] Añadir `data/market/` a `.gitignore` si no queda ya cubierto por la entrada `data/`

**Checkpoint**: la red está cortada en los tests y las dependencias nuevas funcionan.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: el protocolo, el almacenamiento y —sobre todo— el guardián del aislamiento.

**⚠️ CRÍTICO**: ninguna historia puede empezar hasta que esta fase esté completa.

### Tests (escribir primero, deben fallar)

- [X] T007 [P] ★ Test de aislamiento del motor: análisis estático de los imports de `engine/`, `report/` y `strategy/` (ningún `socket`, `http`, `urllib`, `requests`, `httpx`, `ccxt`, `yfinance` ni `invest_ll.fetch`) **y** un backtest completo con `socket` bloqueado que debe terminar correctamente (FR-001..FR-003, SC-003), en `tests/unit/test_engine_isolation.py`
- [X] T008 [P] Test de `FetchRequest`: rango invertido o vacío se rechaza; marcas sin zona se rechazan, en `tests/unit/test_fetch_request.py`
- [X] T009 [P] Test del protocolo `MarketDataProvider`: un objeto con `fetch` y `capabilities` lo cumple sin heredar; el proveedor grabado devuelve velas ordenadas y sin duplicados, en `tests/unit/test_provider_protocol.py`
- [X] T010 [P] Test de `HistoryStore`: `load` devuelve `None` cuando no hay nada (no lanza); `save` escribe un CSV que el loader de la 001 carga sin conversión (FR-005), en `tests/unit/test_store.py`
- [X] T011 [P] Test de atomicidad: un fallo a mitad de la escritura no deja ningún fichero que el motor acepte como completo (FR-012), en `tests/unit/test_store_atomicity.py`
- [X] T012 [P] Test de reintentos: espera creciente, tres intentos, y agotados se conserva lo local (FR-014, FR-015). La espera va inyectada: el test no debe tardar, en `tests/unit/test_retry.py`

### Implementación

- [X] T013 [P] Definir los errores de la capa de datos (`UnknownSymbolError`, `UnsupportedIntervalError`, `NoDataError`, `ProviderUnavailableError`, `RateLimitError`) en `src/invest_ll/fetch/errors.py`
- [X] T014 [P] Implementar `FetchRequest` y `Market` con validación en `src/invest_ll/fetch/request.py`
- [X] T015 [P] Definir el protocolo `MarketDataProvider` y `ProviderCapabilities` en `src/invest_ll/fetch/protocol.py`
- [X] T016 [P] Implementar `Provenance` y `QualityWarning` (serializables a JSON) en `src/invest_ll/fetch/provenance.py`
- [X] T017 Implementar `HistoryStore` con escritura atómica vía fichero temporal en el mismo directorio y `os.replace()` (FR-012) en `src/invest_ll/fetch/store.py` (depende de T014, T016)
- [X] T018 [P] Implementar la espera escalonada inyectable en `src/invest_ll/fetch/retry.py`
- [X] T019 [P] Implementar `RecordedProvider` (respuestas fijas, sin red) en `src/invest_ll/fetch/providers/recorded.py`
- [X] T020 [P] Crear las respuestas grabadas de cripto y de bolsa en `tests/fixtures/recorded/`

**Checkpoint**: el aislamiento del motor está vigilado y el almacenamiento es seguro.

---

## Phase 3: User Story 1 - Traerse el histórico de un activo (Priority: P1) 🎯 MVP

**Goal**: descargar el histórico real de un activo y poder lanzar un backtest sobre él sin
conversión manual.

**Independent Test**: con el proveedor grabado, descargar un histórico y ejecutar un backtest sobre
el fichero resultante.

### Tests para US1 (escribir primero, deben fallar)

- [X] T021 [P] [US1] Test de fusión básica: sin nada almacenado, el resultado es lo descargado, en orden y sin duplicados, en `tests/unit/test_merge.py`
- [X] T022 [P] [US1] Test de la vela en curso: el último periodo no cerrado se descarta; el instante actual va inyectado (FR-007), en `tests/unit/test_current_bar.py`
- [X] T023 [P] [US1] Test de validación: datos que no pasan las reglas del motor no se guardan (FR-019); los huecos se reportan y no se rellenan (FR-020), en `tests/unit/test_fetch_validation.py`
- [X] T024 [P] [US1] Test de errores: activo desconocido, rango sin datos y granularidad no soportada se comunican con claridad y **no dejan fichero a medias** (FR-009), en `tests/unit/test_fetch_errors.py`
- [X] T025 [P] [US1] Test end-to-end: descargar con el proveedor grabado y ejecutar un backtest sobre el CSV resultante sin conversión manual (SC-001), en `tests/integration/test_fetch_to_backtest.py`

### Implementación para US1

- [X] T026 [US1] Implementar `merge` como **función pura** (sin E/S, sin red, sin reloj): fusión, orden y deduplicación, en `src/invest_ll/fetch/merge.py`
- [X] T027 [US1] Implementar `fetch_history`: orquestación completa con `now` y `sleep` inyectados (FR-004..FR-008), en `src/invest_ll/fetch/service.py` (depende de T017, T026)
- [X] T028 [P] [US1] Implementar `CcxtProvider` con paginación, marcas en UTC y control de tasa de la propia librería, en `src/invest_ll/fetch/providers/crypto.py`
- [X] T029 [P] [US1] Implementar `YFinanceProvider` con `auto_adjust=True` para obtener precios ajustados (FR-017), en `src/invest_ll/fetch/providers/equity.py`
- [X] T030 [US1] Implementar la selección de proveedor y calendario según el mercado (cripto → continuo, bolsa → calendario bursátil) en `src/invest_ll/fetch/service.py`
- [X] T031 [US1] Implementar la CLI de descarga `invest-ll-fetch` con los códigos de salida del contrato en `src/invest_ll/cli_fetch.py`
- [X] T032 [US1] Registrar el ejecutable `invest-ll-fetch` en `pyproject.toml`

**Checkpoint**: MVP. Ya se puede backtestear sobre mercado real en vez de sobre series inventadas.

---

## Phase 4: User Story 2 - No corromper un histórico ya usado (Priority: P2)

**Goal**: que un histórico ya usado en un backtest no cambie a espaldas del operador, y que las
revisiones del proveedor se detecten.

**Independent Test**: alterar la respuesta del proveedor grabado, redescargar, y comprobar que se
detecta y **no se sobrescribe**.

### Tests para US2 (escribir primero, deben fallar)

- [ ] T033 [P] [US2] Test de redescarga idéntica: no cambia el fichero ni genera avisos, en `tests/integration/test_discrepancies.py`
- [ ] T034 [P] [US2] Test de discrepancia: valores distintos para una fecha ya almacenada se detectan, **lo local no se toca**, y la versión nueva se guarda aparte (FR-011, FR-026), en `tests/integration/test_discrepancies.py`
- [ ] T035 [P] [US2] Test del contenido del aviso: identifica la fecha concreta y los dos valores en conflicto (FR-027, SC-011), en `tests/unit/test_merge.py`
- [ ] T036 [P] [US2] Test de aceptación explícita: adoptar la versión nueva requiere una acción del operador; nunca ocurre sola (FR-028), en `tests/unit/test_merge.py`
- [ ] T037 [P] [US2] Test de descarga interrumpida: no queda ningún fichero parcial utilizable, en `tests/unit/test_store_atomicity.py`

### Implementación para US2

- [ ] T038 [US2] Implementar la detección de discrepancias en el solape dentro de `merge` — comparación vela a vela con prioridad de lo almacenado, en `src/invest_ll/fetch/merge.py`
- [ ] T039 [US2] Implementar `save_discrepancies`: la versión en conflicto se guarda bajo `discrepancias/` sin tocar el histórico, en `src/invest_ll/fetch/store.py`
- [ ] T040 [US2] Implementar `verify_history`: reverificación completa **explícita**, que no ocurre durante una descarga normal (FR-029), en `src/invest_ll/fetch/service.py`

**Checkpoint**: los backtests de ayer siguen siendo reproducibles hoy.

---

## Phase 5: User Story 3 - Ampliar sin volver a pedirlo todo (Priority: P2)

**Goal**: pedir al proveedor solo las fechas ausentes y comportarse bien ante sus límites.

**Independent Test**: descargar un rango, ampliarlo, y comprobar que `requests_made` refleja solo lo
que faltaba.

### Tests para US3 (escribir primero, deben fallar)

- [ ] T041 [P] [US3] Test incremental: ampliar un rango pide solo las fechas ausentes; un rango ya cubierto pide **cero** (SC-005), en `tests/unit/test_incremental.py`
- [ ] T042 [P] [US3] Test de límite de tasa: se espera y se reintenta de forma escalonada, sin repetir de inmediato (FR-014), en `tests/unit/test_retry.py`
- [ ] T043 [P] [US3] Test de proveedor caído: agotados los reintentos se informa y **el histórico local queda intacto** (FR-015), en `tests/unit/test_retry.py`
- [ ] T044 [P] [US3] Property tests de la fusión: rangos contiguos, solapados, disjuntos, invertidos y vacíos. Invariantes — orden cronológico, sin duplicados, ninguna vela almacenada se pierde ni cambia de valor, en `tests/property/test_merge_invariants.py`

### Implementación para US3

- [ ] T045 [US3] Implementar el cálculo de rangos faltantes a partir de lo almacenado en `src/invest_ll/fetch/merge.py`
- [ ] T046 [US3] Conectar el cálculo de rangos faltantes a `fetch_history` y contabilizar `requests_made` (FR-013) en `src/invest_ll/fetch/service.py`
- [ ] T047 [US3] Aplicar la espera escalonada a las llamadas de ambos proveedores en `src/invest_ll/fetch/providers/`

**Checkpoint**: ampliar un histórico grande deja de ser caro y de castigar al proveedor.

---

## Phase 6: User Story 4 - Saber de dónde salen los números (Priority: P3)

**Goal**: que todo histórico responda quién, cuándo y qué cubre, y que advierta de lo que puede
falsear un backtest.

**Independent Test**: descargar un histórico y consultar su procedencia y sus avisos.

### Tests para US4 (escribir primero, deben fallar)

- [ ] T048 [P] [US4] Test de procedencia: proveedor, momento, activo, rango, granularidad y si los precios están ajustados (FR-016, SC-007), en `tests/unit/test_provenance.py`
- [ ] T049 [P] [US4] Test de avisos derivados de las capacidades: `adjusts_prices=False` genera `UNADJUSTED_PRICES`; `includes_delisted=False` genera `SURVIVORSHIP_BIAS` (FR-018, FR-030, SC-009), en `tests/unit/test_provenance.py`
- [ ] T050 [P] [US4] Test de credenciales: ninguna aparece en procedencia ni en mensajes de error (FR-023, SC-008), en `tests/unit/test_provenance.py`

### Implementación para US4

- [ ] T051 [US4] Implementar la generación de avisos de calidad **derivada de las capacidades declaradas** por el proveedor, no de recordar ponerlos, en `src/invest_ll/fetch/provenance.py`
- [ ] T052 [US4] Propagar los avisos hasta el informe del backtest, aprovechando `data_warnings` que la 001 ya acepta, en `src/invest_ll/fetch/service.py`

**Checkpoint**: las cuatro historias funcionan de forma independiente.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T053 [P] Documentar en `README.md` el uso de la descarga y las advertencias del dominio: splits, dividendos y sesgo de supervivencia
- [ ] T054 [P] Añadir un aviso destacado en la salida de la CLI cuando el histórico traiga `SURVIVORSHIP_BIAS` o `UNADJUSTED_PRICES`, en `src/invest_ll/cli_fetch.py`
- [ ] T055 Ejecutar las 8 validaciones de [quickstart.md](./quickstart.md) y dejar constancia
- [ ] T056 Ejecutar la cadena completa de gates (`ruff` → `pyright` → `pytest`) sin regresión
- [ ] T057 Actualizar `.github/workflows/ci.yml` si hiciera falta para las dependencias nuevas
- [ ] T058 **Comprobación manual contra los proveedores reales** — fuera de la suite, porque toca la red. Descargar un activo de cripto y uno de bolsa y verificar que el formato recibido hoy es el esperado. **La ejecuta Marcos**: los proveedores grabados prueban la lógica, solo el real prueba el formato

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias
- **Foundational (Phase 2)**: depende de Setup. **BLOQUEA todas las historias**
- **US1 (Phase 3)**: depende de Foundational. Es el MVP
- **US2 (Phase 4)**: depende de US1 (necesita que exista una descarga que repetir)
- **US3 (Phase 5)**: depende de US1. Independiente de US2
- **US4 (Phase 6)**: depende de US1. Independiente de US2 y US3
- **Polish (Phase 7)**: depende de las historias que se entreguen

### Dentro de cada historia

Tests primero y **deben fallar** antes de implementar. Protocolo → almacenamiento → fusión →
orquestación → CLI.

### Parallel Opportunities

- Foundational: los seis tests T007–T012 en paralelo; luego T013–T016, T018–T020 en paralelo
- US1: los cinco tests T021–T025 en paralelo; T028 y T029 (los dos proveedores) en paralelo
- Terminado US1, las fases US2, US3 y US4 pueden avanzar en paralelo

---

## Implementation Strategy

### MVP (solo US1)

1. Setup → 2. Foundational (**incluye el guardián del aislamiento**) → 3. US1
4. **PARAR Y VALIDAR**: descargar con el proveedor grabado y backtestear el resultado
5. Aquí el motor ya mide mercado real en vez de series inventadas

### Entrega incremental

1. Setup + Foundational → el motor sigue sin red, garantizado
2. + US1 → **MVP**: histórico real backtesteable
3. + US2 → los backtests de ayer siguen siendo reproducibles hoy
4. + US3 → ampliar históricos deja de ser caro
5. + US4 → sabes de dónde salen los números y qué los puede estar falseando

**Recomendación**: no dejar US2 para más adelante. Sin ella, un histórico puede cambiar bajo los
pies entre dos backtests y no habrá forma de saber por qué los resultados dejaron de cuadrar.

---

## Notes

- 58 tareas: 6 setup · 14 foundational · 12 US1 · 8 US2 · 7 US3 · 5 US4 · 6 polish
- **T007 es la tarea más importante de la feature.** Es lo único que impedirá que la red se cuele en
  el motor, hoy o dentro de seis meses
- **T026 y T038 (`merge.py`) son las de más riesgo.** Un error de solape no rompe nada: deja un
  histórico ligeramente mal que produce un backtest ligeramente falso. Por eso es función pura y por
  eso tiene property tests (T044)
- Prohibido actualizar baselines para hacer pasar un test (constitución)
- T058 no la ejecuta el agente: toca la red y la hace Marcos
