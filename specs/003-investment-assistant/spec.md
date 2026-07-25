# Feature Specification: Asistente de Inversión

**Feature Branch**: `003-investment-assistant`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description: "Decisión asistida por LLM, análisis de activos y ejecución real con salvaguardas. El operador no es experto en inversión y quiere el flujo más simple posible: pedir que se invierta, ver una simulación estimada, y poder pasar a dinero real conectando una cartera de cripto o una API de bolsa."

## User Scenarios & Testing *(mandatory)*

El actor es el **operador**: sabe lo que quiere conseguir con su dinero, pero no es experto en
inversión. Por eso el sistema tiene dos obligaciones que van juntas: hacerle el camino fácil, y no
aprovecharse de que no puede detectar por sí mismo cuándo le están contando algo que no es.

### User Story 1 - Pedir una propuesta y ver qué habría pasado (Priority: P1)

El operador dice cuánto quiere invertir y con qué frecuencia. El sistema propone una cartera
concreta, la simula sobre el histórico disponible y le enseña el resultado con sus advertencias.
No hay que elegir estrategias ni parámetros: eso es lo que el operador no sabe hacer.

**Why this priority**: es el flujo entero visto desde fuera. Sin esto, todo lo construido exige
saber qué pedirle.

**Independent Test**: se pide una propuesta con un importe y una periodicidad, y se obtiene una
cartera concreta acompañada de su simulación y sus avisos.

**Acceptance Scenarios**:

1. **Given** un importe y una periodicidad, **When** el operador pide una propuesta, **Then**
   recibe una cartera concreta, la simulación de qué habría pasado con ella, y los avisos de
   calidad de los datos usados.
2. **Given** una propuesta, **When** el operador la consulta, **Then** puede ver por qué se
   propuso cada activo, en lenguaje que no exige saber de inversión.
3. **Given** una simulación con pocas operaciones o poco histórico, **When** se presenta,
   **Then** se marca como no concluyente antes que cualquier cifra.
4. **Given** cualquier propuesta, **When** se muestra su resultado, **Then** aparece siempre la
   comparación contra no hacer nada.

---

### User Story 2 - Que el LLM elija, y saber si acierta (Priority: P1)

El operador quiere que un LLM seleccione los activos y decida cuándo salir, en vez de una regla
fija. El sistema lo permite — y lo mide con la misma vara que a las demás estrategias.

**Why this priority**: es la petición explícita del operador, y también el mayor riesgo de la
feature. Un LLM que decide sin ser medido es una caja negra que gasta dinero real.

**Independent Test**: se evalúa una decisión del LLM con el mismo motor y las mismas métricas que
una estrategia de reglas fijas, y ambos resultados se pueden poner uno al lado del otro.

**Acceptance Scenarios**:

1. **Given** una decisión tomada por el LLM, **When** se evalúa, **Then** produce un informe con
   exactamente las mismas métricas obligatorias que una estrategia de reglas.
2. **Given** el LLM y una estrategia de reglas, **When** se comparan sobre los mismos datos,
   **Then** el resultado permite decir cuál lo hizo mejor sin ambigüedad.
3. **Given** una decisión del LLM, **When** el operador la consulta, **Then** ve el razonamiento
   que la acompañó, no solo el veredicto.
4. **Given** un LLM que no responde o responde algo inválido, **When** ocurre, **Then** el
   sistema lo trata como fallo y no inventa una decisión por su cuenta.
5. **Given** cualquier presentación de resultados del LLM, **When** se muestra, **Then** no se
   afirma que tenga capacidad de predicción, porque no está demostrada.

---

### User Story 3 - Saber qué hay detrás de cada activo (Priority: P2)

Antes de poner dinero, el operador quiere entender en qué lo pone: qué empresa o entidad hay
detrás, a qué se dedica, qué tamaño tiene y qué riesgos se le conocen.

**Why this priority**: es lo que convierte una lista de siglas en una decisión informada. Va
después de P1 porque sin propuesta no hay nada que analizar.

**Independent Test**: se pide el análisis de un activo y se obtiene una descripción de la entidad
que hay detrás, con la fecha y el origen de cada dato.

**Acceptance Scenarios**:

1. **Given** un activo, **When** el operador pide su análisis, **Then** obtiene qué representa,
   a qué se dedica la entidad, su tamaño y los riesgos que se le conocen.
