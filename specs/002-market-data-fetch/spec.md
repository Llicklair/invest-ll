# Feature Specification: Descarga de Histórico Real de Mercado

**Feature Branch**: `002-market-data-fetch`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description: "Descarga y almacenamiento de histórico real de mercado — cripto y bolsa. Que el operador obtenga histórico real de un activo desde un proveedor público, lo guarde en local, y lo pueda alimentar directamente al motor de backtesting existente sin conversión manual."

## Clarifications

### Session 2026-07-25

- Q: ¿De dónde salen los datos históricos de cripto? → A: ccxt (interfaz unificada sobre múltiples exchanges, sin credenciales)
- Q: ¿De dónde salen los datos históricos de bolsa? → A: yfinance (gratis y con precios ajustados; no oficial, se asume su fragilidad)
- Q: ¿Qué precios se guardan para los activos de bolsa? → A: Solo los ajustados por splits y dividendos
- Q: ¿Cómo se detecta que el proveedor ha revisado datos ya guardados? → A: Comparando el solape que llegue de todos modos, más un comando explícito de verificación
- Q: ¿Qué hace el sistema ante una discrepancia? → A: Avisa y conserva lo local; la versión nueva se guarda aparte para poder compararlas

## User Scenarios & Testing *(mandatory)*

El actor sigue siendo el **operador**. Hasta ahora su motor solo ha medido series inventadas; esta
feature le da mercado de verdad.

### User Story 1 - Traerse el histórico de un activo (Priority: P1)

El operador quiere probar su estrategia sobre el Bitcoin del último año, o sobre una acción
concreta. Indica el activo, el periodo y la granularidad, y obtiene un histórico guardado en local
que el motor de backtesting consume tal cual, sin que él tenga que tocar ni convertir nada.

**Why this priority**: es la razón de existir de la feature. Sin esto, el motor sigue midiendo
ficción.

**Independent Test**: se pide el histórico de un activo con un proveedor simulado que devuelve
respuestas grabadas, y el fichero resultante se carga en el motor y produce un informe.

**Acceptance Scenarios**:

1. **Given** un activo, un periodo y una granularidad, **When** el operador solicita el histórico,
   **Then** obtiene un fichero local que el motor de backtesting carga sin conversión manual.
2. **Given** un histórico ya descargado, **When** se lanza un backtest sobre él, **Then** el
   informe resultante identifica el activo y el periodo reales.
3. **Given** un activo que el proveedor no reconoce, **When** se solicita, **Then** el sistema lo
   comunica con claridad y no deja un fichero a medias.
4. **Given** un periodo para el que el proveedor no tiene datos, **When** se solicita, **Then** se
   informa de que no hay datos, en lugar de devolver un fichero vacío que parezca válido.

---

### User Story 2 - No corromper un histórico ya usado (Priority: P2)

El operador ha evaluado una estrategia sobre un histórico. Meses después vuelve a descargar el
mismo periodo. Necesita la garantía de que los datos sobre los que ya decidió no han cambiado a su
espalda — y, si el proveedor los ha revisado, enterarse.

**Why this priority**: sin esto, dos backtests del "mismo" periodo pueden dar resultados distintos
sin explicación, y la reproducibilidad de la feature 001 se cae por debajo.

**Independent Test**: se descarga un rango, se altera la respuesta del proveedor simulado, se
vuelve a descargar y se comprueba que el cambio se detecta y se avisa en lugar de sobrescribirse.

**Acceptance Scenarios**:

1. **Given** un histórico guardado, **When** se redescarga el mismo rango y los datos coinciden,
   **Then** el fichero no cambia y no se avisa de nada.
2. **Given** un histórico guardado, **When** el proveedor devuelve valores distintos para fechas ya
   almacenadas, **Then** el sistema **avisa de la discrepancia** y no sobrescribe en silencio.
3. **Given** una descarga interrumpida a mitad, **When** el operador vuelve a intentarlo, **Then**
   no queda ningún fichero parcial que pueda confundirse con un histórico completo.

---

