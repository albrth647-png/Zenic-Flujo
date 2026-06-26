"""
HAT NIVEL 4 — ToolWorker Base ABC
==================================

Clase base para workers atómicos del Nivel 4.
Cada worker envuelve UN solo método de una tool (Nivel 5).

Los workers se generan automáticamente por WorkerFactory
mediante introspección de los métodos públicos de cada tool.
NO se escriben manualmente.

Cada worker añade:
1. Idempotency — hash(tool+action+params) para detectar duplicados
2. CircuitBreaker — per-worker, abre circuito si la tool falla N veces
3. Ejecución atómica con timing y error handling
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, TypedDict

from src.core.logging import get_logger

class WorkerResult(TypedDict, total=False):
    """Resultado de la ejecución de un worker (Nivel 4).

    Campos comunes:
    - ``status``: "completed", "failed", o "circuit_open"
    - ``action``: Nombre del método ejecutado
    - ``tool``: Nombre de la tool
    - ``result``: Resultado de la tool (solo si status="completed")
    - ``error``: Mensaje de error (solo si status="failed" o "circuit_open")
    - ``params_hash``: Hash de params para idempotency tracking
    - ``duration_ms``: Tiempo de ejecución
    """
    status: str
    action: str
    tool: str
    result: Any
    error: str
    params_hash: str
    duration_ms: int


logger = get_logger("hat.level4.tool_worker")


class ToolWorker:
    """Worker atómico — envuelve 1 método de 1 tool.

    Atributos de clase (seteados por WorkerFactory al crear dinámicamente):
        tool_name: str — nombre de la tool (ej: "crm")
        action_name: str — nombre del método (ej: "create_lead")
    """

    tool_name: str = ""
    action_name: str = ""

    def __init__(self, tool_instance: Any) -> None:
        self.tool = tool_instance
        self.method: Any = getattr(tool_instance, self.action_name, None)

        if self.method is None:
            raise AttributeError(
                f"Tool '{self.tool_name}' no tiene método '{self.action_name}'"
            )
        if not callable(self.method):
            raise AttributeError(
                f"Atributo '{self.action_name}' en tool '{self.tool_name}' "
                f"es tipo {type(self.method).__name__}, no es invocable"
            )

        # Circuit breaker state per-worker
        self._failure_count: int = 0
        self._failure_threshold: int = 3
        self._circuit_open: bool = False
        self._last_failure_time: float = 0.0
        self._recovery_timeout: float = 60.0  # seconds before trying again

    def run(self, params: dict[str, Any] | None = None) -> WorkerResult:
        """Ejecuta el worker: circuit_breaker check → invoke → return result.

        Args:
            params: Parámetros para el método de la tool.

        Returns:
            WorkerResult con status, action, tool, result, params_hash, duration_ms.
        """
        start = time.monotonic()
        params = params or {}

        # Hash de params para idempotency tracking
        params_hash = self._compute_params_hash(params)

        # Circuit breaker check
        if self._is_circuit_open():
            return {
                "status": "circuit_open",
                "action": self.action_name,
                "tool": self.tool_name,
                "error": f"circuit breaker open for {self.tool_name}.{self.action_name}",
                "params_hash": params_hash,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

        try:
            # Invocar método de la tool (Nivel 5)
            result = self.method(**params) if params else self.method()

            # Success → reset circuit breaker
            self._on_success()

            return {
                "status": "completed",
                "action": self.action_name,
                "tool": self.tool_name,
                "result": result,
                "params_hash": params_hash,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

        except Exception as exc:
            logger.exception(
                "Worker %s.%s falló",
                self.tool_name, self.action_name,
            )
            self._on_failure()

            return {
                "status": "failed",
                "action": self.action_name,
                "tool": self.tool_name,
                "error": str(exc),
                "params_hash": params_hash,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

    # ── Circuit Breaker ──────────────────────────────────────

    def _is_circuit_open(self) -> bool:
        """Verifica si el circuit breaker está abierto."""
        if not self._circuit_open:
            return False
        # Check if recovery timeout has passed
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._recovery_timeout:
            # Half-open: try again
            self._circuit_open = False
            self._failure_count = 0
            logger.info(
                "Circuit breaker half-open for %s.%s",
                self.tool_name, self.action_name,
            )
            return False
        return True

    def _on_success(self) -> None:
        """Resetea el circuit breaker tras éxito."""
        self._failure_count = 0
        self._circuit_open = False

    def _on_failure(self) -> None:
        """Incrementa failure count, abre circuit si supera threshold."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._circuit_open = True
            logger.warning(
                "Circuit breaker OPEN for %s.%s (failures=%d)",
                self.tool_name, self.action_name, self._failure_count,
            )

    # ── Idempotency ──────────────────────────────────────────

    @staticmethod
    def _compute_params_hash(params: dict[str, Any]) -> str:
        """Hash determinista de params para idempotency tracking."""
        canonical = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    # ── Properties ───────────────────────────────────────────

    @property
    def idempotency_key(self) -> str:
        """Key única para este worker (tool + action)."""
        return f"{self.tool_name}.{self.action_name}"

    @property
    def circuit_state(self) -> str:
        """Estado del circuit breaker: 'closed', 'open', 'half_open'."""
        if not self._circuit_open:
            return "closed"
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._recovery_timeout:
            return "half_open"
        return "open"

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} tool={self.tool_name} "
            f"action={self.action_name} circuit={self.circuit_state}>"
        )
