# Specification Quality Checklist: Descarga de Histórico Real de Mercado

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

- Validación pasada en la primera iteración. Tras la clarificación: **30 requisitos funcionales,
  12 criterios de éxito**. Re-validado: 16/16 se mantienen.
- **Sesión de clarificación 2026-07-25**: 5 preguntas resueltas — proveedor de cripto, proveedor de
  bolsa, política de ajuste de precios, mecanismo de detección de revisiones y qué hacer ante una
  discrepancia. Añadidos FR-026..FR-030 y SC-010..SC-012.
- **Tensión resuelta entre FR-013 y la detección de revisiones**: pedir solo lo que falta y a la vez
  detectar que el proveedor cambió algo son objetivos opuestos. Se resuelve comparando el solape que
  el proveedor devuelve de todos modos (coste cero) y dejando la reverificación completa como acción
  explícita del operador (FR-029).
- **Dependencia de la feature 001**: FR-005 y FR-019 se apoyan en el contrato de serie y en las
  reglas de validación ya implementadas. Esta feature no las redefine.
- **Riesgos del dominio explícitamente recogidos**, porque son los que hacen que un backtest con
  datos reales mienta: splits y dividendos sin ajustar, sesgo de supervivencia, vela en curso y
  zonas horarias. Ninguno es un detalle técnico: cada uno produce resultados falsos y creíbles.
- El sesgo de supervivencia se **advierte pero no se corrige**, y así está declarado en
  `Assumptions`. Corregirlo requiere datos de pago. Prometer lo contrario sería justo el tipo de
  falsa garantía que la constitución prohíbe.
