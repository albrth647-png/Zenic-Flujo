"""
Zenic-Flijo API v2 — Router de Conectores
==========================================

Endpoints de gestion y ejecucion de conectores:
- GET    /api/v2/connectors                      — Listar conectores disponibles
- GET    /api/v2/connectors/{name}               — Obtener info de conector
- POST   /api/v2/connectors/{name}/configure     — Configurar credenciales
- POST   /api/v2/connectors/{name}/test          — Probar conexion
- GET    /api/v2/connectors/{name}/actions        — Listar acciones disponibles
- POST   /api/v2/connectors/{name}/execute       — Ejecutar accion
- DELETE /api/v2/connectors/{name}/config         — Eliminar configuracion
- GET    /api/v2/connectors/{name}/schema         — Obtener esquema
- GET    /api/v2/connectors/{name}/health         — Health check del conector

# Audience: External
# Purpose: CRUD de connectors. Paralelo a Flask /api/integrations/* para gestión programática externa.
"""


from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.db import DatabaseManager, RedisService
    from src.sdk.registry import ConnectorRegistry

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import require_permission
from src.api_v2.dependencies import get_connector_registry, get_db, get_redis
from src.api_v2.models import (
    ConnectorActionInfo,
    ConnectorConfigRequest,
    ConnectorExecuteRequest,
    ConnectorExecuteResponse,
    ConnectorInfo,
    ConnectorTestRequest,
    ConnectorTestResponse,
    ErrorResponse,
)
from src.core.logging import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/connectors", tags=["Connectors"])


