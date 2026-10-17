# Panel v3: en vivo — Operar y Bots

Decidido con Marcos el 2026-10-17. Amplía el panel v2 (`docs/panel-v2.md`, cuyos principios,
diccionario y sistema visual siguen valiendo) con dos secciones nuevas:

- **Operar**, al estilo de la pantalla de intercambio de Hyperfluid o Hyperliquid: elegir una moneda,
  ver sus velas, su libro de órdenes y sus operaciones moviéndose en vivo, y comprar o vender.
- **Bots**, al estilo de los *vaults* de Hyperliquid: desplegar bots que operan solos y ver, en vivo,
  cuánto está generando cada uno.

Dos decisiones de Marcos que cambian reglas anteriores, y por eso se escriben aquí:

1. **Dinero ficticio primero.** Todo lo de este documento opera con una **cuenta de práctica** y
   capital ficticio: nada sale al exterior y ninguna clave interviene. Pasar un bot a dinero real
   será una decisión posterior y explícita (y entonces se discutirá la confirmación por orden del
   Principio I).
2. **En vivo.** El panel v2 evitaba refrescarse solo ("una foto fechada, no un chorro"). Aquí
   Marcos quiere precios y cifras moviéndose mientras mira. Se hace, con dos contrapesos: la hora
   y la fuente de cada dato siempre a la vista, y ningún aviso fuera de la pantalla (nada de
   notificaciones del sistema ni sonidos).

## 1. De dónde salen los precios

De **Hyperliquid**, que es un exchange con su propio libro de órdenes, por su API pública (sin cuenta
ni claves):

- REST: `POST https://api.hyperliquid.xyz/info` — `allMids`, `l2Book`, `candleSnapshot`
  (como mucho las 5000 velas más recientes), `metaAndAssetCtxs` (precio de ayer, volumen del día,
  financiación…).
- Streaming: `wss://api.hyperliquid.xyz/ws` — suscripciones `allMids`, `l2Book` (20 niveles por
  lado, una foto por bloque), `trades` y `candle` (1m 3m 5m 15m 30m 1h 2h 4h 8h 12h 1d 3d 1w 1M).

Son los precios de sus **perpetuos** (contratos que siguen al precio de la moneda), muy pegados al
contado. La cuenta de práctica opera **como contado y sin apalancamiento**: compras una moneda con
USDC ficticios y la tienes; no hay financiación ni liquidaciones. La interfaz lo dice una vez, sin
jerga: "Precios en vivo de Hyperliquid. Dinero ficticio."

El servidor mantiene **una** conexión con Hyperliquid (reconecta sola, con espera creciente, y dice
cuándo está desconectado) y reparte a la interfaz por **SSE** (`GET /api/vivo/stream`). Los bots
usan la misma fuente, sin pasar por el navegador: siguen funcionando con la pestaña cerrada, pero
**solo mientras el panel (la ventana de consola) está abierto**, y se dice.

## 2. Operar (cuenta de práctica)

Pantalla de exchange, densa pero legible:

- **Selector de moneda** con buscador: nombre llano, precio, variación 24 h y volumen; las más
  negociadas primero.
- **Gráfico de velas** en vivo con intervalos 1m · 5m · 15m · 1h · 4h · 1d (lightweight-charts u
  otra librería mantenida; la vela en curso se mueve).
- **Libro de órdenes** (compras abajo, ventas arriba, diferencial en medio) y **últimas
  operaciones**, en vivo.
