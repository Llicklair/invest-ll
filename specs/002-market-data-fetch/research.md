# Phase 0 — Research: Descarga de Histórico Real

**Feature**: 002-market-data-fetch | **Fecha**: 2026-07-25

Decisiones técnicas de la feature. Las de proveedor ya vienen cerradas de `/speckit-clarify`; aquí
se resuelve cómo se implementan sin romper lo que la 001 dejó garantizado.

---

## R1. Cómo hacer *verificable* que el motor no toca la red (FR-001..FR-003) ★

**Decisión**: dos comprobaciones complementarias, ambas en la suite:

1. **Estática**: recorrer el AST de todos los módulos bajo `engine/`, `report/` y `strategy/` y
   fallar si aparece un import de red (`socket`, `http`, `urllib`, `requests`, `httpx`, `ccxt`,
   `yfinance`) o de la propia capa de descarga.
2. **Dinámica**: ejecutar un backtest completo con `socket.socket` parcheado para que lance
   excepción. Si el backtest termina, no hubo red.

**Rationale**: la estática detecta la dependencia el día que alguien la añade, aunque no llegue a
usarse; la dinámica demuestra que en tiempo de ejecución tampoco se abre una conexión por una vía
indirecta. Ninguna de las dos sola es suficiente: un import puede colarse detrás de una función y
una llamada puede ocurrir sin import visible.

**Alternativas consideradas**:
- *Solo revisión humana*: es exactamente lo que la constitución llama convención en vez de
  garantía. Se erosiona en la primera prisa.
- *Solo el test dinámico*: no detecta una dependencia importada pero aún no ejercitada, que es
  cómo empiezan estas cosas.
- *Separar en dos paquetes instalables distintos*: la garantía más fuerte, pero introduce la
  complejidad de un monorepo con dos paquetes para un proyecto de una sola persona. Si algún día
  la separación se rompe con frecuencia, esta es la escalada natural.

---

## R2. Proveedor de cripto: `ccxt`

**Decisión**: `ccxt` en modo síncrono, con `enableRateLimit=True`, usando solo endpoints públicos
(`fetch_ohlcv`). Sin credenciales.

**Rationale**: unifica decenas de exchanges tras la misma llamada y ya trae control de tasa
incorporado, lo que resuelve buena parte de FR-014 sin código propio. Los endpoints públicos de
OHLCV no requieren clave, así que el Principio I se cumple por construcción: no hay secreto que
proteger.

**Puntos a tener en cuenta en implementación**:
- `fetch_ohlcv` **pagina**: devuelve un máximo de velas por llamada (típicamente 500–1000 según
  exchange). Descargar un año de velas horarias exige varias peticiones encadenadas por marca
  temporal.
- Devuelve marcas en **milisegundos UTC**, que hay que convertir a `datetime` con zona.
- La **última vela puede estar sin cerrar**. Se descarta siempre (FR-007).

**Alternativas consideradas**: API de Binance directa (menos dependencia, pero ata a un exchange y
a sus restricciones geográficas) y CoinGecko (granularidad limitada en el plan gratuito).

---

## R3. Proveedor de bolsa: `yfinance`

**Decisión**: `yfinance` con `auto_adjust=True`, de forma que los precios lleguen ya ajustados por
splits y dividendos (FR-017).

**Rationale**: es la única fuente gratuita y sin clave que ofrece precios ajustados con histórico
largo. El ajuste importa más que la estabilidad: una serie sin ajustar convierte cada split en un
desplome falso, y eso no se arregla con un proveedor más fiable.

**Riesgo asumido y declarado**: `yfinance` **no es una API oficial**. Obtiene los datos raspando
Yahoo Finance y se rompe cuando Yahoo cambia el formato. No es una posibilidad remota: ocurre cada
cierto tiempo. La mitigación es arquitectónica (R4) y no elimina el riesgo, solo abarata el
recambio.

**Alternativas consideradas**: Stooq (más estable por ser un CSV plano, pero peor cobertura y
ajuste por dividendos menos fiable) y Alpha Vantage (oficial, con clave, pero ~25 peticiones
diarias en el plan gratuito lo hace inservible para descargar varios activos).

---

## R4. Aislamiento de proveedores tras un protocolo propio (FR-025, SC-012)

**Decisión**: un `MarketDataProvider` (`Protocol`) con una única operación —dame las velas de este
activo, en este intervalo, entre estas dos fechas— y tres implementaciones: la de cripto, la de
bolsa y una de test con respuestas grabadas.

**Rationale**: es la misma solución que el `MarketCalendar` de la 001, y por el mismo motivo: el
resto del sistema depende de una abstracción nuestra, no de una librería de terceros. Cuando
`yfinance` se rompa —cuando, no si— el recambio afecta a un fichero.

Además hace posible FR-024: los tests usan el proveedor grabado y **nunca tocan la red**.

**Alternativas consideradas**: llamar a `ccxt` y `yfinance` directamente desde la lógica de
descarga (menos código hoy, refactor obligado el día del cambio) o una librería de grabación de
tráfico HTTP tipo VCR (potente, pero añade dependencia y acopla los tests al formato de la
respuesta del proveedor, que es justo lo que queremos poder cambiar).

---

## R5. Formato y disposición en disco

