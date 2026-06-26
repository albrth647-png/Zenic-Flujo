"""
ORBITAL — LoopHandler Orbital (OVC Compartido)
=================================================

LoopHandler con convergencia orbital usando OVC compartido via OrbitalContext.

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con todos los demas componentes
- Los bucles while usan COD compartido para convergencia

Compatibilidad: mantiene la misma API que LoopHandler.
"""

from __future__ import annotations

import contextlib
import hashlib

from src.orbital.context import OrbitalContext
from src.orbital.models import DEFAULT_THRESHOLD, TWO_PI
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class LoopResult:
    """Resultado de la ejecucion de un bucle."""

    def __init__(self, iterations: int, outputs: list[dict], converged: bool = False, convergence_delta: float = 0.0):
        self.iterations = iterations
        self.outputs = outputs
        self.converged = converged
        self.convergence_delta = convergence_delta


class LoopHandler:
    """
    OrbitalConvergence — Bucles por convergencia orbital (OVC compartido).

    Usa OrbitalContext para compartir el OVC con todos los componentes.
    Los bucles while usan convergencia COD compartida.
    """

    MAX_ITERATIONS_DEFAULT = 1000

    def __init__(self):
        self._ctx = OrbitalContext()

    def execute(self, step: dict, context: dict, step_executor) -> LoopResult:
        """Ejecuta un bucle segun su tipo."""
        loop_type = step.get("type", "foreach")

        if loop_type == "foreach":
            return self._execute_foreach(step, context, step_executor)
        elif loop_type == "for":
            return self._execute_for(step, context, step_executor)
        elif loop_type == "while":
            return self._execute_while_orbital(step, context, step_executor)
        else:
            raise ValueError(f"Tipo de bucle no soportado: {loop_type}")

    def _execute_foreach(self, step: dict, context: dict, step_executor) -> LoopResult:
        """Ejecuta un bucle foreach con enriquecimiento orbital."""
        collection_ref = step.get("collection", "")
        item_var = step.get("item_var", "item")
        index_var = step.get("index_var", "index")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        import json

        from src.core.utils import resolve_variables, safe_get

        collection_str = resolve_variables(collection_ref, context)
        collection = collection_str
        if isinstance(collection_str, str):
            if collection_str == f"${{{collection_ref.lstrip('$')}}}":
                path = collection_ref.lstrip("$")
                collection = safe_get(context, path, None)
            else:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    collection = json.loads(collection_str)

        if not isinstance(collection, (list, tuple)):
            path = collection_ref.lstrip("$")
            collection = safe_get(context, path) or []

        if not isinstance(collection, (list, tuple)):
            collection = [collection]

        if len(collection) > max_iter:
            logger.warning(f"Coleccion truncada de {len(collection)} a {max_iter} iteraciones")
            collection = collection[:max_iter]

        # Fix BUG-W7: usar prefijo de execution_id para aislar workflows
        orbital_prefix = context.get("_orbital_var_prefix", "")
        loop_var_name = f"{orbital_prefix}loop_{step.get('id', 0)}_foreach"
        self._ensure_loop_variable(loop_var_name, step)

        outputs = []
        for idx, item in enumerate(collection):
            iter_context = dict(context)
            iter_context[item_var] = item
            iter_context[index_var] = idx

            loop_var = self._ctx.ovc.get_variable(loop_var_name)
            if loop_var:
                loop_var.advance(dt=1.0)

            iteration_results = self._execute_inner_steps(inner_steps, iter_context, step_executor)
            outputs.append(
                {
                    "index": idx,
                    item_var: item,
                    "results": iteration_results,
                }
            )

        logger.info(f"OrbitalConvergence: Foreach completado — {len(outputs)} iteraciones")
        return LoopResult(iterations=len(outputs), outputs=outputs)

    def _execute_for(self, step: dict, context: dict, step_executor) -> LoopResult:
        """Ejecuta un bucle for con enriquecimiento orbital."""
        start = step.get("start", 0)
        end = step.get("end", 10)
        step_size = step.get("step", 1)
        index_var = step.get("index_var", "i")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        # Fix BUG-W7: usar prefijo de execution_id
        orbital_prefix = context.get("_orbital_var_prefix", "")
        loop_var_name = f"{orbital_prefix}loop_{step.get('id', 0)}_for"
        self._ensure_loop_variable(loop_var_name, step)

        count = 0
        outputs = []
        i = start

        while (step_size > 0 and i < end) or (step_size < 0 and i > end):
            if count >= max_iter:
                logger.warning(f"Bucle for terminado por limite de {max_iter} iteraciones")
                break

            iter_context = dict(context)
            iter_context[index_var] = i

            loop_var = self._ctx.ovc.get_variable(loop_var_name)
            if loop_var:
                loop_var.advance(dt=1.0)

            iteration_results = self._execute_inner_steps(inner_steps, iter_context, step_executor)
            outputs.append(
                {
                    "index": count,
                    "value": i,
                    "results": iteration_results,
                }
            )

            i += step_size
            count += 1

        logger.info(f"OrbitalConvergence: For completado — {count} iteraciones")
        return LoopResult(iterations=count, outputs=outputs)

    def _execute_while_orbital(self, step: dict, context: dict, step_executor) -> LoopResult:
        """Ejecuta un bucle while usando convergencia orbital (COD compartido)."""
        condition = step.get("condition", "True")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        # Fix BUG-W7: usar prefijo de execution_id + filtrar variables por prefijo
        orbital_prefix = context.get("_orbital_var_prefix", "")
        loop_var_name = f"{orbital_prefix}loop_{step.get('id', 0)}_while"
        self._ensure_loop_variable(loop_var_name, step)

        # Fix BUG-W7: filtrar variables por prefijo para no mezclar workflows ajenos
        all_vars = [n for n in self._ctx.ovc.get_all_variables().keys() if n.startswith(orbital_prefix)]
        if len(all_vars) >= 2:
            try:
                from src.orbital.models import CicloOrbital

                cycle = CicloOrbital(
                    name=f"while_cycle_{step.get('id', 0)}",
                    variable_ids=all_vars[:5],
                    threshold=DEFAULT_THRESHOLD,
                )
                self._ctx.rcc.register_cycle(cycle)
            except (ValueError, KeyError):
                pass

        count = 0
        outputs = []
        converged = False
        prev_values = None
        convergence_delta = float("inf")

        from src.workflow.condition_evaluator import ConditionEvaluator

        evaluator = ConditionEvaluator()

        while count < max_iter:
            try:
                should_continue = evaluator.evaluate(condition, context)
            except ValueError:
                should_continue = True

            if not should_continue:
                break

            loop_var = self._ctx.ovc.get_variable(loop_var_name)
            if loop_var:
                loop_var.advance(dt=1.0)

            iteration_results = self._execute_inner_steps(inner_steps, context, step_executor)
            outputs.append(
                {
                    "index": count,
                    "results": iteration_results,
                }
            )

            # Verificar convergencia orbital (COD compartido)
            # Fix Sprint 3 bug #47: antes delta < DEFAULT_EPSILON (1e-6) era
            # prácticamente inalcanzable con amplitudes reales (10-100). Ahora
            # usamos un umbral relativo del 1% del valor anterior, o un mínimo
            # absoluto de 0.01 — lo que sea mayor (más permisivo).
            #
            # Fix Sprint 4: si no hay variables orbitales en el context (ej: test
            # con mock executor que no inyecta vars), prev_values/current_values
            # están vacíos y delta=0 — en ese caso NO converger (respetar
            # max_iterations).
            current_values = self._ctx.ovc.get_value_snapshot()
            if prev_values is not None and current_values:
                delta = 0.0
                for key in current_values:
                    if key in prev_values:
                        delta += abs(current_values[key] - prev_values[key])
                convergence_delta = delta

                # Solo verificar convergencia si hay variables orbitales reales
                # (delta > 0 significa que algo cambió; delta == 0 con values
                # vacíos significa que no hay vars, no que convergió).
                if delta > 0:
                    # Umbral relativo: 1% de la suma de valores absolutos previos,
                    # con mínimo de 0.01 (mucho más alcanzable que 1e-6).
                    prev_sum = sum(abs(v) for v in prev_values.values()) or 1.0
                    rel_threshold = max(0.01, prev_sum * 0.01)

                    if delta < rel_threshold:
                        converged = True
                        logger.info(
                            f"OrbitalConvergence: While CONVERGIO en {count} iteraciones "
                            f"(delta={delta:.6f} < threshold={rel_threshold:.6f})"
                        )
                        break

            prev_values = dict(current_values)
            count += 1

        logger.info(
            f"OrbitalConvergence: While completado — {count} iteraciones, "
            f"convergio={'Si' if converged else 'No'}, delta={convergence_delta:.8f}"
        )
        return LoopResult(
            iterations=count,
            outputs=outputs,
            converged=converged,
            convergence_delta=convergence_delta,
        )

    def _execute_inner_steps(self, steps: list[dict], context: dict, step_executor) -> list[dict]:
        """Ejecuta los pasos internos de una iteracion."""
        results = []
        for inner_step in steps:
            result = step_executor.execute(inner_step, context)
            results.append(
                {
                    "step_id": inner_step.get("id"),
                    "status": result.status,
                    "output": result.output_data,
                    "error": result.error_message,
                }
            )
            if result.status == "failed":
                break
        return results

    # ── Helpers orbitales (OVC compartido) ───────────────────

    def _ensure_loop_variable(self, var_name: str, step: dict) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            # Hash no criptográfico: deriva theta determinista del var_name (B324 mitigado).
            hash_val = int(hashlib.md5(var_name.encode(), usedforsecurity=False).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.1,
                orbit_group="loop_vars",
                metadata={"source": "loop_handler", "type": step.get("type"), "step_id": step.get("id")},
            )
