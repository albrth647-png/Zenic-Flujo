"""
Zenic-Flijo API v2 — Modelos Pydantic v2
==========================================

Modelos de solicitud y respuesta para todos los endpoints de la API v2.
Usa Pydantic v2 con model_config = ConfigDict(...) para configuracion.

Categorias:
- Workflow: Creacion, actualizacion, ejecucion de workflows
- Connector: Informacion, configuracion, pruebas de conectores
- NLU: Comprension, compilacion, simulacion de lenguaje natural
- Tenant: Gestion de multi-tenancy
- Auth: Autenticacion, API keys, tokens
- Marketplace: Busqueda y publicacion de conectores
- Common: Paginacion, errores, health check, info API
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Common Models ──────────────────────────────────────────────


class PaginationParams(BaseModel):
    """Parametros de paginacion para listados."""

    model_config = ConfigDict(json_schema_extra={"example": {"page": 1, "page_size": 20}})

    page: int = Field(default=1, ge=1, description="Numero de pagina (inicia en 1)")
    page_size: int = Field(default=20, ge=1, le=100, description="Elementos por pagina (max 100)")


class PaginatedResponse(BaseModel):
    """Respuesta paginada generica."""

    model_config = ConfigDict(json_schema_extra={"example": {"items": [], "total": 0, "page": 1, "page_size": 20}})

    items: list[Any] = Field(default_factory=list, description="Lista de elementos")
    total: int = Field(default=0, description="Total de elementos")
    page: int = Field(default=1, description="Pagina actual")
    page_size: int = Field(default=20, description="Elementos por pagina")
    total_pages: int = Field(default=0, description="Total de paginas")


class ErrorResponse(BaseModel):
    """Respuesta de error estandarizada."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"error": "not_found", "message": "Recurso no encontrado", "details": {}}}
    )

    error: str = Field(description="Codigo de error")
    message: str = Field(description="Mensaje descriptivo del error")
    details: dict[str, Any] = Field(default_factory=dict, description="Detalles adicionales del error")


class HealthResponse(BaseModel):
    """Respuesta del health check."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "healthy", "version": "2.0.0", "uptime_seconds": 3600, "services": {}}
        }
    )

    status: str = Field(description="Estado general: healthy, degraded, unhealthy")
    version: str = Field(description="Version de la API")
    uptime_seconds: float = Field(description="Tiempo activo en segundos")
    services: dict[str, str] = Field(default_factory=dict, description="Estado de servicios dependientes")


class APIInfoResponse(BaseModel):
    """Respuesta del endpoint de informacion de la API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Zenic-Flijo API v2",
                "version": "2.0.0",
                "endpoints": 55,
                "documentation": "/api/v2/docs",
            }
        }
    )

    name: str = Field(description="Nombre de la API")
    version: str = Field(description="Version de la API")
    endpoints: int = Field(description="Numero total de endpoints")
    documentation: str = Field(description="URL de la documentacion OpenAPI")


# ── Workflow Models ────────────────────────────────────────────


class WorkflowCreate(BaseModel):
    """Solicitud de creacion de workflow."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Mi Workflow",
                "description": "Descripcion del workflow",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            }
        }
    )

    name: str = Field(min_length=1, max_length=200, description="Nombre del workflow")
    description: str = Field(default="", max_length=2000, description="Descripcion del workflow")
    trigger_type: str = Field(default="manual", description="Tipo de trigger: manual, schedule, webhook, event")
    trigger_config: dict[str, Any] = Field(default_factory=dict, description="Configuracion del trigger")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Lista de pasos del workflow")


class WorkflowUpdate(BaseModel):
    """Solicitud de actualizacion de workflow."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "Workflow actualizado", "status": "active"}}
    )

    name: str | None = Field(default=None, min_length=1, max_length=200, description="Nuevo nombre")
    description: str | None = Field(default=None, max_length=2000, description="Nueva descripcion")
    trigger_type: str | None = Field(default=None, description="Nuevo tipo de trigger")
    trigger_config: dict[str, Any] | None = Field(default=None, description="Nueva configuracion del trigger")
    steps: list[dict[str, Any]] | None = Field(default=None, description="Nuevos pasos del workflow")
    status: str | None = Field(default=None, description="Nuevo estado: active, paused, archived")


