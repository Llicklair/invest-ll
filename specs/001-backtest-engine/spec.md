# Feature Specification: Motor de Backtesting

**Feature Branch**: `001-backtest-engine`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description: "Motor de backtesting — el medidor sobre el que se apoya todo el sistema. Dada una serie histórica de precios y una estrategia, simular qué habría pasado si esa estrategia hubiera operado durante ese periodo, y devolver un veredicto honesto sobre si habría ganado o perdido dinero."

## Clarifications

### Session 2026-07-25

- Q: ¿Qué mercado se usa como fuente de datos inicial del backtester? → A: Ambos a la vez (cripto y bolsa)
- Q: ¿A qué precio se ejecuta la orden simulada tras una señal? → A: A la apertura de la vela siguiente
- Q: ¿Cuánto capital compromete cada operación simulada? → A: Una fracción del capital disponible, configurable
- Q: ¿Cómo se cierra una posición abierta? → A: Por señal de la estrategia, más stop-loss y take-profit opcionales gestionados por el motor
- Q: ¿Qué granularidad temporal maneja el motor? → A: Agnóstico; cada serie declara su intervalo

## User Scenarios & Testing *(mandatory)*

El actor de todas las historias es el **operador**: la persona que diseña estrategias de inversión
y necesita saber si funcionan antes de arriesgar dinero.

### User Story 1 - Medir una estrategia sobre el pasado (Priority: P1)

