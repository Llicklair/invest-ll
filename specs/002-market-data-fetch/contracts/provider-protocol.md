# Contrato: capa de datos de mercado

**Feature**: 002-market-data-fetch | **Fecha**: 2026-07-25

Superficie estable de la feature. Lo que hay detrás puede cambiar —y con `yfinance` cambiará— sin
que esto se mueva.

---

## 1. `MarketDataProvider` — el protocolo que aísla a los terceros

```python
class MarketDataProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def fetch(
        self,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]: ...
```

**Obligaciones de toda implementación**:

| Debe | No debe |
|---|---|
| Devolver velas en orden cronológico estricto | Devolver duplicados |
| Marcas en UTC y con zona | Devolver marcas ingenuas o en horario local |
| Lanzar `UnknownSymbolError` ante activo desconocido | Devolver lista vacía cuando el activo no existe |
| Declarar sus capacidades con honestidad | Afirmar que ajusta precios si no lo hace |
| Paginar internamente si el rango excede su límite | Truncar en silencio |

**Lo que el protocolo NO hace**: no sabe de caché, ni de ficheros, ni de discrepancias. Solo trae
datos. Todo lo demás vive por encima y es común a todos los proveedores.

---

## 2. `ProviderCapabilities`

```python
@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    supported_intervals: frozenset[Interval]
    adjusts_prices: bool
    includes_delisted: bool
    max_bars_per_request: int
```

`adjusts_prices=False` obliga a emitir `UNADJUSTED_PRICES`; `includes_delisted=False` obliga a
`SURVIVORSHIP_BIAS`. Las advertencias no dependen de que alguien se acuerde: se derivan de lo que el
proveedor declara.

---

## 3. Punto de entrada

```python
def fetch_history(
    request: FetchRequest,
    provider: MarketDataProvider,
    store: HistoryStore,
    *,
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult: ...
```

`now` se **inyecta**: es lo que permite descartar la vela en curso de forma comprobable sin que el
resultado dependa de cuándo se ejecute el test. `sleep` se inyecta por la misma razón — los tests lo
sustituyen y la suite no espera de verdad.

**Garantías**:
- Nunca deja el histórico local peor que antes: si algo falla, lo que había sigue estando.
- Nunca modifica velas ya almacenadas (FR-010, FR-026).
- Solicita al proveedor únicamente las fechas ausentes (FR-013).
- Nunca guarda datos que no pasen la validación del motor (FR-019).

---

## 4. `FetchResult`

```python
@dataclass(frozen=True)
class FetchResult:
    path: Path                                  # el CSV listo para el motor
    provenance: Provenance
    added_count: int
    discrepancies: tuple[Discrepancy, ...]
    warnings: tuple[QualityWarning, ...]
    requests_made: int                          # cuántas peticiones costó
```

`requests_made` no es telemetría decorativa: es lo que hace verificable SC-005 —que ampliar un rango
ya descargado no vuelva a pedir lo que ya se tenía.

---

## 5. `HistoryStore` — persistencia

```python
class HistoryStore(Protocol):
    def load(self, request: FetchRequest) -> tuple[PriceSeries, Provenance] | None: ...
    def save(self, series: PriceSeries, provenance: Provenance) -> Path: ...
    def save_discrepancies(
        self, request: FetchRequest, bars: Sequence[Bar], at: datetime
    ) -> Path: ...
```

`save` es **atómico**: escribe un temporal en el mismo directorio y lo renombra. Una interrupción no
puede dejar un CSV a medias que el motor tomaría por completo.

`load` devuelve `None` cuando no hay nada guardado — no lanza. Que no exista todavía es el caso
normal la primera vez, no un error.

---

## 6. Verificación de integridad (FR-029)

```python
def verify_history(
    request: FetchRequest,
    provider: MarketDataProvider,
    store: HistoryStore,
) -> tuple[Discrepancy, ...]: ...
```

Reexamina un histórico completo contra el proveedor. Es una operación **explícita y aparte**: no
ocurre durante una descarga normal, porque redescargar todo en cada uso agotaría los límites del
proveedor (FR-013).

No modifica nada. Solo informa.

---

## 7. Fusión (función pura)

```python
def merge(
    stored: PriceSeries | None,
    fetched: Sequence[Bar],
    *,
    interval: Interval,
) -> MergeResult: ...
```

Sin E/S, sin red, sin reloj. Recibe lo que hay y lo que llegó, devuelve el resultado. Es donde se
esconden los errores de solape, así que se aísla para poder atacarla con property tests: rangos
contiguos, solapados, disjuntos, invertidos y vacíos.

**Regla**: ante conflicto, **gana lo almacenado**. La versión del proveedor se reporta como
discrepancia y se guarda aparte, nunca se aplica sola.

---

## 8. Interfaz de línea de comandos

```bash
invest-ll-fetch BTC/USDT --market crypto --interval HOUR_1 --start 2025-01-01 --end 2026-01-01
invest-ll-fetch AAPL --market equity --interval DAY_1 --start 2020-01-01 --end 2026-01-01
invest-ll-fetch AAPL --market equity --interval DAY_1 --verify
```

Códigos de salida: `0` correcto · `1` error de configuración o de datos · `2` activo o rango sin
datos · `3` **descarga correcta pero con discrepancias detectadas** — encadenable en un script sin
tragarse un cambio silencioso.

---

## 9. Estabilidad

Rompe contrato: cambiar la firma de `fetch`, quitar campos de `FetchResult` o `Provenance`, cambiar
el layout en disco, o que `merge` deje de dar prioridad a lo almacenado.

Compatible: nuevos proveedores, nuevos tipos de `QualityWarning`, campos opcionales nuevos en la
procedencia.
