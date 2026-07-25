# Modelo de datos — Feature 003

Entidades nuevas y sus reglas. Todas inmutables (`frozen=True`), como el resto del proyecto: una
decisión o una orden que se puede modificar después no sirve para auditar nada.

---

## Capa de decisión

### `AssetDecision`

Qué hacer con **un** activo en un instante.

| Campo | Tipo | Regla |
|---|---|---|
| `symbol` | `str` | No vacío. Debe existir en el universo. |
| `action` | `Action` | `HOLD` · `ENTER` · `EXIT` |
| `weight` | `Decimal` | Entre 0 y 1. `ENTER` exige > 0. **Se valida en código**, no en el esquema JSON (research D3). |
| `reasoning` | `str` | Obligatorio (FR-012). Vacío ⇒ decisión inválida. |

### `Decision`

La respuesta completa del LLM para un instante.

| Campo | Tipo | Regla |
|---|---|---|
| `timestamp` | `datetime` | Con zona horaria. El instante **simulado**, no el real. |
| `assets` | `tuple[AssetDecision, ...]` | Sin símbolos repetidos. La suma de pesos ≤ 1. |
| `summary` | `str` | Explicación global. |
| `model` | `str` | Qué modelo la produjo (FR-045). |

**Invariante**: la suma de pesos no puede exceder 1 — no hay apalancamiento en v1. Una respuesta
que lo incumpla es un fallo (FR-011), no algo que se recorte en silencio.

### `DecisionRequest`

Lo que determina una decisión. **Es la clave del caché** (FR-043).

| Campo | Tipo | Para qué |
|---|---|---|
| `timestamp` | `datetime` | Instante simulado |
| `symbols` | `tuple[str, ...]` | Ordenada, para que el hash sea estable |
| `market_context` | `str` | El texto derivado de `MarketView` |
| `instructions_version` | `str` | Cambiar las instrucciones invalida el caché |
| `model` | `str` | Cambiar de modelo invalida el caché |

`cache_key` es el hash de todo lo anterior. Nada más entra: si un campo no cambia la decisión, no
debe cambiar la clave.

### `CostEstimate`

Lo que costará un backtest, **antes** de lanzarlo (FR-041).

| Campo | Tipo |
|---|---|
| `decisions` | `int` |
| `cached` | `int` — las que ya están y no se pagan |
| `estimated_cost` | `Decimal` |

`needs_confirmation` es cierto cuando las decisiones nuevas superan el umbral configurado.

---

## Análisis de activos

### `AssetAnalysis`

Separa lo comprobable de lo interpretado (FR-049).

| Campo | Tipo | Naturaleza |
|---|---|---|
| `symbol` | `str` | — |
| `facts` | `tuple[Fact, ...]` | **Verificable.** Cada uno con fecha y fuente. |
| `narrative` | `str` | **Interpretación** del LLM. |
| `scenarios` | `tuple[str, ...]` | Escenarios, nunca predicciones (FR-018). |
| `retrieved_at` | `datetime` | Cuándo se obtuvieron los datos. |

### `Fact`

| Campo | Tipo | Regla |
|---|---|---|
| `label` | `str` | Qué es |
| `value` | `str` | El dato |
| `source` | `str` | De dónde sale (FR-017) |
| `as_of` | `date` | A qué fecha corresponde |

**Regla que cruza toda la entidad**: un `Fact` sin `source` o sin `as_of` no se construye. Si no se
puede decir de dónde viene un dato, no se presenta como dato.

---

## Estimado contra real

### `Forecast`

Lo que el sistema esperaba. **Inmutable una vez escrito** (FR-021).

| Campo | Tipo | Regla |
|---|---|---|
| `issued_at` | `datetime` | Cuándo se emitió |
| `horizon_days` | `int` | > 0 |
| `portfolio` | `tuple[Holding, ...]` | La cartera propuesta |
| `expected_value` | `Decimal` | Lo estimado |
| `basis` | `str` | En qué se basó |

Se guarda **añadiendo** al histórico, nunca sobrescribiendo. Un fichero de estimaciones que se
puede reescribir no es un registro, es una excusa.

### `Outcome`

Qué pasó de verdad.

| Campo | Tipo |
|---|---|
| `forecast_id` | `str` |
| `measured_at` | `datetime` |
| `actual_value` | `Decimal` |

`error` = `actual_value - expected_value`. Un histórico de errores permite ver si el sistema tiende
a pasarse o a quedarse corto (FR-024) — y **los fallos no se borran** (FR-023).

---

## Ejecución

### `OperatingMode`

**Tres tipos distintos, no un booleano.**

| Tipo | Qué hace | Credenciales |
|---|---|---|
| `Simulation` | Nada sale. Es el valor por defecto. | Ninguna |
| `Testnet` | Órdenes reales, dinero ficticio. | Las de pruebas |
| `Real` | Dinero de verdad. | Las reales, **distintas** |

Que sean tipos y no un flag significa que una función que acepta `Real` **no puede** recibir
`Simulation`, y el comprobador de tipos lo detecta antes de ejecutar nada. Un booleano sería una
comprobación en tiempo de ejecución que alguien puede olvidar poner.

`Simulation` es el valor por defecto **por construcción**: es lo que se obtiene sin configurar nada
(FR-025).

### `OrderRequest` → `OrderResult`

Lo que se pidió y lo que ocurrió. Van separados a propósito (FR-030).

**`OrderRequest`**: `symbol`, `side`, `quantity` (> 0), `requested_at`.

**`OrderResult`**: `request`, `status`, `filled_quantity`, `fill_price`, `executed_at`,
`broker_reference`.

`status` ∈ `FILLED` · `PARTIAL` · `REJECTED` · **`UNKNOWN`**.

`UNKNOWN` existe para un caso concreto: se envió la orden y se perdió la conexión. **No se asume
que se ejecutó ni que falló** (FR-035) — cualquiera de las dos suposiciones puede costar dinero.

`matches_request` es falso cuando lo ejecutado difiere de lo pedido, y eso se comunica siempre
(FR-031) en lugar de darse por bueno.

### `ExecutionLedger`

Histórico auditable, solo-añadir. Cada entrada: la orden, el modo en que se envió, y el momento.

**El modo se registra en cada entrada**, no una vez por sesión: así se puede demostrar después que
una orden concreta salió en pruebas y no con dinero real.

---

## Reglas transversales

1. **Todo inmutable.** Un registro que se puede editar no prueba nada.
2. **`Decimal` para dinero, `float` para indicadores.** Como en el motor.
3. **Fechas con zona horaria.** Siempre.
4. **Escritura atómica.** Fichero temporal y `os.replace` en el mismo directorio, como la 002.
5. **Ninguna entidad guarda credenciales.** Ni en memoria ni en disco (FR-034).
