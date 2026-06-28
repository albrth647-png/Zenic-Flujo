"""
Zenic-Flijo API v2 — Interfaz publica REST API
================================================

API v2 de Zenic-Flijo con mas de 50 endpoints organizados en routers:
- workflows: CRUD + ejecucion + monitoreo de workflows
- connectors: Gestion y ejecucion de conectores
- nlu: Pipeline de procesamiento de lenguaje natural
- tenants: Administracion de multi-tenancy
- marketplace: Busqueda e instalacion de conectores
- auth: Autenticacion, autorizacion y gestion de API keys

Construido sobre FastAPI con Pydantic v2, RBAC granular,
rate limiting por API key, y resolucion de tenant por request.
"""

from __future__ import annotations
