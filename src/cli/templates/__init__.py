"""
Zenic CLI — Generador de Plantillas para Scaffolding de Conectores
===================================================================

Genera codigo boilerplate para crear nuevos conectores, soportando
todos los tipos de autenticacion disponibles en el SDK:

- api_key: Autenticacion mediante API key via header o query param
- basic: Autenticacion HTTP Basic (usuario/contrasena)
- oauth2: OAuth 2.0 Authorization Code Flow con token refresh
- oauth1: OAuth 1.0a con firma HMAC-SHA1
- mtls: Mutual TLS con certificado de cliente
- custom: Headers y tokens personalizados
- none: Sin autenticacion (acceso publico)

Cada plantilla genera codigo funcional que hereda de BaseConnector
e implementa todos los metodos abstractos requeridos.
"""

from __future__ import annotations

from src.cli.templates.generators import (
    generate_connector_code,
    generate_init_code,
    generate_manifest,
    generate_schema_code,
    generate_test_code,
)
from src.cli.templates.helpers import (
    AUTH_OPTIONAL_FIELDS,
    AUTH_REQUIRED_FIELDS,
    VALID_AUTH_TYPES,
    to_class_name,
)

__all__ = [
    "AUTH_OPTIONAL_FIELDS",
    "AUTH_REQUIRED_FIELDS",
    "VALID_AUTH_TYPES",
    "generate_connector_code",
    "generate_init_code",
    "generate_manifest",
    "generate_schema_code",
    "generate_test_code",
    "to_class_name",
]
