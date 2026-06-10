"""
ORBITAL — ErrorHandler Orbital (OVC Compartido)
==================================================

ErrorHandler con retroalimentacion orbital usando OVC compartido
via OrbitalContext. Sprint 4: jitter, DeadLetterManager,
continue_on_error, retry_on_timeout.

MEJORA vs version anterior:
- Backoff exponencial con jitter para evitar tormentas de reintentos
- DeadLetterManager dedicado (tabla dead_letter_queue)
- continue_on_error: el workflow sigue aunque falle este paso
- retry_on_timeout: reintentar también en timeouts
- Notificación via EventBus al entrar a dead letter
"""

from __future__ import annotations

import hashlib
import random
import time
from typing import Callable

from src.orbital.models import TWO_PI
from src.orbital.context import OrbitalContext
from src.config import ERROR_MAX_RETRIES, ERROR_BASE_DELAY_SECONDS, ERROR_RETRY_MULTIPLIER, ERROR_USE_FALLBACK
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class ErrorHandlerResult:
    """Resultado del manejo de error."""

    def __init__(self, status: str, output_data: dict | None = None,
                 error_message: str | None = None, retries: int = 0,
                 orbital_theta: float = 0.0,
                 orbital_alignment: float = 0.0):
        self.status = status  # 'recovered' | 'failed' | 'dead_letter' | 'skipped'
        self.output_data = output_data or {}
        self.error_message = error_message
        self.retries = retries
        self.orbital_theta = orbital_theta
        self.orbital_alignment = orbital_alignment


