"""
HAT-ORBITAL Nivel 0 — Intent Hasher.

Genera hashes deterministas para anti-doble-llamada (capa 1 Exact Match
y capa 2 Idempotency Lock del F1).

Hash = sha256(user_id + session_id + normalized_intent + sorted(params))
El mismo input siempre produce el mismo hash → permite detectar duplicados
sin necesidad de LLM ni comparaciones semánticas.

Implementado en F0-D7.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.intent.normalizer import normalize_intent

logger = setup_logging(__name__)


def compute_intent_hash(
    user_id: str,
    session_id: str,
    intent: str,
    params: dict[str, object] | None = None,
) -> str:
    """Calcula el hash determinista de un intent del usuario.

    El hash es sha256 de:
        user_id + "|" + session_id + "|" + normalize_intent(intent) + "|" + sorted(params)

    Args:
        user_id: ID del usuario.
        session_id: ID de la sesión.
        intent: Texto del usuario (se normaliza antes de hashear).
        params: Parámetros adicionales (se serializan como JSON con keys sorted).

    Returns:
        Hex string de 64 caracteres (sha256).

    Raises:
        TypeError: Si user_id o session_id no son strings.
    """
    if not isinstance(user_id, str):
        raise TypeError(f"user_id debe ser str, no {type(user_id).__name__}")
    if not isinstance(session_id, str):
        raise TypeError(f"session_id debe ser str, no {type(session_id).__name__}")

    normalized = normalize_intent(intent)
    params = params or {}
    params_json = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)

    payload = f"{user_id}|{session_id}|{normalized}|{params_json}"
    result = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    logger.debug("compute_intent_hash: user=%s, session=%s, normalized='%.40s' -> hash=%.12s",
                 user_id, session_id, normalized, result)
    return result