2. **Given** un análisis, **When** incluye escenarios sobre el futuro, **Then** se presentan
   explícitamente como escenarios y **no** como predicciones.
3. **Given** un dato de la entidad, **When** se muestra, **Then** consta de cuándo es y de dónde
   sale.
4. **Given** un activo sin entidad detrás (una materia prima, un índice), **When** se analiza,
   **Then** se explica qué es en lugar de inventar una empresa.

---

### User Story 4 - Comparar lo estimado con lo que pasó (Priority: P2)

El operador quiere saber si las estimaciones del sistema se parecen a la realidad. No qué habría
pasado en el pasado, sino si lo que el sistema dijo que pasaría, pasó.

**Why this priority**: es la única forma de saber si las decisiones del LLM valen algo fuera del
backtest. Sin esto, el sistema nunca aprende que se equivoca.

**Independent Test**: se registra una propuesta con su estimación, pasa el tiempo, y se compara
lo estimado con el resultado real.

**Acceptance Scenarios**:

1. **Given** una propuesta, **When** se emite, **Then** su estimación queda registrada con fecha
   y no se puede modificar después.
2. **Given** una estimación registrada y datos posteriores, **When** se comparan, **Then** se
   obtiene la diferencia entre lo estimado y lo ocurrido.
3. **Given** un historial de estimaciones, **When** se consulta, **Then** se ve si el sistema
   tiende a acertar, a quedarse corto o a pasarse.
4. **Given** una estimación que resultó mala, **When** se consulta el historial, **Then** sigue
   ahí: los errores no se borran.

---

### User Story 5 - Pasar a dinero real (Priority: P3)

El operador decide invertir de verdad. Conecta su cartera de cripto o su cuenta de bolsa y el
sistema ejecuta las órdenes.

**Why this priority**: es lo último a propósito. Todo lo anterior existe para que esta decisión se
tome con información. Un sistema que ejecuta antes de poder medirse es un generador de pérdidas.

**Independent Test**: con las credenciales configuradas y el modo real activado explícitamente, se
ejecuta una orden y se registra; sin esas dos condiciones, no se ejecuta nada.

**Acceptance Scenarios**:

1. **Given** el sistema recién instalado, **When** se usa, **Then** está en modo simulación y
   ninguna orden real puede salir.
2. **Given** el modo simulación, **When** se intenta ejecutar una orden real, **Then** se rechaza
   y se explica qué haría falta para hacerlo de verdad.
3. **Given** el modo real activado y credenciales válidas, **When** el sistema propone una orden,
   **Then** espera confirmación explícita del operador antes de enviarla.
4. **Given** una orden confirmada y enviada, **When** se completa, **Then** queda registrada con
   lo que se pidió y lo que realmente ocurrió.
5. **Given** una diferencia entre lo pedido y lo ejecutado, **When** ocurre, **Then** se comunica
   al operador en lugar de darse por buena.

---

### Edge Cases

- **El LLM propone un activo que no existe** o del que no hay histórico descargado.
- **El LLM devuelve algo que no se entiende**: texto libre donde se esperaba una decisión.
- **El LLM se contradice** entre la decisión y su explicación.
- **El proveedor de LLM no responde**, tarda demasiado o agota la cuota.
- **Dos ejecuciones idénticas dan decisiones distintas**, porque el LLM no es determinista.
- **El operador activa el modo real por error** o con credenciales de simulación.
- **La orden se ejecuta a un precio muy distinto** del estimado.
- **La orden se ejecuta solo en parte**, o el mercado está cerrado al enviarla.
- **El saldo real no coincide** con lo que el sistema cree que hay.
- **La conexión se cae con una orden enviada** y sin confirmación de si se ejecutó.
- **El operador pide invertir más de lo que tiene.**
- **Un activo deja de cotizar** o el exchange lo retira mientras se tiene posición.
- **El análisis de una entidad usa datos publicados después** del momento simulado.

## Requirements *(mandatory)*

### Functional Requirements

**Propuesta y simulación (US1)**

- **FR-001**: El sistema MUST aceptar un importe y una periodicidad y devolver una cartera
  concreta con los activos y las cantidades.
- **FR-002**: Toda propuesta MUST ir acompañada de la simulación de qué habría pasado con ella
  sobre el histórico disponible.
