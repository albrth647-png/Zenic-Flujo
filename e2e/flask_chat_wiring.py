"""M8/M10: Flask web chat wiring con HATRouter.

Reemplaza el NLU directo con HATRouter en el blueprint de chat.
Este archivo debe integrarse en src/web/blueprints/nlu.py del repo original.

Flujo anterior (NLU directo):
    Usuario → Flask → NLU pipeline (13 etapas) → WorkflowEngine

Flujo nuevo (HAT):
    Usuario → Flask → HATRouter.handle() → Supervisor → Specialist → Tool

Beneficios:
- Routing por resonancia ORBITAL (no NLU lineal)
- Anti-dup cascade (3 capas)
- Ledger de memoria entre sesiones
- AgentCards para routing sin LLM
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request, session

bp = Blueprint("hat_chat", __name__, url_prefix="/api/hat")


def _get_hat_router() -> Any:
    """Obtiene el HATRouter singleton (lazy import para evitar circular)."""
    from src.hat import get_hat_router
    return get_hat_router()


@bp.route("/chat", methods=["POST"])
def chat() -> Any:
    """Endpoint de chat que usa HATRouter en vez de NLU directo.

    Reemplaza /api/workflows/chat del blueprint nlu.py.

    Request JSON:
        {
            "message": "listar leads",
            "context": {}  // opcional
        }

    Returns:
        JSON con: dispatch_id, domain, response, status, orbital_resonance,
        anti_dup_layer_hit, duration_ms, facts_updated.
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400

    user_id = str(session.get("user_id", "1"))
    session_id = str(session.get("session_id", "default"))
    context = data.get("context", {})

    try:
        router = _get_hat_router()
        result = router.handle(
            user_id=user_id,
            session_id=session_id,
            message=message,
            context=context,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Internal error: {exc}"}), 500


@bp.route("/health", methods=["GET"])
def health() -> Any:
    """Health check del endpoint HAT en Flask."""
    return jsonify({"status": "ok", "module": "hat_flask"})