class ErrorHandler:
    """
    OrbitalRecovery — Manejo de errores con retroalimentacion orbital.

    Sprint 4 mejoras:
    - Jitter en backoff: delay * (0.5 + random() * 0.5) evita tormentas
    - DeadLetterManager persistente en SQLite
    - continue_on_error: skip silencioso con resultado vacío
    - retry_on_timeout: reintentar incluso en timeouts de step
    - Notificación via EventBus al entrar a dead letter
    """

    def __init__(self):
        self.max_retries = ERROR_MAX_RETRIES
        self.base_delay = ERROR_BASE_DELAY_SECONDS
        self.multiplier = ERROR_RETRY_MULTIPLIER
        self.use_fallback = ERROR_USE_FALLBACK
        self._fallback_actions: dict[str, Callable] = {}
        # ── ORBITAL COMPARTIDO ───────────────────────────
        self._ctx = OrbitalContext()

    def handle(self, step: dict, error: Exception, context: dict,
               step_executor) -> ErrorHandlerResult:
        """
        Maneja un error durante la ejecucion de un paso (OVC compartido).

        Sprint 4: Soporta continue_on_error, retry_on_timeout,
        jitter en backoff, y DeadLetterManager.

        Args:
            step: Definición del paso que falló
            error: Excepción lanzada
            context: Contexto de ejecución
            step_executor: StepExecutor para reintentos

        Returns:
            ErrorHandlerResult con el resultado del manejo
        """
        step_id = step.get("id", 0)
        step_retry_config = step.get("retry", {})

        # ── Configuración por step (Sprint 4) ─────────────
        max_retries = step_retry_config.get("max_attempts", self.max_retries)
        base_delay = step_retry_config.get("base_delay", self.base_delay)
        multiplier = step_retry_config.get("multiplier", self.multiplier)
        use_fallback = step_retry_config.get("use_fallback", self.use_fallback)
        retry_on_timeout = step_retry_config.get("retry_on_timeout", False)
        continue_on_error = step.get("continue_on_error", False) or \
            context.get("workflow", {}).get("continue_on_error", False)
        jitter_enabled = step_retry_config.get("jitter", True)

        error_type = type(error).__name__

        # ── Si es timeout y no se debe reintentar ─────────
        is_timeout = "timeout" in str(error).lower() or \
                     "excedio el timeout" in str(error).lower()
        if is_timeout and not retry_on_timeout:
            logger.info(
                f"ErrorHandler: Timeout en paso {step_id}, "
                f"no se reintenta (retry_on_timeout=False)"
            )
            if continue_on_error:
                return self._handle_continue_on_error(step)
            self._send_to_dead_letter(step, error, 0, step_executor,
                                      context)
            return ErrorHandlerResult(
                status="dead_letter",
                error_message=f"Timeout sin reintentos: {error}",
                retries=0,
            )

        # 1. Crear variable orbital para el error
        error_var_name = f"error_{step_id}_{error_type}"
        self._ensure_error_variable(error_var_name, step_id, error_type)

        # 2. Calcular TOR(error, contexto)
        orbital_alignment = 0.0
        context_var_name = f"ctx_{step_id}"
        self._ensure_context_variable(context_var_name, context)

        try:
            tor_result = self._ctx.tor.calculate(error_var_name,
                                                  context_var_name)
            orbital_alignment = tor_result.tor_value
        except KeyError:
            pass

        error_var = self._ctx.ovc.get_variable(error_var_name)
        orbital_theta = error_var.theta if error_var else 0.0

        logger.warning(
            f"ErrorHandler: Error en paso {step_id} ({error_type}) — "
            f"TOR={orbital_alignment:.4f} "
            f"{'RECUPERABLE' if orbital_alignment > 0 else 'DIFICIL'}"
        )

        # 3. Ajustar reintentos segun alineacion orbital
        if orbital_alignment > 0:
            effective_max_retries = max(max_retries, 1)
        else:
            effective_max_retries = max(max_retries // 2, 1)

        # 4. Reintentar con backoff + jitter (Sprint 4)
        for attempt in range(1, effective_max_retries + 1):
            # Backoff base
            delay = base_delay * (multiplier ** (attempt - 1))

            # Ajuste orbital
            if orbital_alignment > 0:
                delay *= 0.7
            else:
                delay *= 1.5

            # Jitter: aleatoriedad para evitar tormentas (Sprint 4)
            if jitter_enabled:
                jitter_factor = 0.5 + random.random() * 0.5  # 0.5 - 1.0
                delay *= jitter_factor

            # Cap máximo de 60s por reintento
            delay = min(delay, 60.0)

            logger.info(
                f"Reintento {attempt}/{effective_max_retries} "
                f"en {delay:.1f}s (jitter={'on' if jitter_enabled else 'off'})..."
            )
            time.sleep(delay)

            try:
                result = step_executor.execute(step, context)
                if result.status == "completed":
                    if error_var:
                        error_var.retrofeed(0.3, damping=0.3)
                    logger.info(
                        f"Reintento {attempt} exitoso para paso {step_id}"
                    )
                    return ErrorHandlerResult(
                        status="recovered",
                        output_data=result.output_data,
                        retries=attempt,
                        orbital_theta=error_var.theta if error_var else 0.0,
                        orbital_alignment=orbital_alignment,
                    )
            except Exception as retry_error:
                if error_var:
                    error_var.retrofeed(-0.1, damping=0.3)
                logger.warning(
                    f"Reintento {attempt} fallo: {retry_error}"
                )

        # 5. Fallback action
        if use_fallback and self._has_fallback(step):
            try:
                fallback_result = self._execute_fallback(step, context)
                if error_var:
                    error_var.retrofeed(0.1, damping=0.3)
                logger.info(f"Fallback ejecutado para paso {step_id}")
                return ErrorHandlerResult(
                    status="recovered",
                    output_data=fallback_result,
                    retries=effective_max_retries,
                    orbital_theta=error_var.theta if error_var else 0.0,
                    orbital_alignment=orbital_alignment,
                )
            except Exception as fb_error:
                logger.error(f"Fallback fallo: {fb_error}")

        # 6. Dead Letter con DeadLetterManager (Sprint 4)
        if continue_on_error:
            logger.info(
                f"continue_on_error=True para paso {step_id}: "
                f"enviando a dead letter y continuando"
            )
            self._send_to_dead_letter(step, error, effective_max_retries,
                                      step_executor, context)
            return self._handle_continue_on_error(step)

        error_var_result = self._send_to_dead_letter(step, error,
                                                      effective_max_retries,
                                                      step_executor, context)
        if error_var:
            error_var.retrofeed(-0.5, damping=0.3)

        logger.error(
            f"Paso {step_id} → dead letter despues de "
            f"{effective_max_retries} reintentos "
            f"(alignment={orbital_alignment:.4f})"
        )

        return ErrorHandlerResult(
            status="dead_letter",
            error_message=(
                f"Error despues de {effective_max_retries} reintentos: {error}"
            ),
            retries=effective_max_retries,
            orbital_theta=error_var.theta if error_var else 0.0,
            orbital_alignment=orbital_alignment,
        )

    def _handle_continue_on_error(self, step: dict) -> ErrorHandlerResult:
        """
        Maneja continue_on_error: retorna resultado vacío 'skipped'.

        El workflow continúa con los siguientes pasos como si este
        paso hubiera sido saltado.
        """
        return ErrorHandlerResult(
            status="skipped",
            output_data={
                "skipped": True,
                "reason": "continue_on_error",
                "step_id": step.get("id"),
            },
            error_message=None,
        )

    @staticmethod
    def _get_context_snapshot(context: dict) -> dict:
        """Toma un snapshot seguro del contexto (sin import circular)."""
        safe_keys = {"input", "output", "steps_output", "workflow",
                     "settings", "_last_step_id", "_last_step_var"}
        snapshot = {}
        for key in safe_keys:
            if key in context:
                val = context[key]
                if isinstance(val, (str, int, float, bool, dict, list)):
                    snapshot[key] = val
        return snapshot

    def _send_to_dead_letter(self, step: dict, error: Exception,
                              retries: int, step_executor,
                              context: dict) -> None:
        """
        Envia el paso fallido a la Dead Letter Queue persistente.

        Sprint 4: Usa DeadLetterManager en vez de insert directo
        en event_queue. Dispara notificación via EventBus.
        """
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()

        workflow_id = context.get("workflow", {}).get("id", 0)
        workflow_name = context.get("workflow", {}).get("name", "")
        execution_id = context.get("_execution_id", 0)

        entry_id = dl.add(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            execution_id=execution_id,
            step_id=step.get("id", 0),
            tool=step.get("tool", ""),
            action=step.get("action", ""),
            error_message=str(error),
            retry_count=retries,
            step_definition=step,
            context_snapshot=self._get_context_snapshot(context),
        )

        # Notificar (Sprint 4)
        try:
            dl.notify_dead_letter(entry_id)
        except Exception as e:
            logger.warning(f"Error al notificar dead letter: {e}")

    # ── Fallback ────────────────────────────────────────────

    def register_fallback(self, action_name: str, func: Callable) -> None:
        self._fallback_actions[action_name] = func

    def _has_fallback(self, step: dict) -> bool:
        fallback = step.get("fallback")
        if fallback is None:
            return False
        if isinstance(fallback, str):
            return fallback in self._fallback_actions or fallback == "skip"
        if isinstance(fallback, dict):
            return True
        return False

    def _execute_fallback(self, step: dict, context: dict) -> dict:
        fallback = step.get("fallback", {})

        if isinstance(fallback, str):
            if fallback == "skip":
                return {"status": "skipped", "reason": "fallback_skip"}
            if fallback in self._fallback_actions:
                return self._fallback_actions[fallback](step, context)
            raise ValueError(f"Funcion de fallback desconocida: {fallback}")

        if isinstance(fallback, dict):
            action = fallback.get("action", "skip")
            params = fallback.get("params", {})

            if action == "skip":
                return {"status": "skipped", "reason": "fallback_skip"}
            if action == "set_default":
                return {"status": "completed",
                        "data": params.get("default_value", {})}
            if action in self._fallback_actions:
                return self._fallback_actions[action](step, context, params)

            raise ValueError(f"Accion de fallback desconocida: {action}")

        raise ValueError(f"Configuracion de fallback invalida: {fallback}")

    # ── Helpers orbitales ───────────────────────────────────

    def _ensure_error_variable(self, var_name: str, step_id: int,
                                error_type: str) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            hash_val = int(hashlib.md5(var_name.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=0.5,
                velocity=0.2,
                orbit_group="errors",
                metadata={"source": "error_handler", "step_id": step_id,
                          "error_type": error_type},
            )

    def _ensure_context_variable(self, var_name: str, context: dict) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            hash_val = int(hashlib.md5(str(context).encode()).hexdigest()[:8],
                           16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.05,
                orbit_group="error_context",
                metadata={"source": "error_handler"},
            )
