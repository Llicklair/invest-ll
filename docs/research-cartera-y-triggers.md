# Poner orden: cartera real, panel denso y retirada segura

**Fecha**: 2026-07-26 · **Para**: decidir la reorganización de INVEST LL (feature 004)
**Research**: gestores de cartera (Ghostfolio, Portfolio Performance, Wealthfolio, Snowball),
dashboards densos (CoinMarketCap, Finviz, TradingView, CoinGecko), bots con salidas automáticas
(Freqtrade, OctoBot, Jesse, 3Commas, Composer).

---

## 1. La pieza que falta y sostiene todo: el ledger de cartera

Hoy INVEST LL no sabe **qué tienes**. Las posiciones se declaran a mano en cada comando
(`--holding GLD:10:180`). Todo lo que pides —ver lo invertido, ver lo retirado, triggers— necesita
que la cartera sea un dato del sistema, no un argumento.

**Cómo lo hacen todos los gestores serios, sin excepción**: un **ledger inmutable de
transacciones** del que las posiciones se DERIVAN. Nunca se edita una posición a mano.

- Ghostfolio: actividades `BUY, SELL, DIVIDEND, FEE, INTEREST...` con fecha, símbolo, cantidad,
  precio, comisión, cuenta.
- Portfolio Performance (el modelo más claro para nosotros): la vista **Trades** empareja compras
  con ventas. Posición abierta = quedan títulos; **cerrada = los títulos llegan a 0**, y entonces
  el P&L pasa de "no realizado" (valoración a mercado) a **realizado** (lo que de verdad pasó).
  Cada trade cerrado lleva: valor de entrada, de salida, días en cartera, y beneficio neto.
- Wealthfolio añade `DEPOSIT/WITHDRAWAL` (dinero que entra/sale del sistema) — el cash es una
  cuenta de primera clase, no un residuo.

**Adaptación**: `portfolio/ledger.py` con actividades BUY/SELL/DEPOSIT/WITHDRAWAL/FEE en JSONL
append-only (mismo patrón que `ExecutionLedger` y `ForecastStore`). Las órdenes de
`invest-ll-execute` anotan su actividad automáticamente; lo que ya tengas en el bróker entra por
CSV (formato Ghostfolio: `Date,Symbol,Type,Quantity,Unit Price,Fee,Currency`). De ahí se derivan:
posiciones abiertas (cantidad, coste medio, P&L no realizado) y cerradas (P&L realizado, motivo,
días). Responde exactamente a "qué activos tengo y si alguno ha sido retirado".

## 2. Panel denso tipo CoinMarketCap — copiando la forma, no el anzuelo

Columnas literales de CMC: `# | Nombre | Precio | 1h% | 24h% | 7d% | Cap | Volumen | Supply |
sparkline 7d`. Cómo consiguen densidad sin ruido:

- **Color SOLO en las celdas de variación** (verde/rojo con ▲▼). Precio y volumen en tinta neutra.
- **Una sparkline por fila** como única imagen, sin ejes, coloreada como el 7d.
- **Ordenación por columna** en vez de vistas separadas.

**Nuestra tabla**: `Activo | Precio | 24h% | 7d% | 30d% | YTD% | desde máximo | sparkline`.
Cambios deliberados frente a CMC:

- **Fuera el 1h%**: ninguna decisión de aportación cambia por la última hora. El propio research
  lo cataloga como mecánica de enganche.
- **"Desde máximo" promovida a columna** (CMC la esconde en el detalle; CoinGecko la trata como
  dato de primera clase con `ath_change_percentage`). Es la columna más honesta que existe.
- **Descartado el catálogo de anzuelos de CMC**, con nombre y apellido: Índice de Miedo y
  Codicia, temporada de altcoins, Tendencias, Más visitados, Ganadores/perdedores del día,
  sentimiento de comunidad, recompensas. Ninguno informa una aportación periódica; todos existen
  para que vuelvas a abrir la app.

## 3. Las cuatro formas de invertir — y una sola puerta de salida al mundo

