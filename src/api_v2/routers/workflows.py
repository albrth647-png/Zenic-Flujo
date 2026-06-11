"""
Zenic-Flijo API v2 — Router de Workflows
=========================================

Endpoints CRUD + ejecucion + monitoreo de workflows:
- GET    /api/v2/workflows                     — Listar workflows con paginacion
- POST   /api/v2/workflows                     — Crear workflow
- GET    /api/v2/workflows/{id}                — Obtener workflow por ID
- PUT    /api/v2/workflows/{id}                — Actualizar workflow
- DELETE /api/v2/workflows/{id}                — Eliminar workflow
- POST   /api/v2/workflows/{id}/execute        — Ejecutar workflow
- POST   /api/v2/workflows/{id}/stop           — Detener ejecucion
- GET    /api/v2/workflows/{id}/executions     — Listar ejecuciones
- GET    /api/v2/workflows/{id}/executions/{exec_id} — Detalle de ejecucion
- GET    /api/v2/workflows/{id}/export         — Exportar como JSON
- POST   /api/v2/workflows/import              — Importar desde JSON
- GET    /api/v2/workflows/{id}/events         — Obtener log de eventos
"""

from __future__ import annotations

import json
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import require_permission
from src.api_v2.dependencies import (
    get_db,
    get_pagination,
    get_workflow_engine,
    get_workflow_repository,
)
from src.api_v2.models import (
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    WorkflowCreate,
    WorkflowExecutionDetail,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    WorkflowExportResponse,
    WorkflowImportRequest,
    WorkflowResponse,
    WorkflowUpdate,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/workflows", tags=["Workflows"])


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="Listar workflows",
    description="Lista todos los workflows con paginacion y filtro opcional por estado.",
    responses={401: {"model": ErrorResponse}},
)
async def list_workflows(
    status_filter: str | None = None,
    pagination: PaginationParams = Depends(get_pagination),
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    repo: Any = Depends(get_workflow_repository),
) -> PaginatedResponse:
    """Lista workflows con paginacion y filtro opcional por estado."""
    all_workflows = repo.list_all(status=status_filter)
    total = len(all_workflows)
    total_pages = math.ceil(total / pagination.page_size) if total > 0 else 0

    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    page_items = all_workflows[start:end]

    items = [WorkflowResponse(**wf.to_dict()) for wf in page_items]

    return PaginatedResponse(
        items=[item.model_dump() for item in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear workflow",
    description="Crea un nuevo workflow con los datos proporcionados.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def create_workflow(
    workflow_data: WorkflowCreate,
    user: dict[str, Any] = Depends(require_permission("workflow", "create")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowResponse:
    """Crea un nuevo workflow."""
    from src.workflow.repository import WorkflowDefinition

    definition = WorkflowDefinition(
        name=workflow_data.name,
        description=workflow_data.description,
        trigger_type=workflow_data.trigger_type,
        trigger_config=workflow_data.trigger_config,
        steps=workflow_data.steps,
    )

    try:
        created = repo.create(definition, user_id=user.get("user_id", 1))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return WorkflowResponse(**created.to_dict())


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Obtener workflow",
    description="Obtiene los datos completos de un workflow por su ID.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_workflow(
    workflow_id: int,
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowResponse:
    """Obtiene un workflow por su ID."""
    definition = repo.get(workflow_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")
    return WorkflowResponse(**definition.to_dict())


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Actualizar workflow",
    description="Actualiza los campos de un workflow existente.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowUpdate,
    user: dict[str, Any] = Depends(require_permission("workflow", "update")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowResponse:
    """Actualiza un workflow existente."""
    updates = workflow_data.model_dump(exclude_none=True)
    if not updates:
        definition = repo.get(workflow_id)
        if not definition:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")
        return WorkflowResponse(**definition.to_dict())

    updated = repo.update(workflow_id, updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")
    return WorkflowResponse(**updated.to_dict())


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar workflow",
    description="Elimina un workflow y todas sus ejecuciones asociadas.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_workflow(
    workflow_id: int,
    user: dict[str, Any] = Depends(require_permission("workflow", "delete")),
    repo: Any = Depends(get_workflow_repository),
) -> None:
    """Elimina un workflow por su ID."""
    definition = repo.get(workflow_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")
    repo.delete(workflow_id)


@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecutionResponse,
    summary="Ejecutar workflow",
    description="Ejecuta un workflow con los datos de trigger proporcionados.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def execute_workflow(
    workflow_id: int,
    execution_data: WorkflowExecutionRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "execute")),
    engine: Any = Depends(get_workflow_engine),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowExecutionResponse:
    """Ejecuta un workflow de forma sincrona o asincrona."""
    definition = repo.get(workflow_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")

    if execution_data.async_execution:
        try:
            result = engine.execute_async(workflow_id, execution_data.trigger_data, execution_data.priority)
            return WorkflowExecutionResponse(
                execution_id=result.get("queue_id", 0),
                workflow_id=workflow_id,
                status="queued",
                duration_ms=0,
                step_results=[],
                error_message=None,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        result = engine.execute(workflow_id, execution_data.trigger_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error ejecutando workflow: {e}"
        ) from e

    return WorkflowExecutionResponse(
        execution_id=result.execution_id,
        workflow_id=result.workflow_id,
        status=result.status,
        duration_ms=result.duration_ms,
        step_results=result.step_results,
        error_message=result.error_message,
        orbital_espectro=result.orbital_espectro,
        orbital_variables=result.orbital_variables,
        orbital_resonance=result.orbital_resonance,
    )


@router.post(
    "/{workflow_id}/stop",
    summary="Detener ejecucion de workflow",
    description="Pausa un workflow activo. No detiene ejecuciones en progreso.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def stop_workflow(
    workflow_id: int,
    user: dict[str, Any] = Depends(require_permission("workflow", "execute")),
    engine: Any = Depends(get_workflow_engine),
    repo: Any = Depends(get_workflow_repository),
) -> dict[str, Any]:
    """Detiene (pausa) un workflow activo."""
    definition = repo.get(workflow_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")

    success = engine.pause(workflow_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"No se pudo detener el workflow {workflow_id}"
        )

    return {"status": "paused", "workflow_id": workflow_id}


@router.get(
    "/{workflow_id}/executions",
    response_model=PaginatedResponse,
    summary="Listar ejecuciones de workflow",
    description="Lista las ejecuciones de un workflow con paginacion.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def list_workflow_executions(
    workflow_id: int,
    limit: int = 50,
    pagination: PaginationParams = Depends(get_pagination),
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    repo: Any = Depends(get_workflow_repository),
) -> PaginatedResponse:
    """Lista las ejecuciones de un workflow."""
    definition = repo.get(workflow_id)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")

    executions = repo.list_executions(workflow_id, limit=limit)
    total = len(executions)

    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    page_items = executions[start:end]

    items = [exec_data.to_dict() for exec_data in page_items]

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=math.ceil(total / pagination.page_size) if total > 0 else 0,
    )


@router.get(
    "/{workflow_id}/executions/{exec_id}",
    response_model=WorkflowExecutionDetail,
    summary="Detalle de ejecucion",
    description="Obtiene el detalle completo de una ejecucion de workflow.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_workflow_execution(
    workflow_id: int,
    exec_id: int,
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowExecutionDetail:
    """Obtiene el detalle de una ejecucion de workflow."""
    execution = repo.get_execution(exec_id)
    if not execution or execution.workflow_id != workflow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ejecucion {exec_id} no encontrada")

    step_logs = repo.get_step_logs(exec_id)

    return WorkflowExecutionDetail(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        trigger_data=execution.trigger_data,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        duration_ms=execution.duration_ms,
        error_message=execution.error_message,
        step_logs=step_logs,
    )


@router.get(
    "/{workflow_id}/export",
    response_model=WorkflowExportResponse,
    summary="Exportar workflow",
    description="Exporta un workflow completo como JSON para importacion posterior.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def export_workflow(
    workflow_id: int,
    user: dict[str, Any] = Depends(require_permission("workflow", "export")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowExportResponse:
    """Exporta un workflow como JSON."""
    exported = repo.export_workflow(workflow_id)
    if not exported:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")

    return WorkflowExportResponse(**exported)


@router.post(
    "/import",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Importar workflow",
    description="Importa un workflow desde JSON exportado previamente.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def import_workflow(
    import_data: WorkflowImportRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "import")),
    repo: Any = Depends(get_workflow_repository),
) -> WorkflowResponse:
    """Importa un workflow desde JSON."""
    try:
        imported = repo.import_workflow(import_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return WorkflowResponse(**imported.to_dict())


@router.get(
    "/{workflow_id}/events",
    summary="Obtener eventos de workflow",
    description="Obtiene el log de eventos asociados a un workflow (durable).",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_workflow_events(
    workflow_id: int,
    limit: int = 50,
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene los eventos de un workflow desde la cola de eventos."""
    definition = db.fetchone("SELECT id FROM workflow_definitions WHERE id = ?", (workflow_id,))
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow {workflow_id} no encontrado")

    events = db.fetchall(
        "SELECT * FROM event_queue WHERE workflow_id = ? ORDER BY created_at DESC LIMIT ?",
        (workflow_id, limit),
    )

    items = []
    for event in events:
        event_data = dict(event)
        if isinstance(event_data.get("event_data"), str):
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                event_data["event_data"] = json.loads(event_data["event_data"])
        items.append(event_data)

    return {"workflow_id": workflow_id, "events": items, "total": len(items)}
