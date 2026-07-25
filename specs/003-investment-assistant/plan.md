# Plan de implementación: Asistente de Inversión

**Feature**: `003-investment-assistant` · **Fecha**: 2026-07-25 · **Spec**: [spec.md](spec.md)

## Resumen

Añade cuatro capacidades sobre el sistema existente: un LLM que decide como una estrategia más,
análisis de los activos, comparación entre lo estimado y lo ocurrido, y ejecución con dinero real.

La feature es grande, pero **el motor no cambia**. Todo lo nuevo se conecta por interfaces que ya
existen: el LLM implementa el mismo protocolo que el cruce de medias, y la ejecución real es un
consumidor del motor, no una modificación suya.

## Contexto técnico

| | |
|---|---|
| **Lenguaje** | Python 3.14 (suelo 3.13) |
| **Gestión** | uv 0.11 |
| **Calidad** | ruff · pyright estricto · pytest · hypothesis |
| **Dependencias nuevas** | `anthropic` (SDK oficial) |
| **Ya integradas** | `ccxt` (cripto), `yfinance` (bolsa), `streamlit` (panel) |
| **Modelo** | `claude-opus-5` — ver [research.md](research.md) D1 |
| **Almacenamiento** | Ficheros locales con escritura atómica, como la 002 |

## Comprobación contra la constitución

| Principio | Cómo lo cumple | Verificado por |
|---|---|---|
| **I · Seguridad del capital** (NO NEGOCIABLE) | El modo viaja en el objeto ejecutor, no en una variable global. Simulación es el tipo por defecto. Confirmación por orden. Credenciales del entorno. | Test que intenta ejecutar real desde el estado por defecto y comprueba que se rechaza (FR-038) |
| **II · No ver el futuro** (NO NEGOCIABLE) | El LLM recibe su contexto de `MarketView`, que ya bloquea offsets negativos y devuelve arrays inmutables | Los tests de look-ahead existentes cubren al LLM sin código nuevo |
| **III · Métricas honestas** | Las decisiones del LLM pasan por `build_report()`: mismas seis métricas, mismo win rate al final con su coletilla | Test que compara el informe del LLM con el de una regla fija |
| **IV · Realismo** | La fricción es del motor, no de la estrategia. El LLM la paga igual | Cubierto por los tests del motor |
| **V · Intercambiables** | `LLMStrategy` implementa `RotationStrategy`. Se puede pasar a `run_rotation()` sin distinguirla | Test que ejecuta ambas por el mismo camino |

**Sin violaciones.** La feature añade superficie de riesgo (red, dinero real), y por eso cada
riesgo nuevo trae su comprobación automática.

## Arquitectura

```
src/invest_ll/
├── engine/          ← SIN CAMBIOS. Sigue sin tocar la red.
├── data/            ← sin cambios
├── strategy/
│   └── llm.py       ← NUEVO · LLMStrategy: implementa RotationStrategy
├── decision/        ← NUEVO · la capa del LLM
│   ├── provider.py      protocolo DecisionProvider + las 3 implementaciones
│   ├── prompt.py        MarketView → texto (puro, testeable sin red)
│   ├── schema.py        esquema JSON de la decisión
│   ├── cache.py         almacén de decisiones, indexado por contenido + modelo
│   └── cost.py          estimación de coste antes de lanzar (FR-041)
├── analysis/        ← NUEVO · US3
│   └── asset.py         datos verificables + contexto, separados
├── tracking/        ← NUEVO · US4
│   └── forecast.py      estimaciones inmutables y su comparación
├── live/            ← NUEVO · US5
│   ├── mode.py          Simulation | Testnet | Real — tipos distintos, no un flag
│   ├── broker.py        protocolo Broker
│   ├── ccxt_broker.py   cripto
│   └── ledger.py        registro de lo pedido vs lo ejecutado
└── dashboard/       ← se amplía con las vistas nuevas
```

**La dependencia va en una sola dirección**: `strategy/llm.py` → `decision/` → red. El motor no
conoce ninguno de los módulos nuevos, igual que hoy no conoce el panel. Hay un test de aislamiento
que lo comprueba por análisis del árbol sintáctico.

## Decisiones clave

Detalle completo en [research.md](research.md). Las tres que más afectan al código:

1. **No hay temperatura que fijar.** `temperature` está eliminado en Opus 5 — enviarlo da error. El
   caché de decisiones no es una optimización: es lo único que hace reproducible un experimento con
   LLM. Sin él, FR-005 sería imposible de cumplir.

2. **La interfaz acepta lotes desde el principio.** Las decisiones de un backtest son
   independientes entre sí, y la Batches API cuesta la mitad. Diseñar solo para "una decisión por
   llamada" dejaría ese descuento inaccesible sin rehacer la interfaz.

3. **El modo no es un booleano.** `Simulation`, `Testnet` y `Real` son tipos distintos. Una función
   que acepta `RealBroker` no puede recibir un simulador por error, y el comprobador de tipos lo
   detecta antes de ejecutar nada. Un flag sería una comprobación en tiempo de ejecución que alguien
   puede olvidar.

## Orden de construcción

Por prioridad de la spec, cada fase entregable por sí sola:

| Fase | Qué | Historia |
|---|---|---|
| 1 | Capa de decisión: protocolo, prompt, esquema, caché | base de US2 |
| 2 | `LLMStrategy` + comparación contra reglas fijas | US2 (P1) |
| 3 | Propuesta de cartera desde importe y periodicidad | US1 (P1) |
| 4 | Análisis de activos | US3 (P2) |
| 5 | Registro y comparación de estimaciones | US4 (P2) |
| 6 | Ejecución: modos, broker, testnet, registro | US5 (P3) |

**La fase 2 es la que responde a la pregunta que motiva la feature**: ¿el LLM elige mejor que una
regla? Todo lo demás se construye sabiendo ya la respuesta.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El LLM pierde contra el cruce de medias | Es un resultado válido y el sistema lo dirá con cifras. Toda la feature está diseñada para poder decirlo. |
| Un backtest se lanza por error y cuesta cientos de euros | FR-041: estimar y confirmar antes de lanzar |
| El caché devuelve una decisión de otro contexto | La clave incluye todo lo que determina la decisión, y el modelo (FR-045) |
| Una orden real sale sin querer | Tipos distintos por modo + confirmación por orden + testnet obligatoria + test que lo verifica |
| Cambia la API del SDK | Aislada tras `DecisionProvider`; solo una implementación la toca |
