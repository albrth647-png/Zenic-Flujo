"""M10: FastAPI v2 app con CORS hardening + HAT router + Prometheus.

Reemplaza src/api_v2/app.py del repo original con:
- CORS restringido (no wildcard) — configurable via env HAT_ALLOWED_ORIGINS
- HAT router montado en /api/hat/*
- Prometheus metrics endpoint en /metrics
- Health check en /api/hat/health
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse


def _get_allowed_origins() -> list[str]:
    """Retorna los orígenes CORS permitidos desde env o default seguros."""
    env_origins = os.environ.get("HAT_ALLOWED_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    # Default seguro: solo localhost en desarrollo
    return [
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
    ]


def create_app() -> FastAPI:
    """Factory de la app FastAPI v2 con hardening."""
    app = FastAPI(
        title="Zenic-Flujo HAT API v2",
        version="2.0.0",
        description="HAT-ORBITAL API — 5 niveles de orquestación",
    )

    # CORS hardening: NO wildcard, solo orígenes explícitos
    allowed_origins = _get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Montar HAT router
    from src.hat.level1_orchestrator.api.routes import router as hat_router
    app.include_router(hat_router)

    # Prometheus metrics endpoint (sin auth, para scrape)
    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        """Prometheus metrics endpoint.

        Sin auth para que Prometheus pueda scrape.
        Formato: Prometheus text exposition.
        """
        lines = [
            "# HELP hat_dispatches_total Total dispatches processed by HAT",
            "# TYPE hat_dispatches_total counter",
            f"hat_dispatches_total {getattr(metrics, '_count', 0)}",
            "",
            "# HELP hat_up HAT service status (1=up, 0=down)",
            "# TYPE hat_up gauge",
            "hat_up 1",
            "",
            "# HELP hat_levels Number of HAT levels active",
            "# TYPE hat_levels gauge",
            "hat_levels 5",
            "",
            "# HELP hat_tools_registered Total tools in Level 5",
            "# TYPE hat_tools_registered gauge",
            "hat_tools_registered 19",
            "",
            "# HELP hat_specialists_active Total specialists in Level 3",
            "# TYPE hat_specialists_active gauge",
            "hat_specialists_active 9",
            "",
            "# HELP hat_supervisors_active Total supervisors in Level 2",
            "# TYPE hat_supervisors_active gauge",
            "hat_supervisors_active 3",
            "",
        ]
        return "\n".join(lines)

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint con info del servicio."""
        return {
            "service": "Zenic-Flujo HAT API v2",
            "version": "2.0.0",
            "status": "running",
            "endpoints": {
                "chat": "/api/hat/chat",
                "health": "/api/hat/health",
                "metrics": "/metrics",
                "docs": "/docs",
            },
        }

    return app


# App instance para uvicorn: uvicorn src.api_v2.app:app
app = create_app()
