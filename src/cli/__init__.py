"""
Zenic CLI — Interfaz de Linea de Comandos para Desarrollo de Conectores
========================================================================

Provee herramientas CLI para el ciclo de vida completo de conectores:

- init: Scaffolding de nuevos conectores con plantillas por tipo de autenticacion
- test: Ejecucion de conectores en un entorno sandbox aislado
- validate: Validacion de estructura, esquema y metodos de conectores
- publish: Empaquetado y publicacion de conectores al marketplace
- version: Gestion de versiones semver de conectores
- list: Listado de conectores registrados en el sistema
- info: Informacion detallada de un conector especifico

Uso:
    python -m src.cli.main <comando> [opciones]
"""

from __future__ import annotations
