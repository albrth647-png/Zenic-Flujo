"""
Workflow Determinista — ErrorHandler
Maneja reintentos (retry), acciones de respaldo (fallback) y cola de mensajes fallidos.
"""
import time
from typing import Any, Callable

from src.utils.logger import setup_logging
from src.config import ERROR_MAX_RETRIES, ERROR_BASE_DELAY_SECONDS, ERROR_RETRY_MULTIPLIER, ERROR_USE_FALLBACK

logger = setup_logging(__name__)


class ErrorHandlerResult:
    """Resultado del manejo de error."""

    def __init__(self, status: str, output_data: dict | None = None,
                 error_message: str | None = None, retries: int = 0):
        self.status = status  # 'recovered' | 'failed' | 'dead_letter'
        self.output_data = output_data or {}
        self.error_message = error_message
        self.retries = retries


class ErrorHandler:
    """
    Maneja fallos en la ejecución de pasos.
    
    Configuración por defecto:
    - max_retries: 3
    - base_delay: 5 segundos
    - multiplier: 2 (retry en 5s, 10s, 20s)
    - use_fallback: True
    """

    def __init__(self):
        self.max_retries = ERROR_MAX_RETRIES
        self.base_delay = ERROR_BASE_DELAY_SECONDS
        self.multiplier = ERROR_RETRY_MULTIPLIER
        self.use_fallback = ERROR_USE_FALLBACK
        self._fallback_actions: dict[str, Callable] = {}

    def handle(self, step: dict, error: Exception, context: dict,
               step_executor) -> ErrorHandlerResult:
        """
        Maneja un error durante la ejecución de un paso.
        
        Args:
            step: Definición del paso que falló
            error: Excepción ocurrida
            context: Contexto de ejecución
            step_executor: StepExecutor para reintentar
        
        Returns:
            ErrorHandlerResult con el resultado del manejo
        """
        step_id = step.get("id", 0)
        step_retry_config = step.get("retry", {})
        max_retries = step_retry_config.get("max_attempts", self.max_retries)
        base_delay = step_retry_config.get("base_delay", self.base_delay)
        multiplier = step_retry_config.get("multiplier", self.multiplier)
        use_fallback = step_retry_config.get("use_fallback", self.use_fallback)

        logger.warning(
            f"Manejando error en paso {step_id}: {error}. "
            f"Intentos máximos: {max_retries}"
        )

        # 1. Reintentar
        for attempt in range(1, max_retries + 1):
            delay = base_delay * (multiplier ** (attempt - 1))
            logger.info(f"Reintento {attempt}/{max_retries} en {delay}s...")
            time.sleep(delay)

            try:
                result = step_executor.execute(step, context)
                if result.status == "completed":
                    logger.info(f"Reintento {attempt} exitoso para paso {step_id}")
                    return ErrorHandlerResult(
                        status="recovered",
                        output_data=result.output_data,
                        retries=attempt,
                    )
            except Exception as retry_error:
                logger.warning(f"Reintento {attempt} falló: {retry_error}")

        # 2. Fallback action
        if use_fallback and self._has_fallback(step):
            try:
                fallback_result = self._execute_fallback(step, context)
                logger.info(f"Fallback ejecutado para paso {step_id}")
                return ErrorHandlerResult(
                    status="recovered",
                    output_data=fallback_result,
                    retries=max_retries,
                )
            except Exception as fb_error:
                logger.error(f"Fallback falló: {fb_error}")

        # 3. Dead letter
        self._send_to_dead_letter(step, error, max_retries)
        logger.error(f"Paso {step_id} enviado a dead letter después de {max_retries} reintentos")

        return ErrorHandlerResult(
            status="dead_letter",
            error_message=f"Error después de {max_retries} reintentos: {error}",
            retries=max_retries,
        )

    def register_fallback(self, action_name: str, func: Callable) -> None:
        """Registra una acción de fallback."""
        self._fallback_actions[action_name] = func

    def _has_fallback(self, step: dict) -> bool:
        """Verifica si el step tiene una acción de fallback configurada."""
        fallback = step.get("fallback")
        if fallback is None:
            return False
        if isinstance(fallback, str):
            return fallback in self._fallback_actions or fallback == "skip"
        if isinstance(fallback, dict):
            return True
        return False

    def _execute_fallback(self, step: dict, context: dict) -> dict:
        """Ejecuta la acción de fallback configurada."""
        fallback = step.get("fallback", {})

        if isinstance(fallback, str):
            if fallback == "skip":
                return {"status": "skipped", "reason": "fallback_skip"}
            if fallback in self._fallback_actions:
                return self._fallback_actions[fallback](step, context)
            raise ValueError(f"Función de fallback desconocida: {fallback}")

        if isinstance(fallback, dict):
            # Fallback con acción específica
            action = fallback.get("action", "skip")
            params = fallback.get("params", {})

            if action == "skip":
                return {"status": "skipped", "reason": "fallback_skip"}
            if action == "set_default":
                return {"status": "completed", "data": params.get("default_value", {})}
            if action in self._fallback_actions:
                return self._fallback_actions[action](step, context, params)

            raise ValueError(f"Acción de fallback desconocida: {action}")

        raise ValueError(f"Configuración de fallback inválida: {fallback}")

    def _send_to_dead_letter(self, step: dict, error: Exception, retries: int) -> None:
        """Envía el paso fallido a la cola de mensajes fallidos (dead letter)."""
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()

        db.execute(
            """INSERT INTO event_queue 
               (event_type, event_data, status) 
               VALUES (?, ?, ?)""",
            (
                "dead_letter.step_failed",
                str({
                    "step_id": step.get("id"),
                    "tool": step.get("tool"),
                    "action": step.get("action"),
                    "error": str(error),
                    "retries": retries,
                    "step_definition": step,
                }),
                "failed",
            ),
        )
        db.commit()
