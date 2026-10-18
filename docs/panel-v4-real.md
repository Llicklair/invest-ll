# Panel v4: bots reales en varios exchanges, con estrategias diseñadas con Claude

Decidido con Marcos el 2026-10-17. Sigue a `docs/panel-v3-vivo.md` (Operar y Bots con dinero
ficticio), cuyos principios siguen valiendo.

## 0. Las decisiones de Marcos, por escrito

1. **Binance es solo un medio.** El sistema se conecta a **varios exchanges**; ninguno es especial.
2. **Un conector con Claude.** Claude (con la suscripción de Marcos, por el CLI `claude`, como el
   chat) diseña las estrategias **a medida** a partir de lo que Marcos pide, las prueba y monta los
   bots.
3. **Los bots reales operan solos, con límites que fija Marcos.** Esto **cambia el Principio I**
   ("cada orden se confirma tecleando la cantidad") **solo para los bots reales que Marcos active
   así**, con límites puestos y activación tecleada. Las órdenes manuales siguen pidiendo su
   confirmación. Es la decisión explícita que el README pedía para quitarla.

Y dos de diseño, por seguridad (dinero real + una IA escribiendo estrategias):

4. **Las estrategias no son código.** Claude escribe una estrategia en un **formato cerrado**
   (JSON: indicadores, reglas, tamaño, stops) que el motor **interpreta**. Nada generado por una
   IA se ejecuta como código en el proceso que tiene las claves. Una estrategia mal hecha puede
   perder dinero dentro de sus límites, pero no puede hacer nada fuera de su formato.
5. **Claude nunca activa dinero real.** Por el conector puede diseñar, validar, probar sobre el
   pasado y desplegar en ficticio. Pasar un bot a real, subirle los límites o tocar claves solo se
   hace desde el panel, por Marcos, con confirmación tecleada.

## 1. Conectores de exchanges (`invest_ll/exchanges/`)

Un protocolo `Conector` y una implementación genérica sobre **ccxt** (que ya usa el proyecto), con
lo propio de cada exchange en un sitio. **Solo contado (spot), sin apalancamiento.**

| Exchange | Red de pruebas | Claves |
|---|---|---|
| Binance | sí (testnet.binance.vision) | API key + secret (HMAC), sin retirada |
| Hyperliquid | sí (testnet; su grifo exige haber depositado antes en la red real) | dirección de la cartera + clave privada de una **API wallet** (opera, no puede retirar) |
| Bybit | sí | API key + secret, sin retirada |
| OKX | sí (modo demo) | API key + secret + passphrase, sin retirada |
| Kraken | no | API key + secret, sin retirada |
| Coinbase (Advanced) | no | clave de la API, sin retirada |

El conector da: mercados (pares de contado, mínimos, pasos de precio y cantidad, comisiones),
precio, libro, velas, saldo, enviar orden (con **id de cliente** para no duplicarla al reintentar),
consultar y cancelar órdenes, y lo que se sepa de los **permisos** de la clave (si puede retirar:
se comprueba donde la API lo dice —Binance— y se avisa donde no). Las claves van al almacén de
credenciales de Windows por exchange y red, y nunca salen por ninguna ruta.

**Cada exchange tiene su camino**: pruebas → real, como el de Binance de v2 (§4.6 de
`panel-v2.md`): claves de pruebas, comprobar, al menos una orden de pruebas ejecutada (evidencia),
y para real claves distintas y "DINERO REAL" tecleado. Los exchanges sin red de pruebas lo dicen y
exigen haber probado la estrategia en ficticio (§3) antes de activar real.

## 2. Estrategias a medida (`invest_ll/estrategias_custom/`)

### El formato
Una estrategia es un JSON validado (con versión y huella) con:
- `monedas` y `intervalo` de las velas;
- `indicadores` con nombre: `sma`, `ema`, `rsi`, `retorno` (n velas), `maximo`, `minimo`,
  `volatilidad`, `atr`, `volumen_medio`… sobre cierre/máximo/mínimo/volumen;
- `entrar` y `salir`: condiciones como árbol (`y`, `o`, `no`, comparaciones `>`, `<`, `>=`, `<=`,
  `cruza_arriba`, `cruza_abajo` entre indicadores, precios y números) — sin expresiones libres;