### User Story 3 - Ampliar sin volver a pedirlo todo (Priority: P2)

El operador ya tiene un año descargado y ahora quiere dos. No debería volver a pedir lo que ya
tiene, ni castigar al proveedor con peticiones innecesarias.

**Why this priority**: los proveedores públicos limitan las peticiones. Sin esto, ampliar un
histórico grande resulta lento o directamente se bloquea.

**Independent Test**: se descarga un rango, se amplía el periodo solicitado, y se comprueba que
solo se piden al proveedor las fechas que faltaban.

**Acceptance Scenarios**:

1. **Given** un rango ya descargado, **When** se pide un periodo que lo contiene, **Then** solo se
   solicitan al proveedor las fechas ausentes.
2. **Given** un límite de peticiones del proveedor alcanzado, **When** el sistema lo detecta,
   **Then** espera y reintenta de forma escalonada, sin repetir la petición en bucle.
3. **Given** un proveedor que no responde, **When** se agotan los reintentos, **Then** se comunica
   el fallo y se conserva intacto lo que ya hubiera en local.

---

### User Story 4 - Saber de dónde salen los números (Priority: P3)

Antes de fiarse de un resultado, el operador quiere poder responder: ¿quién dio estos datos, cuándo
se descargaron, y qué periodo cubren exactamente?

**Why this priority**: la trazabilidad importa cuando un resultado sorprende. Es lo primero que se
mira cuando algo no cuadra.

**Independent Test**: se descarga un histórico y se comprueba que su procedencia queda registrada y
es consultable.

**Acceptance Scenarios**:

1. **Given** un histórico descargado, **When** el operador consulta su procedencia, **Then** obtiene
   proveedor, momento de descarga, activo, rango y granularidad.
2. **Given** un histórico de bolsa, **When** se consulta, **Then** consta si los precios están
   ajustados por splits y dividendos.

---

### Edge Cases

- **Split de acciones**: una división de acciones divide el precio sin que la empresa haya perdido
  valor. Con precios sin ajustar, el motor ve una caída del 50% que nunca ocurrió y cualquier
  estrategia de tendencia reacciona a un fantasma.
- **Dividendos**: el precio cae el día del reparto. Sin ajuste, cada dividendo parece una pérdida.
- **Survivorship bias**: los proveedores gratuitos suelen ofrecer solo empresas que siguen
  cotizando. Un backtest sobre ellas ignora a las que quebraron, y por eso sale mejor de lo que la
  realidad fue. No se puede corregir con datos gratuitos; sí se puede advertir.
- **Zona horaria**: un proveedor que devuelve marcas sin zona, o en horario local, desordena la
  serie o desplaza las sesiones.
- **Vela en curso**: el último periodo devuelto puede estar sin cerrar. Guardarlo como cerrado
  introduce un dato que aún cambiará.
- **Límite de peticiones** alcanzado a mitad de una descarga larga.
- **Activo renombrado o retirado** entre dos descargas.
- **Disco lleno o sin permisos** al escribir el histórico.
- **Granularidad no disponible**: el proveedor no ofrece la que se pide, o solo para un periodo
  reciente.
- **Huecos del proveedor**: faltan velas dentro del horario de mercado.

## Requirements *(mandatory)*

### Functional Requirements

**Separación del motor (crítico)**

- **FR-001**: La descarga MUST vivir en un componente separado del motor de backtesting. El motor
  MUST seguir sin ningún acceso a red (FR-006 de la feature 001).
- **FR-002**: La separación MUST ser verificable de forma automática: debe existir una comprobación
  que falle si el motor adquiere una dependencia de red.
- **FR-003**: La comunicación entre ambos componentes MUST ser a través de ficheros en disco. El
  motor MUST NOT invocar la descarga.

**Obtención de datos**

- **FR-004**: El sistema MUST permitir solicitar el histórico de un activo indicando periodo y
  granularidad.