class WorkflowResponse(BaseModel):
    """Respuesta con datos de un workflow."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str = ""
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowExecutionRequest(BaseModel):
    """Solicitud de ejecucion de workflow."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"trigger_data": {"key": "value"}, "async_execution": False}}
    )

    trigger_data: dict[str, Any] = Field(default_factory=dict, description="Datos de entrada para el trigger")
    async_execution: bool = Field(default=False, description="Ejecutar de forma asincrona")
    priority: int = Field(default=0, ge=0, le=10, description="Prioridad para ejecucion asincrona (0-10)")


class WorkflowExecutionResponse(BaseModel):
    """Respuesta de ejecucion de workflow."""

    model_config = ConfigDict(from_attributes=True)

    execution_id: int
    workflow_id: int
    status: str
    duration_ms: int = 0
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    orbital_espectro: dict[str, Any] | None = None
    orbital_variables: int = 0
    orbital_resonance: float = 0.0


class WorkflowExecutionDetail(BaseModel):
    """Detalle de una ejecucion de workflow."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    status: str
    trigger_data: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    step_logs: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowExportResponse(BaseModel):
    """Respuesta de exportacion de workflow."""

    model_config = ConfigDict(from_attributes=True)

    export_version: str = "1.0"
    exported_at: str
    name: str
    description: str = ""
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "active"


class WorkflowImportRequest(BaseModel):
    """Solicitud de importacion de workflow."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "export_version": "1.0",
                "name": "Workflow importado",
                "description": "",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            }
        }
    )

    export_version: str = Field(default="1.0", description="Version del formato de exportacion")
    name: str = Field(min_length=1, max_length=200, description="Nombre del workflow")
    description: str = Field(default="", description="Descripcion del workflow")
    trigger_type: str = Field(default="manual", description="Tipo de trigger")
    trigger_config: dict[str, Any] = Field(default_factory=dict, description="Configuracion del trigger")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Pasos del workflow")


# ── Connector Models ───────────────────────────────────────────


class ConnectorInfo(BaseModel):
    """Informacion de un conector registrado."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Nombre unico del conector")
    version: str = Field(default="1.0.0", description="Version del conector")
    description: str = Field(default="", description="Descripcion del conector")
    category: str = Field(default="general", description="Categoria del conector")
    icon: str = Field(default="plug", description="Icono del conector")
    author: str = Field(default="", description="Autor del conector")
    class_name: str = Field(default="", description="Nombre de la clase Python")
    module: str = Field(default="", description="Modulo Python del conector")


class ConnectorConfigRequest(BaseModel):
    """Solicitud de configuracion de credenciales de conector."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"auth_type": "api_key", "credentials": {"api_key": "sk-xxx"}}}
    )

    auth_type: str = Field(description="Tipo de autenticacion: api_key, basic, oauth2, oauth1, mtls, custom, none")
    credentials: dict[str, Any] = Field(default_factory=dict, description="Credenciales de autenticacion")
    config: dict[str, Any] = Field(default_factory=dict, description="Configuracion adicional del conector")


class ConnectorTestRequest(BaseModel):
    """Solicitud de prueba de conexion de conector."""

    model_config = ConfigDict(json_schema_extra={"example": {"action": "test", "params": {}}})

    action: str = Field(default="test", description="Accion a probar")
    params: dict[str, Any] = Field(default_factory=dict, description="Parametros para la prueba")


class ConnectorTestResponse(BaseModel):
    """Respuesta de prueba de conexion de conector."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(description="Si la prueba fue exitosa")
    message: str = Field(default="", description="Mensaje descriptivo del resultado")
    latency_ms: float = Field(default=0.0, description="Latencia de la prueba en milisegundos")
    details: dict[str, Any] = Field(default_factory=dict, description="Detalles adicionales")


class ConnectorActionInfo(BaseModel):
    """Informacion de una accion de conector."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Nombre de la accion")
    description: str = Field(default="", description="Descripcion de la accion")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="Esquema de entrada")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="Esquema de salida")


