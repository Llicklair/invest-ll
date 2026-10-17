# Panel v2: invertir sin saber de inversiones

Especificación del rediseño del panel (FastAPI + Next.js), decidido el 2026-10-17. Sustituye a la
interfaz que trasladaba una a una las pestañas de Streamlit: aquella era **un catálogo de
herramientas**; esta es **un camino** para alguien que tiene ahorros, no sabe qué es un ETF ni un
drawdown, y quiere saber qué hacer con su dinero — y hacerlo de verdad, no solo simularlo.

Los principios de INVEST LL no cambian: el sistema no miente sobre sus resultados, cada orden se
confirma tecleando la cantidad, nada notifica ni gamifica, y toda cifra lleva su fecha. Lo que
cambia es **a quién se le habla y en qué orden**.

---

## 1. La persona

**Laura, 34 años.** Tiene 6.000 € en la cuenta corriente y puede apartar 200 € al mes. Ha oído que
"hay que invertir" y que "el bitcoin ha subido mucho". No sabe la diferencia entre un fondo y una
acción. Le dan miedo dos cosas: perder dinero y hacer el ridículo con un botón que no entiende.

Lo que necesita, en orden:
1. **Saber qué hacer** con *su* dinero, no leer sobre estrategias.
2. **Entender el riesgo en euros**: "en el peor momento, tus 1.000 € llegaron a valer 350 €" se
   entiende; "max drawdown −65%" no.
3. **Hacerlo** sin miedo a equivocarse: cada paso dice qué va a pasar antes de que pase.
4. **Ver cómo va** sin obsesionarse: una cifra grande, con su fecha, y qué toca hacer (o que no toca
   nada).

El usuario experto (Marcos) sigue teniendo todo lo de antes, en **Laboratorio**.

## 2. Principios de producto

1. **Una pregunta por pantalla, un botón principal por pantalla.** Lo demás, secundario o plegado.
2. **El riesgo se dice en euros y con el peor caso al lado del resultado**, siempre. Nunca una
   rentabilidad sin su peor momento ni sin la comparación con "dejarlo quieto".
3. **Lenguaje llano.** Jerga prohibida en la interfaz principal; si un término hace falta, va con su
   explicación (`¿Qué es esto?`). Diccionario obligatorio:

   | No digas | Di |
   |---|---|
   | drawdown, max drawdown | peor caída, en el peor momento |
   | P&L no realizado | lo que ganas (o pierdes) si vendieras hoy |
   | P&L realizado | lo que ganaste (o perdiste) al vender |
   | valoración | lo que vale hoy |
   | fricción, slippage | comisiones y costes |
   | CAGR | cuánto creció de media al año |
   | exposición | tiempo invertido (el resto, en liquidez) |
   | rebalanceo | ajustar el reparto |
   | ledger | tu registro de movimientos |
   | backtest | prueba sobre el pasado |
   | forward test | prueba en real desde (fecha) |
   | ticker | — (nombre del activo: "Bitcoin", "Bolsa de EE.UU.") |

4. **El pasado no es una promesa, y se dice donde se mira**, no en un pie de página: cada cifra
   histórica dice "si hubieras empezado en…", y el comparador deja cambiar el año de inicio para
   que se vea cuánto depende de la suerte de la fecha.
5. **El dinero real es un camino de tres pasos** (simulación → pruebas → real) y el panel acompaña
   cada uno. Ningún cerrojo de `docs/operar-de-verdad.md` se relaja.
6. **Nada empuja a operar.** Sin notificaciones, sin rachas, sin confeti, sin "ganadores del día".
   "No toca hacer nada" es un estado bueno y se dice así.

## 3. Mapa

Escritorio (≥1024 px): barra lateral izquierda fija. Móvil: barra inferior con 5 iconos.

| Sección | Pregunta que responde | Contenido |
|---|---|---|
| **Inicio** | ¿Cómo va mi dinero y qué tengo que hacer? | Tu dinero hoy, qué toca hacer, tu plan, avisos |
| **Estrategias** | ¿Cómo invierto? | Cuestionario → recomendación → comparar → empezar plan |
| **Invertir** | Hazlo | Qué toca hoy (Binance y tu bróker), orden manual, conexión |
| **Cartera** | ¿Qué tengo? | Lo que tienes, lo que vendiste, movimientos, protección |
| **Más** | | Mercado · Laboratorio · Ajustes |

