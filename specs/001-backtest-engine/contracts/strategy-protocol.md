# Contrato: interfaz pública del motor de backtesting

**Feature**: 001-backtest-engine | **Fecha**: 2026-07-25

Este es el contrato que consume el operador y que cualquier estrategia debe cumplir. Es la
superficie estable: lo que hay detrás puede cambiar, esto no sin romper compatibilidad.

---

## 1. Protocolo `Strategy`

Lo único que el motor exige de una estrategia. Cualquier objeto con este método sirve — reglas
fijas, envoltorio de un modelo de IA, o un stub de test. No hay que heredar de nada (FR-017).

```python
class Strategy(Protocol):
    def decide(self, view: MarketView) -> Signal | None: ...
```

**Contrato de `decide`**:

| Garantía del motor | Obligación de la estrategia |
|---|---|
| `view` solo expone periodos cerrados hasta el actual | No intentar acceder a periodos futuros |
| `view` es inmutable | No mutar lo recibido |
| Se llama una vez por periodo, en orden cronológico | Ser determinista: misma vista → misma señal |
| No se le pasa capital ni posición | No dimensionar la operación: eso es del motor (FR-027) |

**Prohibido en una estrategia**: E/S de red, aleatoriedad sin semilla fija, reloj del sistema,
estado global compartido. Todo ello rompe FR-005.

---

## 2. `MarketView` — la vista segura

```python
class MarketView(Protocol):
    @property
    def current_timestamp(self) -> datetime: ...
    @property
    def current_bar(self) -> Bar: ...
    def history(self, periods: int) -> Sequence[Bar]: ...
    def closes(self, periods: int) -> NDArray[np.float64]: ...
    def __len__(self) -> int: ...
```

**Garantías**:
- Todo lo devuelto tiene marca temporal ≤ `current_timestamp`.
- `history(n)` devuelve los `n` periodos más recientes ya cerrados; si hay menos de `n`
  disponibles, devuelve los que haya — **nunca rellena** con datos inventados.
- No existe forma pública de alcanzar un periodo futuro. Intentarlo lanza `LookAheadError`.

**Lo que este contrato NO garantiza**: hermeticidad frente a introspección deliberada del atributo
privado. Python no ofrece memoria privada real. La garantía es de interfaz, respaldada por el test
de la estrategia tramposa (SC-003).

---

## 3. `Signal`

```python
class SignalKind(Enum):
    ENTER_LONG = "enter_long"
    EXIT = "exit"


@dataclass(frozen=True)
class Signal:
    kind: SignalKind
    stop_loss: float | None = None
    take_profit: float | None = None
```

Sin cantidad ni precio: la estrategia expresa **intención**, el motor decide tamaño y precio.

---

## 4. Punto de entrada

```python
def run_backtest(
    series: PriceSeries,
    strategy: Strategy,
    *,
    initial_capital: Decimal,
    friction: FrictionConfig,
    risk: RiskConfig,
    min_trades: int = 30,
) -> BacktestReport: ...
```

`friction` y `risk` son **obligatorios y sin valor por defecto**. No se puede lanzar un backtest
sin declarar los costes: el Principio IV se hace cumplir por la firma, no por documentación.

**Garantías**:
- No realiza E/S de red ni toca ningún broker (FR-006). El motor no importa ningún cliente HTTP.
- Determinista: mismas entradas → informe idéntico (FR-005).
- El informe devuelto **siempre** trae las seis métricas (SC-002).

---

## 5. `BacktestReport`

```python
@dataclass(frozen=True)
class BacktestReport:
    net_result: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    trade_count: int
    total_costs: Decimal
    win_rate: float
    conclusive: bool
    inconclusive_reason: str | None
    trades: Sequence[Trade]
    friction: FrictionConfig
    risk: RiskConfig
    series_metadata: SeriesMetadata
    data_warnings: Sequence[DataWarning]
```

**Reglas de presentación** (FR-012):
- La representación textual **no** puede abrir con el win rate.
- Si `conclusive` es `False`, el motivo aparece antes que cualquier cifra: un resultado no
  concluyente no debe poder leerse como bueno de un vistazo.
- Las seis métricas son campos obligatorios del tipo: un informe incompleto no compila.

---

## 6. Contrato de carga de datos

```python
def load_series(
    path: Path,
    *,
    symbol: str,
    interval: Interval,
    calendar: MarketCalendar,
) -> tuple[PriceSeries, Sequence[DataWarning]]: ...
```

Formatos: CSV (obligatorio) y Parquet (opcional). Columnas requeridas: `timestamp`, `open`,
`high`, `low`, `close`, `volume`.

Devuelve los avisos **junto** a la serie en lugar de registrarlos en un log: obliga a quien llama
a recibirlos, y acaban en el informe (FR-016).

Lanza `InvalidSeriesError` ante orden temporal roto, precios no positivos, marcas desalineadas del
intervalo, o coherencia OHLC violada.

---

## 7. Errores

| Error | Causa | Recuperable |
|---|---|---|
| `LookAheadError` | La estrategia intentó leer el futuro | No — invalida el backtest entero |
| `InvalidSeriesError` | Datos que no pasan validación | No — se corrigen los datos |
| `InsufficientCapitalError` | Orden por encima de la caja | Sí — se registra como orden rechazada |

`LookAheadError` **nunca** se captura dentro del motor para continuar. Un backtest contaminado no
produce un resultado degradado: no produce resultado.

---

## 8. Estabilidad

Cambios que rompen contrato: quitar o renombrar campos de `BacktestReport`, cambiar la firma de
`decide`, o dar valor por defecto a `friction` / `risk`.

Cambios compatibles: añadir campos opcionales al informe, nuevos `SignalKind`, nuevas
implementaciones de `MarketCalendar`.