- **FR-003**: Toda simulación MUST incluir las seis métricas obligatorias de la feature 001 y la
  comparación contra no hacer nada.
- **FR-004**: El sistema MUST explicar por qué propone cada activo en lenguaje comprensible para
  alguien que no sabe de inversión.
- **FR-005**: El sistema MUST NOT exigir al operador elegir estrategias ni parámetros para obtener
  una propuesta.

**El LLM como estrategia (US2)**

- **FR-006**: Las decisiones del LLM MUST tomarse a través de la misma interfaz que las
  estrategias de reglas fijas.
- **FR-007**: Las decisiones del LLM MUST poder evaluarse con el mismo motor y las mismas métricas
  que cualquier otra estrategia.
- **FR-008**: El sistema MUST permitir comparar al LLM contra estrategias de reglas y contra no
  hacer nada, sobre los mismos datos.
- **FR-009**: Durante una simulación, el LLM MUST recibir únicamente información disponible en el
  instante simulado.
- **FR-010**: El sistema MUST advertir de que el conocimiento previo del LLM puede incluir hechos
  posteriores al periodo simulado, y de que esa contaminación **no se puede eliminar**, solo
  acotar.
- **FR-011**: Una respuesta del LLM que no se pueda interpretar MUST tratarse como fallo. El
  sistema MUST NOT inventar una decisión ni elegir por defecto.
- **FR-012**: El sistema MUST registrar el razonamiento que acompaña a cada decisión del LLM.
- **FR-013**: El sistema MUST NOT presentar al LLM como capaz de predecir precios.
- **FR-014**: El sistema MUST registrar que dos ejecuciones del LLM pueden diferir, y hacer
  explícito que eso rompe la reproducibilidad que sí tienen las estrategias de reglas.

**Análisis de activos (US3)**

- **FR-015**: El sistema MUST describir, para cada activo, qué representa y qué entidad hay detrás.
- **FR-016**: El análisis MUST incluir tamaño, actividad y riesgos conocidos cuando exista una
  entidad identificable.
- **FR-017**: Todo dato del análisis MUST indicar su fecha y su origen.
- **FR-018**: Los escenarios sobre el futuro MUST presentarse como escenarios, nunca como
  predicciones ni como cifras esperadas.
- **FR-019**: Para activos sin entidad detrás, el sistema MUST explicar qué son en lugar de
  atribuirles una.

**Estimado contra real (US4)**

- **FR-020**: Toda propuesta MUST registrar su estimación con fecha en el momento de emitirse.
- **FR-021**: Una estimación registrada MUST NOT poder modificarse después.
- **FR-022**: El sistema MUST poder comparar cualquier estimación pasada con lo que ocurrió
  después.
- **FR-023**: El sistema MUST conservar las estimaciones fallidas y mostrarlas junto a las
  acertadas.
- **FR-024**: El historial MUST permitir ver si el sistema tiende a sobreestimar o a subestimar.

**Ejecución real (US5) — Principio I**

- **FR-025**: El sistema MUST arrancar en modo simulación. La ausencia de configuración significa
  simulación.
- **FR-026**: Activar el modo real MUST requerir una acción afirmativa explícita del operador
  **y** credenciales distintas de las de simulación.
- **FR-027**: El modo real MUST NOT poder activarse por configuración heredada, por un valor por
  defecto, ni por ningún proceso automático.
- **FR-028**: Toda orden real MUST requerir confirmación explícita del operador **para esa orden**,
  no una autorización general.
- **FR-029**: El sistema MUST NOT ejecutar órdenes reales de forma desatendida bajo ninguna
  configuración.
- **FR-030**: Toda orden enviada MUST registrarse con lo solicitado y lo realmente ejecutado.
- **FR-031**: Cualquier diferencia entre lo pedido y lo ejecutado MUST comunicarse al operador.
- **FR-032**: El sistema MUST verificar el modo en el momento de enviar la orden, no solo al
  arrancar.
- **FR-033**: Las credenciales MUST leerse del entorno y MUST NOT almacenarse en el repositorio.
- **FR-034**: Ningún mensaje, registro ni informe MUST incluir una credencial.
- **FR-035**: Ante pérdida de conexión con una orden enviada, el sistema MUST marcarla como estado
  desconocido y MUST NOT asumir que se ejecutó ni que falló.

