# Operar de verdad

De simulación a dinero real, sin sorpresas. Esta guía documenta lo que el código hace hoy, no lo
que se planea que haga.

---

## Lo primero: qué se puede y qué no

| | Datos y simulación | Enviar órdenes de verdad |
|---|---|---|
| **Cripto** (BTC/USDT, pares de Binance) | Sí | **Sí** — vía ccxt, Binance por defecto |
| **Bolsa** (AAPL, SPY, GLD, ETFs) | Sí | **No. No hay integración con ningún broker** |

Para bolsa el sistema es un asesor, no un ejecutor: descarga el histórico, propone la cartera,
mide y vigila — pero la compra la haces tú donde ya operes, y luego la registras (ver
[Bolsa: el flujo manual](#bolsa-el-flujo-manual)). Añadir un broker de bolsa sería una feature
nueva, no un ajuste de configuración.

## Enviar la orden sigue siendo tuyo

Las estrategias deciden solas. **Cada orden que sale al mercado te pide confirmarla escribiendo la
cantidad exacta a mano** — no un `s/n`, la cifra. Obliga a mirar el número que se va a mover,
porque un "sí" distraído no debería ejecutar 0,5 BTC.

Esa confirmación autoriza **esa orden y ninguna otra**: se construye a partir de la huella de la
orden concreta, así que "autorizar todas" no se puede ni escribir. Si la orden cambia entre
confirmar y enviar, la huella deja de coincidir y el envío se rechaza.

Que uses `--json` para manejar el sistema desde otro programa no cambia esto: el mensaje sale por
stderr y se sigue esperando respuesta. Que un agente pueda leer la salida no significa que pueda
ocupar tu lugar.

---

## El camino: tres etapas, en este orden

### Etapa 1 — Simulación (donde estás ahora)

Es lo que obtienes sin configurar nada. Ninguna orden sale al exterior, con confirmación o sin
ella. Empieza viendo qué se enviaría:

```bash
uv run invest-ll-execute --symbol BTC/USDT --side buy --quantity 0.001 --dry-run
```

Responde `MODO SIMULACION — no se ha enviado nada al exterior` y te recuerda las cuatro
condiciones. `--dry-run` muestra y para, sin preguntar nada.

### Etapa 2 — Red de pruebas (obligatoria)

Órdenes que salen de verdad al exchange, contra dinero ficticio. **Es donde se descubren los fallos
de ejecución sin pagarlos**, y el sistema no te deja saltártela.

1. Crea claves de testnet en `testnet.binance.vision` (spot). **No son las de tu cuenta real** —
   ver [De dónde salen las claves](#de-dónde-salen-las-claves), incluido el tipo de clave que hay
   que elegir.
2. Ponlas en el entorno. En PowerShell:

   ```powershell
   $env:INVEST_LL_MODE = "testnet"
   $env:INVEST_LL_TESTNET_KEY = "tu_clave_de_pruebas"
   $env:INVEST_LL_TESTNET_SECRET = "tu_secreto_de_pruebas"
   ```

   En bash:

   ```bash
   export INVEST_LL_MODE=testnet
   export INVEST_LL_TESTNET_KEY=tu_clave_de_pruebas
   export INVEST_LL_TESTNET_SECRET=tu_secreto_de_pruebas
   ```

3. Comprueba la tubería **antes** de mandar nada. Este script no envía ninguna orden: responde a
   la pregunta previa — ¿apunta a la red de pruebas, hay camino, acepta el exchange mis claves?

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\testnet.ps1
   ```

   Te dirá una de tres cosas: que falta configurar algo (y qué), que el exchange **rechaza** las
   credenciales (revisa que sean de testnet y del tipo HMAC-SHA256), o que todo está listo y te
   mostrará el saldo ficticio disponible.

   Descubrir que la respuesta era «no» en el momento de mandar la orden es el peor momento posible.

4. Manda una orden pequeña y ve el ciclo entero, incluida la confirmación:

   ```bash
   uv run invest-ll-execute --symbol BTC/USDT --side buy --quantity 0.001
   ```

Opera aquí hasta que no te sorprenda nada: una orden rechazada, una parcial, un símbolo que el
exchange nombra distinto. Ese es el objetivo de la etapa, no "que salga bien una vez".

### Etapa 3 — Dinero real

Solo cuando la etapa 2 ya no te enseñe nada nuevo.

```powershell
$env:INVEST_LL_MODE = "real"
$env:INVEST_LL_LIVE_KEY = "tu_clave_real"          # DISTINTA de la de pruebas
$env:INVEST_LL_LIVE_SECRET = "tu_secreto_real"
$env:INVEST_LL_TESTNET_VERIFIED = "1"              # declaras haber hecho la etapa 2
```

Las claves se leen del entorno y **nunca** se guardan en el repositorio. En la cuenta del exchange,
da a esas claves permiso de operar pero **no de retirar fondos**: el sistema no necesita retirar
nada, y una clave que no puede sacar dinero no puede perderlo si se filtra.

---

## De dónde salen las claves

### Tienen que ser HMAC-SHA256

Binance deja elegir el tipo de clave al crearla. **Elige HMAC-SHA256** (a veces aparece como
"HMAC_SHA256" o "System generated"). Las claves **Ed25519 o RSA no funcionan aquí**: el sistema
pasa a ccxt un `apiKey` y un `secret` y nada más — no hay sitio donde meter una clave privada en
PEM. Si eliges Ed25519, lo que te dan como "secret" es una clave privada y el exchange rechazará
todo con error de autenticación, sin que nada esté roto.

Si el comprobador dice *"el exchange RECHAZA las credenciales"* y estás seguro de haberlas copiado
bien, esto es lo primero que hay que mirar.

### Las de pruebas (etapa 2)

1. Entra en **`testnet.binance.vision`** y pulsa **"Log In with GitHub"**. Es el único método de
   acceso: no se crea cuenta ni contraseña. Esa cuenta de pruebas **no tiene nada que ver con tu
   cuenta de Binance**.
2. Ya dentro, genera una clave **HMAC-SHA256**.
3. Copia las dos cosas que te muestra: la **API Key** y la **Secret Key**.
4. **El saldo ficticio te lo dan solo.** Al registrarte recibes automáticamente saldo en muchos
   activos; no hay que pedir nada. Ese dinero no existe fuera de la red de pruebas y no se puede
   sacar.

> **Los precios de la red de pruebas no son los del mercado real.** Tiene su propio libro de
> órdenes, así que BTC puede cotizar ahí a un precio que no existe en Binance. Sirve para ensayar
> la mecánica — que la orden salga, se ejecute y se registre — **no para medir una estrategia**. Eso
> se mide con el backtester sobre histórico real.

> **La red de pruebas se borra aproximadamente una vez al mes, sin avisar.** Se van las órdenes
> pendientes y las ejecutadas, y recibes saldo nuevo. Si un día el comprobador falla o tu saldo
> aparece a cero sin que hayas hecho nada, probablemente hubo un reset: vuelve a entrar y, si hace
> falta, genera otra clave. Cuenta con esto si piensas dejar una prueba corriendo varios días.

### Las reales (etapa 3)

En tu cuenta de Binance: **Perfil → API Management → Create API**, tipo **System generated
(HMAC)**. Al crearla:

- Activa **lectura** y **spot trading**.
- **No** actives retirada de fondos. El sistema no retira nada, y una clave que no puede sacar
  dinero no puede perderlo si se filtra.
- Si tu conexión tiene IP fija, restringe la clave a esa IP. Es la diferencia entre que te roben la
  clave y que además puedan usarla.

### El secreto se muestra UNA vez

Cuando cierres esa pantalla no hay forma de volver a verlo: si lo pierdes, se borra la clave y se
crea otra. No lo pegues en ningún fichero del repositorio — el sistema las lee del entorno
precisamente para que no acaben en un commit.

### Las variables solo viven en esa terminal

`$env:INVEST_LL_MODE = "testnet"` desaparece al cerrar la ventana, y eso es una defensa: cerrar la
terminal te devuelve a simulación. Si te cansa repetirlo, `setx INVEST_LL_TESTNET_KEY "..."` las
deja permanentes para tu usuario de Windows — pero entonces quedan guardadas en el registro y
**cualquier proceso tuyo puede leerlas**. Para las claves de pruebas es un intercambio razonable;
para las de dinero real, pégalas cada vez.

---

## Los cuatro cerrojos, y lo que dice cada uno al saltar

Ninguno basta por sí solo, y los tres bloqueantes están comprobados ejecutándolos:

| Falta | Lo que pasa |
|---|---|
| El modo (`INVEST_LL_MODE`) | Sigues en simulación. Tener credenciales sueltas no activa nada, y un modo mal escrito (`reall`) **falla** en vez de caer en real |
| Las credenciales del modo | `falta INVEST_LL_TESTNET_KEY: el modo pedido necesita las credenciales pruebas` |
| Haber pasado por pruebas | `no se puede operar con dinero real sin haber operado antes en la red de pruebas` |
| Que las claves sean distintas | `la credencial de dinero real coincide con la de pruebas. Tienen que ser distintas: si son la misma, no hay separacion real entre modos` |

El modo se comprueba **al enviar cada orden, no al arrancar**: entre construir el broker y mandar
algo puede pasar cualquier cosa, y la comprobación que importa es la de justo antes.

## Si se corta la red a mitad

El estado es `ESTADO DESCONOCIDO`, nunca "ejecutada" ni "rechazada". Suponer cualquiera de las dos
cuesta dinero: una te lleva a no reintentar algo que no se ejecutó, la otra a duplicar una orden
que sí salió. Cuando lo veas, **compruébalo en el exchange antes de volver a operar**. El sistema
no lo adivina por ti a propósito.

Lo mismo con una orden parcial: te dice cuánto se ejecutó de cuánto pediste, y lo marca como algo
que necesita tu atención.

---

## Cómo se trackea

Tres registros distintos, porque responden a tres preguntas distintas.

### 1. Qué se envió — `ledger/orders.jsonl`

Auditoría que solo añade; un registro de órdenes que se puede reescribir no sirve para auditar
nada. **Cada entrada guarda el modo en que salió**, así que después puedes demostrar que una orden
concreta fue de pruebas y no de dinero real — que es justo la pregunta que te haces cuando algo ha
ido mal. Con `--ledger otra/carpeta` lo llevas a otro sitio.

### 2. Qué tienes — `invest-ll-portfolio`

```bash
uv run invest-ll-portfolio show                      # posiciones, retiradas y efectivo
uv run invest-ll-portfolio add buy --symbol GLD --quantity 10 --price 180.5 --fee 1.2
uv run invest-ll-portfolio cash deposit --amount 1000
uv run invest-ll-portfolio import movimientos.csv    # CSV del broker
```

El importador acepta cabeceras en inglés o español (`date`/`fecha`, `symbol`/`ticker`/`code`,
`type`/`tipo`, `quantity`/`shares`/`cantidad`, `price`/`precio`/`unit price`, `fee`/`comision`), no
duplica lo ya importado, y los movimientos que no son compra/venta (dividendos, intereses,
comisiones sueltas) **se cuentan y se reportan, pero no se importan**.

Esta es también la vía para la bolsa, y lo que lee la pestaña **Mi cartera** del panel.

### 3. Si acertaste — `invest-ll-track`

Una estimación se emite **congelada** y se evalúa después contra lo que pasó. Es lo único que
distingue medir de contarte un cuento: un backtest del LLM sobre el pasado no demuestra nada,
porque el modelo se entrenó con datos posteriores al periodo que simula.

```bash
uv run invest-ll-track issue --expected 335000 --basis "rotacion momentum 4 activos" --horizon 90
uv run invest-ll-track list        # estado de cada una
uv run invest-ll-track record --id b9897c2575f0bc58 --actual 312400
uv run invest-ll-track evaluate    # aciertos, fallos y sesgo acumulado
```

Hay una viva ahora mismo: 335.000 emitida el 25 de julio de 2026, vence el **23 de octubre de
2026**. La pestaña **Estimado vs real** del panel muestra lo mismo.

---

## Bolsa: el flujo manual

1. Trae el histórico: `uv run invest-ll-fetch AAPL --market equity --interval DAY_1 --start 2020-01-01 --end 2026-01-01`
2. Pide la propuesta en el panel (**Simular → Propuesta simple**) o por CLI con `invest-ll-propose`.
3. Compra en tu broker.
4. Registra lo que realmente pagaste, con su comisión: `invest-ll-portfolio add buy ...`, o importa
   el CSV del broker al final del mes.
5. Vigila con la pestaña **Vigilar**: alertas y triggers de retirada te proponen la salida exacta.
   Ejecutarla sigue siendo tuyo.

El paso 4 importa más de lo que parece: si registras el precio ideal en vez del que pagaste, las
métricas empiezan a mentirte y el sistema pierde su única promesa.

---

## Lo que **no** está probado contra un exchange real

Sé honesto con esto antes de meter dinero:

- Los cuatro cerrojos, la confirmación por orden y el manejo de estados raros están cubiertos por
  la suite, con un doble del exchange y **los sockets bloqueados**: una implementación que
  intentara salir a la red haría fallar los tests de forma ruidosa.
- Lo que eso significa: está verificado que el sistema **no manda nada cuando no debe**. Que una
  orden real se ejecute como esperas contra la API de Binance solo lo demuestra la etapa 2. No te
  la salgas.

## Antes de meter dinero

- [ ] Etapa 2 completada, y no solo con una orden que salió bien
- [ ] `scripts\testnet.ps1` termina en verde, con saldo ficticio visible
- [ ] Claves reales **distintas** de las de pruebas, sin permiso de retirada
- [ ] El arranque (`start.ps1 -SoloCheck`) te avisa en amarillo de que puede enviar órdenes reales
- [ ] Sabes qué hacer si sale `ESTADO DESCONOCIDO`: mirar el exchange, no reintentar a ciegas
- [ ] Empiezas con una cantidad cuya pérdida total te dé igual
- [ ] Tienes claro que el win rate no dice si esto funciona: mira expectancy y drawdown