- `tamano`: fracción del capital, reparto igual entre monedas o por volatilidad, con máximo por
  moneda;
- `riesgo` propio: stop de pérdida %, toma de beneficio %, stop que sigue al precio %;
- `explicacion` en llano (para la ficha) y `autor` (Claude / Marcos).
El intérprete es puro y probado, decide **solo con velas cerradas** (el mismo test anti-futuro
que los bots de v3) y produce las mismas órdenes que las plantillas.

### El camino de una estrategia
1. **Borrador** — escrita (por Claude o a mano) y validada.
2. **Probada sobre el pasado** — sobre velas del exchange y monedas elegidos, con comisiones
   y deslizamiento, contra "mantener": resultado, peor caída, operaciones, tiempo dentro. **Se
   cuenta cuántas versiones se han probado** y, a partir de varias, la ficha avisa de que "elegir la
   mejor de muchas pruebas sobre el pasado se parece a hacer trampa" (sobreajuste).
3. **En ficticio** — un bot ficticio en vivo (v3). Recomendado **un mes** antes de real, y aprobar el examen sobre el pasado (§3).
4. **Real** — un bot real con límites (§3). Saltarse el paso 3 se puede, pero exige escribir
   "SIN PRUEBA EN FICTICIO" al activar: es tu dinero, y la decisión queda registrada.