class ConnectorExecuteRequest(BaseModel):
    """Solicitud de ejecucion de accion de conector."""

    model_config = ConfigDict(json_schema_extra={"example": {"action": "send_message", "params": {"text": "Hola"}}})

    action: str = Field(description="Nombre de la accion a ejecutar")
    params: dict[str, Any] = Field(default_factory=dict, description="Parametros de la accion")


class ConnectorExecuteResponse(BaseModel):
    """Respuesta de ejecucion de accion de conector."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(description="Si la ejecucion fue exitosa")
    action: str = Field(description="Nombre de la accion ejecutada")
    output: dict[str, Any] = Field(default_factory=dict, description="Resultado de la ejecucion")
    duration_ms: float = Field(default=0.0, description="Duracion en milisegundos")


# ── NLU Models ────────────────────────────────────────────────


class NLUUnderstandRequest(BaseModel):
    """Solicitud de comprension de lenguaje natural."""

    model_config = ConfigDict(json_schema_extra={"example": {"text": "enviar correo a juan", "lang": "es"}})

    text: str = Field(min_length=1, max_length=5000, description="Texto en lenguaje natural")
    lang: str | None = Field(default=None, description="Idioma forzado (es, en). Auto-detectar si es None")


class NLUUnderstandResponse(BaseModel):
    """Respuesta de comprension de lenguaje natural."""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(description="Texto original")
    lang: str = Field(description="Idioma detectado o forzado")
    tokens: list[str] = Field(default_factory=list, description="Tokens extraidos")
    entities: list[dict[str, Any]] = Field(default_factory=list, description="Entidades detectadas")
    intents: list[dict[str, Any]] = Field(default_factory=list, description="Intenciones clasificadas")
    slots: list[dict[str, Any]] = Field(default_factory=list, description="Slots llenados")
    confidence: float = Field(default=0.0, description="Confianza general (0.0-1.0)")
    trace: list[str] = Field(default_factory=list, description="Traza del pipeline")


class NLUCompileRequest(BaseModel):
    """Solicitud de compilacion de workflow desde lenguaje natural."""

    model_config = ConfigDict(json_schema_extra={"example": {"text": "cuando llegue un correo enviar slack", "lang": "es"}})

    text: str = Field(min_length=1, max_length=5000, description="Texto en lenguaje natural")
    lang: str | None = Field(default=None, description="Idioma forzado (es, en)")


class NLUCompileResponse(BaseModel):
    """Respuesta de compilacion de workflow."""

    model_config = ConfigDict(from_attributes=True)

    workflow: dict[str, Any] = Field(default_factory=dict, description="Workflow compilado")
    explanation: str = Field(default="", description="Explicacion del workflow")
    missing_slots: list[str] = Field(default_factory=list, description="Slots faltantes")
    status: str = Field(description="Estado: ready, needs_clarification, ambiguous, unknown, validation_error")


class NLUDryRunRequest(BaseModel):
    """Solicitud de simulacion dry-run."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "enviar correo a juan", "lang": "es", "context": {}}}
    )

    text: str = Field(min_length=1, max_length=5000, description="Texto en lenguaje natural")
    lang: str | None = Field(default=None, description="Idioma forzado (es, en)")
    context: dict[str, Any] = Field(default_factory=dict, description="Contexto para la simulacion")


class NLUDryRunResponse(BaseModel):
    """Respuesta de simulacion dry-run."""

    model_config = ConfigDict(from_attributes=True)

    workflow_name: str = Field(default="", description="Nombre del workflow simulado")
    trigger_type: str = Field(default="", description="Tipo de trigger")
    total_steps: int = Field(default=0, description="Total de pasos")
    steps_that_would_succeed: int = Field(default=0, description="Pasos que tendrian exito")
    steps_that_would_fail: int = Field(default=0, description="Pasos que fallarian")
    warnings: list[str] = Field(default_factory=list, description="Advertencias de la simulacion")
    overall_feasible: bool = Field(default=False, description="Si el workflow es viable")
    summary: str = Field(default="", description="Resumen de la simulacion")