- **FR-005**: El histórico guardado MUST ser consumible por el motor sin conversión manual.
- **FR-006**: El sistema MUST soportar tanto activos de cripto como de bolsa.
- **FR-007**: El sistema MUST descartar el periodo aún no cerrado, para no guardar como definitivo
  un dato que todavía puede cambiar.
- **FR-008**: El sistema MUST normalizar todas las marcas temporales a una zona horaria única y
  explícita.
- **FR-009**: El sistema MUST comunicar con claridad los casos de activo desconocido, periodo sin
  datos y granularidad no disponible, sin dejar ficheros a medias.

**Integridad e inmutabilidad**

- **FR-010**: Un histórico ya guardado MUST NOT modificarse en silencio.
- **FR-011**: El sistema MUST comparar, vela a vela, toda fecha que el proveedor devuelva y que ya
  estuviera almacenada, y MUST avisar de cualquier diferencia en lugar de sobrescribir.
- **FR-012**: La escritura MUST ser atómica: una descarga interrumpida MUST NOT dejar un fichero
  parcial que parezca completo.
- **FR-026**: Ante una discrepancia, el sistema MUST conservar el histórico local intacto y MUST
  guardar la versión discrepante por separado, de forma que el operador pueda compararlas y decidir.
- **FR-027**: El aviso de discrepancia MUST identificar la fecha afectada y los dos valores en
  conflicto. Un aviso que solo diga que "algo cambió" no permite decidir nada.
- **FR-028**: Aceptar una versión discrepante MUST ser una acción explícita del operador. El sistema
  MUST NOT adoptarla por su cuenta.
- **FR-029**: El sistema MUST ofrecer una verificación de integridad bajo demanda que reexamine un
  histórico completo contra el proveedor. Esta verificación MUST ser explícita y MUST NOT ejecutarse
  como parte de una descarga normal, para no multiplicar las peticiones (FR-013).

**Eficiencia y respeto al proveedor**

- **FR-013**: El sistema MUST solicitar únicamente las fechas que no tenga ya en local.
- **FR-014**: Ante un límite de peticiones, el sistema MUST esperar y reintentar de forma
  escalonada, y MUST NOT reintentar de forma inmediata y repetida.
- **FR-015**: Agotados los reintentos, el sistema MUST conservar intacto el histórico local previo.

**Procedencia y honestidad de los datos**

- **FR-016**: Cada histórico MUST registrar su procedencia: proveedor, momento de descarga, activo,
  rango cubierto y granularidad.
- **FR-017**: Para activos de bolsa, el sistema MUST almacenar los precios **ajustados por splits y
  dividendos**, y MUST dejar constancia de ello en la procedencia.
- **FR-030**: Si el proveedor no puede entregar precios ajustados para un activo, el sistema MUST
  advertirlo de forma destacada: un backtest sobre precios sin ajustar reacciona a caídas que nunca
  ocurrieron.
- **FR-018**: El sistema MUST advertir del sesgo de supervivencia cuando se descarguen datos de
  bolsa de un proveedor que no incluye activos retirados.
- **FR-019**: El sistema MUST validar los datos recibidos con las mismas reglas que exige el motor,
  y rechazar los que no las cumplan antes de guardarlos.
- **FR-020**: Los huecos detectados MUST reportarse, y MUST NOT rellenarse con datos inventados.

**Credenciales**

- **FR-021**: Toda credencial de proveedor MUST leerse del entorno y MUST NOT almacenarse en el
  repositorio.
- **FR-022**: El sistema MUST funcionar con al menos un proveedor que no requiera credenciales.
- **FR-023**: Ningún mensaje de error ni registro de procedencia MUST incluir una credencial.

**Verificabilidad**

- **FR-024**: Los tests MUST poder ejecutarse sin acceso a red, usando respuestas grabadas.
- **FR-025**: El acceso al proveedor MUST estar aislado tras una interfaz sustituible.

### Key Entities

- **Proveedor de datos**: fuente externa de histórico. Cada uno tiene sus activos, granularidades,
  límites de peticiones y política de ajuste de precios. En v1: uno para cripto (interfaz unificada
  sobre exchanges) y otro para bolsa (con precios ajustados).