**Pregunta** (el chat con Claude) no es una sección: es un botón flotante en todas las pantallas
que abre un panel lateral. Gasta cuota y lo dice.

El **modo** (Simulación / Pruebas / Dinero real) va siempre visible arriba como una píldora; en
dinero real, además, una franja fina de color en todo el borde superior.

## 4. Pantallas

### 4.1 Inicio

**Sin plan (primera vez):** bienvenida a pantalla completa.
> **Hola. Vamos a ver qué hacer con tu dinero.**
> Cinco preguntas, sin jerga. Al final verás qué te proponemos, cuánto habría crecido y —igual de
> importante— cuánto habría llegado a bajar.
> [Empezar] · (secundario) "Ya sé lo que quiero → Estrategias"

**Con plan:**
1. **Tu dinero hoy** — cifra grande (`GET /api/inicio`): valor de lo que tienes; debajo, "Has
   puesto X € · +Y € (+Z %)" con color y signo; "precios del cierre del 16 oct". Si la cartera es la
   de pruebas, la cifra va con la etiqueta "dinero ficticio".
2. **Qué toca hacer** — tarjetas de `GET /api/plan/hoy` (máx. 3, "ver todo" lleva a Invertir). Si no
   hay nada: "No toca hacer nada. Tu próxima aportación es el 1 de noviembre." (estado bueno).
3. **Tu plan** — una fila por parte (estrategia, cuánto, cuánto vale), con enlace a cambiarlo.
4. **Avisos** — solo si los hay (datos desactualizados, pausa, ledger con problemas).
5. **El mercado, en una línea** — 3-4 activos con nombre llano y su variación del mes.

### 4.2 Estrategias

Un asistente en tres pasos, con barra de progreso.

**Paso 1 — Cuéntanos** (`Perfil`), una pregunta por pantalla en móvil, todas juntas en escritorio:
1. ¿Con cuánto quieres empezar? (importe; puede ser 0)
2. ¿Cuánto podrías añadir cada mes? (importe; puede ser 0)
3. ¿Cuándo vas a necesitar este dinero? — En menos de 2 años · Entre 2 y 5 · Entre 5 y 10 · En más
   de 10
4. Imagina que lo que inviertes cae a la mitad en unos meses. ¿Qué harías? — Vendería para no
   perder más · Esperaría a que se recupere · Aprovecharía para poner más
5. ¿Quieres algo de criptomonedas? — No · Un poco · Sí

