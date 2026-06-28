"""
HAT NIVEL 4 — Idempotency para workers
=======================================

Hash determinista de (tool + action + params) para detectar duplicados.

Implementación completa en M7.
"""

from __future__ import annotations

import hashlib
import json


def compute_worker_hash(tool_name: str, action_name: str, params: dict[str, object]) -> str:
    """Hash sha256 de (tool_name + action_name + sorted(params)).

    Returns:
        Hex string de 16 caracteres.
    """
    canonical = json.dumps(
        {"tool": tool_name, "action": action_name, "params": params},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
