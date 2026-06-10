"""
ForkHandler — Ejecución en paralelo (DAG Fork/Join)
=====================================================

Permite bifurcar la ejecución de un workflow en N ramas paralelas
y unirlas con diferentes estrategias de merge.

Step types:
- 'parallel': divide en ramas que se ejecutan en paralelo
- 'fork': crea N copias del contexto y ejecuta pasos en cada una
- 'join': espera a que todas las ramas terminen y mergea resultados

Merge strategies:
- 'all': espera a todas las ramas, mergea todos los outputs
- 'any': retorna en cuanto la primera rama termina
- 'race': como 'any' pero las demás se cancelan
"""

from __future__ import annotations

import threading
import time
from typing import Any
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class ForkResult:
    """Resultado de la ejecución de un fork/parallel."""

    def __init__(self, status: str, branches: list[dict],
                 merge_strategy: str = "all",
                 duration_ms: int = 0,
                 error_message: str | None = None):
        self.status = status  # 'completed' | 'partial' | 'failed'
        self.branches = branches
        self.merge_strategy = merge_strategy
        self.duration_ms = duration_ms
        self.error_message = error_message


class JoinResult:
    """Resultado de la unión de ramas paralelas."""

    def __init__(self, status: str, merged_output: dict,
                 branch_count: int, duration_ms: int = 0,
                 error_message: str | None = None):
        self.status = status
        self.merged_output = merged_output
        self.branch_count = branch_count
        self.duration_ms = duration_ms
        self.error_message = error_message


