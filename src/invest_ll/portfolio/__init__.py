"""Tu cartera real: un registro de movimientos que solo añade, y lo que se deriva de él.

Las posiciones no se editan: se derivan. Editable sería una opinión; derivada de un registro que
solo crece, es un hecho auditable.

- `models`: los movimientos y las posiciones (abiertas = valoración, cerradas = hecho).
- `store`: el registro en disco, `portfolio/activities.jsonl`.
- `derive`: de los movimientos a la cartera.
- `csv_import` y `from_orders`: las dos vías de entrada además de teclearlo.
- `reconcile`: la única comprobación que mira fuera — el saldo real del exchange.
- `quotes`: el último cierre descargado, siempre con su fecha.
- `triggers`: reglas de retirada que PROPONEN la venta. Nunca la envían.
"""
