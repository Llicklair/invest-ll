# Investigación técnica — Feature 003

**Fecha**: 2026-07-25 · Resuelve las incógnitas del contexto técnico antes de diseñar.

---

## D1. Modelo y coste

**Decisión**: `claude-opus-5` — $5 por millón de tokens de entrada, $25 de salida.

**Razón**: es el modelo actual por defecto de la API. La decisión de inversión es exactamente el
tipo de tarea donde la capacidad importa: hay que leer contexto de varios activos y razonar sobre
él. Bajar de modelo para ahorrar sería optimizar la parte equivocada — el coste real de esta
feature no son los tokens, es equivocarse.

**Alternativas descartadas**: `claude-sonnet-5` ($3/$15) para ahorrar; `claude-haiku-4-5` ($1/$5).
Ambos siguen disponibles si el coste aprieta, y la interfaz permite cambiarlos sin tocar el motor.

**Coste estimado por backtest** (FR-041): con periodicidad mensual, 21 años = **252 decisiones**.
A ~4.000 tokens de entrada y ~1.000 de salida cada una: ~1M entrada + ~250K salida ≈ **$11 por
backtest completo**. Con caché de prompt y Batches API (abajo) baja a una fracción.

---

## D2. El no-determinismo no se puede acotar con temperatura

**Hallazgo que cambia el diseño**: **`temperature`, `top_p` y `top_k` están eliminados en Opus 5**.
Enviar cualquiera de los tres devuelve un error 400.

Esto invalida la solución habitual —"pon temperatura 0 y será determinista"— por dos motivos:

1. Ya no es posible enviarla.
2. **Nunca garantizó salidas idénticas**, ni en los modelos donde existía.

**Consecuencia**: el caché de decisiones (FR-043..FR-045) deja de ser una optimización de coste y
pasa a ser **el único mecanismo de reproducibilidad disponible**. Sin él, FR-005 sería imposible de
cumplir para el LLM, y comparar dos experimentos no significaría nada.

---

## D3. Forzar el formato de la decisión

**Decisión**: salida estructurada con `output_config.format` y esquema JSON.

**Razón**: FR-011 exige que una respuesta no interpretable se trate como fallo y que el sistema no
invente una decisión. Con un esquema, la validación ocurre en la capa de la API: el modelo no puede
devolver prosa donde se espera una decisión.

**Detalles que afectan al diseño**:

- El esquema exige `additionalProperties: false` y `required` explícito.
- **No admite** esquemas recursivos ni restricciones numéricas (`minimum`, `maximum`). Los límites
  de peso por activo hay que validarlos **en nuestro código**, no delegarlos al esquema.
- Un rechazo por seguridad (`stop_reason: "refusal"`) puede devolver algo que no cumple el esquema:
  hay que comprobar `stop_reason` **antes** de leer el contenido.
- La primera petición con un esquema nuevo paga una compilación; después se cachea 24 h.

**Alternativa descartada**: `strict: true` sobre una herramienta. Equivalente en garantías, pero
añade el ciclo de tool use sin necesidad — aquí no queremos que el modelo ejecute nada, solo que
devuelva una decisión con forma conocida.

---

## D4. Reducir el coste sin tocar la calidad

Tres mecanismos, en orden de impacto:

1. **Caché de decisiones propio** (FR-043). El más importante: repetir un experimento cuesta cero.
2. **Caché de prompt de la API**. El contexto estable (instrucciones, universo, reglas) se marca
   con `cache_control`; las lecturas cuestan ~0,1×. **El mínimo cacheable en Opus 5 son 512 tokens**
   —la mitad que en modelos anteriores—, así que hasta un prompt modesto se beneficia.
   Requisito de diseño: lo que cambia (la fecha simulada, los precios) va **al final**, después del
   punto de caché. Si se interpola la fecha al principio, el caché no sirve para nada.
3. **Batches API: 50% de descuento**. Encaja de forma natural con un backtest: las 252 decisiones
   mensuales son **independientes entre sí** — cada una solo mira su propia ventana de datos. Se
   pueden enviar en lote y recogerse en menos de una hora. Un backtest de 21 años pasa de ~$11 a
   ~$5,50, y de secuencial a una sola espera.

**Consecuencia de diseño**: la interfaz del proveedor debe permitir pedir **muchas decisiones a la
vez**, no solo una. Si se diseña únicamente para "una decisión por llamada", el descuento por lotes
queda inaccesible sin rehacerla.

---

