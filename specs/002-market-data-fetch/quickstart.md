# Quickstart — validar la descarga de histórico

**Feature**: 002-market-data-fetch | **Fecha**: 2026-07-25

Comprobaciones que deben pasar para dar la feature por terminada. Ninguna de ellas necesita
conexión: la suite entera corre con la red bloqueada.

---

## Prerrequisitos

```bash
uv sync
uv run python -c "import ccxt, yfinance; print('deps OK')"
```

La segunda línea es obligatoria, no cortesía: `yfinance` arrastra dependencias propias y la
constitución exige verificar con una ejecución real. Instalado no significa funcional.

---

## Gates del proyecto

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Las mismas cuatro de siempre, y siguen sin admitir regresión.

---

## Validación 1 — el motor sigue sin tocar la red (FR-001..FR-003, SC-003) ★

La comprobación más importante de esta feature. Si falla, la 002 ha roto la 001.

```bash
uv run pytest tests/unit/test_engine_isolation.py -v
```

**Qué prueba**:
- Análisis estático: ningún módulo de `engine/`, `report/` o `strategy/` importa red ni la capa de
  descarga.
- Prueba dinámica: un backtest completo con `socket` bloqueado **termina correctamente**.

**Esperado**: ambas pasan. Si el test dinámico falla, hay una conexión abriéndose por una vía que
el análisis estático no vio.

---

## Validación 2 — la suite no toca la red (FR-024, SC-002)

```bash
uv run pytest -v
```

**Esperado**: la suite completa pasa con `socket` bloqueado globalmente. Un test que dependa de la
red fallará aquí, que es lo que se quiere: no es un test, es una consulta al estado del mundo.

---

## Validación 3 — descarga y backtest de extremo a extremo (US1)

```bash
uv run pytest tests/integration/test_fetch_to_backtest.py -v
```

**Qué prueba**: con un proveedor de respuestas grabadas, se descarga un histórico y se ejecuta un
backtest sobre el fichero resultante **sin ninguna conversión manual**.

**Esperado**: el informe se genera y el activo y el periodo son los descargados.

---

## Validación 4 — no se corrompe lo ya guardado (US2, SC-010, SC-011)

```bash
uv run pytest tests/unit/test_merge.py tests/integration/test_discrepancies.py -v
```

**Esperado**:
- Redescargar datos idénticos no cambia el fichero ni genera avisos.
- Si el proveedor devuelve valores distintos, se detecta, **lo local no se toca**, la versión nueva
  se guarda aparte y el aviso identifica fecha y ambos valores.
- Una escritura interrumpida no deja ningún fichero que el motor acepte como completo.

---

## Validación 5 — solo se pide lo que falta (US3, SC-005)

```bash
uv run pytest tests/unit/test_incremental.py -v
```

**Esperado**: al ampliar un rango ya descargado, `requests_made` refleja únicamente las fechas
ausentes. Si el rango ya está cubierto por completo, **cero peticiones**.

---

## Validación 6 — límites y fallos del proveedor

```bash
uv run pytest tests/unit/test_retry.py -v
```

**Esperado**: ante límite de tasa, espera creciente y tres intentos. Agotados, se comunica el fallo y
**el histórico local queda intacto**. La espera está inyectada: la suite no se detiene de verdad.

---

## Validación 7 — honestidad sobre la calidad del dato (US4, SC-009)

```bash
uv run pytest tests/unit/test_provenance.py -v
```

**Esperado**:
- Todo histórico permite responder quién, cuándo y qué cubre.
- Un proveedor que no ajusta precios genera `UNADJUSTED_PRICES`.
- Un proveedor sin activos retirados genera `SURVIVORSHIP_BIAS`.
- Ninguna credencial aparece en la procedencia ni en los mensajes de error.

---

## Validación 8 — invariantes de la fusión

```bash
uv run pytest tests/property/test_merge_invariants.py -v
```

**Qué prueba**: rangos contiguos, solapados, disjuntos, invertidos y vacíos, generados con
`hypothesis`. Invariantes: el resultado siempre queda en orden cronológico y sin duplicados; ninguna
vela almacenada se pierde; ninguna vela almacenada cambia de valor.

---

## Comprobación manual contra el proveedor real

**No forma parte de la suite**: toca la red y por eso queda fuera.

```bash
uv run invest-ll-fetch BTC/USDT --market crypto --interval DAY_1 \
    --start 2025-01-01 --end 2025-02-01

uv run invest-ll-backtest data/market/*/BTC-USDT/DAY_1.csv \
    --commission 0.001 --slippage 0.0005
```

Hazla al menos una vez antes de dar la feature por buena. Los proveedores grabados prueban la
lógica; solo el proveedor real prueba que el formato que devuelve hoy es el que esperábamos.

---

## Criterio de terminación

Las 8 validaciones en verde, las 4 gates en verde, la comprobación manual hecha una vez, y el
Constitution Check del plan en PASS tras el diseño final.
