# Implementation Plan: Descarga de Histórico Real de Mercado

**Branch**: `002-market-data-fetch` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-market-data-fetch/spec.md`

## Summary

Componente que descarga histórico real de cripto y bolsa, lo guarda en local y lo deja listo para
que el motor de la feature 001 lo consuma sin conversión. Hasta ahora el motor solo ha medido
series sintéticas escritas para los tests; esta feature le da mercado de verdad.

**Enfoque técnico**: un paquete `fetch/` separado, con las librerías de terceros confinadas tras un
protocolo `MarketDataProvider` propio. La descarga escribe ficheros; el motor lee ficheros; no se
hablan. Esa separación no queda como acuerdo: dos tests la vigilan — uno analiza los imports del
motor y otro ejecuta un backtest completo con `socket` bloqueado.

La lógica de fusión (qué falta, qué se solapa, qué cambió) se aísla como **función pura**, sin E/S
ni red ni reloj, porque es donde se concentran los casos límite y así se puede atacar con property
tests.

Decisiones y alternativas descartadas: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.14, suelo `>=3.13` (heredado de la 001)

**Primary Dependencies**: `ccxt` (histórico de cripto, control de tasa incluido, sin credenciales),
`yfinance` (histórico de bolsa con precios ajustados). Ambas **confinadas** al paquete `fetch/`

**Storage**: ficheros locales bajo `data/market/` — CSV con las columnas que ya espera el loader de
la 001, más un fichero hermano JSON con la procedencia. `data/` está en `.gitignore` desde el primer
commit

**Testing**: `pytest` + `hypothesis`. La suite corre con `socket` bloqueado globalmente; los
proveedores se sustituyen por uno de respuestas grabadas

**Target Platform**: Windows 10 (desarrollo), Linux (CI). Sin código específico de plataforma

**Project Type**: librería Python con dos ejecutables de línea de comandos

**Performance Goals**: sin objetivo de latencia — la descarga la marca el proveedor, no el código.
Sí un objetivo de **economía**: cero peticiones cuando el rango ya está cubierto (SC-005)

**Constraints**: el paquete del motor MUST NOT adquirir dependencias de red, verificado de forma
automática (FR-002). Reloj y espera **inyectados**, nunca leídos dentro de la lógica

**Scale/Scope**: un activo por solicitud, dos mercados, descarga bajo demanda. Sin tiempo real ni
actualización programada

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Derived from `.specify/memory/constitution.md` v1.0.0.

**Evaluación inicial (pre-Phase 0): ATENCIÓN** — es la primera feature que introduce red y
credenciales potenciales. Los Principios I y II exigen revisión explícita, no un PASS por defecto.

**Re-evaluación post-Phase 1 (diseño completo)**:

| # | Gate | Estado | Evidencia en el diseño |
|---|------|--------|------------------------|
| I | Seguridad del capital (NO NEGOCIABLE) | **PASS** | Ninguno de los dos proveedores requiere credenciales para histórico público: no hay secreto que filtrar (FR-022). Solo se leen datos — no existe endpoint de órdenes en el diseño. El motor sigue sin red, verificado por dos tests (FR-002). Si algún día entra un proveedor con clave, FR-021 y FR-023 ya la confinan al entorno y la excluyen de errores y procedencia |
| II | Sin look-ahead (NO NEGOCIABLE) | **PASS** | La vela en curso se descarta siempre (FR-007): guardarla metería en el histórico un dato que aún va a cambiar. Lo almacenado es inmutable (FR-010) y una discrepancia jamás se aplica sola (FR-026), así que un backtest de ayer sigue siendo reproducible hoy. El instante actual se **inyecta**, no se lee del reloj dentro de la lógica |
| III | Métricas honestas | **PASS** | Los avisos de calidad viajan **con** el histórico hasta el informe, no a un log. Se derivan de lo que el proveedor declara (`adjusts_prices`, `includes_delisted`), no de que alguien se acuerde de ponerlos. El sesgo de supervivencia se advierte y se declara **no corregido** |
| IV | Fricción realista | **N/A** | Esta feature no simula ejecución. La fricción sigue siendo competencia del motor, que no se modifica |
| V | Estrategias comparables | **PASS** | No toca estrategias. Refuerza la comparabilidad: dos estrategias podrán medirse sobre el mismo histórico real, identificado y auditable |
| — | Gates técnicas | **PASS** | `ruff` → `pyright` → `pytest`. La suite corre sin red (SC-002) |

**Sin violaciones. Complexity Tracking vacío.**

**Riesgo declarado, no violación**: el proveedor de bolsa es una librería **no oficial** que raspa un
portal financiero y se romperá cuando ese portal cambie. No es un fallo del diseño sino una
consecuencia aceptada de querer precios ajustados sin coste (decisión del operador, sesión
2026-07-25). La mitigación es arquitectónica —queda tras un protocolo, sustituible tocando un
fichero— y **no elimina el riesgo, solo abarata el recambio**. Se documenta aquí para que el día que
falle nadie lo viva como una sorpresa.

## Project Structure

### Documentation (this feature)

```text
specs/002-market-data-fetch/
├── plan.md              # Este fichero
├── spec.md              # 30 FR, 12 SC, 5 clarificaciones
├── research.md          # Phase 0 — 10 decisiones técnicas
├── data-model.md        # Phase 1 — entidades e invariantes
├── quickstart.md        # Phase 1 — 8 validaciones ejecutables
├── contracts/
│   └── provider-protocol.md
├── checklists/
│   └── requirements.md  # 16/16
└── tasks.md             # Phase 2 — lo genera /speckit-tasks
```

### Source Code (repository root)

```text
src/invest_ll/
├── data/                 # (001) sin cambios
├── engine/               # (001) sin cambios — y sin red, vigilado por test
├── report/               # (001) sin cambios
├── strategy/             # (001) sin cambios
├── fetch/                # NUEVO — todo lo que toca la red vive aquí
│   ├── protocol.py       # MarketDataProvider, ProviderCapabilities
│   ├── request.py        # FetchRequest, Market
│   ├── providers/
│   │   ├── crypto.py     # CcxtProvider
│   │   ├── equity.py     # YFinanceProvider
│   │   └── recorded.py   # RecordedProvider (tests, sin red)
│   ├── merge.py          # ★ función pura: fusión y discrepancias
│   ├── store.py          # HistoryStore, escritura atómica
│   ├── provenance.py     # Provenance, QualityWarning
│   ├── retry.py          # Espera escalonada, inyectable
│   ├── service.py        # fetch_history, verify_history
│   └── errors.py         # Errores de la capa de datos
├── errors.py             # (001) sin cambios
├── cli.py                # (001) backtest
└── cli_fetch.py          # NUEVO — descarga

tests/
├── unit/                 # engine_isolation ★, merge, incremental, retry, provenance, store
├── integration/          # fetch_to_backtest, discrepancies
├── property/             # merge_invariants
└── fixtures/recorded/    # respuestas grabadas de proveedor
```

**Structure Decision**: `fetch/` es un paquete hermano del motor, no un submódulo suyo. La
dependencia va en un solo sentido: `fetch` conoce `data` (necesita `Bar`, `Interval`, `PriceSeries`
para producir lo que el motor espera), y `engine` **no conoce `fetch`**.

`fetch/merge.py` es el fichero con más riesgo de la feature. No porque sea difícil, sino porque los
errores de solape son silenciosos: no rompen nada, solo dejan un histórico ligeramente mal que
produce un backtest ligeramente falso. Por eso es una función pura y por eso tiene property tests.

`tests/unit/test_engine_isolation.py` es el guardián de la separación. Si esta feature acaba
metiendo red en el motor, ese test es lo único que lo dirá.

## Complexity Tracking

> Sin violaciones de la constitución. Nada que justificar.
