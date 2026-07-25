# Phase 0 — Research: Motor de Backtesting

**Feature**: 001-backtest-engine | **Fecha**: 2026-07-25

Decisiones técnicas que resuelven los puntos abiertos del Technical Context. Cada una registra
qué se eligió, por qué, y qué se descartó.

---

## R1. Cómo hacer el aislamiento temporal *estructural* (FR-002..FR-004)

**Decisión**: la estrategia nunca recibe la serie completa. En cada paso el motor le entrega un
objeto `MarketView` que envuelve la serie y un índice de corte, y cuya interfaz pública solo puede
devolver datos hasta ese corte. Cualquier petición de un periodo posterior lanza
`LookAheadError`.

**Rationale**: es la única de las opciones evaluadas que cumple "estructural" sin coste
cuadrático. La estrategia no puede leer el futuro porque no tiene ninguna referencia pública a él,
y el intento produce un fallo ruidoso en vez de un número.

**Alternativas consideradas**:
- *Pasar una copia truncada de la serie en cada paso*: perfectamente hermético, pero O(n²) en
  memoria y tiempo — inviable con 100.000 periodos.
- *Pasar la serie completa con la convención de no mirar más allá del índice*: es exactamente lo
  que el Principio II prohíbe. Convierte el invariante en disciplina del autor de la estrategia.
- *Generador que emite ventanas por streaming*: válido, pero impide a la estrategia consultar
  histórico arbitrario hacia atrás (necesario para medias móviles largas) sin mantener su propio
  buffer, lo que empuja complejidad a cada estrategia.

**Límite honesto que asumimos**: en Python no existe encapsulación real — una estrategia
determinada a hacer trampa puede alcanzar el atributo interno de `MarketView` por introspección.
La garantía es *estructural en la interfaz pública*, no un sandbox. Por eso FR-004 y SC-003 exigen
además el test de la estrategia tramposa: la barrera de diseño se complementa con una barrera de
verificación. No afirmamos más protección de la que hay.

---

## R2. Núcleo numérico: numpy en el motor, pandas solo en la frontera

**Decisión**: el bucle de simulación opera sobre arrays `numpy` planos. `pandas` se usa
exclusivamente en la capa de datos (lectura de CSV/Parquet, validación, alineación temporal) y
nunca dentro del bucle.

**Rationale**: iterar fila a fila un `DataFrame` es entre uno y dos órdenes de magnitud más lento
que indexar un array de numpy, y SC-001 exige un veredicto en menos de un minuto sobre ~100.000
periodos. Mantener pandas en la frontera da la comodidad de su I/O sin pagar su coste por paso.

**Alternativas consideradas**:
- *pandas en todo*: más simple de escribir, riesgo real de incumplir SC-001 y tentación de usar
  operaciones vectorizadas sobre la serie completa — justo el patrón que produce look-ahead.
- *polars*: más rápido que pandas y con API más limpia, pero aporta poco aquí (el cuello de
  botella es el bucle secuencial, no la carga) y es menos conocido en el dominio financiero.
- *Solo stdlib*: evita dependencias, pero reimplementar carga, validación y estadística es trabajo
  sin retorno.

---

## R3. Representación del dinero: `Decimal` en contabilidad, `float` en indicadores

**Decisión**: caja, comisiones, PnL realizado y todas las cifras del informe usan
`decimal.Decimal`. Precios de mercado e indicadores (medias móviles) usan `float64`.

**Rationale**: la contabilidad tiene pocas operaciones (una por transacción) y es donde el error
de redondeo es visible y molesto para el operador. Los indicadores tienen millones de operaciones
y una tolerancia natural: una media móvil no necesita exactitud decimal. Separar los dos dominios
da exactitud donde se lee y velocidad donde se calcula.

**Alternativas consideradas**:
- *float en todo*: más rápido y más simple; el error acumulado es despreciable frente al slippage,
  pero produce cifras como `10000.000000000002` en el informe.
- *Decimal en todo*: exacto, entre 10× y 100× más lento en el cálculo de indicadores. Pone en
  riesgo SC-001 sin beneficio real.
- *Enteros de mínima unidad (céntimos/satoshis)*: exacto y rápido, pero cada mercado tiene una
  precisión distinta y las conversiones se convierten en fuente de errores propios.

**Nota sobre FR-005 (reproducibilidad)**: `float` es perfectamente determinista para una misma
secuencia de operaciones en la misma plataforma. El riesgo de irreproducibilidad no viene del tipo
numérico sino de fuentes de no-determinismo (orden de iteración, aleatoriedad, concurrencia), que
se prohíben explícitamente en el diseño.

---

## R4. Calendario de mercado: interfaz propia con adaptadores (FR-020..FR-023)

**Decisión**: definir un `MarketCalendar` propio (protocolo mínimo: ¿está abierto en este
instante?, ¿cuál es el siguiente instante negociable?) con dos implementaciones: `Continuous24x7`
para cripto y un adaptador sobre la librería `exchange_calendars` para bolsa.

**Rationale**: el motor debe depender de una abstracción nuestra, no de una librería externa —
así el Principio V (motor agnóstico) se sostiene y cambiar de proveedor de calendarios no toca el
núcleo. Los festivos bursátiles son datos históricos irregulares que no tiene sentido mantener a
mano.

