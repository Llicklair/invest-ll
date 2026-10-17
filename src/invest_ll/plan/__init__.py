"""Tu plan y qué toca hacer hoy (docs/panel-v2.md, 4.2 paso 3, 4.3 y 7).

- `almacen`: el plan guardado en `plan/plan.json` (fuera de git: son datos tuyos).
- `calendario`: qué aportaciones han vencido y cuándo toca la siguiente.
- `hoy`: las órdenes de cripto y la lista de la compra de bolsa, calculadas sin tocar nada.

Nada de aquí envía órdenes: las de Binance se ejecutan con `POST /api/ordenes` (con la cantidad
tecleada) y las del bróker las haces tú y se anotan.
"""
