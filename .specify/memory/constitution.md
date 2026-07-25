<!--
SYNC IMPACT REPORT
Version change: TEMPLATE (sin ratificar) → 1.0.0
Bump rationale: MAJOR inicial. Primera ratificación: la constitución pasa de plantilla con
placeholders a documento de gobierno con cinco principios vinculantes.

Modified principles: ninguno (ratificación inicial; los cinco placeholders del template se
sustituyen por principios concretos).

Added sections:
  - I. Seguridad del Capital por Defecto (NO NEGOCIABLE)
  - II. El Backtester No Puede Ver el Futuro (NO NEGOCIABLE)
  - III. Las Métricas No Pueden Mentir
  - IV. Realismo en la Simulación
  - V. Estrategias Intercambiables y Comparables
  - Restricciones Técnicas y de Seguridad (sección 2)
  - Flujo de Desarrollo y Gates de Calidad (sección 3)
  - Governance

Removed sections: ninguna.

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — Constitution Check alineado (v1.0.0)
  ✅ .specify/templates/spec-template.md — revisado, alineado sin cambios
  ✅ .specify/templates/tasks-template.md — revisado, alineado sin cambios

Deferred TODOs:
  - Branch protection en GitHub pendiente hasta que exista un workflow de CI que ejecute la
    suite (ver Governance). Hasta entonces el enforcement del "nunca auto-merge" es DEGRADADO.
-->

# INVEST LL Constitution

INVEST LL es un sistema de inversión automática en bolsa y criptomonedas. Opera de forma
autónoma, sin intervención humana por operación. Esa autonomía es precisamente lo que hace
que estos principios no sean negociables: un sistema que mueve capital solo y se equivoca en
silencio es más peligroso que uno que no existe.

## Core Principles

### I. Seguridad del Capital por Defecto (NO NEGOCIABLE)

El modo simulación es el estado por defecto del sistema. Ninguna orden con dinero real
puede ejecutarse sin una activación explícita y deliberada del operador humano.

- El sistema MUST arrancar en modo simulación cuando el modo no esté especificado. Ausencia
  de configuración significa simulación, nunca real.
- Activar el modo real MUST requerir una acción afirmativa explícita (variable de entorno
  dedicada o flag de invocación) Y credenciales de trading distintas de las de simulación.
  Un solo interruptor no basta.
- El modo real MUST NOT ser activable por un valor heredado de configuración, un default de
  código, un fichero commiteado, o un agente automático.
- Las credenciales de broker/exchange MUST vivir fuera del repositorio. Ningún secreto se
  commitea, jamás.
- Todo código que envíe una orden MUST verificar el modo en el punto de ejecución, no solo
  al arrancar.

**Rationale**: Un fallo aquí no produce un test rojo, produce pérdida de dinero real e
irreversible. Es el único error del sistema que no se puede deshacer con un revert.

### II. El Backtester No Puede Ver el Futuro (NO NEGOCIABLE)

Ninguna decisión simulada puede usar información posterior al instante que está simulando.

- El motor de backtest MUST exponer a la estrategia únicamente los datos disponibles hasta
  la marca temporal simulada. La restricción MUST ser estructural (la estrategia no recibe
  los datos futuros) y no una convención que el autor de la estrategia deba recordar.
- Los indicadores calculados sobre la serie completa antes de simular MUST NOT alimentar
  decisiones, salvo que se demuestre que solo usan datos pasados en cada punto.
- Toda estrategia MUST tener un test que falle si se le filtran datos futuros.

**Rationale**: El look-ahead bias es el error que hace que cualquier estrategia parezca
rentable en papel. Es silencioso, no rompe nada, y produce resultados excelentes que se
evaporan con dinero real. Si es posible cometerlo, se cometerá.

### III. Las Métricas No Pueden Mentir

El win rate por sí solo NO es criterio de éxito y MUST NOT presentarse como tal.

- Todo resultado de backtest MUST reportar, junto al win rate: expectancy por operación,
  drawdown máximo, número de operaciones, y el coste total de comisiones y slippage.
- Ninguna estrategia MUST declararse apta basándose en el win rate aislado.
- Un resultado con muestra insuficiente MUST etiquetarse como no concluyente en lugar de
  presentarse como positivo.

