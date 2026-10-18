# Panel v5: menos lío, los bots en directo y las wallets

Marcos, 17/10/2026: «creo que puede llegar a ser algo confusa, hay que reestructurarla; además no
podemos ver los movimientos y las métricas de los agentes en tiempo real; y cambiar las conexiones
para conectar distintos exchanges o wallets como MetaMask o parecidos».

## 0. Las decisiones de Marcos

- **Siete secciones claras**, sin grupos ni pestañas que mezclen dos productos: Resumen, Bots,
  Estrategias, Operar, Mi plan, Conexiones, Ajustes.
- **Wallets: operar en Hyperliquid y ver saldos.** Conectas tu wallet del navegador (MetaMask,
  Rabby, Coinbase Wallet, Phantom…), firmas UNA vez para autorizar una *wallet agente* que puede
  operar en Hyperliquid pero **no puede retirar**, y ves lo que tienes en tus wallets. Nada de
  operar en DEX con una clave que pueda moverlo todo (más adelante, si acaso).
- Los bots de dinero real siguen **aparcados** (docs/panel-v4-real.md §3): v5 no los toca.

## 1. Por qué confunde hoy

- Dos productos mezclados: el **plan a largo plazo** (5 preguntas, Invertir, Cartera) y el
  **trading** (Bots, Operar, Estrategias a medida, Mercado, Laboratorio). «Estrategias» los mezcla
  con pestañas; la pastilla «Simulación» del menú es del plan, no de los bots.
- **Inicio** es la bienvenida al cuestionario: no dice cuánto dinero tienes ni qué está pasando.
- Los bots ya se actualizan cada ~2 s por el stream, pero **no se nota**: tarjetas largas como
  documentos, sin una lista de movimientos que vaya apareciendo, sin posiciones, órdenes
  pendientes ni métricas (aciertos, caída máxima, comisiones…).

## 2. El menú nuevo

| Sección | Ruta | Qué junta |
|---|---|---|
| **Resumen** | `/` | Tu panel de control en directo (§3). Si no hay nada: bienvenida con dos caminos, «Quiero un plan a largo plazo» y «Quiero poner un bot». |
| **Bots** | `/bots/` | Los bots en directo (§4), su ficha y desplegar. |
| **Estrategias** | `/estrategias/` | Plantillas de bots, A medida (biblioteca + Diseñar con Claude) y Laboratorio (probar, catálogo, investigación, estimado vs real, alertas de datos). |
| **Operar** | `/operar/` | La pantalla de exchange + Mercado (lista de mercados y precios; «Mercado a fondo» del Laboratorio). |
| **Mi plan** | `/plan/` | El largo plazo: Cuéntanos → Propuesta → Tu plan, Invertir y la Cartera del plan (lo que tienes, movimientos, frenos, pausa, órdenes enviadas). La pastilla de modo del plan («Simulación») vive aquí. |
| **Conexiones** | `/conexiones/` | Exchanges (lo de v4), **Wallets** (§5) y Conectar con Claude. |
| **Ajustes** | `/ajustes/` | Tema, datos, acerca de. |

- Las rutas viejas (`/invertir/`, `/cartera/`, `/mercado/`, `/laboratorio/`, `/mas/`,
  `/ajustes/#conexion`) **redirigen** a su sitio nuevo (export estático: redirección en cliente);
  ningún enlace del panel apunta ya a ellas.
- Móvil: barra inferior con Resumen, Bots, Estrategias, Operar y «Más» (Mi plan, Conexiones,
  Ajustes).
- Abajo del menú, siempre: el indicador «En directo» (Hyperliquid conectado o no) y, si algún día
  hay bots reales, el interruptor «Parar todo lo real».

## 3. Resumen: el panel de control

- **Todo tu dinero**, por modo y sin mezclar: ficticio (bots + cuenta de práctica), pruebas, real
  (bots, plan, exchanges y wallets conectados). Cada cifra con su hora. El servidor da los totales
  (el cliente no suma Decimals).
- **Bots en marcha**: tabla corta en directo (nombre, modo, valor, ganancia, hoy, mini curva, última
  operación «hace 12 s»). Las cifras que cambian parpadean un instante.
- **Ahora mismo**: los movimientos de todos los bots según ocurren (compras, ventas, avisos,
  paradas), lo nuevo arriba y resaltado.
- **Necesita tu atención**: bots parados por error o pausados, datos viejos, conexiones caídas.

## 4. Bots en directo (como las vaults de Hyperliquid)

- **Lista**: en escritorio una **tabla** ordenable (nombre, modo/exchange, estado, valor, ganancia
  en dinero y %, frente a mantener, hoy, peor caída, operaciones, mini curva, última operación); en
  móvil, tarjetas compactas. Encima, los totales por modo. Al lado (o debajo en móvil), **Ahora
  mismo**: el feed de movimientos de todos los bots.