class ForkHandler:
    """
    ForkHandler — Ejecuta pasos en paralelo con merge strategies.

    Uso en workflow:
    {
        "id": 3,
        "type": "parallel",
        "branches": [
            {
                "name": "email",
                "steps": [
                    {"id": 4, "tool": "notification", "action": "send_email", "params": {...}},
                    {"id": 5, "tool": "crm", "action": "log_activity", "params": {...}}
                ]
            },
            {
                "name": "invoice",
                "steps": [
                    {"id": 6, "tool": "invoice", "action": "create", "params": {...}}
                ]
            }
        ],
        "merge_strategy": "all",
        "timeout": 120
    }
    """

    MAX_BRANCHES = 50
    DEFAULT_TIMEOUT = 120

    def __init__(self, step_executor):
        self._step_executor = step_executor

    def execute_parallel(self, step: dict, context: dict) -> ForkResult:
        """
        Ejecuta ramas en paralelo y espera según merge strategy.

        Args:
            step: Definición del paso parallel/fork
            context: Contexto de ejecución del workflow

        Returns:
            ForkResult con los resultados de todas las ramas
        """
        branches = step.get("branches", [])
        if not branches:
            return ForkResult(
                status="completed",
                branches=[],
                duration_ms=0,
            )

        if len(branches) > self.MAX_BRANCHES:
            logger.warning(f"Parallel: truncado de {len(branches)} a {self.MAX_BRANCHES} ramas")
            branches = branches[:self.MAX_BRANCHES]

        merge_strategy = step.get("merge_strategy", "all")
        timeout = step.get("timeout", self.DEFAULT_TIMEOUT)
        step_id = step.get("id", 0)

        logger.info(f"ForkHandler: Ejecutando {len(branches)} ramas en paralelo "
                    f"(strategy={merge_strategy}, timeout={timeout}s)")

        start_time = time.time()
        results: list[dict | None] = [None] * len(branches)
        lock = threading.Lock()
        completed_count = 0
        failed_count = 0
        early_exit = threading.Event()

        def _run_branch(branch: dict, idx: int):
            """Ejecuta una rama completa con sus pasos internos.
            
            Cada rama recibe su PROPIA copia del context para evitar
            condiciones de carrera (ej: _last_step_id).
            """
            nonlocal completed_count, failed_count
            branch_context = dict(context)  # ← Copia independiente por rama
            branch_name = branch.get("name", f"branch_{idx}")
            branch_steps = branch.get("steps", [])
            branch_results = []
            branch_status = "completed"
            branch_error = None

            for inner_step in branch_steps:
                # Verificar early exit (strategy 'race' o 'any')
                if early_exit.is_set():
                    branch_results.append({
                        "step_id": inner_step.get("id"),
                        "status": "cancelled",
                        "reason": "early_exit",
                    })
                    continue

                try:
                    result = self._step_executor.execute(inner_step, branch_context)
                    branch_results.append({
                        "step_id": inner_step.get("id"),
                        "tool": inner_step.get("tool"),
                        "action": inner_step.get("action"),
                        "status": result.status,
                        "output": result.output_data,
                        "duration_ms": result.duration_ms,
                        "error": result.error_message,
                    })
                    if result.status == "failed":
                        branch_status = "failed"
                        branch_error = result.error_message
                        if merge_strategy == "race":
                            early_exit.set()
                        break
                except Exception as e:
                    branch_results.append({
                        "step_id": inner_step.get("id"),
                        "status": "failed",
                        "error": str(e),
                    })
                    branch_status = "failed"
                    branch_error = str(e)
                    if merge_strategy == "race":
                        early_exit.set()
                    break

            with lock:
                results[idx] = {
                    "name": branch_name,
                    "status": branch_status,
                    "steps": branch_results,
                    "error": branch_error,
                }
                if branch_status == "completed":
                    completed_count += 1
                else:
                    failed_count += 1

                # Para strategy 'any', marcar early exit en cuanto una completa
                if merge_strategy == "any" and branch_status == "completed":
                    early_exit.set()

        # Lanzar todas las ramas en hilos paralelos
        threads = []
        for idx, branch in enumerate(branches):
            thread = threading.Thread(
                target=_run_branch,
                args=(branch, idx),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        # Esperar con timeout global
        for thread in threads:
            thread.join(timeout=max(1, timeout // len(threads)))

        # Si alguna rama no terminó, marcarla como timeout
        remaining = 0
        for idx, result in enumerate(results):
            if result is None:
                results[idx] = {
                    "name": branches[idx].get("name", f"branch_{idx}"),
                    "status": "timeout",
                    "steps": [],
                    "error": f"Excedió timeout de {timeout}s",
                }
                remaining += 1

        if remaining > 0:
            logger.warning(f"ForkHandler: {remaining} rama(s) no terminaron dentro del timeout")

        duration = int((time.time() - start_time) * 1000)

        # Determinar status global según merge strategy
        if remaining > 0:
            global_status = "partial"
        elif merge_strategy == "all" and failed_count > 0:
            global_status = "failed"
        elif merge_strategy in ("any", "race") and completed_count > 0:
            global_status = "completed"
        elif completed_count == len(branches):
            global_status = "completed"
        else:
            global_status = "partial"

        # Recolectar primer error de ramas fallidas para el StepResult
        error_msg = next(
            (b.get("error") for b in results if b and b.get("error")),
            None
        )

        return ForkResult(
            status=global_status,
            branches=[r for r in results if r is not None],
            merge_strategy=merge_strategy,
            duration_ms=duration,
            error_message=error_msg,
        )

    def execute_fork(self, step: dict, context: dict) -> ForkResult:
        """
        Fork simple: crea N contextos a partir de una lista/colección
        y ejecuta los mismos pasos en cada uno.

        Diferencias con parallel:
        - parallel: ramas DIFERENTES (cada rama tiene sus propios pasos)
        - fork: MISMO pasos para cada elemento de una colección

        Uso:
        {
            "id": 5,
            "type": "fork",
            "collection": "$input.items",
            "item_var": "item",
            "steps": [
                {"id": 6, "tool": "crm", "action": "create_lead", "params": {...}}
            ],
            "merge_strategy": "all",
            "max_concurrency": 5
        }
        """
        collection_ref = step.get("collection", "")
        item_var = step.get("item_var", "item")
        index_var = step.get("index_var", "index")
        inner_steps = step.get("steps", [])
        merge_strategy = step.get("merge_strategy", "all")
        max_concurrency = step.get("max_concurrency", 10)
        timeout = step.get("timeout", self.DEFAULT_TIMEOUT)

        from src.utils.helpers import resolve_variables, safe_get
        import json

        # Resolver la colección desde el contexto
        collection = None
        if isinstance(collection_ref, (list, tuple)):
            # Ya es una lista, usarla directamente
            collection = collection_ref
        elif isinstance(collection_ref, str) and collection_ref.startswith("$"):
            path = collection_ref.lstrip("$")
            collection = safe_get(context, path)
        else:
            collection_str = resolve_variables(collection_ref, context) if isinstance(collection_ref, str) else collection_ref
            if isinstance(collection_str, str):
                try:
                    collection = json.loads(collection_str)
                except (json.JSONDecodeError, TypeError):
                    pass
            else:
                collection = collection_str

        if not isinstance(collection, (list, tuple)):
            collection = [collection] if collection is not None else []

        if len(collection) > 100:
            logger.warning(f"Fork: truncado de {len(collection)} a 100 items")
            collection = collection[:100]

        if not collection:
            logger.info("ForkHandler: Colección vacía, nada que forkear")
            return ForkResult(status="completed", branches=[], merge_strategy=merge_strategy, duration_ms=0)

        logger.info(f"ForkHandler: Forkeando {len(collection)} items (concurrency={max_concurrency})")

        start_time = time.time()
        results: list[dict] = []
        semaphore = threading.Semaphore(max_concurrency)
        lock = threading.Lock()
        early_exit = threading.Event()

        def _run_fork_item(item: Any, idx: int):
            """Ejecuta los pasos del fork para un item."""
            if early_exit.is_set():
                return

            with semaphore:
                iter_context = dict(context)
                iter_context[item_var] = item
                iter_context[index_var] = idx
                item_results = []

                for inner_step in inner_steps:
                    try:
                        result = self._step_executor.execute(inner_step, iter_context)
                        item_results.append({
                            "step_id": inner_step.get("id"),
                            "status": result.status,
                            "output": result.output_data,
                            "error": result.error_message,
                        })
                        if result.status == "failed":
                            if merge_strategy == "race":
                                early_exit.set()
                            break
                    except Exception as e:
                        item_results.append({
                            "step_id": inner_step.get("id"),
                            "status": "failed",
                            "error": str(e),
                        })
                        if merge_strategy == "race":
                            early_exit.set()
                        break

                with lock:
                    results.append({
                        "index": idx,
                        item_var: item,
                        "status": "completed" if not any(
                            r["status"] == "failed" for r in item_results
                        ) else "failed",
                        "steps": item_results,
                    })
                    if merge_strategy == "any" and item_results and item_results[-1]["status"] == "completed":
                        early_exit.set()

        # Lanzar hilos con semáforo para control de concurrencia
        threads = []
        for idx, item in enumerate(collection):
            if early_exit.is_set() and merge_strategy == "race":
                break
            t = threading.Thread(target=_run_fork_item, args=(item, idx), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=max(1, timeout))

        duration = int((time.time() - start_time) * 1000)

        failed_count = sum(1 for r in results if r["status"] == "failed")
        completed_count = sum(1 for r in results if r["status"] == "completed")

        if merge_strategy == "all" and failed_count > 0:
            global_status = "failed"
        elif completed_count > 0:
            global_status = "completed"
        else:
            global_status = "partial"

        return ForkResult(
            status=global_status,
            branches=results,
            merge_strategy=merge_strategy,
            duration_ms=duration,
        )


class JoinHandler:
    """
    JoinHandler — Une ramas paralelas con estrategias de merge.

    Se usa después de un fork/parallel para combinar los outputs
    de todas las ramas en un solo resultado.
    """

    def join(self, fork_result: ForkResult, step: dict, context: dict) -> JoinResult:
        """
        Une los resultados de un fork/parallel según la merge strategy.

        Merge strategies:
        - 'all': mergea outputs de TODAS las ramas completadas
        - 'any': usa el output de la primera rama que completó
        - 'race': usa el output de la primera rama (cancela las demás)

        Args:
            fork_result: Resultado del ForkHandler
            step: Definición del paso join
            context: Contexto de ejecución

        Returns:
            JoinResult con el output mergeado
        """
        strategy = fork_result.merge_strategy
        branches = fork_result.branches
        step_id = step.get("id", 0)

        logger.info(f"JoinHandler: Uniendo {len(branches)} ramas (strategy={strategy})")

        start_time = time.time()

        if strategy == "all":
            merged_output = self._merge_all(branches, step)
        elif strategy == "any":
            merged_output = self._merge_any(branches, step)
        elif strategy == "race":
            merged_output = self._merge_race(branches, step)
        else:
            merged_output = self._merge_all(branches, step)

        # Guardar merged_output en contexto para pasos siguientes
        context[f"_join_{step_id}"] = merged_output

        duration = int((time.time() - start_time) * 1000)

        return JoinResult(
            status=fork_result.status,
            merged_output=merged_output,
            branch_count=len(branches),
            duration_ms=duration,
        )

    def _merge_all(self, branches: list[dict], step: dict) -> dict:
        """
        Merge 'all': combina outputs de todas las ramas completadas.

        Cada rama contribuye con su último output al resultado final.
        Los nombres de rama se usan como keys.
        """
        merged = {"branches": {}, "branch_order": [], "total_branches": len(branches)}

        for branch in branches:
            name = branch.get("name", "unnamed")
            branch_status = branch.get("status", "unknown")

            merged["branch_order"].append(name)

            if branch_status == "completed" and branch.get("steps"):
                last_step = branch["steps"][-1]
                merged["branches"][name] = {
                    "status": "completed",
                    "output": last_step.get("output", {}),
                    "steps_count": len(branch["steps"]),
                }
            else:
                merged["branches"][name] = {
                    "status": branch_status,
                    "error": branch.get("error"),
                    "steps_count": len(branch.get("steps", [])),
                }

        # Items individuales (para forks)
        for branch in branches:
            if "index" in branch:
                key = f"item_{branch['index']}"
                if key not in merged["branches"]:
                    merged["branches"][key] = {
                        "status": branch.get("status", "unknown"),
                        "output": branch.get("steps", [{}])[-1].get("output", {})
                        if branch.get("steps") else {},
                    }

        return merged

    def _merge_any(self, branches: list[dict], step: dict) -> dict:
        """
        Merge 'any': retorna el output de la primera rama que completó.

        Útil para workflows donde cualquier resultado sirve.
        """
        for branch in branches:
            name = branch.get("name", "unnamed")
            if branch.get("status") == "completed":
                last_step = branch.get("steps", [{}])[-1] if branch.get("steps") else {}
                return {
                    "selected_branch": name,
                    "merge_strategy": "any",
                    "output": last_step.get("output", {}),
                    "total_branches": len(branches),
                }

        # Si ninguna completó, retornar la primera
        if branches:
            branch = branches[0]
            last_step = branch.get("steps", [{}])[-1] if branch.get("steps") else {}
            return {
                "selected_branch": branch.get("name", "first"),
                "merge_strategy": "any",
                "output": last_step.get("output", {}),
                "total_branches": len(branches),
            }

        return {"merge_strategy": "any", "output": {}, "total_branches": 0}

    def _merge_race(self, branches: list[dict], step: dict) -> dict:
        """
        Merge 'race': retorna la primera rama en completar (carrera).

        Similar a 'any', pero explícitamente diseñado para carreras
        donde solo importa el ganador.
        """
        return self._merge_any(branches, step)

    def get_tool_definition(self) -> dict:
        """Retorna la definición del tool para el editor visual."""
        return {
            "tool": "fork_join",
            "name": "Fork/Join Paralelo",
            "description": "Ejecuta pasos en paralelo con merge strategies",
            "actions": {
                "parallel": {
                    "name": "Parallel",
                    "description": "Ramas diferentes en paralelo",
                    "params": [
                        {"name": "branches", "type": "list", "required": True,
                         "label": "Ramas (cada una con sus steps)"},
                        {"name": "merge_strategy", "type": "select",
                         "options": ["all", "any", "race"],
                         "default": "all", "label": "Estrategia de merge"},
                        {"name": "timeout", "type": "number",
                         "default": 120, "label": "Timeout (segundos)"},
                    ],
                },
                "fork": {
                    "name": "Fork",
                    "description": "Mismos steps para cada item de una colección",
                    "params": [
                        {"name": "collection", "type": "string", "required": True,
                         "label": "Colección (referencia $input.items)"},
                        {"name": "merge_strategy", "type": "select",
                         "options": ["all", "any", "race"],
                         "default": "all", "label": "Estrategia de merge"},
                        {"name": "max_concurrency", "type": "number",
                         "default": 10, "label": "Máx. concurrencia"},
                    ],
                },
            },
        }
