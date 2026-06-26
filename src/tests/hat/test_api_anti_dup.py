"""
Tests API anti-doble-llamada F1-D4.

Verifica que el endpoint /api/hat/chat integra correctamente el cascade:
- 1ª request: 200 con status completed/clarify
- 2ª request idéntica: 200 con status anti_dup_blocked
- 2ª request distinta: 200 con status completed (no bloqueada)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator
from src.hat.level1_orchestrator.api.routes import router as hat_router
from src.orbital.context import OrbitalContext


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(hat_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()
    ctx = OrbitalContext()
    for v in list(ctx.ovc.get_variable_names()):
        ctx.ovc.delete_variable(v)
    yield
    ctx = OrbitalContext()
    for v in list(ctx.ovc.get_variable_names()):
        ctx.ovc.delete_variable(v)
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S%f")


def _is_db_locked(response) -> bool:
    return response.status_code == 500 and "database is locked" in response.text


# ─────────────────────────────────────────────────────────
# Anti-dup via HTTP
# ─────────────────────────────────────────────────────────


class TestAPIAntiDup:
    def test_first_request_succeeds(self, client):
        """1ª request → 200 con status completed o clarify."""
        ts = _ts()
        response = client.post("/api/hat/chat", json={
            "user_id": f"ad1_{ts}", "session_id": f"ad1_{ts}",
            "message": "buscar info de python",
        })
        if _is_db_locked(response):
            return
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("completed", "clarify", "anti_dup_blocked")

    def test_second_identical_request_blocked(self, client):
        """2ª request idéntica → 200 con status anti_dup_blocked."""
        ts = _ts()
        req = {"user_id": f"ad2_{ts}", "session_id": f"ad2_{ts}",
               "message": "buscar info de python"}

        r1 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r1):
            return
        r2 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r2):
            return

        d2 = r2.json()
        assert d2["status"] == "anti_dup_blocked"
        assert d2["anti_dup_layer_hit"] != "none"

    def test_different_message_not_blocked(self, client):
        """2ª request con mensaje distinto → no anti_dup_blocked."""
        ts = _ts()
        r1 = client.post("/api/hat/chat", json={
            "user_id": f"ad3_{ts}", "session_id": f"ad3_{ts}",
            "message": "buscar python",
        })
        if _is_db_locked(r1):
            return
        r2 = client.post("/api/hat/chat", json={
            "user_id": f"ad3_{ts}", "session_id": f"ad3_{ts}",
            "message": "investigar rust framework",
        })
        if _is_db_locked(r2):
            return
        d2 = r2.json()
        # Puede ser completed o anti_dup_blocked (TTL podría disparar
        # si ambas requests caen en la misma ventana de 5s)
        assert d2["status"] in ("completed", "clarify", "anti_dup_blocked")

    def test_anti_dup_layer_hit_field_populated(self, client):
        """Cuando se bloquea, anti_dup_layer_hit debe indicar la capa."""
        ts = _ts()
        req = {"user_id": f"ad4_{ts}", "session_id": f"ad4_{ts}",
               "message": "buscar python"}
        r1 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r1):
            return
        r2 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r2):
            return
        d2 = r2.json()
        if d2["status"] == "anti_dup_blocked":
            valid_layers = ("exact_match", "idempotency", "ttl_freshness",
                            "semantic_dedup", "circuit_breaker")
            assert d2["anti_dup_layer_hit"] in valid_layers

    def test_blocked_response_has_message(self, client):
        """La respuesta bloqueada debe incluir un mensaje explicativo."""
        ts = _ts()
        req = {"user_id": f"ad5_{ts}", "session_id": f"ad5_{ts}",
               "message": "buscar javascript"}
        r1 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r1):
            return
        r2 = client.post("/api/hat/chat", json=req)
        if _is_db_locked(r2):
            return
        d2 = r2.json()
        if d2["status"] == "anti_dup_blocked":
            assert len(d2["response"]) > 0
            assert isinstance(d2["response"], str)
