"""
Connector SDK — Kit de Desarrollo de Conectores para Zenic-Flijo
=================================================================

El Connector SDK permite a los desarrolladores crear nuevos conectores
en horas, no dias. Provee toda la infraestructura comun que un conector
necesita: autenticacion, reintentos, circuit breaker, rate limiting,
validacion de esquemas, metricas y registro.

Inicio rapido:

    from src.sdk import BaseConnector, connector_action, APIKeyAuth

    class MiConector(BaseConnector):
        name = "mi_conector"
        version = "1.0.0"
        description = "Mi conector personalizado"

        def connect(self):
            self._log_operation("connect")
            self._connected = True
            return True

        def disconnect(self):
            self._log_operation("disconnect")
            self._connected = False
            return True

        def execute(self, action, params):
            if action in self._action_metadata:
                method = getattr(self, self._action_metadata[action]["method_name"])
                return method(params)
            raise ActionNotFoundError(action=action, connector_name=self.name)

        def validate(self):
            return bool(self.name)

        @connector_action("listar", "Lista elementos")
        def listar_elementos(self, params):
            return {"items": []}

    # Usar el conector
    with MiConector(auth_provider=APIKeyAuth("mi-api-key")) as conn:
        result = conn.safe_execute("listar", {})

Modulos:
    - base: Clase BaseConnector abstracta con toda la infraestructura
    - auth: Sistema de autenticacion (APIKey, Basic, OAuth2, OAuth1, mTLS, Custom)
    - schema: Definicion de esquemas con Pydantic y generacion OpenAPI
    - decorators: Decoradores para desarrollo rapido de acciones
    - registry: Registro singleton de conectores con auto-descubrimiento
    - exceptions: Jerarquia de excepciones del SDK
"""

from __future__ import annotations

from src.sdk.auth import (
    APIKeyAuth,
    AuthProvider,
    BasicAuth,
    CustomAuth,
    MTLSAuth,
    OAuth1Auth,
    OAuth2Auth,
)
from src.sdk.base import (
    BaseConnector,
    CircuitBreakerConfig,
    CircuitState,
    RateLimitConfig,
    RetryConfig,
)
from src.sdk.decorators import (
    circuit_breaker,
    connector_action,
    get_action_metadata,
    rate_limit,
    retry,
    track_metrics,
    validate_input,
    validate_output,
)
from src.sdk.exceptions import (
    ActionNotFoundError,
    AuthenticationError,
    CircuitBreakerOpenError,
    ConnectionError,
    ConnectorError,
    RateLimitError,
    SchemaError,
    ValidationError,
)
from src.sdk.registry import ConnectorRegistry
from src.sdk.schema import (
    ActionDefinition,
    AuthRequirement,
    ConnectorSchema,
    OpenAPIGenerator,
    SchemaValidator,
    SchemaVersion,
)

__all__ = [
    "APIKeyAuth",
    "ActionNotFoundError",
    "AuthProvider",
    "AuthRequirement",
    "AuthenticationError",
    "BaseConnector",
    "BasicAuth",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "ConnectionError",
    "ConnectorError",
    "ConnectorRegistry",
    "ConnectorSchema",
    "CustomAuth",
    "MTLSAuth",
    "OAuth1Auth",
    "OAuth2Auth",
    "OpenAPIGenerator",
    "RateLimitConfig",
    "RateLimitError",
    "RetryConfig",
    "SchemaError",
    "SchemaValidator",
    "SchemaVersion",
    "ValidationError",
    "circuit_breaker",
    "connector_action",
    "get_action_metadata",
    "rate_limit",
    "retry",
    "track_metrics",
    "validate_input",
    "validate_output",
]
