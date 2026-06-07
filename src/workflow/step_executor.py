"""
Workflow Determinista — StepExecutor
Ejecuta pasos individuales de un workflow, llamando a la herramienta correcta.
"""
import threading
import time
from typing import Any

from src.utils.helpers import resolve_variables, safe_get
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class StepResult:
    """Resultado de la ejecución de un paso."""

    def __init__(self, status: str, output_data: dict | None = None,
                 duration_ms: int = 0, error_message: str | None = None):
        self.status = status  # 'completed' | 'failed' | 'skipped'
        self.output_data = output_data or {}
        self.duration_ms = duration_ms
        self.error_message = error_message


class StepExecutor:
    """
    Ejecuta un paso individual.
    
    Un paso se define como:
    {
        "id": 1,
        "tool": "crm",
        "action": "create_lead",
        "params": {"name": "$input.nombre", "email": "$input.email"},
        "timeout": 30,
        "condition": "stock < 10"  # opcional
    }
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register_tool(self, tool_name: str, tool_instance: Any) -> None:
        """Registra una herramienta para que esté disponible en los steps."""
        self._tools[tool_name] = tool_instance

    def execute(self, step: dict, context: dict) -> StepResult:
        """
        Ejecuta un paso con timeout.
        
        Args:
            step: Definición del paso
            context: Contexto de ejecución con $input, $output de pasos previos, etc.
        
        Returns:
            StepResult con el resultado
        """
        start_time = time.time()
        step_id = step.get("id", 0)
        tool_name = step.get("tool", "")
        action = step.get("action", "")
        params = step.get("params", {})
        timeout = step.get("timeout", 30)

        logger.info(f"Ejecutando paso {step_id}: {tool_name}.{action} (timeout: {timeout}s)")

        try:
            # 1. Resolver variables en los parámetros
            resolved_params = self._resolve_params(params, context)

            # 2. Validar que la tool existe
            if tool_name not in self._tools and tool_name != "system":
                return StepResult(
                    status="failed",
                    error_message=f"Tool '{tool_name}' no registrada. Tools disponibles: {list(self._tools.keys())}",
                    duration_ms=self._elapsed(start_time),
                )

            # 3. Ejecutar la acción con timeout via threading
            output = {}
            execution_error = None

            def _run_action():
                nonlocal output, execution_error
                try:
                    if tool_name == "system":
                        output = self._execute_system_action(action, resolved_params)
                    else:
                        tool = self._tools[tool_name]
                        action_func = getattr(tool, action, None)
                        if action_func is None:
                            raise ValueError(f"Acción '{action}' no encontrada en tool '{tool_name}'")
                        output = action_func(**resolved_params)
                except Exception as e:
                    execution_error = e

            thread = threading.Thread(target=_run_action, daemon=True)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                raise TimeoutError(f"Paso {step_id} excedió el timeout de {timeout}s")
            if execution_error:
                raise execution_error

            duration = self._elapsed(start_time)
            logger.info(f"Paso {step_id} completado en {duration}ms")
            return StepResult(status="completed", output_data=output, duration_ms=duration)

        except TimeoutError as e:
            duration = self._elapsed(start_time)
            logger.error(f"Paso {step_id} timeout: {e}")
            return StepResult(
                status="failed",
                error_message=str(e),
                duration_ms=duration,
            )
        except Exception as e:
            duration = self._elapsed(start_time)
            logger.error(f"Paso {step_id} falló: {e}")
            return StepResult(
                status="failed",
                error_message=str(e),
                duration_ms=duration,
            )

    def _resolve_params(self, params: dict, context: dict) -> dict:
        """Resuelve variables en los parámetros del paso."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = resolve_variables(value, context)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_params(item, context) if isinstance(item, dict)
                    else resolve_variables(item, context) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _execute_system_action(self, action: str, params: dict) -> dict:
        """Ejecuta acciones del sistema (backup, etc.)."""
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()

        if action == "backup_database":
            dest = params.get("dest", "")
            path = db.backup(dest) if dest else db.backup(db._db_path.parent)
            return {"path": path, "status": "completed"}
        elif action == "get_setting":
            key = params.get("key", "")
            return {"value": db.get_setting(key)}
        else:
            raise ValueError(f"Acción de sistema desconocida: {action}")

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)
