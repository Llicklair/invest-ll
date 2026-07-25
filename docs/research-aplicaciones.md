# Qué hacen otras aplicaciones, y qué merece copiarse

**Fecha**: 2026-07-25 · **Para**: decidir qué construir en INVEST LL y qué evitar deliberadamente

Cuatro categorías revisadas: gestores de cartera autoalojados, plataformas de backtesting,
robo-advisors y —la más útil— lo que los reguladores han **medido** sobre cómo las apps de
inversión inducen a operar de más.

La conclusión corta: **la idea más valiosa no es una función nueva, es un freno**. Y la segunda
mejor idea del research ya la tenemos a medias.

---

## 1. El hallazgo que más importa: la gamificación tiene coste medido

La FCA británica probó una app experimental con **más de 9.000 personas** y midió el efecto de
cada elemento de diseño:

| Elemento | Efecto en nº de operaciones | Efecto en inversiones arriesgadas |
|---|---|---|
| Notificaciones push | **+11%** | +8% |
| Puntos y sorteos | **+12%** | +6% |

Y un detalle que nos afecta directamente: el efecto es **mayor** en personas con baja
alfabetización financiera y en menores de 35 años. El operador de este proyecto ha declarado
explícitamente no entender de inversión — está en el grupo donde estas técnicas más daño hacen.

**Por qué esto importa aquí y no es una nota moral.** Nuestros propios datos ponen precio a ese
+11%:

```
423 operaciones  ->   2.890 de resultado, 18.151 en comisiones
 65 operaciones  ->  19.246 de resultado,  4.387 en comisiones
  1 operación    ->  37.773 de resultado,     87 en comisiones
```

Un +11% de operaciones no es una métrica de interacción: es dinero que se va en comisiones. La
FCA también señala el **confeti y los mensajes de celebración tras una operación exitosa** como
refuerzo positivo que lleva a sobreoperar.

**Qué hacemos ya bien**: el panel no tiene notificaciones, ni rachas, ni celebraciones, ni
"temporada de altcoins". Y el win rate nunca aparece solo.

**Lo que falta**: que eso sea **verificable**, no una intención. Un test que escanee el panel
buscando patrones de gamificación (contadores de racha, emojis de celebración, notificaciones,
rankings) y falle si aparecen. Lo mismo que ya hacemos con las expresiones que afirman capacidad
de predicción.

---

## 2. La idea que ya tenemos a medias: medidor de sobreajuste

**QuantConnect** muestra un *power gauge* con el **número de backtests ejecutados**, los
parámetros usados y el tiempo invertido en la estrategia — como estimación del riesgo de haber
sobreajustado.

Es exactamente el problema que `sweep.py` resuelve para un barrido: contar cuántas cosas se
probaron y calcular qué habría salido por azar. Pero **solo dentro de una ejecución**. Si pruebas
40 configuraciones hoy, 40 mañana y 40 pasado, cada barrido dice "0 de 40" y ninguno sabe que
llevas 120.

**Adaptación concreta**: un contador persistente por universo de datos. Cada backtest ejecutado
sobre los mismos activos incrementa la cuenta, y el informe lo muestra:

```
Has ejecutado 137 backtests sobre este universo.
Con 137 pruebas sin ventaja real, esperarías ~68 positivas por azar.
Cualquier resultado que encuentres ahora necesita ser MUCHO mejor
que hace 137 pruebas para significar lo mismo.
```

Barato de construir —ya tenemos `probabilidad_por_azar()`— y ataca justo el error que produjo el
caso de `dual momentum` documentado en [research-estrategias.md](research-estrategias.md).

---

## 3. La segunda idea de QuantConnect: reservar datos por construcción

QuantConnect permite a un administrador **forzar que todos los backtests terminen N meses antes
de hoy**, reservando por ejemplo el último año como periodo fuera de muestra que nadie puede
tocar.

Es la misma filosofía que `MarketView`: **hacer imposible lo que no debe pasar, en vez de
recordar no hacerlo**. Nosotros hoy partimos train/validation manualmente con `--split`; nada
impide mirar la validación, ajustar, y volver a mirar.

**Adaptación**: un fichero `reserved.json` en `data/market/` que declare la fecha de corte, y que
el cargador **recorte las series ahí** salvo con una bandera explícita. La reserva se fija una vez
y "quitarla para echar un vistazo" pasa a ser un acto deliberado y registrado.

---

## 4. Lo que sí funciona de los robo-advisors, con su límite

Durante el desplome de 2020, los inversores con robo-advisor superaron a los autodirigidos en
**12,67%**, y la razón no fue mejor selección de activos: fue **no vender en pánico en el peor
momento**.

Pero el mismo estudio trae la letra pequeña que importa: **solo protegió a quien se quedó**. Los
que entraron en la aplicación, vieron pérdidas y se pasaron a efectivo por su cuenta no estuvieron
protegidos por la disciplina del algoritmo.