**Decisión**: un CSV por (proveedor, activo, intervalo), acompañado de un fichero de metadatos
JSON hermano.

```
data/market/<proveedor>/<activo>/<intervalo>.csv        # la serie
data/market/<proveedor>/<activo>/<intervalo>.meta.json  # procedencia y avisos
data/market/<proveedor>/<activo>/discrepancias/         # versiones en conflicto
```

**Rationale**: el CSV se mantiene **exactamente** con las columnas que el loader de la 001 ya
espera, así que FR-005 se cumple sin escribir ni una conversión. Meter la procedencia dentro del
propio CSV obligaría a cabeceras o columnas extra y rompería esa compatibilidad; un fichero hermano
la deja al lado sin tocar el dato.

`data/` ya está en `.gitignore` desde el primer commit: los históricos no se versionan.

**Alternativas consideradas**: Parquet (más compacto y rápido, pero ilegible sin herramientas —
mala elección cuando la tarea habitual es mirar por qué un backtest da algo raro) y una base de
datos embebida (infraestructura desproporcionada para ficheros inmutables).

---

## R6. Escritura atómica (FR-012)

**Decisión**: escribir a un fichero temporal en el **mismo directorio** y renombrarlo con
`os.replace()` al terminar.

**Rationale**: `os.replace()` es atómico dentro del mismo sistema de ficheros, y en Windows además
sobrescribe sin error, a diferencia de `os.rename()`. Una descarga interrumpida deja como mucho un
temporal huérfano, nunca un CSV a medias que el motor aceptaría como histórico completo.

El temporal debe ir en el mismo directorio y no en el temporal del sistema: cruzar sistemas de
ficheros convierte el renombrado en copia, y la copia no es atómica.

---

## R7. Detección de discrepancias (FR-011, FR-026..FR-029)

**Decisión**: al fusionar lo descargado con lo almacenado, comparar vela a vela las marcas
temporales presentes en ambos. Cualquier diferencia en un precio o en el volumen produce una
`Discrepancy` con fecha, valor almacenado y valor nuevo. Lo local no se toca; la versión nueva se
guarda bajo `discrepancias/`.

**Rationale**: comparar solo lo que ya venía en la respuesta no cuesta ninguna petición adicional,
lo que respeta FR-013. La reverificación completa existe como operación aparte y explícita
(FR-029).

**Importante**: en bolsa las discrepancias serán **frecuentes y legítimas**. Cada nuevo split o
dividendo recalcula toda la serie ajustada hacia atrás. El sistema no puede tratarlas como
corrupción ni como error: las reporta y deja decidir. Por eso el aviso incluye los dos valores —
una diferencia proporcional y uniforme en toda la serie tiene la firma inconfundible de un ajuste.

---

## R8. Control de tasa y reintentos (FR-014, FR-015)

**Decisión**: espera exponencial con tres intentos (1s, 2s, 4s) ante fallo de red o límite de tasa.
Para cripto se apoya además en el control de tasa propio de `ccxt`.

**Rationale**: tres intentos cubren la caída pasajera sin castigar al proveedor. La espera creciente
es lo que distingue reintentar de martillear.

**Sobre el determinismo**: la espera introduce dependencia del reloj, y la constitución exige
reproducibilidad. Se resuelve inyectando la función de espera, de forma que los tests la sustituyan
por una que no espera. La suite completa sigue corriendo en segundos.

---

## R9. La vela en curso (FR-007)

**Decisión**: descartar el último periodo si su marca más la duración del intervalo aún no ha
pasado. El instante actual se **inyecta**, no se lee del reloj dentro de la lógica.

**Rationale**: guardar la vela en curso como definitiva es meter en el histórico un dato que todavía
va a cambiar — un backtest de hoy y otro de mañana sobre "el mismo" fichero darían resultados
distintos. Inyectar el instante actual mantiene la lógica comprobable sin depender de cuándo se
ejecuta el test.

---

## R10. Estrategia de pruebas sin red (FR-024, SC-002)

**Decisión**: `pytest` con un proveedor grabado que devuelve respuestas fijas, más un test global
que bloquea `socket` durante toda la suite salvo donde se permita explícitamente.

**Rationale**: un test que depende de la red no es un test, es una consulta al estado del mundo:
falla cuando no hay conexión, cuando el proveedor cambia y cuando el activo deja de existir. Además,
el bloqueo global convierte FR-024 en algo mecánico en vez de en una intención.

Property tests con `hypothesis` para la fusión de rangos, que es donde se esconden los errores de
solapes: rangos contiguos, solapados, disjuntos, invertidos o vacíos.

---

## Resumen de dependencias nuevas

| Dependencia | Uso | Justificación |
|---|---|---|
| `ccxt` | Histórico de cripto | Interfaz unificada, control de tasa incluido, sin credenciales |
| `yfinance` | Histórico de bolsa | Única fuente gratuita con precios ajustados |

Ambas quedan confinadas al paquete de descarga. El motor de backtesting no las conoce, y hay dos
tests que fallan si eso deja de ser cierto.

**A verificar con ejecución real en implementación**: que ambas instalan y funcionan en Python 3.14.
`yfinance` en particular arrastra dependencias propias. Instalado no significa funcional.