@router.get(
    "",
    response_model=list[ConnectorInfo],
    summary="Listar conectores",
    description="Lista todos los conectores registrados en el sistema.",
    responses={401: {"model": ErrorResponse}},
)
async def list_connectors(
    category: str | None = None,
    user: dict[str, Any] = Depends(require_permission("connector", "read")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> list[ConnectorInfo]:
    """Lista todos los conectores registrados, opcionalmente filtrados por categoria."""
    raw_list = registry.list_by_category(category) if category else registry.list_all()

    return [ConnectorInfo(**item) for item in raw_list]


@router.get(
    "/{name}",
    response_model=ConnectorInfo,
    summary="Obtener info de conector",
    description="Obtiene la informacion completa de un conector por su nombre.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_connector(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "read")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorInfo:
    """Obtiene la informacion de un conector por su nombre."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    metadata = registry.get_metadata(name) or {}
    metadata["name"] = name
    cls = registry.get(name)
    if cls:
        metadata["class_name"] = cls.__name__
        metadata["module"] = cls.__module__

    return ConnectorInfo(**metadata)


@router.post(
    "/{name}/configure",
    summary="Configurar credenciales de conector",
    description="Configura las credenciales de autenticacion para un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def configure_connector(
    name: str,
    config_data: ConnectorConfigRequest,
    user: dict[str, Any] = Depends(require_permission("connector", "update")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
    db: DatabaseManager = Depends(get_db),
    redis: RedisService = Depends(get_redis),
) -> dict[str, Any]:
    """Configura las credenciales de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    # Almacenar configuracion cifrada en BD
    from src.core.security.encryption import encrypt_value

    encrypted_credentials = {}
    for key, value in config_data.credentials.items():
        if isinstance(value, str):
            encrypted_credentials[key] = encrypt_value(value)
        else:
            encrypted_credentials[key] = json.dumps(value)

    config_json = json.dumps(
        {
            "auth_type": config_data.auth_type,
            "credentials": encrypted_credentials,
            "config": config_data.config,
        },
        default=str,
    )

    # Guardar o actualizar configuracion
    existing = db.fetchone("SELECT id FROM connector_configs WHERE connector_name = ?", (name,))
    if existing:
        db.execute("UPDATE connector_configs SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (config_json, existing["id"]))
    else:
        db.execute(
            "INSERT INTO connector_configs (connector_name, config, user_id) VALUES (?, ?, ?)",
            (name, config_json, user.get("user_id", 1)),
        )
    db.commit()

    # Invalidar cache
    redis.delete(f"connector_config:{name}")

    return {"status": "ok", "connector": name, "auth_type": config_data.auth_type}


@router.post(
    "/{name}/test",
    response_model=ConnectorTestResponse,
    summary="Probar conexion de conector",
    description="Prueba la conexion a un conector con las credenciales configuradas.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def test_connector(
    name: str,
    test_data: ConnectorTestRequest,
    user: dict[str, Any] = Depends(require_permission("connector", "execute")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorTestResponse:
    """Prueba la conexion de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    start_time = time.time()
    try:
        connector_cls = registry.get(name)
        if not connector_cls:
            return ConnectorTestResponse(success=False, message="Clase del conector no encontrada")

        # Intentar instanciar y probar
        instance = connector_cls()
        test_action = test_data.action or "test"

        if hasattr(instance, "test_connection"):
            result = instance.test_connection()
            latency = (time.time() - start_time) * 1000
            success = bool(result)
            message = "Conexion exitosa" if success else "Conexion fallida"
            if isinstance(result, dict):
                message = result.get("message", message)
            return ConnectorTestResponse(success=success, message=message, latency_ms=latency, details=result if isinstance(result, dict) else {})

        if hasattr(instance, test_action):
            latency = (time.time() - start_time) * 1000
            return ConnectorTestResponse(success=True, message="Accion de prueba ejecutada", latency_ms=latency)

        return ConnectorTestResponse(success=False, message=f"Accion '{test_action}' no disponible", latency_ms=(time.time() - start_time) * 1000)

    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return ConnectorTestResponse(success=False, message=f"Error en prueba: {e}", latency_ms=latency, details={"error_type": type(e).__name__})


@router.get(
    "/{name}/actions",
    response_model=list[ConnectorActionInfo],
    summary="Listar acciones de conector",
    description="Lista todas las acciones disponibles de un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def list_connector_actions(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "read")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> list[ConnectorActionInfo]:
    """Lista las acciones disponibles de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    connector_cls = registry.get(name)
    if not connector_cls:
        return []

    actions = []
    instance = connector_cls()

    # Buscar metodos que parezcan acciones
    if hasattr(instance, "get_actions"):
        raw_actions = instance.get_actions()
        for action in raw_actions:
            if isinstance(action, dict):
                actions.append(ConnectorActionInfo(
                    name=action.get("name", ""),
                    description=action.get("description", ""),
                    input_schema=action.get("input_schema", {}),
                    output_schema=action.get("output_schema", {}),
                ))
            elif isinstance(action, str):
                actions.append(ConnectorActionInfo(name=action))

    # Si tiene ACTIONS definido como atributo de clase
    if not actions and hasattr(connector_cls, "ACTIONS"):
        for action_def in connector_cls.ACTIONS:
            if isinstance(action_def, dict):
                actions.append(ConnectorActionInfo(
                    name=action_def.get("name", ""),
                    description=action_def.get("description", ""),
                    input_schema=action_def.get("input_schema", {}),
                    output_schema=action_def.get("output_schema", {}),
                ))

    # Fallback: introspeccion de metodos publicos
    if not actions:
        import inspect

        for method_name, _method in inspect.getmembers(instance, predicate=inspect.ismethod):
            if not method_name.startswith("_") and method_name not in ("test_connection", "get_actions"):
                actions.append(ConnectorActionInfo(name=method_name, description=f"Accion {method_name}"))

    return actions


@router.post(
    "/{name}/execute",
    response_model=ConnectorExecuteResponse,
    summary="Ejecutar accion de conector",
    description="Ejecuta una accion especifica de un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def execute_connector_action(
    name: str,
    execute_data: ConnectorExecuteRequest,
    user: dict[str, Any] = Depends(require_permission("connector", "execute")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorExecuteResponse:
    """Ejecuta una accion de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    connector_cls = registry.get(name)
    if not connector_cls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Clase del conector '{name}' no encontrada")

    start_time = time.time()
    try:
        instance = connector_cls()
        action_name = execute_data.action

        if not hasattr(instance, action_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Accion '{action_name}' no encontrada en conector '{name}'",
            )

        method = getattr(instance, action_name)
        result = method(**execute_data.params) if execute_data.params else method()
        duration_ms = (time.time() - start_time) * 1000

        output = result if isinstance(result, dict) else {"result": str(result)}

        return ConnectorExecuteResponse(
            success=True,
            action=action_name,
            output=output,
            duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ConnectorExecuteResponse(
            success=False,
            action=execute_data.action,
            output={"error": str(e), "error_type": type(e).__name__},
            duration_ms=duration_ms,
        )


@router.delete(
    "/{name}/config",
    summary="Eliminar configuracion de conector",
    description="Elimina las credenciales y configuracion almacenadas de un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_connector_config(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "delete")),
    db: DatabaseManager = Depends(get_db),
    redis: RedisService = Depends(get_redis),
) -> dict[str, Any]:
    """Elimina la configuracion almacenada de un conector."""
    existing = db.fetchone("SELECT id FROM connector_configs WHERE connector_name = ?", (name,))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuracion del conector '{name}' no encontrada",
        )

    db.execute("DELETE FROM connector_configs WHERE connector_name = ?", (name,))
    db.commit()

    # Invalidar cache
    redis.delete(f"connector_config:{name}")

    return {"status": "ok", "message": f"Configuracion del conector '{name}' eliminada"}


@router.get(
    "/{name}/schema",
    summary="Obtener esquema de conector",
    description="Obtiene el esquema de entrada/salida de un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_connector_schema(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "read")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> dict[str, Any]:
    """Obtiene el esquema de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    connector_cls = registry.get(name)
    schema_data = {
        "name": name,
        "input_schema": {},
        "output_schema": {},
        "actions": {},
    }

    if connector_cls:
        # Extraer esquemas de la clase
        if hasattr(connector_cls, "INPUT_SCHEMA"):
            schema_data["input_schema"] = connector_cls.INPUT_SCHEMA
        if hasattr(connector_cls, "OUTPUT_SCHEMA"):
            schema_data["output_schema"] = connector_cls.OUTPUT_SCHEMA
        if hasattr(connector_cls, "ACTION_SCHEMAS"):
            schema_data["actions"] = connector_cls.ACTION_SCHEMAS

    return schema_data


@router.get(
    "/{name}/health",
    summary="Health check de conector",
    description="Verifica el estado de salud de un conector.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def connector_health_check(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "read")),
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> dict[str, Any]:
    """Verifica el estado de salud de un conector."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado")

    connector_cls = registry.get(name)
    status_value = "unknown"

    if connector_cls:
        try:
            instance = connector_cls()
            if hasattr(instance, "health_check"):
                result = instance.health_check()
                status_value = "healthy" if result else "unhealthy"
            elif hasattr(instance, "test_connection"):
                result = instance.test_connection()
                status_value = "healthy" if result else "unhealthy"
            else:
                status_value = "available"
        except Exception as e:
            status_value = "unhealthy"
            return {"connector": name, "status": status_value, "error": str(e)}

    return {"connector": name, "status": status_value}