### Diseñar con Claude
En el panel, **Estrategias → Diseñar con Claude**: una conversación (gasta cuota de la
suscripción) donde Marcos dice lo que quiere ("compra ETH cuando rebote del mínimo de 30 días,
vende si cae un 8 %") y Claude, con las herramientas del conector (§2.1), escribe la estrategia,
la valida, la prueba sobre el pasado, enseña los resultados **con sus pegas** y, si Marcos quiere,
la despliega en ficticio. La conversación y cada versión quedan guardadas.

### 2.1 El conector MCP (`invest-ll-mcp`)
Un servidor MCP local (stdio) con herramientas: `exchanges`, `monedas`, `velas`, `esquema`
(el formato de estrategia), `validar`, `probar` (sobre el pasado), `guardar`, `estrategias`,
`desplegar_ficticio`, `bots` (estado), `parar_bot`. **No** tiene herramientas para activar real,
cambiar límites ni tocar claves. El panel lo usa con `claude -p --mcp-config …`; el mismo
servidor se puede añadir a Claude Code o Claude Desktop (Ajustes enseña el bloque de
configuración) para hablar con el sistema desde ahí.

## 3. Bots reales (`invest_ll/bots/` ampliado)

Un bot tiene **modo** `ficticio | pruebas | real` y **exchange**. Los de pruebas y real ejecutan
con el conector; los ficticios, como en v3. Ejecutan una plantilla de v3 **o** una estrategia a
medida.

### Límites (obligatorios en pruebas y real)
- **Capital máximo** del bot (no puede gastar más, aunque haya saldo en la cuenta).
- **Tamaño máximo por orden.**
- **Pérdida máxima**: si el bot cae un X % desde su capital, se **para** y, si así se eligió,
  **vende todo** lo suyo.
- **Operaciones máximas por día.**
- **Monedas permitidas** (las de su estrategia).
- Globales: **pérdida máxima diaria de todos los bots reales** y el **interruptor "Parar todo lo
  real"** (para todos los bots reales y cancela sus órdenes abiertas), siempre a la vista.

### Cómo se protege cada orden
- Comprobación de límites **antes** de cada orden; si no cabe, no sale (evento en llano).
- Id de cliente por orden: un reintento no la duplica.
- Estado desconocido (se cortó la red) → el bot **se pausa** y lo dice; no se adivina.
- **Conciliación** cada pocos minutos: lo que el bot cree tener frente al saldo del exchange; si
  no cuadra, se pausa y enseña la diferencia.
- Toda orden real queda en el registro de órdenes (`ledger/`) con su modo, exchange, bot y motivo,
  y pasa a la cartera del modo.
- Activar real: con límites puestos, desde el panel, escribiendo `ACTIVAR <nombre del bot>`
  (y "SIN PRUEBA EN FICTICIO" si no pasó por ficticio). Subir límites pide lo mismo.

### Cómo quedó (`bots/real.py` + `bots/motor.py`, octubre 2026)
- **Decide con Hyperliquid, opera en su exchange.** Las velas y la señal son las de Hyperliquid
  (las de todos los bots); la orden sale a mercado al exchange del bot, al paso de su par (misma
  base o con la U de los envueltos de Hyperliquid, en USDC antes que en USDT). Se valora con el
  precio de su exchange, leído cada 15 s.
- **Los límites frenan lo que gasta.** Operaciones del día (desde las 00:00 de Madrid), máximo por
  orden y capital máximo se comprueban antes de cada **compra**. Vender lo suyo siempre se puede:
  un límite no lo deja atrapado en una posición. El «no sale» se apunta una vez, no en cada vuelta.
- **El id se guarda antes de enviar.** Antes de cada orden el bot queda en disco en pausa
  «desconocido» con su id de cliente; al volver la respuesta, se quita. Si el motor muere a mitad,
  al cargar está en pausa y al reanudarlo se consulta esa orden (si salió, se apunta).
- **Conciliación** al cargar (ningún bot de exchange opera antes de cuadrar) y cada 5 minutos, por
  exchange y red: se suman los bots que comparten cuenta. El exchange puede tener más (lo de
  Marcos fuera de los bots), nunca menos (con una tolerancia del 0,5 % o un paso). Si no cuadra,
  se pausan todos los de esa cuenta; reanudar vuelve a comprobarlo.
- **Activar real empieza de cero**: su capital pasa a ser su capital máximo, su historia de antes
  se archiva aparte (`curva-<modo>-<fecha>.jsonl`) y antes de activarlo se comprueba que en la
  cuenta real hay saldo para él y para los reales que ya operan allí. Un bot de pruebas con
  monedas no se activa (que las venda antes).
- **Pérdida máxima** (desde su capital): se para y, si así se eligió, vende todo. **Límite
  diario** (de todos los reales, lo que ganan unos compensa lo que pierden otros): al llegar, «Parar
  todo lo real», que para los reales y cancela solo las órdenes que dejaron abiertas los bots
  (nunca las de Marcos). Reanudar todo quita el interruptor; cada bot se reanuda a mano.
- **Borrar no vende**: un bot de exchange se para antes de borrarlo y lo suyo se queda en la cuenta.
- **Examen sobre el pasado antes de real** (`bots/examen.py`, octubre 2026): la regla del bot corre
  en 6 tramos del último año, cada uno desde cero y frente a mantener (velas de Binance o, si no
  tiene sus monedas, de Hyperliquid). Aprueba si hay al menos 4 tramos, al menos 6 operaciones y en
  2 de cada 3 tramos le va como mínimo como a mantener (gana más, o cae menos de la mitad sin
  quedarse más de 5 puntos por detrás). Vale 30 días y para esa misma regla (huella). Activar real
  sin examen aprobado pide escribir `SIN EXAMEN`; con menos de **30 días** en ficticio (antes 7),
  `SIN PRUEBA EN FICTICIO`. Una sola prueba buena puede ser suerte del periodo; seis, mucho menos.
- Todo probado contra `ConectorFalso` (`tests/unit/test_bots_real.py`,
  `tests/integration/test_api_bots_real.py`): las pruebas no envían nada a ningún exchange.

## 4. Pantallas

- **Ajustes → Conexiones**: la lista de exchanges con su estado (sin conectar · pruebas · real),
  el asistente de cada uno (como el de Binance de v2) y el bloque para añadir el conector MCP a
  Claude Code / Desktop.
- **Estrategias** gana "A medida": tu biblioteca (estado: borrador · probada · en ficticio ·
  real), "Diseñar con Claude" (conversación + la estrategia que va saliendo + sus pruebas) y la
  ficha de cada estrategia (explicación, reglas en llano, resultados sobre el pasado frente a
  mantener, versiones probadas, desplegar).
- **Bots**: modo y exchange en cada tarjeta (dinero real en rojo, inconfundible), límites y lo
  consumido de cada uno, el interruptor "Parar todo lo real" siempre visible arriba, y el
  asistente de desplegar con la elección de modo/exchange/límites y la activación tecleada.

## 5. Lo que no cambia
- Ninguna IA mueve dinero real por decisión propia: Claude no puede activar real ni subir límites.
- Las claves no salen nunca; la API solo atiende a `localhost`; los errores en llano.
- Las órdenes manuales (Invertir, Operar en real si llega) siguen con confirmación tecleada.