Tu lista: LLM por CLI dentro / LLM desde fuera (esta conversación) / botón simple / bot
determinista. Las cuatro **ya casi existen** y la arquitectura correcta es que ninguna ejecute
nada: todas producen una PROPUESTA, y solo `invest-ll-execute` —con su confirmación escribiendo la
cantidad— toca el mundo real.

| Vía | Estado | Qué falta |
|---|---|---|
| LLM dentro (CLI) | `invest-ll-generate/compare/propose` | nada |
| LLM fuera (yo, u otro agente) | `--json` en los 8 comandos | nada |
| Botón simple | — | pestaña Invertir: botón → propuesta + comando exacto listo para copiar |
| Bot determinista | momentum ya evaluable | exponerlo en esa misma pestaña |

El botón del panel **muestra el comando, no lo ejecuta**. Freqtrade y OctoBot arman el bot y este
opera solo; nuestro Principio I dice confirmación humana por orden, y el panel es de solo lectura
respecto al dinero. Esa diferencia es deliberada y no negociable.

## 4. Retirada segura: triggers que PROPONEN, no que disparan

Lo que hacen los bots reales:

- **Freqtrade**: cinco vías de salida (ROI por tiempo, stop fijo, trailing, señales, callbacks) y
  "**protections**" que NO fuerzan salidas sino que **bloquean entradas**: StoplossGuard (N stops
  seguidos → parar), MaxDrawdown (caída máxima → parar), CooldownPeriod (no reentrar recién
  salido). Una vez armado opera solo, sin confirmación por operación.
- **3Commas**: formularios sin código — hasta 4 take-profits, trailing, stop a breakeven.
- **Patrón universal de kill switch**: TODOS separan "dejar de entrar" de "liquidarlo todo", y el
  pánico ignora deliberadamente las condiciones de beneficio (`/stopentry` vs `/forceexit all`;
  "Panic Sell"; "Sell All").

**Adaptación — triggers armados sobre el ledger, ejecución siempre humana**:

- Un trigger es una regla persistida: `si la posición GLD cae >15% desde mi entrada` / `si la
  caída supera la peor simulada` / `si llevo N días en pérdidas`. Se evalúan con el motor de
  alertas que ya existe (`invest-ll-triggers check`, y el panel las enseña).
- Cuando un trigger salta, produce **la orden de salida exacta lista para confirmar** — símbolo,
  cantidad, y el comando `invest-ll-execute` completo. Un paso del humano, no cero.
- **Kill switch en dos niveles**, copiando la distinción universal: "no proponer más entradas"
  (un flag local) y "liquidar todo" (`--liquidate-all`, que propone las N órdenes de venta juntas
  y las confirma una a una).
- **Las "protections" de Freqtrade, adaptadas al operador**: son la misma idea que nuestro
  contador de sobreajuste — límites que te protegen de ti mismo. Un CooldownPeriod local ("has
  vendido GLD hace 3 días, reentrar ahora son comisiones") encaja con todo lo medido aquí.

**La advertencia que el research no cambia**: el stop-loss automático, medido sobre 21 años y 84
decisiones reales, **no mejoró nada** (docs/experimento-stop-loss.md). Los triggers de este diseño
no prometen alpha: son protección del operador — límites visibles, con el humano dentro — no una
estrategia de salida superior. Por eso proponen y no disparan.

## Orden de construcción

| # | Pieza | Por qué primero |
|---|---|---|
| 1 | **Ledger de cartera** (actividades → posiciones abiertas/cerradas, import CSV) | Todo lo demás lee de aquí |
| 2 | **Pestaña Mi cartera** (abiertas con P&L no realizado, cerradas con realizado) | "Qué tengo y qué retiré" |
| 3 | **Panorama denso** (tabla CMC-style con sparklines y "desde máximo") | Muchos datos en pantalla |
| 4 | **Pestaña Invertir** (botón → propuesta LLM o momentum + comando listo) | Las 4 vías visibles |
| 5 | **Triggers** (reglas armadas + check + kill switch de dos niveles) | Necesita el ledger vivo |

Cada pieza es committeable por separado y deja las gates en verde.