- **Solicitud de histórico**: activo, rango temporal y granularidad que pide el operador.
- **Histórico almacenado**: serie guardada en local, consumible por el motor sin conversión.
- **Procedencia**: proveedor, momento de descarga, rango cubierto, granularidad, y si los precios
  están ajustados.
- **Discrepancia**: diferencia detectada entre un dato ya almacenado y el que el proveedor devuelve
  ahora.
- **Aviso de calidad**: hueco, falta de ajuste de precios o sesgo de supervivencia. Acompaña al
  histórico igual que los avisos de datos acompañan al informe en la feature 001.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El operador obtiene un histórico real y ejecuta un backtest sobre él sin editar ni
  convertir ningún fichero a mano.
- **SC-002**: El 100% de las suites de test se ejecuta sin acceso a red.
- **SC-003**: El motor de backtesting mantiene cero dependencias de red, verificado de forma
  automática.
- **SC-004**: El 100% de las discrepancias entre datos almacenados y datos redescargados se detecta
  y se comunica; ninguna se aplica en silencio.
- **SC-005**: Al ampliar un rango ya descargado, el número de periodos solicitados al proveedor no
  supera el número de periodos que faltaban.
- **SC-006**: Una descarga interrumpida no deja ningún fichero que el motor acepte como completo.
- **SC-007**: El 100% de los históricos almacenados permite responder quién dio los datos, cuándo y
  qué cubren.
- **SC-008**: Ninguna credencial aparece en el repositorio, en los mensajes de error ni en los
  registros de procedencia.
- **SC-009**: Todo histórico de bolsa sin ajustar por splits y dividendos va acompañado de su
  advertencia.
- **SC-010**: Ninguna discrepancia detectada modifica el histórico local sin una decisión explícita
  del operador.
- **SC-011**: Todo aviso de discrepancia permite identificar la fecha concreta y los dos valores en
  conflicto.
- **SC-012**: El proveedor de cada mercado se puede sustituir modificando un único componente, sin
  tocar el resto del sistema — verificado incorporando un proveedor simulado en los tests.

## Assumptions

- **Uso bajo demanda**: el operador lanza la descarga cuando la necesita. La actualización
  automática y programada queda fuera de alcance.
- **Un activo por solicitud**: descargar carteras completas de una vez queda fuera de alcance.
- **Solo histórico**: los precios en tiempo real quedan fuera de alcance; corresponden a una feature
  de operación en vivo.
- **Formato de salida**: el mismo que ya consume el motor de la feature 001, para no introducir una
  conversión intermedia.
- **Reintentos**: se asumen tres intentos con espera creciente antes de dar una descarga por
  fallida.
- **Ámbito de la advertencia de sesgo**: el sistema advierte del sesgo de supervivencia, pero **no
  lo corrige**. Corregirlo exige datos de pago con activos retirados, que quedan fuera de alcance.
- **Precisión del ajuste**: cuando el proveedor ofrece precios ajustados, se toman como buenos. El
  sistema no recalcula los ajustes por su cuenta.
- **Fragilidad del proveedor de bolsa** (decisión del operador, sesión 2026-07-25): la fuente
  elegida es gratuita y **no oficial** — obtiene los datos raspando un portal financiero y se rompe
  cuando ese portal cambia. Se acepta a cambio de tener precios ajustados sin coste. FR-025 exige
  aislarla tras una interfaz precisamente para que sustituirla sea barato cuando ocurra.
- **Ajuste retroactivo**: los precios ajustados **cambian** cada vez que hay un nuevo split o
  dividendo, porque el ajuste se recalcula hacia atrás. Esto hará que aparezcan discrepancias
  legítimas al redescargar histórico de bolsa. No son un error del sistema ni del proveedor, y por
  eso FR-026 conserva lo local en lugar de tratarlas como corrupción.
- **Contexto de gobierno**: se somete a la constitución v1.0.0. FR-001..FR-003 derivan del
  Principio I, y FR-010..FR-012 del Principio II.
