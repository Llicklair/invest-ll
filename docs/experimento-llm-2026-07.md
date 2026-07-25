# El LLM decidiendo de verdad: 84 decisiones sobre 21 años

**Fecha**: 2026-07-25 · **Modelo**: `claude-opus-4-6` vía CLI de Claude Code
**Activos**: GLD, TLT, XLE, XLF · **Periodo**: 2005-01 a 2025-12 (5.283 sesiones)
**Frecuencia**: trimestral (cada 63 sesiones) · **Costes**: 0,1% comisión + 0,05% slippage

Decisiones reproducibles en `decisions/llm-trimestral/`. Repetir el experimento no consume nada:

```bash
uv run invest-ll-compare data/market/yfinance/{GLD,TLT,XLE,XLF}/DAY_1.csv \
    --strategies llm,momentum --commission 0.001 --slippage 0.0005 \
    --recorded decisions/llm-trimestral --model claude-opus-4-6 --every 63
```

---

## El resultado

| | Resultado | Drawdown | Operaciones | Costes | vs no hacer nada |
|---|---:|---:|---:|---:|---:|
| **LLM** | 19.246 | −20.336 | 65 | 4.387 | **−18.527** |
| Momentum relativo | 2.890 | −13.359 | 423 | 18.151 | −34.883 |
| **Comprar y mantener** | **37.773** | **−5.668** | 1 | 87 | *referencia* |

**Ninguna estrategia batió a comprar y mantener.**

---

## 1. Lo que el LLM hizo bien

**Ganó al momentum por 16.356.** No es casualidad ni ruido: operó **65 veces frente a 423**, y eso
se tradujo en **4.387 € de comisiones en lugar de 18.151**.

Llegó por su cuenta a la conclusión que a este proyecto le costó cuarenta barridos: *operar menos
es mejor*. En su primera decisión, con un solo punto de precio disponible, se quedó fuera del
mercado razonando que "no hay señal de tendencia" — que es exactamente lo correcto y lo que una
regla mecánica no habría hecho.

## 2. Lo que hizo mal

Quedó **18.527 por debajo de no hacer nada**, con un drawdown de **−20.336 frente a −5.668**.

Ganó aproximadamente la mitad y sufrió casi cuatro veces más. Pagó 4.387 € en comisiones para
terminar peor que quien compró una vez y se olvidó.

## 3. El patrón que ya no admite discusión

```
Operaciones:   423   →   65   →   1
Resultado:   2.890  → 19.246 → 37.773
```

Es la quinta medición del día que apunta en la misma dirección, y la primera con un modelo
decidiendo de verdad en lugar de una fórmula. **El movimiento no es la ventaja: es el coste.**

---

## Por qué este resultado es más concluyente de lo que parece

El modelo fue entrenado con datos que incluyen 2005–2025. Se le ocultaron fechas y nombres —los
activos se le presentaron como A, B, C, D con precios normalizados a 100— pero un patrón
reconocible delata la época: quien identifique una caída del 50% en seis meses sabe que está en
2008.

Es decir: **el LLM jugaba con una ventaja imposible de tener en la vida real, y aun así perdió
contra comprar y esperar.** Si con información del futuro no gana, difícilmente ganará sin ella.

## Lo que este experimento NO demuestra

Que el LLM sirva o no sirva **hacia adelante**. Un backtest contaminado no puede responder eso, ni
a favor ni en contra.

La única prueba limpia es registrar hoy lo que estima y comprobarlo cuando venza el plazo. La
infraestructura para hacerlo está construida y probada (`invest-ll-track`, pestaña *Estimado vs
real* del panel), pero **todavía no tiene ni un solo dato**: hay que emitir la primera estimación y
esperar.

---

## Notas de método

**Aislamiento temporal**: el LLM recibió su contexto de `UniverseView`, la misma estructura que
impide a las estrategias de reglas ver el futuro. La garantía es estructural, no una convención.

**Reproducibilidad**: `temperature` está eliminada en los modelos actuales, así que no hay forma de
pedir determinismo. Las 84 decisiones están guardadas en disco; repetir la comparación da el mismo
resultado sin consultar al modelo.

**Un fallo que casi arruina el experimento**: las primeras decisiones devolvían `"C"` en lugar de
`XLE`. El contexto va anonimizado y la traducción de vuelta existía, pero nunca se conectaba. Los
tests con dobles no lo detectaban porque los dobles devuelven símbolos reales — el hueco estaba
entre las piezas que cada test daba por buenas. Se detectó **mirando las decisiones guardadas**, no
leyendo el código.

**Limitación de ritmo**: generar 84 decisiones seguidas provocó fallos transitorios del CLI (código
1 sin mensaje) a partir de la vigésimo quinta. Se resolvió con tres reintentos y espera creciente.
Un fallo de *formato*, en cambio, no se reintenta: volver a pedir lo mismo daría lo mismo.

---

## Fuentes relacionadas

- [Qué dice la evidencia sobre las estrategias de inversión](research-estrategias.md) — el 79% de
  los fondos activos no bate a su índice, y a 15 años no hay ni una categoría donde la mayoría lo
  consiga.