class NLUTrainRequest(BaseModel):
    """Solicitud de entrenamiento del pipeline NLU."""

    model_config = ConfigDict(json_schema_extra={"example": {"language": "es", "data": []}})

    language: str = Field(default="es", description="Idioma para el entrenamiento (es, en)")
    data: list[dict[str, Any]] = Field(default_factory=list, description="Datos de entrenamiento adicionales")


class NLUTrainResponse(BaseModel):
    """Respuesta de entrenamiento NLU."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str = Field(description="ID del trabajo de entrenamiento")
    status: str = Field(description="Estado: queued, training, completed, failed")
    message: str = Field(default="", description="Mensaje descriptivo")


class NLUTrainingStatus(BaseModel):
    """Estado del entrenamiento NLU."""

    model_config = ConfigDict(from_attributes=True)

    job_id: str = Field(description="ID del trabajo de entrenamiento")
    status: str = Field(description="Estado: queued, training, completed, failed")
    progress: float = Field(default=0.0, description="Progreso del entrenamiento (0.0-1.0)")
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


# ── Tenant Models ──────────────────────────────────────────────


class TenantCreate(BaseModel):
    """Solicitud de creacion de tenant."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "Acme Corp", "slug": "acme-corp", "plan": "free"}}
    )

    name: str = Field(min_length=1, max_length=200, description="Nombre del tenant")
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$", description="Slug URL-safe unico")
    plan: str = Field(default="free", description="Plan: free, smb, enterprise")
    config: dict[str, Any] = Field(default_factory=dict, description="Configuracion adicional")


class TenantUpdate(BaseModel):
    """Solicitud de actualizacion de tenant."""

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Acme Corp Updated", "plan": "smb"}})

    name: str | None = Field(default=None, min_length=1, max_length=200, description="Nuevo nombre")
    domain: str | None = Field(default=None, description="Dominio custom")
    plan: str | None = Field(default=None, description="Nuevo plan: free, smb, enterprise")
    config: dict[str, Any] | None = Field(default=None, description="Nueva configuracion")


class TenantResponse(BaseModel):
    """Respuesta con datos de un tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    domain: str | None = None
    plan: str = "free"
    status: str = "active"
    config: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)
    settings: dict[str, str] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class TenantUserCreate(BaseModel):
    """Solicitud de agregar usuario a tenant."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"username": "juan", "password": "secret123", "role": "editor"}}
    )

    username: str = Field(min_length=1, max_length=100, description="Nombre de usuario")
    password: str = Field(min_length=6, max_length=200, description="Contrasena del usuario")
    role: str = Field(default="admin", description="Rol: admin, editor, viewer")
    display_name: str = Field(default="", description="Nombre para mostrar")
    email: str = Field(default="", description="Correo electronico")


class TenantUserResponse(BaseModel):
    """Respuesta con datos de usuario de tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str = "admin"
    display_name: str = ""
    email: str = ""
    is_active: int = 1
    created_at: str | None = None


class TenantFeatureToggle(BaseModel):
    """Solicitud de toggle de feature de tenant."""

    model_config = ConfigDict(json_schema_extra={"example": {"enabled": True}})

    enabled: bool = Field(description="True para habilitar, False para deshabilitar")


# ── Auth Models ────────────────────────────────────────────────


class APIKeyCreate(BaseModel):
    """Solicitud de creacion de API key."""

    model_config = ConfigDict(json_schema_extra={"example": {"name": "Mi API Key", "scopes": ["workflow:read"]}})

    name: str = Field(min_length=1, max_length=100, description="Nombre descriptivo de la API key")
    scopes: list[str] = Field(default_factory=list, description="Lista de scopes (permisos) de la API key")
    expires_in_days: int | None = Field(default=None, ge=1, le=3650, description="Dias hasta expiracion (None = sin expiracion)")


class APIKeyResponse(BaseModel):
    """Respuesta con datos de API key."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    key: str = Field(default="", description="API key (solo visible en creacion)")
    key_prefix: str = Field(default="", description="Prefijo de la API key para identificacion")
    scopes: list[str] = Field(default_factory=list)
    created_at: str | None = None
    expires_at: str | None = None
    last_used_at: str | None = None
    is_active: bool = True