## D5. Aislar el LLM para poder testear sin red ni gasto

**Decisión**: un protocolo `DecisionProvider` con tres implementaciones — igual que se hizo con los
proveedores de datos en la feature 002.

| Implementación | Para qué |
|---|---|
| `AnthropicProvider` | La real. Única que toca la red. |
| `RecordedProvider` | Lee decisiones guardadas. Es el caché y a la vez el sustituto en tests. |
| `ScriptedProvider` | Decisiones fijas escritas a mano, para probar casos límite. |

**Razón**: FR-036 prohíbe que los tests toquen la red o gasten llamadas. La suite ya corre con los
sockets bloqueados, así que una implementación que intentara salir **fallaría de forma ruidosa**, no
silenciosa. Es la misma garantía estructural que protege al motor.

**Ventaja secundaria**: `RecordedProvider` sirve para las tres cosas —caché, tests y
reproducibilidad— sin código distinto para cada una.

---

## D6. Clave del caché

**Decisión**: hash del contenido que determina la decisión, más el identificador del modelo.

Entra en el hash: el modelo, la versión de las instrucciones, el instante simulado, los activos
considerados y la ventana de datos vista. **No entra** nada que no afecte a la decisión.

**Razón**: FR-045 exige que cambiar de modelo no reutilice decisiones del anterior. Y si cambian las
instrucciones, la decisión ya no es la misma pregunta — reutilizarla sería mentir sobre qué se
midió.

---

## D7. Qué ve el LLM dentro de un backtest

**Decisión**: recibe la misma `MarketView` que las estrategias de reglas, traducida a texto.

**Razón**: es la aplicación literal del Principio II. `MarketView` ya impide estructuralmente ver el
futuro: `bar_at(offset)` rechaza offsets negativos y las ventanas de precios se devuelven como
arrays de solo lectura. Si el LLM recibe su contexto de ahí, hereda esa garantía sin código nuevo.

**Lo que no arregla**: la contaminación del propio entrenamiento del modelo. Por eso las
instrucciones **no mencionan fechas ni nombres reales de activos** durante un backtest — se acota lo
que se puede acotar y se advierte del resto (FR-010).

---

## D8. Ejecución real

**Decisión**: cripto primero con `ccxt`, en **testnet obligatoria** antes de dinero real.

**Razón**: `ccxt` ya está integrado de la feature 002 y expone `create_order` con la misma interfaz
para decenas de exchanges. Binance ofrece una red de pruebas con infraestructura real y dinero
ficticio: es donde se descubren los fallos de ejecución sin pagarlos.

**Para bolsa**: Alpaca tiene API moderna y cuenta de prácticas incluida. Llega después (FR-046).

**Salvaguarda estructural** (FR-025..FR-032): el modo no se lee de una variable global sino que
viaja en el objeto que ejecuta. Una función que solo acepta un `LiveBroker` no puede recibir un
simulador por error, y al revés. El modo se comprueba **en el momento de enviar**, no al arrancar.

---

## D9. Análisis fundamental

**Decisión**: datos de `yfinance` (`Ticker.info`) más contexto del LLM, en secciones separadas.

**Razón**: `yfinance` da sector, capitalización, márgenes y deuda sin coste. Son verificables contra
su fuente.

**Límite que hay que declarar** (FR-051): **son datos de hoy**. Usarlos para analizar una decisión
de 2018 sería look-ahead — la empresa de entonces no es la de ahora. Sirven para decidir hacia
adelante, no para juzgar el pasado.

---

## Resumen de decisiones

| # | Decisión | Consecuencia principal |
|---|---|---|
| D1 | `claude-opus-5` | ~$11 por backtest de 21 años; ~$5,50 en lote |
| D2 | Sin temperatura (eliminada) | El caché es la **única** vía a la reproducibilidad |
| D3 | Salida estructurada por esquema | Los límites numéricos se validan en nuestro código |
| D4 | Caché + prompt caching + lotes | La interfaz debe aceptar decisiones **en lote** |
| D5 | Protocolo con 3 implementaciones | Tests sin red ni gasto, como en la 002 |
| D6 | Clave = contenido + modelo | Cambiar de modelo invalida el caché |
| D7 | El LLM ve `MarketView` | Hereda la garantía anti-look-ahead existente |
| D8 | ccxt + testnet obligatoria | El modo viaja en el objeto, no en una global |
| D9 | yfinance + LLM, separados | Los datos actuales **no** valen para el pasado |
