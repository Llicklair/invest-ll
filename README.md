# INVEST LL

Sistema de inversión automática en bolsa y criptomonedas. Opera sin intervención humana por
operación, y por eso se construye con una regla por delante de todas: **el sistema no puede
mentirte sobre sus propios resultados**.

**Estado**: v1 en desarrollo. Solo simulación — no ejecuta órdenes con dinero real.

**Arrancar**: doble clic en `levantar.cmd` (o `.\scripts\start.ps1` desde una terminal). Comprueba el entorno, cierra paneles viejos y abre el panel en http://localhost:8601.

---

## Lo primero que debes saber

**El porcentaje de aciertos no dice si una estrategia funciona.** Una estrategia puede acertar el
90% de las operaciones y perder dinero, si las pérdidas del 10% restante superan a todas las
ganancias juntas. Por eso este proyecto nunca presenta el win rate como criterio de éxito: todo
informe reporta además expectancy por operación, drawdown máximo y el coste real de comisiones y
slippage.

Un backtest que solo te enseña el win rate te está vendiendo algo.

---

## Principios no negociables

Recogidos en [la constitución del proyecto](.specify/memory/constitution.md):

1. **Seguridad del capital por defecto** — el modo simulación es el estado por defecto. Ninguna
   orden real puede ejecutarse sin activación explícita y credenciales separadas.
2. **El backtester no puede ver el futuro** — ninguna decisión simulada usa datos posteriores al
   instante que simula. Es una propiedad del diseño, no una convención a recordar.
3. **Las métricas no pueden mentir** — ver arriba.
4. **Realismo en la simulación** — comisiones, slippage y órdenes rechazadas siempre modeladas.
   Una simulación sin fricción es una mentira optimista.
5. **Estrategias intercambiables** — reglas fijas e IA se miden con la misma vara.

---

## Componentes

| Feature | Estado | Descripción |
|---|---|---|
| [001 · Motor de backtesting](specs/001-backtest-engine/) | Funcional | Mide una estrategia sobre el pasado y emite un veredicto honesto |
| [002 · Descarga de histórico](specs/002-market-data-fetch/) | Funcional | Trae mercado real de cripto y bolsa, listo para el motor |
| Carteras y rotación | Funcional | Universo de activos, momentum relativo, aportaciones periódicas y análisis de diversificación |
| Panel interactivo | Funcional | Streamlit sobre el mismo motor |

Soporta cripto (mercado continuo) y bolsa (con horario de sesión y festivos) sobre el mismo
motor, con cualquier granularidad de vela. Incluye dos estrategias de referencia: cruce de medias
móviles y ruptura de máximos.

## Uso

**Traer datos reales:**

```bash
uv run invest-ll-fetch BTC/USDT --market crypto --interval DAY_1 \
    --start 2025-01-01 --end 2026-01-01

uv run invest-ll-fetch AAPL --market equity --interval DAY_1 \
    --start 2020-01-01 --end 2026-01-01
```

**Arrancar todo de una vez:**

```powershell
.\scripts\start.ps1              # Windows
bash scripts/start.sh            # Linux / macOS
```

Comprueba el entorno, **te dice si el sistema puede enviar órdenes reales**, lista los históricos
descargados y las decisiones ya generadas, y abre el panel. Con `-SoloCheck` / `--solo-check`
comprueba sin arrancar nada.

> No hay "frontend y backend" separados: el panel llama al motor en el mismo proceso, sin API por
> medio. Un script que arrancara dos cosas arrancaría una sola dos veces.

**Pedir una propuesta de cartera** (lo más simple que hay):

```bash
uv run invest-ll-propose data/market/yfinance/*/DAY_1.csv --amount 500 --frequency monthly
```

Solo pide cuánto y cada cuánto. Devuelve una cartera concreta, por qué está cada activo, y la
simulación de qué habría pasado.

**Comparar el LLM contra reglas fijas:**

