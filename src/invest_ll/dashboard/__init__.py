"""Lógica pura del panel, sin framework: qué hay descargado, las tablas y la puerta de órdenes.

El panel es la API de `invest_ll.api` (FastAPI) más el frontend de `web/`; esto es lo que ambos
usan y lo que tiene tests. Sobrevivió al cambio desde Streamlit sin tocarse precisamente porque
nunca dependió de cómo se pinta.
"""
