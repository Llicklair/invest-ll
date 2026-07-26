# Horizontes: cripto activa, bolsa a largo

Decidido el 2026-07-26 a partir de lo medido, no de una preferencia. Este documento existe para
que la decisión no se re-litigue cada vez y para que las cifras que la sostienen se puedan
comprobar.

| | Cripto | Bolsa |
|---|---|---|
| **Horizonte** | Semanal (mira 30 días atrás) | Meses |
| **Enfoque** | Rotación activa entre 4 monedas | Comprar y mantener, o aportaciones periódicas |
| **Ejecución** | Real posible vía Binance/ccxt | Manual en tu bróker; el sistema propone |

**No se mezclan nunca en la misma cartera.**

---

## Por qué en bolsa no se opera

Siete estrategias sobre 8 ETFs y 21 años de histórico. Ninguna batió a no hacer nada:

| Estrategia | Neto | Semanas en verde |
|---|---|---|
| **Comprar y mantener** | **+69.207** | — |
| Rotación 252d | +48.654 | 53,9% |
| Precio vs media 200 | +34.625 | 40,5% |
| Rotación 126d | −1.809 | 50,4% |

Sobre 10.000 de capital. La rotación de 126 días **perdió dinero pagando 14.279 en comisiones**, y
la que más operaba (600 operaciones) fue de las peores. En bolsa el enemigo no es elegir mal el
activo: es la fricción de operar.

## Por qué en cripto sí

Misma medición sobre 4 monedas. La rotación batió a comprar y mantener, y —lo que importa— la
configuración elegida **solo con datos hasta 2024** también ganó en el tramo que no se usó para
elegirla: **+3.063 mientras el mercado caía entre un 20% y un 62%**.

**El hallazgo no es un parámetro, es el filtro.** Con `min_return=0` (quedarse fuera del mercado si
ningún activo sube) las tres configuraciones ganadoras ganaron dinero; **todas las variantes sin
filtro lo perdieron**, con cualquier lookback. Se sostiene porque tiene una razón: lo que salvó el
capital no fue acertar la moneda, fue no estar cuando todo caía.

## Por qué semanal y no diaria

La cadencia casi no cambia el resultado. Medianas de resultado neto por cadencia, cruzando cinco
lookbacks:

| Cadencia | 1d | 3d | 7d | 14d | 30d |
|---|---|---|---|---|---|
| **Mediana** | 399 | 385 | 395 | **579** | 146 |

Entre diario y quincenal la diferencia es ruido. La mensual sí es peor: reacciona tarde. Así que la
cadencia se elige por lo que **sí** es medible:

- **Fricción**: semanal son 10,2 operaciones al año; diaria, 24,3. Binance cobra **0,1% por
  operación** (verificado contra su API), y en la mejor configuración la fricción ya se lleva el
  **41,7%** de lo que se habría ganado sin costes.
- **Esfuerzo y error humano**: cada orden es un comando con la cantidad tecleada a mano.

> Un aviso sobre un espejismo: en un barrido apareció una combinación (lookback 30, cadencia 7d)
> con 3.012 de resultado frente a 990 y 1.216 de sus vecinas inmediatas. Es una celda aislada, es
> decir, ruido. **Lo que sobrevive al mover un parámetro vecino es la fila del lookback 30**, no
> ese pico. No se toman decisiones con celdas sueltas.

## Por qué no se mezclan

El motor cruza las fechas comunes de los activos y descarta los días en que alguno no cotizó
— comparar un activo que cotizó con otro que no, no compara nada. En la práctica:

| Cartera | Fechas usables | Datos perdidos |
|---|---|---|
| BTC/USDT + GLD | 2.105 | **954 velas de cripto (31%)** |
| GLD + TLT | 5.283 | 0 |

Mezclar cripto con bolsa tira un tercio del histórico de cripto en silencio, porque el cripto
cotiza fines de semana y la bolsa no.

## Lo que esto implica al usar el sistema

- Medir y proponer **siempre por separado**. El panel ya lo hace: en **Mercado** salen en tablas
  distintas.
- En bolsa, la propuesta por defecto es aportar y mantener. Desconfía de cualquier resultado que
  diga lo contrario: ya se probaron siete formas de batirlo y ninguna pudo.
- En cripto, no quitar el filtro. Es la única pieza que resistió la validación fuera de muestra.
- La reserva de datos está fijada en **2025-01-01** (`data/market/reserved.json`). Los backtests se
  recortan ahí. Ese tramo ya se gastó una vez validando el afinado de cripto; no se vuelve a usar
  para elegir nada.
- Estas cifras salen de un histórico concreto y **no garantizan nada del futuro**. El drawdown de
  las configuraciones de cripto va de −290.000 a −1,8 millones sobre un capital que llegó a valer
  millones: se pierde más de la mitad de lo acumulado, varias veces, por el camino.

Ver también [operar de verdad](operar-de-verdad.md) para el paso de simulación a dinero real.