- **Ficha** con la cifra grande viva y pestañas:
  - **Resumen**: curva frente a mantener y las métricas clave.
  - **Posiciones**: lo que tiene, a precio de ahora, con «si vendiera ahora».
  - **Qué hará después**: sus órdenes pendientes en llano (la rejilla: «comprará 0,95 SOL si baja
    a 101,0»; la periódica: «próxima compra de 20 USDC a las 23:00»; Bitcoin con freno: «mira de
    nuevo al cerrar la vela diaria, a las 02:00»). En pruebas/real, además, las órdenes abiertas
    en el exchange.
  - **Operaciones**: el feed en directo de este bot, cada una con su porqué.
  - **Métricas**: aciertos (% de operaciones cerradas con ganancia), factor de beneficio, ganancia
    media y pérdida media, peor caída, comisiones pagadas, ganancia realizada y sin realizar,
    tiempo dentro (exposición), operaciones por día y frente a mantener. Con pocas operaciones,
    lo dice («con 3 operaciones no hay métrica que valga»).
  - **Lo que ha pasado** (eventos) y **Cómo está ajustado**.
- API nueva: `GET /api/actividad?bot=&limite=` (los últimos movimientos) y el evento SSE
  `actividad` en `/api/vivo/stream` (cada movimiento nuevo al ocurrir); `metricas` y `pendientes`
  en la ficha del bot; totales por modo en `GET /api/bots`; `GET /api/resumen` para §3.

## 5. Wallets

- **Descubrir**: las wallets instaladas en el navegador con EIP-6963 (MetaMask, Rabby, Coinbase
  Wallet, Phantom, Brave…), y `window.ethereum` si no hay ninguna anunciada. Nada de WalletConnect
  por ahora (exige registrarse en un servicio externo).
- **Conectar** = solo la **dirección** (`eth_requestAccounts`). El panel nunca pide ni guarda la
  clave privada de tu wallet. Se guarda la dirección y el nombre de la wallet.
- **Saldos (solo lectura)**: el servidor lee, con RPC públicos y sin claves, el saldo nativo y de
  las stablecoins principales (USDC, USDT) en Ethereum, Arbitrum y Base, y lo que tienes en
  Hyperliquid (contado y perpetuos) con su API pública de info. Valorado en USD donde haya precio;
  si no, «sin precio». Con su hora.
- **Operar en Hyperliquid con tu wallet (wallet agente)**:
  1. El servidor crea una clave nueva de *wallet agente* y la guarda en el almacén de claves de
     Windows; nunca sale del equipo.
  2. Prepara la autorización `approveAgent` de Hyperliquid (EIP-712) para la red elegida
     (pruebas/real) y la cadena en la que esté tu wallet.
  3. Tu wallet la firma (`eth_signTypedData_v4`): una ventana de MetaMask, nada más.
  4. El servidor la envía a Hyperliquid y deja Hyperliquid conectado con la dirección de tu wallet
     y la clave del agente. A partir de ahí sigue el camino de v4 (pruebas → orden de prueba →
     real con «DINERO REAL»).
  - En llano y a la vista: la wallet agente **puede operar pero no puede retirar** tus fondos;
    para revocarla, desconectar borra su clave de este equipo y se explica cómo quitarla también
    en Hyperliquid.

## 6. Lo que no cambia

- El estilo (colores, tipografía, el castellano llano, «nada notifica ni empuja a operar»).
- Ninguna IA mueve dinero real por decisión propia; las claves no salen nunca; la API solo atiende
  a `localhost`; los errores en llano.
- Los bots siguen funcionando solo con el panel abierto.

## 7. Lo que pidió Marcos el 18/10

«Pon un botón para conectar Claude por suscripción para los planes; en Operar, ver los bots en
tiempo real sobre la gráfica y poder operar de verdad: Hyperliquid es el panel visual para operar
de verdad, y la práctica, otra pestaña aparte.»

- **Claude con tu suscripción**: `GET /api/claude` (lo que dice `claude auth status`: si hay
  sesión, con suscripción o con clave de la API, y el plan; nada que identifique la cuenta) y
  `POST /api/claude/conectar` (abre en este equipo `claude auth login --claudeai`). Tarjeta arriba
  de Conexiones y, en la barra de Mi plan, «Claude · Max» o el botón para conectarlo.
- **Operar en dos pestañas**: Hyperliquid (`/operar/`, para operar de verdad) y Práctica
  (`/operar/practica/`, la cuenta ficticia), más Mercados. En las dos, los bots que operan con la
  moneda elegida encima de la gráfica: una flecha por compra o venta (las 40 últimas) y líneas
  discontinuas con sus órdenes preparadas más cercanas al precio.
- **Operar de verdad** (`/api/operar/{exchange}`): órdenes de contado manuales con la cuenta
  conectada, a la red activa (pruebas o real). Cada una: la red que se veía tiene que ser la
  activa; la cantidad, tecleada; los cerrojos de activación, comprobados otra vez; id de cliente
  (sin duplicados); estado desconocido sin adivinar; y al registro de órdenes (en pruebas, la
  evidencia para activar real). Sin apalancamiento: los perpetuos no se operan desde aquí.
- **Wallets** (§5), hechas: EIP-6963 en el navegador, solo la dirección en `config/wallets.json`,
  saldos de solo lectura y la wallet agente de Hyperliquid (`approveAgent` con el formato del SDK
  oficial 0.24.0; la firma se comprueba antes de enviar nada; la clave del agente, al almacén de
  claves como la de cualquier exchange). Dependencia nueva: `eth-account`.
