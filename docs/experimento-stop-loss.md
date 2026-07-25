# Stop-loss en rotación: implementado, medido, y no sirve

**Fecha**: 2026-07-25 · **Universo**: GLD/TLT/XLE/XLF, 5.283 periodos (21 años)
**Decisiones**: las 84 grabadas en `decisions/llm-trimestral`, sin volver a preguntar al LLM

## Por qué se hizo

`ExitReason.STOP_LOSS` existía desde la feature 001 y **ninguna estrategia lo había ejercitado
nunca**. `backtest.py` (un activo) lo respetaba; `rotation.py` —el motor que usa el LLM— ni lo
miraba. En el modo del LLM no había ninguna salida por pérdida: si el activo elegido se hundía, se
seguía dentro hasta la siguiente decisión, **entre 21 y 63 días después**.

La hipótesis era que eso explicaba el drawdown de -20.336 del LLM frente a los -5.668 de comprar y
mantener.

## Lo medido

```
estrategia                    RESULTADO     DRAWDOWN   ops  stops     COSTES
----------------------------------------------------------------------------
LLM sin stop                     19,246      -20,336    65      0      4,387
LLM stop 10%                     19,007      -19,698    65     13      4,154
LLM stop 15%                     14,973      -20,102    65      5      4,020
LLM stop 20%                     14,852      -21,781    65      2      4,040
LLM stop 25%                     11,608      -23,345    65      2      3,819
----------------------------------------------------------------------------
momentum sin stop                 2,890      -13,359   423      0     18,151
momentum stop 15%                 3,779      -12,701   424      1     18,549
----------------------------------------------------------------------------
comprar y mantener               37,773       -5,668     1      0         87
```

## La hipótesis era falsa

**Ninguna configuración mejora el resultado.** El mejor caso (10%) cuesta 239 de resultado para
ganar 638 de drawdown: un empate, no una mejora. A partir del 15% empeora todo, y **con stops del
20% y 25% el drawdown es PEOR que sin stop ninguno**.

Eso último parece imposible —cortar pérdidas debería reducir la caída máxima— y tiene explicación:
tras un corte, el veto mantiene fuera hasta que la estrategia cambie de idea, y eso puede tardar
63 días. Se materializa la pérdida **y** se pierde el rebote. El pico-a-valle de la curva de
patrimonio acaba siendo más profundo, no menos.

## Lo que el experimento sí enseña

El stop del 10% saltó **13 veces** y cambió el resultado en un 1,2%. Si las pérdidas del LLM
vinieran de caídas profundas en un activo concreto, cortarlas 13 veces habría cambiado mucho más.

**No vienen de ahí.** Vienen de estar en el activo equivocado durante periodos largos. Un stop-loss
no arregla eso: solo corta el síntoma cuando ya ha ocurrido, y encima te deja fuera de la
recuperación.

El número de operaciones se queda en 65 con y sin stop, lo cual confirma que el veto hace lo suyo:
el corte adelanta la salida de una operación que igualmente iba a cerrarse, en vez de generar una
nueva. Los costes bajan (4.387 → 4.154) porque se sale antes y con menos importe.

## Sobre el +889 de momentum

Pasa de 2.890 a 3.779 con stop del 15%. **Con UN solo stop disparado en 21 años.** Un evento no es
evidencia: es la definición de ruido. No se puede concluir nada de ahí, y presentarlo como "el stop
mejora momentum un 31%" sería exactamente la clase de afirmación que este proyecto existe para
evitar.

## Decisión

**El stop-loss queda implementado pero desactivado por defecto** (`--stop-loss` hay que pedirlo).
Está disponible, medido, y la medición dice que no lo uses en este universo con estas decisiones.

Y por sexta vez aparece el mismo patrón: **423 operaciones → 65 → 1, con el resultado subiendo**.
Cada mecanismo que se añade para intervenir mejor acaba midiendo lo mismo — que intervenir menos
habría sido mejor.

## Lo que esto NO dice

- No dice que un stop-loss sea mala idea en general. Dice que en **este** universo, con **estas**
  decisiones, no ayuda.
- No dice que el stop esté mal implementado. Los tests lo verifican, incluido que un hueco a la
  baja se come la protección.
- Este resultado sale de datos que el LLM ya conocía al decidir. Lo único limpio sigue siendo el
  registro de `invest-ll-track` que vence el **23 de octubre de 2026**.