```bash
uv run invest-ll-compare data/market/yfinance/*/DAY_1.csv     --strategies llm,momentum --commission 0.001 --slippage 0.0005     --recorded decisions/mi-experimento
```

Las mismas métricas para todas. Si el LLM elige mejor, se ve en los números; si no, también.

**Ver qué hay detrás de un activo:**

```bash
uv run invest-ll-analyze AAPL GLD
```

Separa los datos verificables (con su fuente y su fecha) de la interpretación.

**Abrir el panel interactivo:**

```bash
uv run invest-ll-panel
```

Tres pestañas: evaluar una estrategia sobre un activo, analizar una cartera (diversificación,
aportaciones periódicas, rotación) y ver el estado de los históricos descargados. Todas las cifras
salen del mismo motor que la línea de comandos, con las mismas advertencias.

**Evaluar una estrategia sobre ellos:**

```bash
uv run invest-ll data/market/ccxt-binance/BTC-USDT/DAY_1.csv --symbol BTC \
    --strategy ma-cross --short 10 --long 30 \
    --commission 0.001 --slippage 0.0005 --fraction 0.5
```

### Lo que debes saber sobre los datos de bolsa

Tres cosas hacen que un backtest con datos reales mienta con toda credibilidad. El sistema avisa
de las tres, pero solo puede **corregir** las dos primeras:

- **Splits**: una división de acciones parte el precio sin que la empresa pierda valor. Sin
  ajustar, el motor vería una caída del 50% que nunca ocurrió. → Se guardan precios ajustados.
- **Dividendos**: el precio cae el día del reparto. Sin ajustar, cada dividendo parece una
  pérdida. → Se guardan precios ajustados.
- **Sesgo de supervivencia**: los proveedores gratuitos solo listan empresas que siguen
  cotizando. Un backtest sobre ellas ignora a las que quebraron y sale mejor de lo que la
  realidad fue. → **Se advierte, no se corrige.** Corregirlo exige datos de pago con activos
  retirados.

El histórico se guarda junto a un fichero de procedencia que dice quién dio los datos, cuándo se
descargaron y qué cubren. Si el proveedor revisa datos que ya tenías, el sistema avisa y
**conserva lo local**: un backtest de hace tres meses sigue siendo reproducible hoy.

`--commission` y `--slippage` son **obligatorios**. No se puede lanzar un backtest sin declarar
los costes: una simulación sin fricción da resultados que no existen.

Códigos de salida: `0` resultado concluyente · `3` no concluyente (pocas operaciones) · `1` error
de configuración · `2` fichero no encontrado.

---

## Desarrollo

```bash
uv sync                      # Python 3.13 + dependencias
uv run pytest                # suite completa
uv run ruff check .          # lint
uv run pyright               # tipos
```

Las cuatro gates deben pasar antes de integrar cualquier cambio. Los baselines y snapshots **no**
se actualizan para hacer pasar un test.

## Dinero real

**El sistema arranca siempre en modo simulación.** No es una opción por defecto que se pueda
cambiar en un fichero de configuración: es lo que se obtiene sin configurar nada.

Para operar de verdad hacen falta **cuatro cosas a la vez**, y ninguna basta por sí sola:

1. `INVEST_LL_MODE=real` — activación explícita
2. `INVEST_LL_LIVE_KEY` y `INVEST_LL_LIVE_SECRET` — credenciales **distintas** de las de pruebas
3. `INVEST_LL_TESTNET_VERIFIED=1` — haber operado antes en la red de pruebas
4. Confirmación **de cada orden concreta** en el momento de enviarla

Tener las credenciales sin pedir el modo real no lo activa. Un error tipográfico en el modo
(`reall`) falla en lugar de caer en real. Y si la credencial real coincide con la de pruebas, se
rechaza: si son la misma, no hay separación entre modos.

Las claves se leen del entorno y **nunca** se guardan en el repositorio.

---

Flujo de trabajo: [Spec Kit](https://github.com/github/spec-kit) — constitution → spec → clarify →
plan → tasks → implement.