class TokenRequest(BaseModel):
    """Solicitud de token de autenticacion."""

    model_config = ConfigDict(json_schema_extra={"example": {"username": "admin", "password": "secret"}})

    username: str = Field(min_length=1, description="Nombre de usuario")
    password: str = Field(min_length=1, description="Contrasena")


class TokenResponse(BaseModel):
    """Respuesta con token de autenticacion."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(description="Token de acceso JWT")
    refresh_token: str = Field(default="", description="Token de refresco JWT")
    token_type: str = Field(default="bearer", description="Tipo de token")
    expires_in: int = Field(default=3600, description="Segundos hasta expiracion del token")
    user_id: int = Field(description="ID del usuario autenticado")
    username: str = Field(description="Nombre del usuario autenticado")
    role: str = Field(default="admin", description="Rol del usuario")


class RefreshTokenRequest(BaseModel):
    """Solicitud de refresco de token."""

    model_config = ConfigDict(json_schema_extra={"example": {"refresh_token": "eyJ..."}})

    refresh_token: str = Field(min_length=1, description="Token de refresco")


class MFAEnableRequest(BaseModel):
    """Solicitud de activacion de MFA."""

    model_config = ConfigDict(json_schema_extra={"example": {"method": "totp"}})

    method: str = Field(default="totp", description="Metodo MFA: totp, sms, email")


class MFAVerifyRequest(BaseModel):
    """Solicitud de verificacion de codigo MFA."""

    model_config = ConfigDict(json_schema_extra={"example": {"code": "123456", "method": "totp"}})

    code: str = Field(min_length=4, max_length=8, description="Codigo MFA")
    method: str = Field(default="totp", description="Metodo MFA usado")


# ── Marketplace Models ─────────────────────────────────────────


class ConnectorSearchRequest(BaseModel):
    """Solicitud de busqueda de conectores en el marketplace."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"query": "slack", "category": "messaging", "page": 1, "page_size": 20}}
    )

    query: str = Field(default="", max_length=200, description="Termino de busqueda")
    category: str | None = Field(default=None, description="Filtrar por categoria")
    page: int = Field(default=1, ge=1, description="Numero de pagina")
    page_size: int = Field(default=20, ge=1, le=100, description="Elementos por pagina")
    sort_by: str = Field(default="name", description="Ordenar por: name, downloads, rating, updated")
    sort_order: str = Field(default="asc", description="Orden: asc, desc")


class ConnectorSearchResult(BaseModel):
    """Resultado individual de busqueda de conector."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"
    icon: str = "plug"
    author: str = ""
    downloads: int = 0
    rating: float = 0.0
    installed: bool = False


class ConnectorSearchResponse(BaseModel):
    """Respuesta de busqueda de conectores."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ConnectorSearchResult] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class ConnectorPublishRequest(BaseModel):
    """Solicitud de publicacion de conector al marketplace."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"connector_name": "mi_conector", "version": "1.0.0", "visibility": "public"}}
    )

    connector_name: str = Field(min_length=1, max_length=100, description="Nombre del conector a publicar")
    version: str = Field(default="1.0.0", description="Version a publicar")
    visibility: str = Field(default="public", description="Visibilidad: public, private, organization")
    changelog: str = Field(default="", description="Notas de la version")


class MarketplaceCategory(BaseModel):
    """Categoria del marketplace."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Nombre de la categoria")
    count: int = Field(default=0, description="Numero de conectores en la categoria")
    icon: str = Field(default="folder", description="Icono de la categoria")


class MarketplaceStats(BaseModel):
    """Estadisticas del marketplace."""

    model_config = ConfigDict(from_attributes=True)

    total_connectors: int = 0
    total_downloads: int = 0
    total_categories: int = 0
    featured_connectors: list[str] = Field(default_factory=list, description="Nombres de conectores destacados")


# ── Event Models ───────────────────────────────────────────────


class WorkflowEvent(BaseModel):
    """Evento de workflow (para endpoint de eventos)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str = Field(description="Tipo de evento")
    event_data: dict[str, Any] = Field(default_factory=dict, description="Datos del evento")
    status: str = Field(default="pending", description="Estado del evento")
    created_at: str | None = None
    processed_at: str | None = None