**Alternativas consideradas**:
- *Implementar los festivos a mano*: fuente garantizada de errores silenciosos; un festivo mal
  puesto produce operaciones fantasma en un día cerrado.
- *Acoplar el motor directamente a `exchange_calendars`*: obligaría a que cripto finja ser un
  calendario bursátil abierto siempre, e invierte la dependencia.
- *Derivar el calendario de los datos presentes*: tentador y peligroso — no permite distinguir un
  cierre legítimo de un dato ausente, que es justo lo que FR-021 exige distinguir.

---

## R5. Interfaz de estrategia: `typing.Protocol` (FR-017, FR-018)

**Decisión**: la estrategia se define como un `Protocol` estructural con un método que recibe un
`MarketView` y devuelve una `Signal` opcional. No se exige heredar de ninguna clase base.

**Rationale**: el tipado estructural permite que cualquier objeto compatible sirva como estrategia
— reglas fijas, envoltorio de un modelo de IA, o un stub de test — sin importar de dónde herede.
`pyright` verifica la conformidad en tiempo de análisis. Añadir una estrategia no toca el motor
(FR-018) porque el motor solo conoce el protocolo.

**Alternativas consideradas**:
- *Clase base abstracta (ABC)*: obliga a heredar, lo que estorba al envolver un modelo externo.
- *Convención de duck typing sin tipo*: sin verificación estática; los errores aparecen a mitad de
  un backtest largo.
- *Registro por decorador*: útil para descubrimiento automático, innecesario en v1 y añade estado
  global.

---

## R6. Formato de datos de entrada

**Decisión**: CSV como formato obligatorio de v1, Parquet como opcional. Ambos se leen tras un
esquema explícito de columnas y se validan antes de simular (FR-015).

**Rationale**: CSV es universal, inspeccionable a ojo y diffeable — importante para depurar un
backtest que da un resultado sospechoso. Parquet aporta tamaño y velocidad cuando la serie crece,
y soportarlo cuesta poco al usar pandas en la frontera.

**Alternativas consideradas**:
- *Solo Parquet*: mejor rendimiento pero ilegible sin herramientas; peor experiencia de depuración.
- *Base de datos*: infraestructura desproporcionada para ficheros de histórico inmutables.

---

## R7. Estrategia de pruebas

**Decisión**: `pytest` como base, más `hypothesis` para los invariantes del motor.

**Rationale**: los invariantes de este dominio son property-based por naturaleza — "la caja nunca
es negativa", "el drawdown máximo nunca es positivo", "la suma de resultados por operación
reconstruye el resultado neto" (SC-007). Un property test los prueba contra series generadas que
ningún caso escrito a mano se habría inventado.

Pruebas específicas exigidas por la constitución:
- **Estrategia tramposa** que intenta leer el futuro → debe lanzar `LookAheadError` (SC-003).
- **Doble ejecución** idéntica → informes idénticos (SC-006, FR-005).
- **Serie sintética con resultado calculado a mano** → valida las métricas de extremo a extremo.

**Sobre mutation testing**: la constitución lo contempla como gate de calidad de los tests. En esta
máquina (Windows nativo) `mutmut` se instala pero **no ejecuta**; requiere WSL o contenedor. Queda
fuera del bucle de desarrollo de esta feature y se decidirá al cerrar el lote, con ejecución real
verificada antes de darlo por activo.

---

## R8. Versión de Python y gestión de dependencias

**Decisión**: Python **3.13**, gestionado con `uv` (ya presente, v0.11.16). Dependencias fijadas en
`pyproject.toml` con `uv.lock` commiteado.

**Rationale**: la máquina tiene 3.11.9 y 3.14.0 instalados; `uv` descarga 3.13 de forma
transparente. 3.13 es el punto dulce actual: mejoras de tipado sobre 3.11 y ecosistema científico
(numpy, pandas, exchange_calendars) plenamente empaquetado, cosa que en 3.14 aún puede faltar en
alguna dependencia transitiva. El lock commiteado sostiene la reproducibilidad de FR-005 más allá
del código.

**Alternativas consideradas**:
- *3.11 (ya instalado)*: cero fricción de instalación, pero renuncia a tres versiones de mejoras.
- *3.14 (ya instalado)*: lo más reciente; riesgo real de wheels ausentes en dependencias
  transitivas y de ser el primero en encontrar los fallos.

**A verificar en implementación**: que las tres dependencias resuelvan e instalen en 3.13 con una
ejecución real. Instalado no significa funcional.

---

## Resumen de dependencias

| Dependencia | Uso | Justificación |
|---|---|---|
| `numpy` | Núcleo del bucle de simulación | Rendimiento (SC-001) |
| `pandas` | Carga y validación de series | I/O y validación en la frontera |
| `exchange_calendars` | Calendario bursátil | Festivos históricos, tras adaptador propio |
| `pytest` | Suite de tests | Gate de la constitución |
| `hypothesis` | Property tests de invariantes | Invariantes del motor |
| `ruff` · `pyright` | Lint y tipos | Gates de la constitución |

Sin dependencias de red, de broker ni de exchange: el motor es simulación pura (FR-006) y no puede
conectarse a nada aunque quisiera.
