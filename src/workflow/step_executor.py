"""
ORBITAL — StepExecutor Orbital (Motor Unico — OVC Compartido)
===============================================================

StepExecutor con tension orbital TOR usando OVC compartido via OrbitalContext.

Diferencia fundamental:
- StepExecutor LINEAL: Step1 → Step2 → Step3 → FIN (ejecucion secuencial fija)
- StepExecutor ORBITAL: Cada step genera variable orbital, TOR decide prioridad,
  el resultado retroalimenta al OVC COMPARTIDO (CIERRA EL CICLO)

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con todos los demas componentes
- Lo que el EventBus retroalimenta, el StepExecutor lo ve, y viceversa
- Estado orbital unificado: una sola fuente de verdad

Compatibilidad: mantiene la misma API que StepExecutor.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from datetime import UTC

from src.core.logging import setup_logging
from src.core.utils import resolve_variables
from src.orbital.context import OrbitalContext
from src.orbital.models import TWO_PI
from typing import Any

logger = setup_logging(__name__)


class StepResult:
    """Resultado de la ejecucion de un paso (compatible + enriquecido con orbital)."""

    def __init__(
        self,
        status: str,
        output_data: dict[str, Any] | None = None,
        duration_ms: int = 0,
        error_message: str | None = None,
        orbital_theta: float = 0.0,
        orbital_tension: float = 0.0,
        orbital_resonance: bool = False,
    ):
        self.status = status  # 'completed' | 'failed' | 'skipped'
        self.output_data = output_data or {}
        self.duration_ms = duration_ms
        self.error_message = error_message
        self.orbital_theta = orbital_theta
        self.orbital_tension = orbital_tension
        self.orbital_resonance = orbital_resonance


class StepExecutor:
    """
    StepExecutor Orbital — ejecuta pasos con tension TOR (OVC compartido).

    Usa OrbitalContext para compartir el OVC con todos los demas componentes.
    Las variables orbitales que crea aqui son visibles por WorkflowEngine,
    EventBus, ConditionEvaluator, etc.

    1. Cada step genera una variable orbital (OVC compartido)
    2. La tension TOR entre pasos determina si se ejecuta o se salta
    3. Si TOR(step_anterior, step_actual) > 0 → ejecutar (alineados)
    4. Si TOR(step_anterior, step_actual) < umbral → saltar (anti-alineados)
    5. El resultado retroalimenta las variables orbitales (CIERRA EL CICLO)
    """

    def __init__(self):
        self._tools: dict[str, object] = {}
        # ── ORBITAL COMPARTIDO ───────────────────────────
        self._ctx = OrbitalContext()
        self._step_phases: dict[str, float] = {}
        self._tor_threshold = -0.5  # Umbral: si TOR < -0.5, saltar paso

    @property
    def ovc(self):
        """OVC compartido via OrbitalContext."""
        return self._ctx.ovc

    @property
    def tor(self):
        """TOR compartido via OrbitalContext."""
        return self._ctx.tor

    # ── Registro de herramientas ────────────────────────────

    def register_tool(self, tool_name: str, tool_instance: object) -> None:
        """Registra una herramienta para que este disponible en los steps."""
        self._tools[tool_name] = tool_instance

    # ── Ejecucion ORBITAL ───────────────────────────────────

    def execute(self, step: dict[str, Any], context: dict[str, Any]) -> StepResult:
        """
        Ejecuta un paso con tension orbital (OVC compartido).

        Proceso ORBITAL:
        1. Registrar paso como variable orbital (OVC compartido)
        2. Calcular tension TOR con el paso anterior
        3. Si hay anti-resonancia fuerte → saltar paso
        4. Ejecutar la accion de la herramienta
        5. Actualizar variable orbital con el resultado
        6. Retroalimentar el resultado al OVC compartido
        """
        start_time = time.time()
        step_id = step.get("id", 0)
        tool_name = step.get("tool", "")
        action = step.get("action", "")
        params = step.get("params", {})
        timeout = step.get("timeout", 30)

        logger.info(f"Ejecutando paso {step_id}: {tool_name}.{action} (timeout: {timeout}s)")

        # 1. Registrar paso como variable orbital (en OVC compartido)
        # Fix BUG-W6: usar prefijo de execution_id para aislar workflows concurrentes
        orbital_prefix = context.get("_orbital_var_prefix", "")
        var_name = f"{orbital_prefix}step_{step_id}_{tool_name}"
        self._ensure_step_variable(var_name, step)

        # 2. Calcular tension con paso anterior
        tor_value = 0.0
        is_resonant = False
        prev_step_id = context.get("_last_step_id")
        if prev_step_id:
            prev_var_name = context.get("_last_step_var")
            if prev_var_name and self._ctx.ovc.get_variable(prev_var_name):
                try:
                    tor_result = self._ctx.tor.calculate(var_name, prev_var_name)
                    tor_value = tor_result.tor_value
                    is_resonant = tor_result.is_resonant
                except KeyError:
                    pass

        # 3. Decision orbital: anti-resonancia fuerte → saltar
        if tor_value < self._tor_threshold and prev_step_id:
            logger.info(
                f"OrbitalStep: Paso {step_id} SALTADO por anti-resonancia (TOR={tor_value:.4f} < {self._tor_threshold})"
            )
            return StepResult(
                status="skipped",
                output_data={"skipped": True, "reason": "anti_resonance", "tor": tor_value},
                duration_ms=self._elapsed(start_time),
                orbital_theta=self._ctx.ovc.get_variable(var_name).theta
                if self._ctx.ovc.get_variable(var_name)
                else 0.0,
                orbital_tension=tor_value,
                orbital_resonance=is_resonant,
            )

        # 4. Resolver variables en los parametros
        try:
            resolved_params = self._resolve_params(params, context)
        except Exception as e:
            return StepResult(
                status="failed",
                error_message=f"Error resolviendo parametros: {e}",
                duration_ms=self._elapsed(start_time),
            )

        # 5. Validar que la tool existe
        if tool_name not in self._tools and tool_name != "system":
            return StepResult(
                status="failed",
                error_message=f"Tool '{tool_name}' no registrada. Tools disponibles: {list(self._tools.keys())}",
                duration_ms=self._elapsed(start_time),
            )

        # 6. Ejecutar la accion con timeout via threading
        output = {}
        execution_error = None

        def _run_action():
            nonlocal output, execution_error
            try:
                if tool_name == "system":
                    output = self._execute_system_action(action, resolved_params, context)
                else:
                    tool = self._tools[tool_name]
                    action_func = getattr(tool, action, None)
                    if action_func is None:
                        raise ValueError(f"Accion '{action}' no encontrada en tool '{tool_name}'")
                    output = action_func(**resolved_params)
            except Exception as e:
                execution_error = e

        # Fix Sprint 2 bug #15: usar ThreadPoolExecutor con cancelación cooperativa
        # vía threading.Event, en vez de thread daemon sin cancelación real.
        # El thread daemon anterior seguía corriendo tras el timeout, causando
        # efectos secundarios duplicados si el workflow se reintenta.
        cancel_event = threading.Event()

        def _run_action_cancelable():
            if cancel_event.is_set():
                return
            _run_action()

        # Usar ThreadPoolExecutor para mejor gestión del ciclo de vida
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"step_{step_id}") as executor:
            future = executor.submit(_run_action_cancelable)
            try:
                future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                duration = self._elapsed(start_time)
                # Señal de cancelación cooperativa (el thread puede checkear
                # cancel_event y abortar si lo soporta)
                cancel_event.set()
                # Anti-resonancia por timeout
                var = self._ctx.ovc.get_variable(var_name)
                if var:
                    var.retrofeed(-0.3, damping=0.5)
                logger.warning(
                    f"StepExecutor: paso {step_id} excedió timeout de {timeout}s — "
                    f"señal de cancelación enviada (el thread puede seguir corriendo "
                    f"si la tool no soporta cancelación cooperativa)"
                )
                return StepResult(
                    status="failed",
                    error_message=f"Paso {step_id} excedio el timeout de {timeout}s",
                    duration_ms=duration,
                    orbital_theta=var.theta if var else 0.0,
                    orbital_tension=tor_value,
                )
            except Exception as e:
                # Excepción propagada desde _run_action
                if execution_error is None:
                    execution_error = e

        # NOTA: el `with` block del ThreadPoolExecutor garantiza que se llame
        # executor.shutdown(wait=False) al salir, pero los threads en flight
        # pueden seguir corriendo si la tool no respeta cancel_event.
        # Para tools que soportan cancelación, checkear cancel_event periódicamente.

        if execution_error:
            duration = self._elapsed(start_time)
            # Fallo → retroalimentacion negativa
            var = self._ctx.ovc.get_variable(var_name)
            if var:
                var.retrofeed(-0.2, damping=0.5)
            return StepResult(
                status="failed",
                error_message=str(execution_error),
                duration_ms=duration,
                orbital_theta=var.theta if var else 0.0,
                orbital_tension=tor_value,
            )

        # 7. Exito → avanzar fase y reforzar amplitud
        var = self._ctx.ovc.get_variable(var_name)
        if var:
            var.advance(dt=1.0)
            var.amplitude = min(var.amplitude * 1.1, 10.0)

        # 8. Actualizar contexto para el siguiente paso
        context["_last_step_id"] = str(step_id)
        context["_last_step_var"] = var_name

        theta = var.theta if var else 0.0
        duration = self._elapsed(start_time)
        logger.info(
            f"OrbitalStep: Paso {step_id} ({tool_name}.{action}) → completed "
            f"theta={math.degrees(theta):.1f} deg TOR={tor_value:.4f} en {duration}ms"
        )

        return StepResult(
            status="completed",
            output_data=output,
            duration_ms=duration,
            orbital_theta=theta,
            orbital_tension=tor_value,
            orbital_resonance=is_resonant,
        )

    # ── Helpers ─────────────────────────────────────────────

    def _resolve_params(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resuelve variables en los parametros del paso y convierte tipos."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved_val = resolve_variables(value, context)
                if isinstance(resolved_val, str):
                    resolved[key] = self._coerce_numeric(resolved_val)
                else:
                    resolved[key] = resolved_val
            elif isinstance(value, dict):
                resolved[key] = self._resolve_params(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_params(item, context)
                    if isinstance(item, dict)
                    else self._coerce_numeric(resolve_variables(item, context))
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _coerce_numeric(value: str) -> str | int | float:
        """Convierte strings que parecen numeros a int/float.

        Fix Sprint 4 bug #51: delega a utils.helpers.coerce_numeric para
        evitar duplicación. Mantiene la firma antigua (str → str|int|float)
        para backward compatibility con callers que esperan int (no float)
        para enteros.
        """
        from src.core.utils import coerce_numeric

        if not isinstance(value, str):
            return value
        result = coerce_numeric(value, default=value)
        # coerce_numeric siempre retorna float; convertir a int si es entero
        # para preservar compat con callers que esperan int
        if isinstance(result, float) and result.is_integer() and "." not in value:
            return int(result)
        return result

    def _execute_system_action(self, action: str, params: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ejecuta acciones del sistema (backup, wait, schedule)."""
        from src.core.db import DatabaseManager

        db = DatabaseManager()

        if action == "backup_database":
            dest = params.get("dest", "")
            path = db.backup(dest) if dest else db.backup(db._db_path.parent)
            return {"path": path, "status": "completed"}
        elif action == "get_setting":
            key = params.get("key", "")
            return {"value": db.get_setting(key)}
        elif action == "wait":
            """Pausa por N segundos. Bloqueante, con límite máximo de 86400s (24h)."""
            import time

            seconds = float(params.get("seconds", 1))
            seconds = max(0, min(seconds, 86400))  # Cap at 24 hours
            if seconds >= 3600:
                logger.warning(f"Wait node: pausa de {seconds:.0f}s ({seconds / 3600:.1f}h) ")
            time.sleep(seconds)
            return {"waited_seconds": int(seconds), "status": "completed"}
        elif action == "wait_until":
            """Pausa hasta una fecha/hora específica. Usa UTC para evitar naive/aware crashes."""
            import time
            from datetime import datetime

            target_str = params.get("datetime", "")
            if not target_str:
                return {"waited_seconds": 0, "status": "skipped", "reason": "no_datetime"}
            try:
                target = datetime.fromisoformat(target_str)
                # Normalizar a UTC: si target es naive, asumir UTC; si es aware, convertir
                if target.tzinfo is None:
                    target = target.replace(tzinfo=UTC)
                now = datetime.now(UTC)
                if target <= now:
                    return {"waited_seconds": 0, "status": "completed", "reason": "already_passed"}
                diff = (target - now).total_seconds()
                diff = min(diff, 86400)  # Cap at 24 hours
                if diff >= 3600:
                    logger.warning(f"WaitUntil node: esperando {diff:.0f}s ({diff / 3600:.1f}h) hasta {target_str}")
                time.sleep(diff)
                return {"waited_seconds": int(diff), "status": "completed"}
            except ValueError as e:
                raise ValueError(
                    f"Formato datetime inválido: {target_str}. Usa ISO 8601 (2026-06-15T14:30:00). Error: {e}"
                ) from e
        elif action == "variable":
            """
            Workflow variable operations: set, get, delete, exists,
            transform (upper, lower, trim, replace, split, join,
            substring, length), math (add, subtract, multiply, divide,
            floor, ceil, round, abs, min, max, power, sqrt, modulo),
            y aggregate (sum, avg, count, min, max).
            """
            from src.workflow.workflow_variables import WorkflowVariables

            return WorkflowVariables.execute(params, context)
        elif action == "schedule_interval":
            """Configura un intervalo de ejecución recurrente.
            Se guarda en la DB y el ScheduleWorker lo recoge.
            """
            interval_minutes = int(params.get("interval_minutes", 60))
            workflow_id = params.get("workflow_id")
            if not workflow_id:
                return {"status": "failed", "reason": "workflow_id required"}
            db.set_setting(f"interval_{workflow_id}", str(interval_minutes))
            return {"interval_minutes": interval_minutes, "workflow_id": workflow_id, "status": "scheduled"}
        else:
            raise ValueError(f"Accion de sistema desconocida: {action}")

    def _ensure_step_variable(self, var_name: str, step: dict[str, Any]) -> None:
        """Crea una variable orbital para un paso si no existe (en OVC compartido)."""
        if self._ctx.ovc.get_variable(var_name) is None:
            # Hash no criptográfico: deriva theta determinista del var_name (B324 mitigado).
            hash_val = int(hashlib.md5(var_name.encode(), usedforsecurity=False).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.1,
                orbit_group="workflow_steps",
                metadata={"step_id": step.get("id"), "tool": step.get("tool"), "action": step.get("action")},
            )

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    def get_step_phase(self, step_id: str) -> float | None:
        """Retorna la fase orbital de un paso."""
        for _var_name, var in self._ctx.ovc.get_all_variables().items():
            if var.metadata.get("step_id") == step_id:
                return var.theta
        return None

    def get_orbital_snapshot(self) -> dict[str, Any]:
        """Retorna snapshot del estado orbital de los pasos."""
        return {
            "variables": self._ctx.ovc.get_value_snapshot(),
            "phases": self._ctx.ovc.get_phase_snapshot(),
            "mode": "ORBITAL",
            "shared": True,
        }