**Traducción para nosotros**: la disciplina no se puede imponer, pero sí se puede hacer visible el
coste de romperla. Idea concreta, y encaja con lo que ya calculamos:

> **"Qué habría pasado si hubieras vendido".** Sobre la cartera propuesta, mostrar el resultado de
> haber liquidado en el peor mes de cada crisis (2008, 2020, 2022) frente a haber aguantado. No es
> un consejo: son dos cifras al lado.

Los datos para eso ya están descargados: tenemos 2005–2025 de ocho activos, con 2008 y 2020
dentro.

---

## 5. Gestores autoalojados: dónde estamos bien y dónde no

**Ghostfolio** es el referente en autoalojado: AGPL-3.0, sin niveles de pago, **sin telemetría**,
los datos se quedan en tu máquina. Su argumento central es que ninguna startup puede cerrar y
llevarse tu histórico.

Ahí ya estamos: local, sin telemetría, ficheros CSV que puedes leer con cualquier cosa.

**Lo que ellos tienen y nosotros no**, por orden de utilidad real:

| Función | ¿Merece la pena? |
|---|---|
| **Importar movimientos desde CSV del bróker** | **Sí.** Hoy la cartera es hipotética; sin esto nunca sabremos qué tienes de verdad |
| Precios actuales automáticos | Sí, pero fuera del motor — el aislamiento de red no se negocia |
| Múltiples cuentas / divisas | Solo si operas en varias |
| Informes fiscales | No. Es un dominio entero y equivocarse ahí tiene consecuencias legales |

Ghostfolio tampoco tiene funciones fiscales y recomienda una herramienta aparte. Coincido: es la
decisión correcta.

---

## Qué construir, por orden

| # | Idea | De dónde | Coste | Por qué |
|---|---|---|---|---|
| 1 | **Contador persistente de backtests** con aviso de sobreajuste | QuantConnect | Bajo | Ya tenemos la estadística; falta persistirla |
| 2 | **Test anti-gamificación** del panel | FCA | Bajo | Convierte una intención en una garantía |
| 3 | **Reserva de datos estructural** | QuantConnect | Medio | Misma filosofía que `MarketView` |
| 4 | **"Qué habría pasado si hubieras vendido"** | Robo-advisors | Medio | Los datos ya están; ataca el error que más cuesta |
| 5 | **Importar movimientos del bróker** | Ghostfolio | Alto | Convierte la cartera de hipotética a real |

Las tres primeras son baratas y refuerzan lo que este proyecto ya intenta ser. La cuarta es la que
más valor daría a alguien que no entiende de inversión. La quinta es la más cara y la única que
cambia la naturaleza del producto.

---

## Lo que decidimos NO copiar

- **Notificaciones push, rachas, insignias, rankings, confeti.** Medido: +11–12% de operaciones,
  y más daño en quien menos sabe.
- **Índices de sentimiento** tipo "miedo y codicia" o "temporada de altcoins". No informan de nada
  accionable; existen para generar urgencia.
- **Funciones fiscales.** Dominio aparte, consecuencias legales, y hasta Ghostfolio lo evita.
- **Precios en vivo dentro del motor.** El aislamiento de red del backtester es una garantía
  estructural que ya nos ha salvado; los precios actuales van en su propia capa o no van.

---

## Fuentes

- [FCA: elementos de juego en apps de trading ligados a inversión arriesgada](https://www.financemagnates.com/forex/trading-apps-game-like-elements-linked-to-risky-investing-fca-finds/)
- [FCA advierte a las apps de trading sobre la gamificación](https://www.financemagnates.com/forex/fca-warns-trading-app-operators-to-stop-the-trading-gamification/)
- [La gamificación de la inversión: EE. UU. frente a la UE — Berkeley Technology Law Journal](https://btlj.org/2025/11/the-gamification-of-investments-a-comparative-approach-between-the-us-and-eu/)
- [Tu app de trading parece una casa de apuestas: los reguladores lo han notado](https://www.financemagnates.com/forex/your-trading-app-looks-like-a-gambling-shop-regulators-have-noticed/)
- [QuantConnect — Guía de investigación (medidor de sobreajuste)](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide)
- [QuantConnect — Backtesting](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting)
- [Ghostfolio: gestor de cartera autoalojado](https://www.pistack.xyz/posts/ghostfolio-self-hosted-portfolio-tracker-wealth-management-guide-2026/)
- [Ghostfolio frente a Portfolio Performance](https://www.findmymoat.com/vs/ghostfolio-vs-portfolio-performance)
- [Robo-advisors y finanzas del comportamiento: revisión crítica — Frontiers](https://www.frontiersin.org/journals/behavioral-economics/articles/10.3389/frbhe.2024.1489159/full)
- [Robo-advisor frente a asesor humano: la brecha a 20 años](https://truthifi.com/education/robo-advisor-vs-human-financial-advisor)
