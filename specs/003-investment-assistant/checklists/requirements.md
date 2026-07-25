# Specification Quality Checklist: Asistente de Inversión

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validación pasada en la primera iteración. **38 requisitos funcionales, 12 criterios de éxito,
  5 historias, 13 edge cases** — es la feature más grande del proyecto y la única que toca dinero
  real.
- **Sin marcadores [NEEDS CLARIFICATION]**: las decisiones abiertas (qué proveedor de LLM, qué
  exchange, cómo acotar el no-determinismo) son de implementación y se resuelven en
  `/speckit-clarify`. La spec las cubre de forma agnóstica.

### Lo que esta spec hace distinto, y por qué

- **El LLM entra como estrategia, no como oráculo.** FR-006 a FR-008 lo obligan a pasar por la
  misma interfaz y las mismas métricas que el cruce de medias. Es la lectura literal del Principio
  V, y la única forma de que "el LLM elige mejor" sea una afirmación comprobable en vez de una
  esperanza.

- **La contaminación de conocimiento del LLM se declara insalvable.** Un modelo entrenado en 2026
  sabe qué pasó en 2020: cualquier backtest anterior a su corte está contaminado y **ningún diseño
  lo arregla**. FR-010 obliga a advertirlo y `Assumptions` lo dice sin rodeos. Por eso existe la
  US4: comparar contra resultados **futuros** reales es la única evidencia que no está viciada.

- **US5 (dinero real) es P3 a propósito.** Va la última porque todo lo anterior existe para que esa
  decisión se tome con información. FR-029 prohíbe el modo desatendido; el operador pidió que el
  sistema ejecutara solo, y la respuesta es que confirme cada orden — con nueve defectos
  encontrados al usar el sistema, la diferencia entre una orden mal calculada que ves y un bot
  operando mientras duermes no es burocracia.

- **FR-013 y FR-018 son restricciones sobre lo que el sistema PUEDE DECIR**, no sobre lo que hace.
  Están porque el operador ha declarado no entender de inversión: eso obliga a más honestidad en la
  presentación, no a menos.
