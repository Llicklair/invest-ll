# Validación de la feature 003

Escenarios ejecutables que demuestran que cada historia funciona. No es documentación de uso: es la
lista de lo que hay que poder ejecutar para decir que está terminada.

## Antes de empezar

```bash
uv sync                    # instala el SDK de Anthropic
uv run pytest -q           # la suite entera debe pasar antes de tocar nada
```

Para los escenarios con LLM real:

```bash
export ANTHROPIC_API_KEY=...     # nunca en el repositorio
```

**Los escenarios 1, 2 y 6 no necesitan clave** — usan decisiones grabadas. Es lo normal: solo se
paga cuando se genera algo nuevo.

---

## E1 · El LLM se mide con la misma vara (US2 · P1)

**Es el escenario que justifica la feature.** Responde a: ¿elige mejor que una regla?

```bash
uv run invest-ll-compare --universe data/market/yfinance/*/DAY_1.csv \
    --strategies llm,momentum,buy-and-hold \
    --split 0.6 --recorded decisions/experimento-01
```

**Esperado**: una tabla con las tres estrategias y las **mismas seis métricas** en todas. El win
rate aparece el último con su coletilla. La diferencia contra comprar y mantener está presente en
las tres.

**Se valida si**: no se puede distinguir por el formato del informe cuál es el LLM. Si el informe
del LLM tuviera un formato propio, el Principio V estaría roto.

---

## E2 · La misma pregunta da la misma respuesta (FR-044)

```bash
uv run invest-ll-compare --strategies llm --recorded decisions/experimento-01 > a.txt
uv run invest-ll-compare --strategies llm --recorded decisions/experimento-01 > b.txt
diff a.txt b.txt && echo "REPRODUCIBLE"
```

**Esperado**: sin diferencias, y ninguna llamada nueva al modelo.

**Por qué importa**: `temperature` no existe en Opus 5, así que el caché es lo único que hace
comparables dos ejecuciones. Si este escenario falla, comparar el LLM con cualquier otra cosa deja
de significar algo.

---

## E3 · Un backtest caro avisa antes de serlo (FR-041)

```bash
uv run invest-ll-compare --strategies llm --frequency daily --start 2005-01-01
```

**Esperado**:

```
Este backtest necesita 5.283 decisiones nuevas (~$105 estimados, ~2h).
Con periodicidad mensual serian 252 (~$5). Continuar? [s/N]
```

**Se valida si**: responder cualquier cosa distinta de `s` no gasta ni un euro.

---

## E4 · Una propuesta sin saber de inversión (US1 · P1)

```bash
uv run invest-ll-propose --amount 500 --frequency monthly
```

**Esperado**: una cartera concreta con cantidades, la explicación de cada activo en lenguaje llano,
la simulación de qué habría pasado, y la comparación contra no hacer nada.

**Se valida si**: no hizo falta elegir estrategia ni parámetros. Ese es justamente el conocimiento
que el operador no tiene.

---

## E5 · Se ve qué es dato y qué es interpretación (US3 · P2)

```bash
uv run invest-ll-analyze AAPL
```

**Esperado**: dos secciones separadas — los datos verificables con su fecha y su fuente, y el
contexto del LLM aparte. Los escenarios etiquetados como escenarios.

**Se valida si**: cada cifra de la primera sección se puede contrastar contra su fuente, y ninguna
frase presenta un escenario como una predicción.

---

## E6 · Los fallos siguen ahí (US4 · P2)

```bash
uv run invest-ll-track --list
uv run invest-ll-track --evaluate
```

**Esperado**: el histórico completo de estimaciones, con las acertadas y las falladas, y si el
sistema tiende a pasarse o a quedarse corto.

**Se valida si**: una estimación que salió mal sigue en la lista. Un registro que solo guarda los
aciertos no mide nada.

---

## E7 · Dinero real: lo que NO debe poder pasar (US5 · P3)

Este escenario comprueba negativos. Todos deben fallar.

```bash
# 1. Sin configurar nada, no sale nada
uv run invest-ll-execute --symbol BTC/USDT --side buy --quantity 0.001
# → rechazado, y explica qué haría falta

# 2. Con credenciales de pruebas, el modo real se niega
INVEST_LL_MODE=real BINANCE_TESTNET_KEY=... uv run invest-ll-execute ...
# → rechazado: son credenciales de pruebas

# 3. Sin haber operado en testnet, el modo real se niega
INVEST_LL_MODE=real BINANCE_KEY=... uv run invest-ll-execute ...
# → rechazado: primero hay que operar en la red de pruebas

# 4. Con todo en regla, pide confirmacion de ESTA orden
INVEST_LL_MODE=real BINANCE_KEY=... uv run invest-ll-execute ...
# → muestra la orden y espera confirmacion explicita
```

**Se valida si los cuatro se comportan como se describe.** El cuarto es el único que puede llegar a
enviar algo, y solo tras una confirmación de esa orden concreta.

---

## E8 · Las garantías estructurales siguen en pie

```bash
uv run pytest tests/unit/test_engine_isolation.py -v
uv run pytest tests/unit/test_live_safety.py -v
uv run pytest -q
```

**Esperado**: el motor sigue sin importar red ni LLM ni broker. Ninguna orden real puede salir en
modo simulación. Toda la suite pasa **sin tocar la red ni gastar una llamada al modelo**.

**Se valida si**: se puede desconectar el cable de red y la suite entera sigue pasando.

---

## Las cuatro gates, como siempre

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Las cuatro en verde antes de integrar nada. Los baselines no se actualizan para que un test pase.
