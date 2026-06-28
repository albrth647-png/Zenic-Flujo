"""
Connector SDK — Excepciones Especificas del SDK
=================================================

Jerarquia de excepciones para el Connector SDK de Zenic-Flijo.
Cada excepcion provee contexto detallado para facilitar el diagnostico
y la resolucion de problemas en conectores de produccion.

Jerarquia:
    ConnectorError (base)
    +-- ConnectionError
    +-- AuthenticationError
    +-- ValidationError
    +-- RateLimitError
    +-- CircuitBreakerOpenError
    +-- ActionNotFoundError
    +-- SchemaError
"""

from __future__ import annotations

from typing import Any


class ConnectorError(Exception):
    """
    Excepcion base para todos los errores del Connector SDK.

    Provee contexto enriquecido: codigo de error, detalles del conector,
    y metadata adicional para diagnostico.

    Args:
        message: Mensaje descriptivo del error
        connector_name: Nombre del conector que genero el error
        error_code: Codigo de error estandarizado (ej: 'CONN_001')
        details: Diccionario con informacion adicional del error
    """

    def __init__(
        self,
        message: str = "",
        connector_name: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.connector_name = connector_name
        self.error_code = error_code
        self.details = details or {}
        self.timestamp: float | None = None
        super().__init__(message)

    def set_timestamp(self, ts: float) -> ConnectorError:
        """Establece la marca temporal del error y retorna self para encadenamiento."""
        self.timestamp = ts
        return self

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa la excepcion a un diccionario estructurado.

        Retorna:
            Diccionario con todos los campos del error para logging o API responses.
        """
        result: dict[str, Any] = {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "error_code": self.error_code,
        }
        if self.connector_name:
            result["connector_name"] = self.connector_name
        if self.details:
            result["details"] = self.details
        if self.timestamp:
            result["timestamp"] = self.timestamp
        return result

    def __repr__(self) -> str:
        parts = [f"{self.__class__.__name__}({str(self)!r}"]
        if self.error_code:
            parts.append(f"code={self.error_code!r}")
        if self.connector_name:
            parts.append(f"connector={self.connector_name!r}")
        return ", ".join(parts) + ")"


class ConnectionError(ConnectorError):
    """
    Error de conexion con un servicio externo.

    Se lanza cuando no se puede establecer o mantener una conexion
    con el servicio objetivo. Incluye informacion sobre reintentos
    y el estado de la conexion.

    Args:
        message: Mensaje descriptivo del error de conexion
        connector_name: Nombre del conector
        url: URL del servicio al que se intento conectar
        retry_count: Numero de reintentos realizados antes del fallo
        cause_exception: Excepcion original que causo el error
    """

    def __init__(
        self,
        message: str = "Error de conexion con el servicio externo",
        connector_name: str | None = None,
        url: str | None = None,
        retry_count: int = 0,
        cause_exception: Exception | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if url:
            details["url"] = url
        if retry_count > 0:
            details["retry_count"] = retry_count
        if cause_exception:
            details["cause_type"] = type(cause_exception).__name__
            details["cause_message"] = str(cause_exception)
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "CONN_001"),
            details=details,
        )
        self.url = url
        self.retry_count = retry_count
        self.cause_exception = cause_exception


class AuthenticationError(ConnectorError):
    """
    Error de autenticacion con un servicio externo.

    Se lanza cuando las credenciales son invalidas, expiraron,
    o el metodo de autenticacion no es soportado.

    Args:
        message: Mensaje descriptivo del error de autenticacion
        connector_name: Nombre del conector
        auth_type: Tipo de autenticacion que fallo (api_key, basic, oauth2, etc.)
        reason: Razon especifica del fallo (invalid_credentials, expired_token, etc.)
    """

    def __init__(
        self,
        message: str = "Error de autenticacion",
        connector_name: str | None = None,
        auth_type: str | None = None,
        reason: str | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if auth_type:
            details["auth_type"] = auth_type
        if reason:
            details["reason"] = reason
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "AUTH_001"),
            details=details,
        )
        self.auth_type = auth_type
        self.reason = reason


class ValidationError(ConnectorError):
    """
    Error de validacion de datos de entrada o salida.

    Se lanza cuando los datos no cumplen con el esquema definido
    para una accion del conector. Incluye detalles sobre los
    campos que fallaron la validacion.

    Args:
        message: Mensaje descriptivo del error de validacion
        connector_name: Nombre del conector
        action: Nombre de la accion donde ocurrio el error
        field: Campo especifico que fallo la validacion
        validation_errors: Lista de errores de validacion detallados
    """

    def __init__(
        self,
        message: str = "Error de validacion de datos",
        connector_name: str | None = None,
        action: str | None = None,
        field: str | None = None,
        validation_errors: list[dict[str, Any]] | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if action:
            details["action"] = action
        if field:
            details["field"] = field
        if validation_errors:
            details["validation_errors"] = validation_errors
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "VAL_001"),
            details=details,
        )
        self.action = action
        self.field = field
        self.validation_errors = validation_errors or []

    @classmethod
    def from_pydantic(
        cls,
        validation_exception: Exception,
        connector_name: str | None = None,
        action: str | None = None,
    ) -> ValidationError:
        """
        Crea un ValidationError desde una excepcion de Pydantic.

        Extrae los errores de validacion de la excepcion de Pydantic
        y los transforma al formato del SDK.

        Args:
            validation_exception: Excepcion ValidationError de Pydantic
            connector_name: Nombre del conector
            action: Nombre de la accion

        Retorna:
            Instancia de ValidationError con los errores detallados
        """
        errors_list: list[dict[str, Any]] = []
        if hasattr(validation_exception, "errors"):
            for err in validation_exception.errors():
                errors_list.append(
                    {
                        "field": ".".join(str(loc) for loc in err.get("loc", [])),
                        "message": err.get("msg", ""),
                        "type": err.get("type", ""),
                    }
                )
        return cls(
            message=f"Validacion fallida: {len(errors_list)} error(es)",
            connector_name=connector_name,
            action=action,
            validation_errors=errors_list,
            error_code="VAL_002",
        )


class RateLimitError(ConnectorError):
    """
    Error de limite de frecuencia (rate limiting).

    Se lanza cuando se excede el numero maximo de llamadas permitidas
    en el periodo configurado. Incluye informacion sobre los limites
    y el tiempo hasta que se restablezcan.

    Args:
        message: Mensaje descriptivo del error
        connector_name: Nombre del conector
        max_calls: Numero maximo de llamadas permitidas
        period_seconds: Periodo de la ventana en segundos
        remaining: Llamadas restantes en el periodo actual
        reset_at: Timestamp cuando se restablecen los limites
    """

    def __init__(
        self,
        message: str = "Limite de frecuencia excedido",
        connector_name: str | None = None,
        max_calls: int | None = None,
        period_seconds: int | None = None,
        remaining: int = 0,
        reset_at: int | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if max_calls is not None:
            details["max_calls"] = max_calls
        if period_seconds is not None:
            details["period_seconds"] = period_seconds
        details["remaining"] = remaining
        if reset_at is not None:
            details["reset_at"] = reset_at
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "RATE_001"),
            details=details,
        )
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.remaining = remaining
        self.reset_at = reset_at


class CircuitBreakerOpenError(ConnectorError):
    """
    Error de circuit breaker abierto.

    Se lanza cuando el circuit breaker esta en estado OPEN y no permite
    llamadas al servicio. Incluye informacion sobre el estado del circuito,
    el numero de fallos consecutivos y el tiempo hasta que se pase a HALF_OPEN.

    Args:
        message: Mensaje descriptivo del error
        connector_name: Nombre del conector
        state: Estado actual del circuit breaker ('OPEN')
        failure_count: Numero de fallos consecutivos que abrieron el circuito
        recovery_timeout: Segundos hasta que el circuito pase a HALF_OPEN
        last_failure_time: Timestamp del ultimo fallo registrado
    """

    def __init__(
        self,
        message: str = "Circuit breaker abierto - llamadas bloqueadas",
        connector_name: str | None = None,
        state: str = "OPEN",
        failure_count: int = 0,
        recovery_timeout: float | None = None,
        last_failure_time: float | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        details["state"] = state
        details["failure_count"] = failure_count
        if recovery_timeout is not None:
            details["recovery_timeout"] = recovery_timeout
        if last_failure_time is not None:
            details["last_failure_time"] = last_failure_time
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "CB_001"),
            details=details,
        )
        self.state = state
        self.failure_count = failure_count
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = last_failure_time


class ActionNotFoundError(ConnectorError):
    """
    Error de accion no encontrada en el conector.

    Se lanza cuando se intenta ejecutar una accion que no esta
    registrada en el conector. Incluye la lista de acciones
    disponibles para facilitar el diagnostico.

    Args:
        message: Mensaje descriptivo del error
        connector_name: Nombre del conector
        action: Nombre de la accion solicitada
        available_actions: Lista de acciones disponibles en el conector
    """

    def __init__(
        self,
        message: str = "Accion no encontrada en el conector",
        connector_name: str | None = None,
        action: str | None = None,
        available_actions: list[str] | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if action:
            details["requested_action"] = action
        if available_actions is not None:
            details["available_actions"] = available_actions
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "ACT_001"),
            details=details,
        )
        self.action = action
        self.available_actions = available_actions or []


class SchemaError(ConnectorError):
    """
    Error de definicion o carga de esquema del conector.

    Se lanza cuando hay problemas con la definicion del esquema
    de un conector, como esquemas de entrada/salida invalidos,
    conflictos de version, o definiciones de acciones malformadas.

    Args:
        message: Mensaje descriptivo del error
        connector_name: Nombre del conector
        schema_version: Version del esquema afectada
        schema_path: Ruta del esquema con el problema
        conflict_field: Campo especifico con conflicto
    """

    def __init__(
        self,
        message: str = "Error en la definicion del esquema",
        connector_name: str | None = None,
        schema_version: str | None = None,
        schema_path: str | None = None,
        conflict_field: str | None = None,
        # legítimo: wrapper genérico. kwargs se pasan a super().__init__ (skill §1.2).
        **kwargs: Any,
    ) -> None:
        details: dict[str, Any] = kwargs.get("details", {})
        if schema_version:
            details["schema_version"] = schema_version
        if schema_path:
            details["schema_path"] = schema_path
        if conflict_field:
            details["conflict_field"] = conflict_field
        super().__init__(
            message=message,
            connector_name=connector_name,
            error_code=kwargs.get("error_code", "SCH_001"),
            details=details,
        )
        self.schema_version = schema_version
        self.schema_path = schema_path
        self.conflict_field = conflict_field
