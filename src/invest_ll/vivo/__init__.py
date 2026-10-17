"""En vivo (docs/panel-v3-vivo.md): precios de Hyperliquid, cuenta de práctica y lo que comparten
con los bots.

- `fuente`: lo que cualquiera puede pedir a la fuente de precios (`FuentePrecios`), y una fuente
  falsa para las pruebas. La de verdad (Hyperliquid) vive en su propio módulo.
- `ejecucion`: cómo se ejecuta una orden ficticia contra el libro real del momento. Puro.

Nada de este paquete envía órdenes a ningún exchange ni toca claves: todo es dinero ficticio.
"""