- **Boleto**: Comprar / Vender, A mercado / Con límite, cantidad en USDC o en la moneda, accesos de
  25-50-75-100 % del saldo; antes de enviar dice qué va a pasar ("Comprarás unos 0,0148 BTC por
  1.000 USDC, comisión ~0,45 USDC"). No hace falta teclear la cantidad para confirmar: es dinero
  ficticio.
- **Abajo**: posiciones, órdenes con límite pendientes (cancelables), historial; saldo, valor total
  y ganancia de la cuenta, en vivo. Botón de reiniciar la cuenta (con confirmación).

**Ejecución ficticia creíble** (`invest_ll/vivo/ejecucion.py`, puro y probado):
- A mercado se ejecuta **contra el libro real del momento**, nivel a nivel (si compras más de lo
  que hay en el primer nivel, pagas los siguientes), más comisión de tomador.
- Con límite: queda pendiente y se ejecuta cuando el precio la cruza, a su precio, con comisión de
  creador.
- Comisiones por defecto las de Hyperliquid de nivel base: tomador 0,045 %, creador 0,015 %.

## 3. Bots

### La lista (como los vaults)
Arriba, el total de tus bots: capital ficticio puesto, lo que vale ahora y lo ganado, en vivo.
Debajo, una tarjeta por bot: nombre, plantilla, monedas, estado (en marcha · parado · con error),
**cuánto ha generado** (€ y %), hoy, peor caída, días en marcha, operaciones, y la comparación con
**"si solo hubieras mantenido"** desde el mismo momento — siempre al lado, al mismo tamaño. Curva
pequeña. Ordenable por ganancia, por días, por riesgo.

### Desplegar un bot
Asistente corto: plantilla → monedas → capital ficticio → parámetros (con valores por defecto y la
explicación llana de cada uno) → nombre → **Desplegar**.

### La ficha de un bot
Curva en vivo frente a "mantener", posiciones, operaciones con **el porqué de cada una** ("Compré
0,01 BTC a 67.010: la media de 20 velas cruzó por encima de la de 50"), eventos (arranques,
paradas, cortes de conexión, huecos por panel cerrado), parámetros, y Parar / Reanudar / Borrar.

### Plantillas

| Clave | Nombre | Qué hace | Velas | Evidencia |
|---|---|---|---|---|
| `btc-freno` | Bitcoin con freno | Dentro de BTC si sus 30 días suben; si no, en USDC. Decide una vez al día | 1d | Probada sobre el pasado; en prueba real desde 15 oct 2026 |
| `tendencia` | Tendencia rápida | Cruce de dos medias (por defecto 20 y 50 velas de 1 h) | 15m-4h | Ninguna: es un experimento |
| `rejilla` | Rejilla | Reparte compras escalonadas en un rango y vende cada escalón al subir | en vivo | Ninguna: gana si el precio oscila dentro del rango, pierde si sale por abajo |
| `periodica` | Compra periódica | Compra una cantidad fija cada N horas | — | La de "aportar y mantener", sin elegir momento |

Cada plantilla declara su riesgo (1-5), cuántas operaciones esperar ("decenas al día" en la
rejilla) y sus avisos. Las que no tienen evidencia lo dicen en la tarjeta del bot, no solo al
crearlo. Ningún bot opera fuera de su capital ficticio ni con apalancamiento.

### Cómo corren
- Un **motor** en el proceso del panel: en cada vela cerrada de su intervalo (o en cada precio, la
  rejilla) cada bot en marcha decide; las órdenes se ejecutan con `vivo/ejecucion.py` contra el
  libro del momento; entre medias, el valor se recalcula con cada precio.
- **Estado en disco** (`bots/`, fuera de git): definición, posiciones y un registro de operaciones
  y eventos que solo añade. Al reabrir el panel, cada bot sigue donde estaba y apunta el hueco
  ("panel cerrado de 14:02 a 18:30: no pudo operar").
- Un bot que falla queda en "con error" con el motivo; no tumba a los demás.

## 4. Navegación

Entran **Operar** y **Bots** como secciones principales. En escritorio, la barra lateral las
añade; en móvil la barra inferior sigue con 5 huecos (lo que no quepa, en "Más"). El diseño decide
el orden con un criterio: quien no sabe empieza por Estrategias; quien ya juega, por Bots y Operar.

## 5. Contrato

`src/invest_ll/api/schemas_v3.py` y los routers `vivo.py`, `practica.py` y `bots.py`. El stream SSE
(`GET /api/vivo/stream`) emite eventos cuyo `data` es exactamente el JSON de una ruta REST, para
que la interfaz use los mismos tipos:

| Evento | Cada | `data` igual que |
|---|---|---|
| `monedas` | ~1 s | `GET /api/vivo/monedas` |
| `libro` | cada foto del libro de la moneda pedida | `GET /api/vivo/libro?coin=` |
| `operaciones` | cada operación nueva | lista de `OperacionMercado` |
| `vela` | cada cambio de la vela en curso | `Vela` (con `coin` e `intervalo` en `VelaVivo`) |
| `cuenta` | ~1 s | `GET /api/practica` |
| `bots` | ~2 s | `GET /api/bots` |
| `estado` | al cambiar | `EstadoVivo` (conectado, fuente, aviso) |

Parámetros del stream: `coin` (para libro, operaciones y vela), `intervalo` (vela) y `canales`
(lista separada por comas; por defecto todos).

## 6. Lo que no cambia

- Nada de esto envía órdenes a ningún exchange ni toca claves: la cuenta de práctica y los bots son
  ficticios. `POST /api/ordenes` (Binance, con confirmación tecleada) sigue siendo la única puerta
  al dinero.
- La API solo atiende a `localhost`, y los errores son siempre `{"detail": "texto en llano"}`.