**Paso 2 — Te proponemos** (`POST /api/estrategias/recomendar` + `POST /api/estrategias/simular`):
- Arriba, la **recomendación**: el reparto (p. ej. "90 % Equilibrada · 10 % Bitcoin con freno") con
  un "por qué" de 2-3 frases que citan las respuestas ("Porque lo necesitarás en más de 10 años y
  dijiste que esperarías a que se recupere"), y sus avisos. Si `no_invertir`, lo primero que se ve
  es eso: "Para dinero que necesitas en menos de 2 años, ninguna de estas estrategias es buena
  idea: en su peor momento cayeron entre un 10 % y un 80 %. Una cuenta remunerada o un depósito
  encajan mejor." (y aun así se puede seguir mirando).
- Debajo, **el gráfico con tus números**: línea de "lo que habrías tenido" de cada estrategia
  propuesta frente a "lo que habrías puesto" (escalón), desde el año elegido. Selector "Empezar
  en": 2018 · 2019 · 2020 · 2021 · 2022 · 2023. Texto bajo el gráfico: "Si hubieras empezado en
  2021, justo antes de una caída, el resultado sería muy distinto: prueba a cambiar el año."
- **Tarjetas de estrategia** (todas las del catálogo que no son de laboratorio; las recomendadas
  primero y marcadas). Cada tarjeta:
  - Nombre llano y una frase. Medidor de riesgo de 5 segmentos con su palabra (Tranquila · Suave ·
    Moderada · Movida · Muy movida).
  - "Con tus números desde 2018: **tendrías 14.200 €** (pusiste 9.800 €)".
  - "En el peor momento **llegó a valer 6.100 €**, en marzo de 2020" (siempre, al mismo tamaño que
    el resultado).
  - Quién lo hace: "Automático en Binance (tú confirmas cada orden)" o "Lo compras tú en tu
    bróker; te decimos qué y cuánto".
  - Evidencia: chip "Probada sobre el pasado" o "En prueba real desde el 15 oct 2026".
  - [Ver cómo funciona] abre una hoja con: cómo funciona en 3 pasos, para quién es, sus avisos, el
    gráfico a 10.000 € desde el principio de los datos y sus cifras en llano.
- Botón secundario **Comparar**: elegir 2-4 tarjetas y verlas en el mismo gráfico y en una tabla de
  4 filas en llano (tendrías · pusiste · peor momento · meses por debajo de lo puesto).

**Paso 3 — Tu plan** (`PUT /api/plan`): importes por estrategia (precargados del reparto),
día del mes para aportar (1-28), resumen en una frase ("Cada día 1 pondrás 180 € en Equilibrada y
20 € en Bitcoin con freno"), y [Guardar mi plan] → lleva a Invertir, a "Qué toca hoy".

### 4.3 Invertir

1. **Qué toca hoy** (`GET /api/plan/hoy`), agrupado:
   - **En Binance (automático)**: tarjeta por orden — "Comprar Bitcoin · 0,00123 BTC ≈ 100 USDT",
     el porqué en una frase ("Bitcoin lleva 30 días subiendo: tu estrategia dice estar dentro"), y
     [Revisar y confirmar]. En simulación la tarjeta se ve igual pero el botón es "Conectar Binance
     para hacerlo de verdad".
   - **En tu bróker (tú)**: lista de la compra — "Compra unos 108 € de un ETF del S&P 500" con el
     equivalente que se compra desde España (`equivalente`), precio de referencia y su fecha, y
     [Ya lo he comprado] → formulario precargado (cantidad, precio real, comisión, fecha) que lo
     anota en tu registro (`POST /api/plan/hoy/{id}/hecho`).
   - Si no hay nada: el mismo estado bueno que en Inicio.
2. **Confirmar una orden** (hoja modal, 3 estados):
   - Resumen: qué, cuánto, a qué precio aproximado, en qué modo. En dinero real, recuadro rojo.
   - "Escribe **0.00123** para confirmar" — campo sin pegar; el botón se activa solo cuando
     `POST /api/ordenes/comprobar` dice `puede`.
   - Resultado (`POST /api/ordenes`): ejecutada / parcial / rechazada / **desconocida** (y entonces:
     "Compruébalo en Binance antes de volver a operar"). Las órdenes ejecutadas en pruebas o real
     pasan solas a la cartera de ese modo.
3. **Orden manual** (plegado, "Avanzado").
4. **Conexión** — tarjeta con el modo actual y [Cambiar] → Ajustes · Conexión.

### 4.4 Cartera

- **Lo que tienes**: una fila por activo con nombre llano, "tienes 0,012 BTC · valen 980 € · +80 €
  si vendieras hoy" y la fecha del precio.
- **Lo que ya vendiste**: "ganaste 190 € con Oro (ene–mar 2026)".
- **Movimientos**: lista cronológica (`GET /api/cartera/movimientos`), y [Anotar un movimiento]
  (compra/venta/ingreso/retirada; dice que NO envía nada).
- **Protección** (lo que antes era Vigilar/triggers): "Frenos" — "Avísame con una propuesta de
  venta si pierdo más de un 15 % desde que compré" — y la pausa de compras con su motivo.
- **Órdenes enviadas** (plegado).
- En modo pruebas, la cartera que se ve es la de pruebas, con la etiqueta "dinero ficticio".

### 4.5 Más

- **Mercado**: buscador y lista con nombres llanos ("Oro", "Bolsa de EE.UU.", "Bitcoin"), precio
  con fecha, variación del mes y del año, y "desde su máximo"; hoja con gráfico al pinchar.
  Cotizaciones al momento con un botón (foto con hora). Actualizar históricos.
- **Laboratorio** (para quien sabe): todo lo del panel anterior — Probar estrategias (las cuatro
  vías: propuesta, aportaciones/rotación, un activo, LLM), Investigación (cartera prerregistrada,
  prueba hacia delante, último estudio), Estimado vs real, Alertas de datos. Los costes
  (comisión/slippage) se configuran aquí, no en la cabecera.
- **Ajustes**: Conexión con Binance (el asistente de 4.6), tema claro/oscuro/sistema, datos
  (actualizar históricos), acerca de.

### 4.6 Conectar Binance (Ajustes · Conexión)

Un camino de tres etapas con su estado (`GET /api/conexion`):

1. **Pruebas** — qué es ("dinero ficticio, órdenes de verdad: aprendes sin pagar"), enlace a
   `testnet.binance.vision` (entrar con GitHub, crear clave **HMAC-SHA256**), pegar clave y secreto
   (`PUT /api/conexion/claves/pruebas`), [Probar conexión] (`POST /api/conexion/probar/pruebas` →
   saldo ficticio) y [Usar modo pruebas] (`PUT /api/conexion/modo`).
2. **Haz una orden de prueba** — se marca sola cuando hay una orden de pruebas ejecutada en el
   registro (es la evidencia de que la etapa se hizo, no una casilla que se marca a mano).
3. **Dinero real** — permisos de la clave (lectura y spot; **nunca retirada**; IP fija si se puede),
   pegar claves reales (tienen que ser distintas de las de pruebas), probar (saldo real) y
   [Activar dinero real] con confirmación tecleada: escribir `DINERO REAL`.

Los cuatro cerrojos se ven como una lista con su estado. Las claves se guardan en el **almacén de
credenciales de Windows** (keyring), nunca en el repositorio ni en un fichero; se pueden borrar. Si
las variables de entorno de `docs/operar-de-verdad.md` están puestas, mandan ellas y el panel lo
dice ("configurado desde el entorno").

## 5. Catálogo de estrategias

Seis para el camino principal y el resto solo en Laboratorio. Las cifras **no se escriben a mano**:
salen de ejecutar cada estrategia sobre los datos descargados (`historico` del catálogo). Las de
abajo son las del estudio del 2026-10-16 (`docs/quant-research.md`) y sirven para validar.

| Clave | Nombre | Mercado / ejecución | Riesgo | Qué es (motor) | Peor caída (estudio) |
|---|---|---|---|---|---|
| `bolsa-equilibrada` | Equilibrada | bolsa / tu bróker | 3 Moderada | 60 % SPY + 40 % IEF, mensual | −32 % |
| `bolsa-prudente` | Prudente con freno | bolsa / tu bróker | 2 Suave | Paridad de riesgo + filtro de tendencia, 8 ETF | −10 % |
| `bolsa-eeuu` | Bolsa de EE.UU. | bolsa / tu bróker | 4 Movida | Mantener SPY | −52 % |
| `btc-freno` | Bitcoin con freno | cripto / Binance | 4 Movida | TrendAsset BTC 30 días, semanal, 7 tramos | −65 % |
| `cripto-cesta-freno` | Cesta cripto con freno | cripto / Binance | 4 Movida | Etapa 2: MarketFilter(momentum) + banda 2 % | −47 % |
| `btc-mantener` | Bitcoin y olvidarse | cripto / Binance | 5 Muy movida | Mantener BTC | −81 % |

Avisos obligatorios por estrategia (en la tarjeta y en la hoja):
- `cripto-cesta-freno`: "Se diseñó después de ver los primeros resultados: su historia es más
  bonita de lo que probablemente será su futuro." y "Hace muchas operaciones: los impuestos se
  comen una parte visible."
- `btc-freno`: "Pasa casi la mitad del tiempo fuera, en liquidez: habrá años en que lo haga peor
  que tener Bitcoin quieto."
- `bolsa-prudente`: "Cae mucho menos, pero también crece aproximadamente la mitad."
- `btc-mantener`: "Ha llegado a perder más del 80 %. Solo con dinero que puedas olvidar."
- Todas las de bolsa: "Las cifras usan fondos de EE.UU.; desde España se compran sus versiones
  europeas (UCITS), que se comportan casi igual." y "Sin contar el cambio euro-dólar."
- Todas las de cripto: "En dólares digitales (USDT)."

Equivalentes para "Qué toca hoy" en tu bróker (`equivalente`): describe el tipo de fondo y pon un
ejemplo; **ISIN solo donde no hay duda**:
- SPY → "un ETF UCITS del S&P 500 (p. ej. iShares Core S&P 500, ISIN IE00B5BMR087)"
- IEF → "un ETF UCITS de bonos del Tesoro de EE.UU. a 7-10 años"
- GLD → "un ETC de oro físico (p. ej. iShares Physical Gold, ISIN IE00B4ND3602)"
- EEM → "un ETF UCITS de mercados emergentes (p. ej. iShares Core MSCI EM IMI, ISIN IE00BKM4GZ66)"
- El resto: la categoría en llano ("un ETF UCITS de bolsa de países desarrollados fuera de EE.UU.",
  "de bonos del Tesoro de EE.UU. a más de 20 años", "de materias primas", "inmobiliario
  estadounidense (REIT)", "de bonos del Tesoro a corto plazo"), sin ISIN.

En Laboratorio, además: la cartera prerregistrada, la rotación de antes (marcada **retirada**, con
el porqué: "sin el sesgo de supervivencia se fue casi a cero"), y las demás del estudio de ETF.

## 6. La recomendación (reglas, a la vista)

Reglas fijas y explicables (`POST /api/estrategias/recomendar`); el "por qué" cita las respuestas.

1. **Horizonte < 2 años** → `no_invertir = true` (se explica) y, si aun así quiere seguir,
   `bolsa-prudente` 100 %, sin cripto.
2. **Bolsa** según la reacción a una caída a la mitad:
   - vendería → `bolsa-prudente`
   - esperaría → `bolsa-equilibrada`
   - pondría más → `bolsa-eeuu` si el horizonte es de más de 5 años; si no, `bolsa-equilibrada`.
3. **Cripto** (nunca más del 15 %; si vendería ante una caída, como mucho 5 %):
   - no → 0 %
   - un poco → 5 % en `btc-freno`
   - sí → 10 % en `btc-freno` (15 % si pondría más ante una caída y el horizonte > 5 años)
4. El reparto se aplica al importe inicial y a la aportación mensual. Alternativas: las otras
   estrategias del mismo mercado.
5. Avisos siempre: "Esto sale de reglas fijas aplicadas a tus respuestas, no de predecir el
   mercado." y, si hay cripto: "Limitamos la cripto porque, incluso con freno, ha llegado a caer
   un 65 %."

## 7. Qué toca hoy (cálculo)

Un plan tiene como mucho una estrategia de bolsa y una de cripto (`PUT /api/plan` rechaza más).

- **Cripto (Binance)**: dinero de la parte = inicial + mensual × aportaciones vencidas desde que se
  creó el plan. Peso objetivo de hoy = el de la estrategia tras el último cierre
  (`quant.paper.current_targets`). Lo que hay = las posiciones de cripto de la cartera **del modo
  activo**, valoradas al último cierre. Una orden por moneda cuya diferencia supere 10 USDT;
  cantidades redondeadas al paso del exchange cuando se conozca (si no, 6 decimales). Ventas
  antes que compras.
- **Bolsa (tu bróker)**: el día del mes del plan (o después, si este mes aún no se anotó ninguna
  compra de esa parte), una línea por fondo con importe = aportación × peso objetivo (la primera
  vez, también el inicial). Cantidad aproximada = importe / último cierre. No se ajusta el
  reparto con ventas: aportar a los pesos objetivo es más barato y casi igual de bueno.
- Si faltan datos para calcular algo, la acción no se inventa: aparece en `avisos` diciendo qué
  falta (p. ej. "Descarga los datos de Binance: uv run invest-ll-quant download").

## 8. Sistema visual

Cálido, sereno y legible; nada de azul corporativo genérico ni de rojo/verde de casino.

**Color** (tokens CSS; modo oscuro con los mismos nombres):

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--fondo` | `#F6F3EE` | `#121311` | Fondo de la app (marfil cálido) |
| `--superficie` | `#FFFFFF` | `#1B1C19` | Tarjetas |
| `--superficie-2` | `#EFEBE4` | `#24251F` | Zonas hundidas, chips |
| `--tinta` | `#1D1C1A` | `#EEEBE4` | Texto |
| `--tinta-suave` | `#625E56` | `#A9A59C` | Texto secundario |
| `--linea` | `#E2DDD3` | `#33342E` | Bordes |
| `--marca` | `#23395B` | `#9DB7DD` | Acción principal, enlaces (azul tinta) |
| `--marca-suave` | `#E3E9F2` | `#22303F` | Fondos de acento |
| `--destaque` | `#C98A2B` | `#E0B060` | Recomendado, foco (azafrán) |
| `--sube` | `#2F7D5B` | `#6FC39C` | Ganancias (siempre con "+" y palabra) |
| `--baja` | `#B5543A` | `#E58B70` | Pérdidas (siempre con "−" y palabra) |
| `--real` | `#B23A3A` | `#E07070` | Dinero real: franja superior y recuadros |
| `--pruebas` | `#B7791F` | `#E0A85A` | Modo pruebas |

Riesgo 1-5: `#5E8FB8` · `#6FA39A` · `#C9A13B` · `#D27D3E` · `#B5543A`.
Las series de los gráficos siguen la skill `dataviz` (paleta validada, ambos temas).

**Tipografía**: titulares y cifras grandes en **Fraunces** (serif suave, `next/font/google`,
alojada en el build); interfaz en **Inter**. Cifras siempre con `font-variant-numeric:
tabular-nums`. Formato español: `1.234,56 €`, `+4,6 %`, fechas "16 oct 2026".

**Forma**: tarjetas con radio 16 px y sombra muy suave; botones de 48 px de alto, uno primario
relleno por pantalla; espacio generoso (múltiplos de 8). Iconos de trazo fino (lucide).

**Componentes base**: `CifraGrande` (valor + variación + fecha), `MedidorRiesgo`,
`TarjetaEstrategia`, `TarjetaAccion`, `HojaLateral`/`HojaInferior` (móvil), `Asistente` (pasos con
progreso), `QueEsEsto` (glosario plegable), `EstadoVacio` (bueno, no triste), `PildoraModo`,
`ConfirmacionTecleada`.

**Tono**: tú; frases cortas; primero lo que significa para ti, luego el dato. Nada de
exclamaciones ni de emojis.

## 9. Contrato (lo nuevo de la API)

Detalle en `src/invest_ll/api/schemas.py` y los routers; el OpenAPI en `web/openapi.json`.

| Ruta | Para |
|---|---|
| `GET /api/inicio` | Tu dinero hoy, plan resumido, acciones pendientes, avisos, mini mercado |
| `GET /api/estrategias` | Catálogo con descripciones llanas y cifras históricas calculadas |
| `POST /api/estrategias/simular` | Tus números (inicial + mensual desde un año) en 1-4 estrategias |
| `POST /api/estrategias/recomendar` | Perfil → reparto recomendado, por qué y avisos |
| `GET/PUT/DELETE /api/plan` | El plan guardado (`plan/plan.json`, fuera de git) |
| `GET /api/plan/hoy` | Qué toca hacer hoy |
| `POST /api/plan/hoy/{id}/hecho` | Anotar una compra hecha en tu bróker |
| `GET /api/cartera/movimientos` | El registro de movimientos, legible |
| `GET /api/conexion` | Modo, claves guardadas por red, cerrojos, qué falta para cada modo |
| `PUT/DELETE /api/conexion/claves/{red}` | Guardar/borrar claves (almacén de Windows) |
| `POST /api/conexion/probar/{red}` | Probar claves: saldo o error en llano. No envía órdenes |
| `PUT /api/conexion/modo` | Cambiar de modo (real exige cerrojos + "DINERO REAL") |
| `GET /api/saldo` | Saldo del exchange en el modo activo (409 en simulación) |

Cambios en lo existente: el modo que usa la API es el **efectivo** (entorno si está puesto; si no,
lo configurado en el panel); `POST /api/ordenes` importa a la cartera del modo (real →
`portfolio/`, pruebas → `portfolio-pruebas/`) lo que se ejecute; y `GET /api/cartera` muestra la
cartera del modo activo.

## 10. Lo que no se toca

- Los cuatro cerrojos de `live/mode.py` y la confirmación tecleada (`dashboard/ordenes.py`).
- La línea de comandos: sigue leyendo solo del entorno.
- Ninguna ruta envía órdenes salvo `POST /api/ordenes`.
- La API solo atiende a `localhost`.
