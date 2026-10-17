"""Las estrategias del panel v2, contadas para quien no sabe de inversiones (docs/panel-v2.md, 5-6).

- `catalogo`: qué es cada una en llano y con qué motor de `invest_ll.quant` se ejecuta.
- `datos`: los paneles de precios descargados, leídos una vez por versión del fichero.
- `historico`: cada estrategia ejecutada sobre esos datos, guardada en memoria por su huella.
- `simulacion`: tus números (inicial + mensual desde un año) sobre esas ejecuciones.
- `recomendacion`: de tus respuestas a un reparto, con reglas fijas y a la vista.
- `objetivo`: el reparto que quiere cada estrategia tras el último cierre.

Las cifras no se escriben a mano en ningún sitio: salen de ejecutar el motor sobre los datos.
"""