**Verificabilidad**

- **FR-036**: Los tests MUST ejecutarse sin red y sin llamadas reales a un LLM.
- **FR-037**: El acceso al LLM y al bróker MUST estar aislado tras interfaces sustituibles.
- **FR-038**: MUST existir una comprobación automática de que ninguna orden real puede salir en
  modo simulación.

### Key Entities

- **Perfil de inversión**: lo que el operador quiere — importe, periodicidad y tolerancia a
  perder.
- **Propuesta**: cartera concreta con activos y cantidades, su justificación y su simulación.
- **Estimación registrada**: lo que el sistema esperaba en el momento de proponer. Inmutable.
- **Decisión del LLM**: qué eligió, cuándo, con qué información y con qué razonamiento.
- **Análisis de activo**: qué representa, quién está detrás, tamaño, actividad, riesgos y fecha de
  los datos.
- **Modo de operación**: simulación (por defecto) o real. Con credenciales separadas.
- **Orden**: lo que se pidió ejecutar, lo que se ejecutó realmente, y su estado.
- **Registro de ejecución**: histórico auditable de todo lo enviado a un mercado real.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un operador sin conocimientos de inversión obtiene una propuesta con simulación
  indicando solo importe y periodicidad.
- **SC-002**: El 100% de las decisiones del LLM se evalúan con las mismas métricas que las
  estrategias de reglas, y ambas pueden compararse sobre los mismos datos.
- **SC-003**: El 100% de las respuestas no interpretables del LLM se tratan como fallo; ninguna
  produce una decisión inventada.
- **SC-004**: Ninguna presentación de resultados afirma capacidad de predicción.
- **SC-005**: El 100% de los datos del análisis de activos indica fecha y origen.
- **SC-006**: El 100% de las estimaciones emitidas queda registrado y es comparable con lo que
  ocurrió después.
- **SC-007**: Ninguna estimación registrada puede alterarse a posteriori.
- **SC-008**: Con el sistema recién instalado, el 100% de los intentos de ejecutar una orden real
  se rechaza.
- **SC-009**: El 100% de las órdenes reales enviadas fue confirmado explícitamente por el operador
  para esa orden concreta.
- **SC-010**: Ninguna credencial aparece en el repositorio, en los registros ni en los informes.
- **SC-011**: El 100% de la suite de tests se ejecuta sin red y sin llamadas reales a un LLM.
- **SC-012**: El 100% de las órdenes enviadas queda registrado con lo pedido y lo ejecutado.

## Assumptions

- **Un LLM no predice precios.** No hay evidencia de que un modelo de lenguaje anticipe el
  movimiento de los mercados. Esta feature le da voz y le mide los resultados; **no** asume que
  acierte. Si en las comparaciones sale peor que una regla fija, ese es el resultado.
- **La contaminación de conocimiento del LLM no se puede eliminar.** Un modelo entrenado en 2026
  "sabe" lo que pasó en 2020, así que cualquier backtest sobre periodos anteriores a su corte de
  entrenamiento está contaminado de una forma que ningún diseño corrige. Se puede acotar (no darle
  fechas, no darle nombres) y se debe advertir, pero un resultado bueno del LLM sobre el pasado no
  es evidencia de nada. **Solo la comparación con resultados futuros reales (US4) lo es.**
- **Ejecución real solo con confirmación por orden.** No hay modo desatendido. Es una decisión de
  diseño, no una limitación: el sistema lleva nueve defectos encontrados al usarlo, y ninguno se
  vio leyendo el código.
- **Cripto primero para la ejecución.** Los exchanges de cripto permiten operar por API con menos
  fricción que los brókers de bolsa, que suelen exigir contratos y aprobaciones.
- **Sin asesoramiento financiero.** El sistema informa y simula; no recomienda formalmente ni
  sustituye a un asesor.
- **Datos fundamentales del proveedor gratuito.** Con sus límites: los datos actuales no sirven
  para analizar el pasado sin incurrir en look-ahead.
- **Sin apalancamiento, sin cortos, sin derivados.** Fuera de alcance en v1.
- **Contexto de gobierno**: constitución v1.0.0. FR-025..FR-035 derivan del Principio I (NO
  NEGOCIABLE); FR-009 y FR-010 del Principio II; FR-006..FR-008 del Principio V.
