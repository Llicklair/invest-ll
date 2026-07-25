# Qué dice la evidencia sobre las estrategias de inversión

**Fecha**: 2026-07-25 · **Para**: decidir qué merece la pena implementar en INVEST LL

Resumen de lo que la investigación publicada sostiene y lo que no, contrastado con lo que este
proyecto ha medido por su cuenta sobre 21 años y cuatro mercados.

La conclusión corta: **lo que medimos coincide con la literatura**, incluida la parte incómoda.

---

## 1. El punto de partida: la gestión activa pierde, y cuanto más tiempo pasa, más

Los informes SPIVA de S&P llevan 25 años midiendo cuántos fondos de gestión activa baten a su
índice. Los datos de cierre de 2025:

- **79%** de los fondos de gran capitalización de EE. UU. quedaron por debajo del S&P 500 en 2025.
  Es el cuarto peor año para la gestión activa en 25 años de historia del informe.
- A **15 años vista, no hay ni una sola categoría** —renta variable nacional, internacional o renta
  fija— donde la mayoría de gestores activos supere a su índice.
- En renta fija va aún peor: 70% de media, y 82% en grado de inversión.

Esto lo hacen profesionales con equipos, datos de pago y acceso a información que ni tú ni yo
tenemos. Es el listón real contra el que compite cualquier cosa que construyamos.

**Coincide con lo nuestro**: cinco enfoques, cuatro mercados, ninguno batió a comprar y mantener
de forma reproducible.

---

## 2. Lo que sí tiene evidencia: los factores

Hay cuatro características de los activos que han mostrado exceso de rentabilidad de forma
persistente en estudios independientes:

| Factor | Qué es | Evidencia |
|---|---|---|
| **Momentum** | Lo que ha subido tiende a seguir subiendo | La más robusta: 46 países, más de 150 años de datos |
| **Value** | Empresas baratas respecto a sus fundamentales | Fama y French, Nobel 2013 |
| **Quality** | Empresas rentables y poco endeudadas | Exceso de rentabilidad sostenido |
| **Low volatility** | Activos que se mueven menos | Sólida hasta ~2015; ver la trampa abajo |

El momentum es el que más nos interesa porque es el único que se puede calcular **solo con
precios** — sin datos fundamentales de pago y sin riesgo de look-ahead.

La explicación que se le da no es matemática sino psicológica: la gente reacciona tarde, se ancla
a precios previos y sigue a la manada. Eso es más creíble que una fórmula, porque explica por qué
no desaparece en cuanto se publica.

**Pero ojo con el detalle**: la propia investigación reconoce que el momentum "tiene puntos débiles,
sobre todo en los giros de mercado". Es exactamente lo que medimos: nuestra rotación por momentum
ganaba en Bitcoin 2017-2020 (con el desplome de 2018 dentro) y perdía en periodos alcistas
sostenidos.

---

## 3. La trampa que este proyecto ya conoce: publicar mata la estrategia

Es el hallazgo más importante de todo el research, y confirma lo que medimos hoy.

**Dual momentum** es una de las estrategias tácticas más famosas de la última década. Su
comportamiento tras publicarse:

- La rentabilidad anualizada **cayó a un tercio** de la que tenía antes de publicarse.
- Su caída máxima pasó a igualar la del índice al que supuestamente mejoraba.
- El análisis lo dice sin rodeos: esa divergencia entre antes y después "es un indicio de que la
  estrategia fue resultado de minería de datos y sesgo de selección".

Lo mismo con **low volatility**: funcionó hasta que se hizo popular. El dinero invertido pasó de
menos de 50.000 millones en 2010 a casi 400.000 millones en 2024, las valoraciones subieron y el
descuento que producía la ventaja desapareció.

**Esto es literalmente lo que medimos hoy**: `breakout 20` daba +149.592 en el periodo de
entrenamiento y −20.792 en el de validación. La diferencia entre "funcionó" y "funciona" es la
única que importa.