El operador tiene una idea de estrategia (por ejemplo, "compra cuando la media corta cruza por
encima de la media larga"). Quiere saber qué habría pasado si la hubiera aplicado durante el
último año, sin arriesgar ni un euro. Aporta un periodo histórico y una estrategia, y recibe un
informe con el resultado económico y las métricas que permiten juzgarlo.

**Why this priority**: Es la razón de existir del componente. Sin esto no hay nada que medir y
ninguna otra historia tiene sentido. Es el MVP completo por sí solo.

**Independent Test**: Se prueba de extremo a extremo aportando una serie de precios conocida y
una estrategia de cruce de medias, y comprobando que el informe resultante refleja las
operaciones esperadas y su resultado económico.

**Acceptance Scenarios**:

1. **Given** una serie histórica de precios y una estrategia de cruce de medias, **When** el
   operador lanza la evaluación, **Then** recibe un informe con resultado económico neto,
   expectancy por operación, drawdown máximo, número de operaciones, coste total de comisiones
   y slippage, y win rate.
2. **Given** una estrategia que nunca genera señal de compra, **When** se evalúa, **Then** el
   informe indica cero operaciones y se etiqueta como **no concluyente**, no como resultado
   neutro o positivo.
3. **Given** una estrategia rentable antes de costes pero cuyas ganancias no cubren comisiones y
   slippage, **When** se evalúa, **Then** el informe muestra resultado neto negativo y el coste
   total que lo causa.
4. **Given** un resultado con win rate alto pero expectancy negativa, **When** se presenta el
   informe, **Then** el win rate no aparece como indicador de éxito y el veredicto refleja la
   pérdida neta.

---

### User Story 2 - Confiar en que el medidor no miente (Priority: P2)

El operador necesita poder confiar en el veredicto. La forma más común de que un backtest engañe
es dejar que la estrategia use información que en el momento real no existía todavía. El operador
quiere una garantía demostrable de que eso no puede ocurrir.

**Why this priority**: Un medidor que se puede engañar es peor que no tener medidor, porque
produce confianza injustificada. Va después de P1 solo porque necesita que exista el motor para
poder demostrarse sobre él.

**Independent Test**: Se escribe una estrategia deliberadamente tramposa que intenta consultar
precios posteriores al instante simulado y se comprueba que el intento falla de forma visible en
lugar de producir un resultado excelente.

**Acceptance Scenarios**:

1. **Given** una estrategia que intenta acceder a precios posteriores al instante simulado,
   **When** se ejecuta la evaluación, **Then** el intento falla de forma explícita y el backtest
   no produce un resultado aparentemente válido.
2. **Given** cualquier estrategia en cualquier instante de la simulación, **When** solicita el
   histórico disponible, **Then** solo obtiene datos con marca temporal anterior o igual al
   instante que se está simulando.
3. **Given** el mismo conjunto de datos y la misma estrategia, **When** se evalúa dos veces,
   **Then** el resultado es idéntico.
4. **Given** una señal emitida a partir de un periodo cerrado, **When** se ejecuta la orden,
   **Then** el precio aplicado es el de apertura del periodo siguiente, no el de cierre del
   periodo que generó la señal.

---

### User Story 3 - Comparar estrategias con la misma vara (Priority: P3)

El operador quiere decidir entre varias estrategias — incluidas unas basadas en reglas fijas y
otras basadas en un modelo de IA. Necesita medirlas sobre exactamente los mismos datos y con
exactamente las mismas métricas para que la comparación signifique algo.

**Why this priority**: Es lo que convierte el motor en herramienta de decisión en vez de en
herramienta de medición aislada. Requiere P1 y se apoya en la confianza que da P2.

**Independent Test**: Se evalúan dos estrategias distintas sobre el mismo periodo y se comprueba
que ambas producen informes con la misma estructura de métricas, comparables entre sí.

**Acceptance Scenarios**:

1. **Given** dos estrategias con mecanismos internos distintos, **When** se evalúan sobre el
   mismo periodo, **Then** ambas producen informes con el mismo conjunto de métricas.
2. **Given** una estrategia nueva, **When** el operador la añade al sistema, **Then** no necesita
   modificar el motor de simulación para poder evaluarla.

---

### User Story 4 - Ver cuánto pesa la fricción (Priority: P3)

El operador quiere entender cuánto de su resultado se lo comen las comisiones y el slippage, y
comprobar si su estrategia sobrevive a condiciones de mercado menos favorables.

**Why this priority**: Es refinamiento sobre P1. Valioso para decidir, no imprescindible para
obtener un primer veredicto.

**Independent Test**: Se evalúa la misma estrategia con dos niveles de fricción distintos y se
comprueba que el resultado neto empeora al aumentar los costes.

**Acceptance Scenarios**:

1. **Given** una estrategia evaluada con comisiones bajas, **When** se reevalúa con comisiones
   más altas, **Then** el resultado neto empeora de forma proporcional al número de operaciones.
2. **Given** una configuración de costes, **When** se genera el informe, **Then** los parámetros
   de fricción aplicados aparecen explícitamente en él.

---

### Edge Cases

- **Serie con huecos**: qué ocurre cuando faltan periodos en el histórico por fallo de la fuente
  de datos. El motor debe informar del hueco, no interpolar en silencio.
- **Cierre legítimo vs dato perdido**: en un mercado con horario de sesión, la ausencia de datos
  durante la noche o un festivo es normal y no debe reportarse como anomalía; la ausencia de una
  vela dentro de la sesión sí.
- **Gap de apertura**: una posición mantenida durante el cierre puede reabrir a un precio muy
  distinto al de cierre. El resultado debe reflejar ese salto, incluido cuando es adverso.
- **Señal fuera de horario**: qué ocurre cuando la estrategia emite una señal en un instante en
  que el mercado está cerrado. La ejecución se difiere a la siguiente apertura disponible.
- **Señal en el último periodo**: una señal emitida en la última vela de la serie no tiene
  apertura siguiente donde ejecutarse; no debe producir una operación fantasma.
- **Posición abierta al terminar la serie**: cómo se valora una posición que sigue abierta cuando
  se acaba el histórico, sin contarla como ganancia realizada.
- **Serie demasiado corta**: cuando no hay suficiente historia para que la estrategia calcule sus
  medias, la evaluación no debe operar a ciegas durante ese arranque.
- **Muestra insuficiente**: un backtest con muy pocas operaciones no permite conclusiones
  estadísticas; debe etiquetarse como no concluyente aunque el resultado sea positivo.
- **Capital agotado**: qué ocurre cuando una secuencia de pérdidas consume el capital simulado.
- **Orden rechazada**: la simulación debe poder representar que una orden no se ejecuta y que la
  estrategia siga funcionando sin asumir que su posición cambió.
- **Ejecución parcial**: una orden ejecutada solo en parte debe reflejarse como tal.
- **Precios anómalos**: valores cero, negativos o saltos extremos en los datos de entrada.
- **Señales contradictorias**: la estrategia pide vender sin tener posición abierta, o comprar
  teniendo ya el capital comprometido.

## Requirements *(mandatory)*

### Functional Requirements

**Simulación y aislamiento temporal**

- **FR-001**: El sistema MUST simular la ejecución de una estrategia sobre una serie histórica de
  precios, avanzando instante a instante en orden cronológico.
- **FR-002**: El sistema MUST exponer a la estrategia únicamente los datos con marca temporal
  anterior o igual al instante simulado.
- **FR-003**: El aislamiento temporal MUST ser estructural: la estrategia no debe recibir los
  datos futuros en ninguna forma, en lugar de recibirlos con la instrucción de no usarlos.
- **FR-004**: El sistema MUST fallar de forma visible ante un intento de acceso a datos
  posteriores al instante simulado, en lugar de devolver un resultado.
- **FR-005**: Dos evaluaciones de la misma estrategia sobre los mismos datos MUST producir
  resultados idénticos.
- **FR-024**: Una señal emitida a partir de un periodo cerrado MUST ejecutarse al precio de
  apertura del periodo siguiente disponible, nunca al precio de cierre del periodo que la generó.
- **FR-025**: El sistema MUST NOT ofrecer un modo de ejecución al cierre del propio periodo de la
  señal, por asumir un precio desconocido en el momento de decidir.
- **FR-006**: El sistema MUST NOT ejecutar órdenes reales ni conectarse a ningún broker o
  exchange para operar. Es simulación pura.

**Modelo de mercado y fricción**

- **FR-007**: Toda orden simulada MUST aplicar comisiones y slippage según la configuración de
  fricción vigente.
- **FR-008**: Los parámetros de fricción MUST ser explícitos y aparecer en el informe. El sistema
  MUST NOT aplicar coste cero por defecto silencioso.
- **FR-009**: El sistema MUST poder representar órdenes rechazadas y ejecuciones parciales, y
  reflejarlas en el estado de la posición.
- **FR-010**: El sistema MUST rechazar operaciones que excedan el capital simulado disponible.
- **FR-026**: Cada entrada en mercado MUST comprometer una fracción configurable del capital
  disponible en ese instante. La fracción MUST ser explícita y aparecer en el informe.
- **FR-027**: El tamaño de posición MUST ser competencia del motor, no de la estrategia: dos
  estrategias distintas evaluadas con la misma configuración MUST dimensionar igual sus entradas,
  para que sus métricas sean comparables.
- **FR-028**: El motor MUST cerrar una posición cuando la estrategia lo indique, y además MUST
  soportar stop-loss y take-profit opcionales aplicados por el propio motor.
- **FR-029**: Cuando un nivel de stop-loss o take-profit quede comprendido dentro del rango de un
  periodo, el sistema MUST valorar la salida con la convención pesimista: si tanto el stop como el
  take son alcanzables en el mismo periodo, MUST asumirse que se ejecutó el stop.
- **FR-030**: Cuando el precio abra atravesando el nivel de stop, el sistema MUST ejecutar al
  precio de apertura real y no al nivel del stop, reflejando la pérdida efectiva del hueco.
- **FR-031**: El informe MUST distinguir las operaciones cerradas por señal de las cerradas por
  stop-loss y por take-profit.
- **FR-032**: Cada serie histórica MUST declarar su intervalo temporal, y el motor MUST operar con
  cualquier intervalo sin modificación.
- **FR-033**: Los parámetros temporales de una estrategia MUST expresarse en número de periodos y
  no en unidades de calendario, para que la misma estrategia sea evaluable con cualquier intervalo.
- **FR-034**: El sistema MUST rechazar una serie cuyas marcas temporales no correspondan al
  intervalo declarado.

**Informe de resultados**

- **FR-011**: Todo informe MUST incluir: resultado económico neto, expectancy por operación,
  drawdown máximo, número de operaciones, coste total de comisiones y slippage, y win rate.
- **FR-012**: El sistema MUST NOT presentar el win rate como criterio de éxito aislado.
- **FR-013**: El sistema MUST etiquetar como **no concluyente** todo resultado cuyo número de
  operaciones esté por debajo del umbral mínimo de significancia, con independencia de si el
  resultado económico es positivo.
- **FR-014**: El informe MUST incluir el registro de operaciones simuladas, de forma que el
  operador pueda auditar cómo se llegó al resultado.

**Datos e integración de estrategias**

- **FR-015**: El sistema MUST aceptar series históricas de precios y validarlas antes de simular,
  detectando huecos, precios no positivos y desorden cronológico.
- **FR-016**: El sistema MUST informar de los huecos detectados en la serie en lugar de rellenar
  los datos que faltan sin avisar.
- **FR-017**: Las estrategias MUST conectarse al motor mediante una interfaz común, idéntica para
  estrategias de reglas fijas y para estrategias basadas en modelos de IA.
- **FR-018**: Añadir una estrategia nueva MUST NOT requerir modificar el motor de simulación.
- **FR-019**: El sistema MUST incluir una estrategia de cruce de medias móviles como caso de
  referencia para validar el motor de extremo a extremo.
- **FR-020**: El sistema MUST soportar en v1 tanto mercados de negociación continua (cripto, 24/7)
  como mercados con horario de sesión y días no hábiles (bolsa), sobre el mismo motor de
  simulación.
- **FR-021**: Cada serie histórica MUST declarar el calendario de mercado que le aplica. El motor
  MUST distinguir entre un periodo sin datos por cierre legítimo del mercado y un hueco por dato
  ausente, y MUST NOT reportar el primero como anomalía.
- **FR-022**: El sistema MUST NOT emitir órdenes simuladas en instantes en que el mercado
  correspondiente está cerrado.
- **FR-023**: El sistema MUST representar el salto de precio entre el cierre de una sesión y la
  apertura de la siguiente, y aplicarlo a las posiciones mantenidas durante ese intervalo.

### Key Entities

- **Serie histórica de precios**: sucesión ordenada de observaciones de mercado de un activo, cada
  una con marca temporal y precios. Declara su intervalo temporal y el calendario de mercado que
  le aplica. Es la entrada del backtest.
- **Calendario de mercado**: define cuándo el mercado está abierto. Permite distinguir un cierre
  legítimo de un dato ausente, y aplica tanto a mercados continuos como a los de sesión.
- **Estrategia**: componente que, dado el histórico disponible hasta un instante, decide si emite
  una señal de operación. Su mecanismo interno (reglas o modelo) es irrelevante para el motor.
- **Señal**: intención de operar emitida por la estrategia en un instante concreto.
- **Orden simulada**: intento de ejecutar una señal, sujeto a fricción, y que puede ejecutarse
  completa, parcialmente o ser rechazada.
- **Operación**: ciclo completo de entrada y salida del mercado, con su resultado económico.
- **Posición**: exposición al mercado en un instante dado.
- **Configuración de fricción**: comisiones, slippage y reglas de rechazo aplicables.
- **Configuración de riesgo**: fracción del capital por entrada y niveles opcionales de stop-loss
  y take-profit. Es competencia del motor, no de la estrategia.
- **Informe de backtest**: veredicto completo — métricas obligatorias, parámetros aplicados,
  registro de operaciones y etiqueta de concluyente / no concluyente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El operador obtiene el veredicto completo de una estrategia sobre un año de
  histórico en menos de un minuto desde que lanza la evaluación.
- **SC-002**: El 100% de los informes emitidos incluye las seis métricas obligatorias. Ningún
  informe puede emitirse con métricas ausentes.
- **SC-003**: El 100% de los intentos de acceso a datos futuros por parte de una estrategia son
  detectados y bloqueados, verificado mediante una estrategia tramposa de control.
- **SC-004**: El 100% de los resultados por debajo del umbral mínimo de operaciones se presentan
  etiquetados como no concluyentes.
- **SC-005**: Añadir una estrategia nueva al sistema no requiere ninguna modificación del motor de
  simulación, verificado incorporando una segunda estrategia distinta a la de referencia.
- **SC-006**: Dos ejecuciones idénticas producen informes idénticos en el 100% de los casos.
- **SC-007**: El operador puede reconstruir cualquier cifra del informe a partir del registro de
  operaciones incluido en él.
- **SC-008**: El 100% de las órdenes simuladas se ejecuta a la apertura del periodo siguiente al
  que generó la señal, verificable en el registro de operaciones.
- **SC-009**: La misma estrategia se evalúa sin modificaciones sobre series de distinta
  granularidad y sobre series de mercado continuo y de mercado con sesión.
- **SC-010**: Ningún cierre legítimo de mercado se reporta como hueco de datos, y ningún dato
  ausente dentro de sesión pasa desapercibido.

## Assumptions

- **Mercados soportados**: la v1 cubre **cripto y bolsa simultáneamente** (decisión del operador,
  sesión 2026-07-25). El motor es agnóstico al mercado; las diferencias de calendario se resuelven
  en la capa de datos mediante el calendario declarado por cada serie (FR-020..FR-023). Un backtest
  concreto evalúa un solo activo de un solo mercado; "ambos" significa que el motor admite series
  de cualquiera de los dos, no que mezcle mercados en una misma simulación.
- **Un activo por backtest**: la v1 evalúa una estrategia sobre un único activo de un único
  mercado. Carteras de varios activos simultáneos quedan fuera de alcance.
- **Escala de referencia**: SC-001 se mide sobre una serie de hasta ~100.000 periodos, suficiente
  para un año de velas horarias o varias décadas de velas diarias.
- **Convención pesimista en la ambigüedad intra-periodo**: con datos en velas no se conoce el
  recorrido del precio dentro del periodo. Cuando stop-loss y take-profit son ambos alcanzables en
  la misma vela, se asume el stop. Es deliberadamente conservador: prefiere subestimar el
  resultado a inflarlo.
- **Una posición abierta a la vez**: no se contemplan posiciones simultáneas ni apalancamiento en
  la v1.
- **Solo posiciones largas**: la v1 no contempla ventas en corto.
- **Datos aportados, no descargados**: el motor consume series históricas que ya existen
  localmente. La descarga automática desde un proveedor externo es una feature separada.
- **Umbral de significancia**: se asume un mínimo de 30 operaciones para considerar un resultado
  concluyente, valor estándar de referencia estadística, ajustable por configuración.
- **Sin interfaz gráfica**: el informe se consume de forma programática o textual. Un panel visual
  queda fuera de alcance.
- **Sin optimización de parámetros**: la búsqueda automática de los mejores parámetros de una
  estrategia queda fuera de alcance; introduce riesgo de sobreajuste y merece su propia
  especificación con salvaguardas.
- **Contexto de gobierno**: esta especificación se somete a la constitución del proyecto v1.0.0.
  Los requisitos FR-002 a FR-006 derivan de principios marcados como NO NEGOCIABLES.
