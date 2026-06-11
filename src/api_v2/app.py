"""
Zenic-Flijo API v2 — Aplicacion FastAPI Principal
===================================================

Aplicacion FastAPI con:
- Titulo: Zenic-Flijo API v2
- Version: 2.0.0
- CORS middleware (configurable)
- Middleware de autenticacion (API Key + Bearer Token)
- Middleware de resolucion de tenant
- OpenTelemetry instrumentation (si esta disponible)
- Routers: workflows, connectors, nlu, tenants, marketplace, auth
- Health check: GET /api/v2/health
- API info: GET /api/v2/info
- Eventos startup/shutdown
- Manejadores de excepciones personalizados
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api_v2.models import APIInfoResponse, ErrorResponse, HealthResponse
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Tiempo de inicio ──────────────────────────────────────────

_start_time: float = 0.0


# ── Lifespan (startup/shutdown) ────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicacion: startup y shutdown."""
    global _start_time
    _start_time = time.time()
    logger.info("Zenic-Flijo API v2 iniciando...")

    # Inicializar servicios
    try:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        _ensure_api_v2_tables(db)
        logger.info("Base de datos inicializada para API v2")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")

    try:
        from src.observability.telemetry import TelemetryService

        telemetry = TelemetryService()
        telemetry.initialize()
        logger.info("Telemetria inicializada")
    except Exception as e:
        logger.warning(f"Telemetria no disponible: {e}")

    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry FastAPI instrumentation habilitada")
    except ImportError:
        logger.debug("opentelemetry-instrumentation-fastapi no instalado, instrumentation deshabilitada")

    logger.info("Zenic-Flijo API v2 lista para recibir requests")
    yield

    # Shutdown
    logger.info("Zenic-Flijo API v2 cerrando...")

    try:
        from src.observability.telemetry import TelemetryService

        telemetry = TelemetryService()
        telemetry.shutdown()
        logger.info("Telemetria cerrada")
    except Exception as e:
        logger.warning(f"Error cerrando telemetria: {e}")

    try:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        db.close_all()
        logger.info("Conexiones de base de datos cerradas")
    except Exception as e:
        logger.warning(f"Error cerrando base de datos: {e}")

    try:
        from src.data.redis_service import RedisService

        redis = RedisService()
        redis.close()
        logger.info("Conexion Redis cerrada")
    except Exception as e:
        logger.warning(f"Error cerrando Redis: {e}")

    logger.info("Zenic-Flijo API v2 cerrada correctamente")