**Rationale**: Una estrategia puede acertar el 90% de las operaciones y perder dinero neto,
si las pérdidas del 10% restante superan a todas las ganancias. Optimizar el porcentaje de
aciertos sin mirar la magnitud es la forma más común de construir un sistema que parece
funcionar hasta que deja de hacerlo.

### IV. Realismo en la Simulación

La simulación MUST modelar la fricción real del mercado.

- Toda orden simulada MUST aplicar comisiones y slippage según el mercado que representa.
- El simulador MUST poder representar órdenes rechazadas y ejecuciones parciales.
- Los parámetros de fricción MUST ser explícitos y auditables, nunca cero por defecto
  silencioso.

**Rationale**: Una simulación sin fricción es una mentira optimista. La diferencia entre
simulación ideal y mercado real es donde mueren las estrategias de alta frecuencia de
operación, que son justo las que mejor puntúan en un backtest sin costes.

### V. Estrategias Intercambiables y Comparables

Las estrategias deterministas y las basadas en IA MUST implementarse tras la misma interfaz.

- Toda estrategia MUST consumir la misma forma de entrada y producir la misma forma de
  señal, independientemente de su mecanismo interno.
- Toda estrategia MUST ser evaluable sobre los mismos datos y con las mismas métricas
  (Principio III), para permitir comparación honesta.
- Añadir una estrategia MUST NOT requerir modificar el motor de backtest ni el de ejecución.

**Rationale**: La pregunta "¿reglas deterministas o IA?" solo se puede responder midiendo.
Si cada enfoque se mide con vara distinta, la comparación es una opinión disfrazada de dato.

## Restricciones Técnicas y de Seguridad

**Stack**: Python. Gates obligatorias: `ruff` (lint), `pyright` (tipos), `pytest` (tests).

**Modos de operación**: `simulación` (default, obligatorio en v1) y `real` (no implementado
en v1; su introducción es un cambio que requiere revisión explícita contra el Principio I).

**Secretos**: `.gitignore` MUST excluir `.env`, claves y credenciales. Un secreto commiteado
se trata como incidente: rotar la credencial, no solo borrar el commit.

**Entorno**: la gate de mutation testing (`mutmut`) no se ejecuta en Windows nativo. En esta
máquina MUST correrse vía WSL o contenedor. Instalado no significa funcional: un oráculo se
declara activo solo tras una ejecución real verificada.

## Flujo de Desarrollo y Gates de Calidad

**Test-first**: el comportamiento nuevo empieza por un test que falla. Los Principios I, II y
III MUST tener cobertura de test explícita — un principio sin test es una intención, no una
garantía.

**Gates antes de integrar**: `ruff` → `pyright` → `pytest` (suite completa, sin regresión).
Un cambio que rompe un test existente MUST NOT integrarse aunque el test roto parezca
irrelevante.

**Baselines**: actualizar un baseline o snapshot es un evento de aprobación humana, nunca un
arreglo automático. Los agentes MUST NOT usar flags de actualización de snapshots.

**Nunca auto-merge**: ningún proceso automático MUST aprobar y mergear su propio trabajo. La
integración a `main` requiere revisión humana.

## Governance

Esta constitución prevalece sobre cualquier otra práctica del proyecto. Cuando una decisión
técnica entre en conflicto con un principio, gana el principio o se enmienda la constitución
— nunca se ignora en silencio.

**Enmiendas**: toda modificación MUST documentarse en el Sync Impact Report de este fichero,
justificar el cambio de versión, y propagarse a las plantillas dependientes.

**Versionado**: MAJOR para eliminación o redefinición incompatible de principios; MINOR para
principios o secciones nuevas o materialmente ampliadas; PATCH para aclaraciones y correcciones
sin cambio semántico.

**Cumplimiento**: toda revisión de cambios MUST verificar conformidad con los principios. Los
marcados NO NEGOCIABLE (I y II) no admiten excepción justificada: un cambio que los viole se
rechaza, no se discute.

**Enforcement externo**: la garantía de "nunca auto-merge" solo es mecánica cuando vive fuera
del perímetro del agente, en la branch protection de GitHub (revisión requerida ≥1 y status
check de CI obligatorio). TODO(BRANCH_PROTECTION): activar cuando exista el workflow de CI que
ejecuta la suite. Hasta entonces el enforcement es DEGRADADO y depende de disciplina humana.

**Version**: 1.0.0 | **Ratified**: 2026-07-25 | **Last Amended**: 2026-07-25
