# Phase 1 — Data Model: Descarga de Histórico Real

**Feature**: 002-market-data-fetch | **Fecha**: 2026-07-25

Entidades nuevas de esta feature. Reutiliza `Bar`, `Interval` y `PriceSeries` de la 001 sin
modificarlas: el objetivo es alimentar el motor existente, no cambiarlo.

---

## FetchRequest — lo que pide el operador

| Campo | Tipo | Reglas |
|---|---|---|
| `symbol` | `str` | Identificador del activo tal como lo entiende el proveedor |
| `interval` | `Interval` | Reutilizado de la 001 |
| `start` / `end` | `datetime` (UTC) | `start < end`; ambos con zona obligatoria |
| `market` | `CRYPTO` \| `EQUITY` | Determina el proveedor y el calendario |

**Validación**: rango no vacío ni invertido, marcas con zona, intervalo soportado por el proveedor.

---

## MarketDataProvider — protocolo ★

La abstracción que aísla las librerías de terceros (FR-025).

Una sola operación: dado un activo, un intervalo y un rango, devolver las velas disponibles. El
protocolo **no** conoce caché, ni ficheros, ni discrepancias — solo trae datos.

| Implementación | Mercado | Notas |
|---|---|---|
| `CcxtProvider` | Cripto | Pagina internamente; control de tasa propio de la librería |
| `YFinanceProvider` | Bolsa | `auto_adjust=True`: precios ya ajustados |
| `RecordedProvider` | Tests | Respuestas fijas. Nunca toca la red |

**Invariantes que todo proveedor debe cumplir**:
- Devuelve velas en orden cronológico estricto, sin duplicados.
- Todas las marcas en UTC y con zona.
- **Nunca** devuelve la vela en curso (la descarta quien corresponda antes de guardar).
- Ante activo desconocido lanza error; no devuelve una lista vacía que parezca "sin datos".

---

## ProviderCapabilities — qué sabe hacer cada proveedor

| Campo | Tipo | Notas |
|---|---|---|
| `name` | `str` | Aparece en la procedencia |
| `supported_intervals` | conjunto de `Interval` | Para rechazar antes de pedir |
| `adjusts_prices` | `bool` | `False` obliga a la advertencia de FR-030 |
| `includes_delisted` | `bool` | `False` obliga a la advertencia de sesgo (FR-018) |
| `max_bars_per_request` | `int` | Gobierna la paginación |

Declarar las capacidades permite fallar pronto y con un mensaje útil, en vez de descubrir a mitad
de la descarga que el intervalo pedido no existe.

---

## Provenance — de dónde salen los datos (FR-016)

| Campo | Tipo | Notas |
|---|---|---|
| `provider` | `str` | |
| `symbol` / `interval` / `market` | | |
| `downloaded_at` | `datetime` (UTC) | Instante inyectado, no leído del reloj interno |
| `range_start` / `range_end` | `datetime` | Cobertura real, no la solicitada |
| `bar_count` | `int` | |
| `prices_adjusted` | `bool` | Si están corregidos por splits y dividendos |
| `quality_warnings` | lista de `QualityWarning` | Acompaña siempre al histórico |

Se guarda como fichero hermano en JSON para no alterar el CSV que el motor consume (ver R5).

---

## QualityWarning — lo que el operador debe saber

| Tipo | Cuándo | Por qué importa |
|---|---|---|
| `GAP` | Falta una vela con el mercado abierto | Puede alterar indicadores sin avisar |
| `UNADJUSTED_PRICES` | El proveedor no ajusta splits/dividendos | Cada split parece un desplome |
| `SURVIVORSHIP_BIAS` | El proveedor solo lista activos vivos | El backtest sale mejor que la realidad |
| `PARTIAL_RANGE` | El proveedor cubre menos de lo pedido | El periodo evaluado no es el que se creía |

Viajan **con** el histórico hasta el informe del backtest, igual que los `DataWarning` de la 001.
Un aviso que se queda en un log no lo lee nadie.

---

## StoredHistory — el histórico en disco

| Componente | Fichero | Contenido |
|---|---|---|
| Serie | `<intervalo>.csv` | Exactamente las columnas que espera el loader de la 001 |
| Procedencia | `<intervalo>.meta.json` | `Provenance` completo |
| Conflictos | `discrepancias/<fecha>.json` | Versiones en conflicto sin aplicar |

**Invariantes**:
- El CSV **nunca** se modifica en el sitio: se escribe un temporal y se renombra (FR-012).
- Una serie almacenada siempre pasa la validación del motor: si no la pasa, no se guarda (FR-019).
- Los huecos no se rellenan jamás; se reportan (FR-020).

---

## Discrepancy — un dato que cambió

| Campo | Tipo |
|---|---|
| `timestamp` | `datetime` — la vela afectada |
| `field` | qué cambió (`open`, `high`, `low`, `close`, `volume`) |
| `stored_value` / `provider_value` | `float` |

**Regla**: detectarla **nunca** modifica el histórico local (FR-026). Aplicar la versión nueva es
una acción explícita del operador (FR-028).

**Nota de dominio**: en bolsa las discrepancias son frecuentes y **legítimas** — cada nuevo split o
dividendo recalcula la serie ajustada hacia atrás. Una diferencia proporcional y uniforme en toda la
serie es la firma de un ajuste, no de una corrupción. El sistema informa; interpretar es del
operador.

---

## MergeResult — resultado de fusionar lo nuevo con lo guardado

| Campo | Notas |
|---|---|
| `series` | La serie resultante (solo con las velas nuevas incorporadas) |
| `added_count` | Cuántas velas se añadieron |
| `discrepancies` | Las detectadas en el solape |
| `warnings` | Avisos de calidad generados |

La fusión es **pura**: no escribe en disco ni llama a nadie. Recibe lo almacenado y lo descargado y
devuelve el resultado. Es la parte con más casos límite (rangos contiguos, solapados, disjuntos,
invertidos) y aislarla así es lo que la hace comprobable con property tests.

---

## Errores del dominio

| Error | Cuándo | Recuperable |
|---|---|---|
| `UnknownSymbolError` | El proveedor no reconoce el activo | No |
| `UnsupportedIntervalError` | Granularidad no disponible | No |
| `NoDataError` | El rango no tiene datos | No |
| `ProviderUnavailableError` | Fallo de red tras agotar reintentos | Sí — se conserva lo local |
| `RateLimitError` | Límite alcanzado | Sí — espera y reintenta |

`ProviderUnavailableError` **nunca** deja el histórico local en peor estado que antes (FR-015).

---

## Flujo de una descarga

```
FetchRequest
  → ¿el proveedor soporta el intervalo?      no → UnsupportedIntervalError
  → cargar lo ya almacenado (si existe)
  → calcular qué falta                        nada → devolver lo local sin pedir nada
  → pedir al proveedor (paginando, con reintentos y control de tasa)
  → descartar la vela en curso
  → validar con las reglas del motor          falla → no se guarda
  → fusionar: detectar discrepancias en el solape
      hay discrepancias → conservar lo local + guardar la version nueva aparte + avisar
  → escribir CSV temporal y renombrar (atómico)
  → escribir procedencia y avisos
```

El motor de backtesting no aparece en este flujo, y ese es exactamente el punto: cuando termina,
solo hay ficheros en disco.
