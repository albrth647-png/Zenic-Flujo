"""Tests para api/routes — endpoints FastAPI del HAT.

Cubre:
- HATRequest model: validación de campos requeridos.
- HATResponse model: estructura esperada.
- /chat endpoint: usa HATRouter singleton (no instancia por request).
- /health endpoint: retorna status ok.
- Manejo de errores: ValueError → 400, Exception → 500.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.hat.level1_orchestrator.api.routes import (
    HATRequest,
    HATResponse,
    health,
    router,
)

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    """App FastAPI con el router HAT montado."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient de FastAPI."""
    return TestClient(app)


# ── Tests de HATRequest ────────────────────────────────────────────────


class TestHATRequest:
    """Modelo HATRequest — validación de campos."""

    def test_valid_request(self) -> None:
        """Request con todos los campos requeridos es válido."""
        req = HATRequest(
            user_id="u1",
            session_id="s1",
            message="listar leads",
        )
        assert req.user_id == "u1"
        assert req.session_id == "s1"
        assert req.message == "listar leads"
        assert req.context == {}  # default

    def test_request_with_context(self) -> None:
        """Request con context opcional."""
        req = HATRequest(
            user_id="u1",
            session_id="s1",
            message="test",
            context={"key": "value"},
        )
        assert req.context == {"key": "value"}

    def test_empty_user_id_raises(self) -> None:
        """user_id vacío → ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HATRequest(user_id="", session_id="s1", message="test")

    def test_empty_session_id_raises(self) -> None:
        """session_id vacío → ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HATRequest(user_id="u1", session_id="", message="test")

    def test_empty_message_raises(self) -> None:
        """message vacío → ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HATRequest(user_id="u1", session_id="s1", message="")


# ── Tests de HATResponse ───────────────────────────────────────────────


class TestHATResponse:
    """Modelo HATResponse — estructura esperada."""

    def test_valid_response(self) -> None:
        """Response con todos los campos es válido."""
        resp = HATResponse(
            dispatch_id="disp_123",
            domain="operaciones",
            response="Resultado: lead creado",
            orbital_resonance=0.85,
            anti_dup_layer_hit="none",
            duration_ms=150,
            facts_updated=[],
            status="completed",
        )
        assert resp.dispatch_id == "disp_123"
        assert resp.domain == "operaciones"
        assert resp.orbital_resonance == 0.85
        assert resp.status == "completed"

    def test_response_with_facts_updated(self) -> None:
        """Response con facts_updated poblado."""
        resp = HATResponse(
            dispatch_id="d1",
            domain="operaciones",
            response="ok",
            orbital_resonance=0.5,
            anti_dup_layer_hit="none",
            duration_ms=100,
            facts_updated=["active_domain"],
            status="completed",
        )
        assert resp.facts_updated == ["active_domain"]


# ── Tests de /health endpoint ──────────────────────────────────────────


class TestHealthEndpoint:
    """GET /api/hat/health."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        """Health retorna status ok."""
        response = client.get("/api/hat/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "hat"

    def test_health_callable_directly(self) -> None:
        """health() puede invocarse directamente (async)."""
        import asyncio

        result = asyncio.run(health())
        assert result["status"] == "ok"
        assert result["module"] == "hat"


# ── Tests de /chat endpoint ────────────────────────────────────────────


class TestChatEndpoint:
    """POST /api/hat/chat."""

    def test_chat_uses_singleton_router(self, client: TestClient) -> None:
        """El endpoint usa get_hat_router() singleton (no HATRouter() por request)."""
        # Mock get_hat_router para verificar que se llama
        mock_router = MagicMock()
        mock_router.handle.return_value = {
            "dispatch_id": "disp_test",
            "domain": "operaciones",
            "response": "ok",
            "orbital_resonance": 0.5,
            "anti_dup_layer_hit": "none",
            "duration_ms": 100,
            "facts_updated": [],
            "status": "completed",
        }

        # Patch sys.modules para inyectar src.hat.bootstrap mockeado
        import sys

        mock_bootstrap = MagicMock()
        mock_bootstrap.get_hat_router.return_value = mock_router

        with patch.dict(sys.modules, {"src.hat.bootstrap": mock_bootstrap}):
            response = client.post(
                "/api/hat/chat",
                json={
                    "user_id": "u1",
                    "session_id": "s1",
                    "message": "listar leads",
                },
            )

        assert response.status_code == 200
        assert mock_router.handle.called
        data = response.json()
        assert data["dispatch_id"] == "disp_test"
        assert data["domain"] == "operaciones"

    def test_chat_returns_400_on_value_error(self, client: TestClient) -> None:
        """ValueError del router → 400."""
        mock_router = MagicMock()
        mock_router.handle.side_effect = ValueError("invalid input")

        import sys

        mock_bootstrap = MagicMock()
        mock_bootstrap.get_hat_router.return_value = mock_router

        with patch.dict(sys.modules, {"src.hat.bootstrap": mock_bootstrap}):
            response = client.post(
                "/api/hat/chat",
                json={
                    "user_id": "u1",
                    "session_id": "s1",
                    "message": "test",
                },
            )

        assert response.status_code == 400
        assert "invalid input" in response.json()["detail"]

    def test_chat_returns_500_on_unexpected_error(
        self, client: TestClient,
    ) -> None:
        """Exception inesperada → 500."""
        mock_router = MagicMock()
        mock_router.handle.side_effect = RuntimeError("boom")

        import sys

        mock_bootstrap = MagicMock()
        mock_bootstrap.get_hat_router.return_value = mock_router

        with patch.dict(sys.modules, {"src.hat.bootstrap": mock_bootstrap}):
            response = client.post(
                "/api/hat/chat",
                json={
                    "user_id": "u1",
                    "session_id": "s1",
                    "message": "test",
                },
            )

        assert response.status_code == 500
        assert "Error interno HAT" in response.json()["detail"]

    def test_chat_validates_request_body(self, client: TestClient) -> None:
        """Request sin campos requeridos → 422 (Pydantic validation)."""
        response = client.post(
            "/api/hat/chat",
            json={"user_id": "u1"},  # falta session_id y message
        )
        assert response.status_code == 422