def _ensure_api_v2_tables(db: Any) -> None:
    """Crea las tablas adicionales necesarias para la API v2."""
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            key_hash    TEXT UNIQUE NOT NULL,
            key_prefix  TEXT,
            user_id     INTEGER NOT NULL,
            tenant_id   TEXT,
            scopes      TEXT DEFAULT '[]',
            is_active   INTEGER DEFAULT 1,
            expires_at  TIMESTAMP,
            last_used_at TIMESTAMP,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
        CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);

        CREATE TABLE IF NOT EXISTS connector_configs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connector_name  TEXT UNIQUE NOT NULL,
            config          TEXT NOT NULL DEFAULT '{}',
            user_id         INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_connector_configs_name ON connector_configs(connector_name);

        CREATE TABLE IF NOT EXISTS marketplace_published (
            connector_name  TEXT PRIMARY KEY,
            version         TEXT NOT NULL,
            visibility      TEXT DEFAULT 'public',
            changelog       TEXT DEFAULT '',
            publisher_id    INTEGER,
            metadata        TEXT DEFAULT '{}',
            published_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (publisher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS user_mfa (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            method      TEXT NOT NULL DEFAULT 'totp',
            secret      TEXT DEFAULT '',
            backup_codes TEXT DEFAULT '[]',
            is_active   INTEGER DEFAULT 1,
            enabled_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_mfa_user ON user_mfa(user_id);
    """)
    conn.commit()


# ── Crear aplicacion FastAPI ───────────────────────────────────

app = FastAPI(
    title="Zenic-Flijo API v2",
    version="2.1.0",
    description=(
        "API publica v2 de Zenic-Flijo con mas de 70 endpoints para "
        "gestion de workflows, conectores, NLU, multi-tenancy, marketplace, "
        "agent framework, BPMN y compliance SOC 2."
    ),
    lifespan=lifespan,
    docs_url="/api/v2/docs",
    redoc_url="/api/v2/redoc",
    openapi_url="/api/v2/openapi.json",
)


# ── CORS Middleware ────────────────────────────────────────────

_cors_origins = os.environ.get("WFD_API_V2_CORS_ORIGINS", "*").split(",")
_cors_allow_all = "*" in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_allow_all else _cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


# ── Tenant Resolution Middleware ───────────────────────────────


@app.middleware("http")
async def tenant_resolution_middleware(request: Request, call_next):
    """Middleware que resuelve el tenant desde la solicitud y lo inyecta en el estado."""
    # Solo procesar rutas de la API v2
    if not request.url.path.startswith("/api/v2"):
        return await call_next(request)

    # Skip rutas que no necesitan tenant
    skip_paths = ("/api/v2/health", "/api/v2/info", "/api/v2/docs", "/api/v2/redoc", "/api/v2/openapi.json")
    if request.url.path in skip_paths:
        return await call_next(request)

    # Resolver tenant (sin bloquear si falla)
    try:
        from src.tenant.service import TenantService

        tenant_service = TenantService()
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            tenant = tenant_service.get_tenant(tenant_id)
            if tenant:
                request.state.tenant = tenant
                request.state.tenant_id = tenant_id
    except Exception as e:
        logger.debug(f"Error resolviendo tenant: {e}")

    return await call_next(request)


# ── Request ID Middleware ──────────────────────────────────────


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Middleware que agrega un ID unico a cada request."""
    import uuid

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Custom Exception Handlers ─────────────────────────────────


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Maneja errores de validacion de datos."""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(error="validation_error", message=str(exc)).model_dump(),
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    """Maneja errores de permisos."""
    return JSONResponse(
        status_code=403,
        content=ErrorResponse(error="permission_denied", message=str(exc)).model_dump(),
    )


@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError):
    """Maneja errores de conexion con servicios externos."""
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(error="connection_error", message=str(exc)).model_dump(),
    )


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request: Request, exc: TimeoutError):
    """Maneja errores de timeout."""
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(error="timeout", message=str(exc)).model_dump(),
    )


# ── Excepciones del SDK ───────────────────────────────────────

try:
    from src.sdk.exceptions import AuthenticationError, ConnectorError, ValidationError

    @app.exception_handler(ConnectorError)
    async def connector_error_handler(request: Request, exc: ConnectorError):
        """Maneja errores de conectores del SDK."""
        status_code = 502
        if isinstance(exc, AuthenticationError):
            status_code = 401
        elif isinstance(exc, ValidationError):
            status_code = 400
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error=exc.__class__.__name__,
                message=str(exc),
                details=exc.to_dict(),
            ).model_dump(),
        )

except ImportError:
    pass


# ── Incluir Routers ────────────────────────────────────────────

from src.api_v2.routers.agents import router as agents_router
from src.api_v2.routers.auth_routes import router as auth_router
from src.api_v2.routers.bpmn import router as bpmn_router
from src.api_v2.routers.compliance import router as compliance_router
from src.api_v2.routers.connectors import router as connectors_router
from src.api_v2.routers.marketplace import router as marketplace_router
from src.api_v2.routers.nlu import router as nlu_router
from src.api_v2.routers.tenants import router as tenants_router
from src.api_v2.routers.workflows import router as workflows_router
from src.mobile.api import router as mobile_router

app.include_router(workflows_router)
app.include_router(connectors_router)
app.include_router(nlu_router)
app.include_router(tenants_router)
app.include_router(marketplace_router)
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(bpmn_router)
app.include_router(compliance_router)
app.include_router(mobile_router)


# ── Health Check Endpoint ──────────────────────────────────────


@app.get(
    "/api/v2/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Verifica el estado de salud de la API v2 y sus servicios dependientes.",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """Verifica el estado de salud de la API v2 y sus dependencias."""
    services: dict[str, str] = {}

    # Verificar base de datos
    try:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        db.fetchone("SELECT 1 as test")
        services["database"] = "healthy"
    except Exception:
        services["database"] = "unhealthy"

    # Verificar Redis
    try:
        from src.data.redis_service import RedisService

        redis = RedisService()
        if redis.ping():
            services["redis"] = "healthy"
        else:
            services["redis"] = "unhealthy"
    except Exception:
        services["redis"] = "unavailable"

    # Verificar workflow engine
    try:
        from src.workflow.engine import WorkflowEngine

        WorkflowEngine()
        services["workflow_engine"] = "healthy"
    except Exception:
        services["workflow_engine"] = "unhealthy"

    # Verificar NLU
    try:
        from src.nlu.pipeline import Pipeline

        Pipeline()
        services["nlu"] = "healthy"
    except Exception:
        services["nlu"] = "unhealthy"

    # Verificar connector registry
    try:
        from src.sdk.registry import ConnectorRegistry

        registry = ConnectorRegistry()
        services["connector_registry"] = "healthy"
        services["connectors_count"] = str(registry.count())
    except Exception:
        services["connector_registry"] = "unhealthy"

    # Verificar agent runtime (Phase 3)
    try:
        from src.agents.runtime import AgentRuntime

        runtime = AgentRuntime.get_instance()
        stats = runtime.get_stats()
        services["agent_runtime"] = "healthy"
        services["agents_active"] = str(stats["active_count"])
    except Exception:
        services["agent_runtime"] = "unhealthy"

    # Verificar compliance manager (Phase 3)
    try:
        from src.compliance import ComplianceManager

        manager = ComplianceManager.get_instance()
        score = manager.calculate_compliance_score()
        services["compliance"] = "healthy"
        services["compliance_score"] = f"{score['overall_score']:.0f}%"
    except Exception:
        services["compliance"] = "unhealthy"

    # Verificar BPMN engine (Phase 3)
    try:
        from src.bpmn import BPMNParser

        services["bpmn_engine"] = "healthy"
    except Exception:
        services["bpmn_engine"] = "unhealthy"

    # Determinar estado general
    all_healthy = all(v in ("healthy", "unavailable") for v in services.values() if not v.replace(".", "").replace("%", "").isdigit())
    overall_status = "healthy" if all_healthy else "degraded"

    return HealthResponse(
        status=overall_status,
        version="2.1.0",
        uptime_seconds=time.time() - _start_time if _start_time else 0,
        services=services,
    )


# ── API Info Endpoint ──────────────────────────────────────────


@app.get(
    "/api/v2/info",
    response_model=APIInfoResponse,
    summary="API info",
    description="Retorna informacion general sobre la API v2.",
    tags=["System"],
)
async def api_info() -> APIInfoResponse:
    """Retorna informacion de la API v2."""
    # Contar endpoints
    endpoint_count = 0
    for route in app.routes:
        if hasattr(route, "methods"):
            endpoint_count += len(route.methods)

    return APIInfoResponse(
        name="Zenic-Flijo API v2",
        version="2.0.0",
        endpoints=endpoint_count,
        documentation="/api/v2/docs",
    )
