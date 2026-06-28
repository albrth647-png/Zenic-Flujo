"""
Connector SDK — Sistema de Autenticacion
=========================================

Provee un sistema extensible de autenticacion para conectores,
soportando multiples mecanismos de auth:

- APIKeyAuth: API key via header o query param
- BasicAuth: usuario/contrasena
- OAuth2Auth: Authorization Code Flow con token refresh
- OAuth1Auth: OAuth 1.0a con generacion de firma
- MTLSAuth: mTLS con certificado de cliente
- CustomAuth: Headers/tokens personalizados

Todos los proveedores implementan la interfaz AuthProvider con:
- apply_auth(request): Aplica credenciales a una peticion
- refresh(): Renueva las credenciales si es posible
- is_expired(): Verifica si las credenciales expiraron
- validate(): Valida que las credenciales sean correctas
"""

from __future__ import annotations

from src.sdk.auth.api_key import APIKeyAuth
from src.sdk.auth.base import AuthProvider
from src.sdk.auth.basic import BasicAuth
from src.sdk.auth.custom import CustomAuth
from src.sdk.auth.mtls import MTLSAuth
from src.sdk.auth.oauth1 import OAuth1Auth
from src.sdk.auth.oauth2 import OAuth2Auth

__all__ = [
    "APIKeyAuth",
    "AuthProvider",
    "BasicAuth",
    "CustomAuth",
    "MTLSAuth",
    "OAuth1Auth",
    "OAuth2Auth",
]