---

## 4. Cripto: mucho ruido y poca evidencia

Aquí hay que tener el filtro puesto. Las búsquedas devuelven cosas como:

- "Backtests de 30 minutos que multiplican por 10 en dos meses"
- "CAGR del 145% con una media de cinco días"

**Ninguna de esas cifras significa nada** sin validación fuera de muestra, y la literatura seria lo
reconoce: los estudios académicos señalan que el efecto momentum existe en cripto pero **queda
abierto cuánto es real y cuánto es un artefacto de la liquidez** del mercado.

Las limitaciones que la propia literatura enumera para el backtesting en cripto son exactamente
las que sufrimos nosotros: histórico corto, estructura de mercado que cambia sin parar, cambios de
régimen, y la validación fuera de muestra como requisito para no acabar ajustando la curva.

**Traducción**: cripto es el terreno donde más fácil es engañarse y donde más gente publica
resultados espectaculares. Un backtest de cripto sin validación fuera de muestra no vale nada.

---

## 5. Qué significa esto para INVEST LL

**Lo que la evidencia respalda construir:**

1. **Aportaciones periódicas sobre cartera diversificada.** Ya implementado. Es lo que el 79% de
   los profesionales no consigue batir.
2. **Momentum como factor, con expectativas realistas.** Ya implementado (rotación). La evidencia
   es sólida a 150 años, pero nuestra propia medición dice que con un universo elegido por regla no
   aportó. Ambas cosas pueden ser ciertas: el factor existe y capturarlo neto de costes es otra
   historia.
3. **Diversificación medida, no supuesta.** Ya implementado. Los seis sectores de bolsa equivalen a
   1,5 activos independientes: eso no es opinión, es aritmética.

**Lo que la evidencia desaconseja:**

1. **Buscar la estrategia que bata al mercado.** 25 años de SPIVA y nuestros propios 21 años
   apuntan igual.
2. **Fiarse de un backtest sin validación fuera de muestra.** El caso del dual momentum es el aviso
   más caro que hay.
3. **Optimizar parámetros mirando resultados.** Es cómo se fabrica un dual momentum propio.

**Lo que queda genuinamente abierto:**

- **Value y quality** exigen datos fundamentales con fecha de publicación real (*point-in-time*),
  que son de pago. Sin ellos, cualquier intento tendría look-ahead.
- **El LLM leyendo información actual para decidir hacia adelante** no tiene precedente que
  consultar. No hay literatura porque es reciente. Por eso la única forma de saberlo es la historia
  4 de la feature 003: registrar lo estimado y compararlo con lo que pase.

---

## Fuentes

- [SPIVA Mid-Year 2025 Results Around the World — S&P Dow Jones Indices](https://www.indexologyblog.com/2025/11/12/spiva-mid-year-2025-results-around-the-world/)
- [SPIVA U.S. Persistence Scorecard Year-End 2025](https://www.spglobal.com/spdji/en/spiva/article/us-persistence-scorecard/)
- [Momentum factor investing: Evidence and evolution (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5561720)
- [Factor Indexing Through the Decades — MSCI](https://www.msci.com/downloads/web/msci-com/research-and-insights/paper/factor-indexing-through-the-decades/factor-indexing-through-the-decades.pdf)
- [Deep Dive: Low-volatility investing — The Evidence-Based Investor](https://www.evidenceinvestor.com/post/low-volatility-investing)
- [Dual Momentum Post-Publication Performance — Price Action Lab](https://www.priceactionlab.com/Blog/2023/03/dual-momentum/)
- [Momentum and liquidity in cryptocurrencies (arXiv)](https://arxiv.org/pdf/1904.00890)
- [Cryptocurrency Trading: A Comprehensive Survey (arXiv)](https://arxiv.org/pdf/2003.11352)
- [Navigating the factor zoo around the world (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8074275/)
