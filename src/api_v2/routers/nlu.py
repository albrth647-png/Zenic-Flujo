"""
Zenic-Flijo API v2 — Router de NLU (Natural Language Understanding)
===================================================================

Endpoints del pipeline de procesamiento de lenguaje natural:
- POST /api/v2/nlu/understand   — Pipeline completo NLU (etapas 1-6)
- POST /api/v2/nlu/compile      — Compilar workflow desde texto (etapas 1-11)
- POST /api/v2/nlu/dry-run      — Simulacion dry-run (etapas 1-12)
- GET  /api/v2/nlu/intents      — Listar intenciones registradas
- GET  /api/v2/nlu/entities     — Listar tipos de entidades
- POST /api/v2/nlu/train        — Disparar entrenamiento NLU
- GET  /api/v2/nlu/status       — Estado del entrenamiento
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.db import DatabaseManager, RedisService
    from src.nlu.pipeline import Pipeline

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import require_permission
from src.api_v2.dependencies import get_db, get_nlu_pipeline, get_redis
from src.api_v2.models import (
    ErrorResponse,
    NLUCompileRequest,
    NLUCompileResponse,
    NLUDryRunRequest,
    NLUDryRunResponse,
    NLUTrainRequest,
    NLUTrainResponse,
    NLUTrainingStatus,
    NLUUnderstandRequest,
    NLUUnderstandResponse,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/nlu", tags=["NLU"])


@router.post(
    "/understand",
    response_model=NLUUnderstandResponse,
    summary="Comprender texto en lenguaje natural",
    description="Ejecuta el pipeline NLU completo (etapas 1-6): normalizacion, tokenizacion, deteccion de idioma, extraccion de entidades, clasificacion de intenciones y llenado de slots.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def understand_text(
    request: NLUUnderstandRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    pipeline: Pipeline = Depends(get_nlu_pipeline),
) -> NLUUnderstandResponse:
    """Ejecuta el pipeline NLU (etapas 1-6) para comprender texto en lenguaje natural."""
    try:
        result = pipeline.process(request.text, lang=request.lang)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en pipeline NLU: {e}",
        ) from e

    return NLUUnderstandResponse(
        text=result.text,
        lang=result.lang,
        tokens=list(result.tokens),
        entities=[{"type": e.type, "value": e.value, "span": list(e.span)} for e in result.entities],
        intents=[{"intent": i.intent, "score": i.score} for i in result.intents],
        slots=[{"name": s.name, "value": s.value} for s in result.slots],
        confidence=result.confidence,
        trace=list(result.trace),
    )


@router.post(
    "/compile",
    response_model=NLUCompileResponse,
    summary="Compilar workflow desde lenguaje natural",
    description="Ejecuta el pipeline completo (etapas 1-11): analisis NLU + desambiguacion + compilacion + validacion + explicacion.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def compile_workflow(
    request: NLUCompileRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "create")),
    pipeline: Pipeline = Depends(get_nlu_pipeline),
) -> NLUCompileResponse:
    """Compila un workflow desde texto en lenguaje natural."""
    try:
        result = pipeline.compile(request.text, lang=request.lang)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error compilando workflow: {e}",
        ) from e

    return NLUCompileResponse(
        workflow=result.workflow,
        explanation=result.explanation,
        missing_slots=list(result.missing_slots),
        status=result.status,
    )


@router.post(
    "/dry-run",
    response_model=NLUDryRunResponse,
    summary="Simulacion dry-run de workflow",
    description="Ejecuta una simulacion completa (etapas 1-12) sin efectos secundarios para validar la viabilidad de un workflow.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def dry_run_workflow(
    request: NLUDryRunRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    pipeline: Pipeline = Depends(get_nlu_pipeline),
) -> NLUDryRunResponse:
    """Ejecuta una simulacion dry-run del pipeline NLU."""
    try:
        result = pipeline.simulate(request.text, lang=request.lang, context=request.context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en simulacion dry-run: {e}",
        ) from e

    return NLUDryRunResponse(
        workflow_name=result.workflow_name,
        trigger_type=result.trigger_type,
        total_steps=result.total_steps,
        steps_that_would_succeed=result.steps_that_would_succeed,
        steps_that_would_fail=result.steps_that_would_fail,
        warnings=list(result.warnings),
        overall_feasible=result.overall_feasible,
        summary=result.summary,
    )


@router.get(
    "/intents",
    summary="Listar intenciones registradas",
    description="Lista todas las intenciones registradas en el sistema NLU.",
    responses={401: {"model": ErrorResponse}},
)
async def list_intents(
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    db: DatabaseManager = Depends(get_db),
) -> dict[str, Any]:
    """Lista las intenciones registradas en el clasificador de intenciones."""
    from src.nlu.intent_classifier import IntentClassifier

    classifier = IntentClassifier()

    # Obtener intenciones desde la base de datos
    intent_vectors = db.fetchall("SELECT DISTINCT intent FROM nlp_intent_vectors ORDER BY intent")
    synonyms = db.fetchall("SELECT DISTINCT intent FROM nlp_synonyms ORDER BY intent")

    # Combinar fuentes
    intents_set = set()
    for row in intent_vectors:
        intents_set.add(row["intent"])
    for row in synonyms:
        intents_set.add(row["intent"])

    # Agregar intenciones del clasificador si tiene datos
    if hasattr(classifier, "_intents"):
        intents_set.update(classifier._intents.keys())

    intents = sorted(intents_set)

    return {
        "intents": [{"name": intent, "source": "database"} for intent in intents],
        "total": len(intents),
    }


@router.get(
    "/entities",
    summary="Listar tipos de entidades",
    description="Lista todos los tipos de entidades soportados por el extractor NLU.",
    responses={401: {"model": ErrorResponse}},
)
async def list_entities(
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
) -> dict[str, Any]:
    """Lista los tipos de entidades soportados por el sistema NLU."""
    entity_types = [
        {"name": "email", "description": "Direcciones de correo electronico", "patterns": ["regex"]},
        {"name": "url", "description": "URLs y enlaces web", "patterns": ["regex"]},
        {"name": "phone", "description": "Numeros de telefono", "patterns": ["regex"]},
        {"name": "date", "description": "Fechas en diversos formatos", "patterns": ["regex"]},
        {"name": "money", "description": "Cantidades monetarias", "patterns": ["regex", "keyword"]},
        {"name": "quantity", "description": "Cantidades numericas con unidades", "patterns": ["regex"]},
        {"name": "duration", "description": "Duraciones de tiempo", "patterns": ["regex", "keyword"]},
        {"name": "condition", "description": "Condiciones y operadores logicos", "patterns": ["keyword"]},
        {"name": "person", "description": "Nombres de personas", "patterns": ["keyword"]},
    ]

    return {
        "entities": entity_types,
        "total": len(entity_types),
    }


@router.post(
    "/train",
    response_model=NLUTrainResponse,
    summary="Disparar entrenamiento NLU",
    description="Inicia un trabajo de entrenamiento del pipeline NLU. El entrenamiento se ejecuta de forma asincrona.",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def train_nlu(
    request: NLUTrainRequest,
    user: dict[str, Any] = Depends(require_permission("workflow", "create")),
    db: DatabaseManager = Depends(get_db),
    redis: RedisService = Depends(get_redis),
) -> NLUTrainResponse:
    """Dispara un entrenamiento del pipeline NLU."""
    # Verificar si ya hay un entrenamiento en curso
    current_training = redis.get_json("nlu:training:status")
    if current_training and current_training.get("status") == "training":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya hay un entrenamiento NLU en curso. Espere a que termine.",
        )

    # Crear trabajo de entrenamiento
    job_id = str(uuid.uuid4())
    training_status = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "language": request.language,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
    }

    # Almacenar estado del entrenamiento
    redis.set_json("nlu:training:status", training_status, ttl=3600)

    # En una implementacion completa, esto encolaria el entrenamiento en un worker
    # Por ahora, marcamos como completado inmediatamente (solo re-indexa datos existentes)
    try:
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()
        # Re-cargar datos de entrenamiento
        if hasattr(classifier, "_load_training_data"):
            classifier._load_training_data()

        training_status["status"] = "completed"
        training_status["progress"] = 1.0
        redis.set_json("nlu:training:status", training_status, ttl=3600)
    except Exception as e:
        training_status["status"] = "failed"
        training_status["error_message"] = str(e)
        redis.set_json("nlu:training:status", training_status, ttl=3600)

    return NLUTrainResponse(
        job_id=job_id,
        status=training_status["status"],
        message=f"Entrenamiento NLU {training_status['status']} para idioma {request.language}",
    )


@router.get(
    "/status",
    response_model=NLUTrainingStatus,
    summary="Estado del entrenamiento NLU",
    description="Obtiene el estado actual del ultimo trabajo de entrenamiento NLU.",
    responses={401: {"model": ErrorResponse}},
)
async def get_training_status(
    user: dict[str, Any] = Depends(require_permission("workflow", "read")),
    redis: RedisService = Depends(get_redis),
) -> NLUTrainingStatus:
    """Obtiene el estado del entrenamiento NLU."""
    training_status = redis.get_json("nlu:training:status")

    if not training_status:
        return NLUTrainingStatus(
            job_id="none",
            status="idle",
            progress=0.0,
        )

    return NLUTrainingStatus(
        job_id=training_status.get("job_id", "unknown"),
        status=training_status.get("status", "unknown"),
        progress=training_status.get("progress", 0.0),
        started_at=training_status.get("started_at"),
        completed_at=training_status.get("completed_at"),
        error_message=training_status.get("error_message"),
    )
