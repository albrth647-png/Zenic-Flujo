"""
Webhook Callback Registry — Registro de callbacks asíncronos.
Sprint 5.4 del Roadmap Competitivo.
"""

from __future__ import annotations

import secrets
import threading
import time

from src.utils.logger import setup_logging
from typing import Any

logger = setup_logging(__name__)


class WebhookCallbackRegistry:
    """
    Registro de callbacks asíncronos para webhooks.

    Permite registrar una URL de callback que será llamada cuando
    una respuesta asíncrona esté disponible. Almacena el estado
    de los callbacks (pending, completed, failed) en memoria.
    """

    def __init__(self):
        self._callbacks: dict[str, dict] = {}
        self._lock = threading.RLock()

    def register(self, callback_url: str, original_request: dict[str, Any], timeout_seconds: int = 3600) -> str:
        callback_id = secrets.token_hex(16)
        with self._lock:
            self._callbacks[callback_id] = {
                "id": callback_id,
                "callback_url": callback_url,
                "original_request": original_request,
                "status": "pending",
                "response": None,
                "created_at": time.time(),
                "expires_at": time.time() + timeout_seconds,
                "error": None,
            }
        logger.info(f"WebhookCallback registrado: {callback_id} → {callback_url}")
        return callback_id

    def complete(self, callback_id: str, response: dict[str, Any]) -> bool:
        with self._lock:
            if callback_id not in self._callbacks:
                return False
            self._callbacks[callback_id].update({
                "status": "completed",
                "response": response,
                "completed_at": time.time(),
            })
        logger.info(f"WebhookCallback completado: {callback_id}")
        return True

    def fail(self, callback_id: str, error: str) -> bool:
        with self._lock:
            if callback_id not in self._callbacks:
                return False
            self._callbacks[callback_id].update({
                "status": "failed",
                "error": error,
                "completed_at": time.time(),
            })
        logger.warning(f"WebhookCallback fallido: {callback_id}: {error}")
        return True

    def get(self, callback_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._callbacks.get(callback_id)
            if entry and time.time() > entry["expires_at"]:
                entry["status"] = "expired"
            return dict(entry) if entry else None

    def list_pending(self) -> list[dict]:
        with self._lock:
            now = time.time()
            return [dict(c) for c in self._callbacks.values() if c["status"] == "pending" and now <= c["expires_at"]]

    def cleanup_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._callbacks.items() if now > v["expires_at"]]
            for k in expired:
                del self._callbacks[k]
            return len(expired)
