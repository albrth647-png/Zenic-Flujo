"""ParallelExecutionService — ejecución en paralelo (DAG Fork/Join).

Contiene ForkHandler y JoinHandler extraídos de fork_handler.py.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

from src.core.logging import setup_logging
from src.workflow.execution.result import ForkResult, JoinResult

logger = setup_logging(__name__)


class ForkHandler:
    """ForkHandler — Ejecuta pasos en paralelo con merge strategies."""

    MAX_BRANCHES = 50
    DEFAULT_TIMEOUT = 120

    def __init__(self, step_executor):
        self._step_executor = step_executor

    def execute_parallel(self, step: dict[str, Any], context: dict[str, Any]) -> ForkResult:
        """Ejecuta ramas en paralelo y espera según merge strategy."""
        branches = step.get("branches", [])
        if not branches:
            return ForkResult(status="completed", branches=[], duration_ms=0)

        if len(branches) > self.MAX_BRANCHES:
            logger.warning(f"Parallel: truncado de {len(branches)} a {self.MAX_BRANCHES} ramas")
            branches = branches[: self.MAX_BRANCHES]

        merge_strategy = step.get("merge_strategy", "all")
        timeout = step.get("timeout", self.DEFAULT_TIMEOUT)
        step_id = step.get("id", 0)

        logger.info(f"ForkHandler: Ejecutando {len(branches)} ramas en paralelo "
                     f"(id={step_id}, strategy={merge_strategy}, timeout={timeout}s)")

        start_time = time.time()
        results: list[dict | None] = [None] * len(branches)
        lock = threading.Lock()
        completed_count = 0
        failed_count = 0
        early_exit = threading.Event()

        def _run_branch(branch: dict[str, Any], idx: int):
            nonlocal completed_count, failed_count
            branch_context = dict(context)
            branch_name = branch.get("name", f"branch_{idx}")
            branch_steps = branch.get("steps", [])
            branch_results = []
            branch_status = "completed"
            branch_error = None

            for inner_step in branch_steps:
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
                if merge_strategy == "any" and branch_status == "completed":
                    early_exit.set()

        threads = []
        for idx, branch in enumerate(branches):
            thread = threading.Thread(target=_run_branch, args=(branch, idx), daemon=True)
            thread.start()
            threads.append(thread)

        # Fix Sprint 3 bug #46: antes dividía el timeout entre el número de threads
        # (timeout // len(threads)), dando a cada thread solo timeout/N segundos.
        # Con 50 branches y timeout=120s, cada thread tenía 2.4s — insuficiente.
        # Ahora: deadline global = now + timeout; cada thread.join() espera hasta
        # el deadline restante (no dividido).
        deadline = time.time() + timeout
        for thread in threads:
            remaining_time = max(0.1, deadline - time.time())
            thread.join(timeout=remaining_time)
            if time.time() >= deadline:
                # Deadline alcanzado: no esperar más threads
                break

        remaining = 0
        for idx, result in enumerate(results):
            if result is None:
                results[idx] = {
                    "name": branches[idx].get("name", f"branch_{idx}"),
                    "status": "timeout",
                    "steps": [],
                    "error": f"Excedio timeout de {timeout}s",
                }
                remaining += 1

        duration = int((time.time() - start_time) * 1000)

        if remaining > 0:
            global_status = "partial"
        elif merge_strategy == "all" and failed_count > 0:
            global_status = "failed"
        elif (merge_strategy in ("any", "race") and completed_count > 0) or completed_count == len(branches):
            global_status = "completed"
        else:
            global_status = "partial"

        error_msg = next((b.get("error") for b in results if b and b.get("error")), None)

        return ForkResult(
            status=global_status,
            branches=[r for r in results if r is not None],
            merge_strategy=merge_strategy,
            duration_ms=duration,
            error_message=error_msg,
        )

    def execute_fork(self, step: dict[str, Any], context: dict[str, Any]) -> ForkResult:
        """Fork simple: crea N contextos y ejecuta mismos pasos en cada uno."""
        collection_ref = step.get("collection", "")
        item_var = step.get("item_var", "item")
        index_var = step.get("index_var", "index")
        inner_steps = step.get("steps", [])
        merge_strategy = step.get("merge_strategy", "all")
        max_concurrency = step.get("max_concurrency", 10)
        timeout = step.get("timeout", self.DEFAULT_TIMEOUT)

        import json

        from src.core.utils import resolve_variables, safe_get

        collection = None
        if isinstance(collection_ref, (list, tuple)):
            collection = collection_ref
        elif isinstance(collection_ref, str) and collection_ref.startswith("$"):
            path = collection_ref.lstrip("$")
            collection = safe_get(context, path)
        else:
            collection_str = resolve_variables(collection_ref, context) if isinstance(collection_ref, str) else collection_ref
            if isinstance(collection_str, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    collection = json.loads(collection_str)
            else:
                collection = collection_str

        if not isinstance(collection, (list, tuple)):
            collection = [collection] if collection is not None else []

        if len(collection) > 100:
            logger.warning(f"Fork: truncado de {len(collection)} a 100 items")
            collection = collection[:100]

        if not collection:
            logger.info("ForkHandler: Coleccion vacia, nada que forkear")
            return ForkResult(status="completed", branches=[], merge_strategy=merge_strategy, duration_ms=0)

        logger.info(f"ForkHandler: Forkeando {len(collection)} items (concurrency={max_concurrency})")
        start_time = time.time()
        results: list[dict] = []
        semaphore = threading.Semaphore(max_concurrency)
        lock = threading.Lock()
        early_exit = threading.Event()

        # legítimo: item de fork, tipo dinámico según branch del workflow
        def _run_fork_item(item: Any, idx: int):
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
                        "status": "completed" if not any(r["status"] == "failed" for r in item_results) else "failed",
                        "steps": item_results,
                    })
                    if merge_strategy == "any" and item_results and item_results[-1]["status"] == "completed":
                        early_exit.set()

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
    """JoinHandler — Une ramas paralelas con estrategias de merge."""

    def join(self, fork_result: ForkResult, step: dict[str, Any], context: dict[str, Any]) -> JoinResult:
        """Une los resultados de un fork/parallel según la merge strategy."""
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

        context[f"_join_{step_id}"] = merged_output
        duration = int((time.time() - start_time) * 1000)

        return JoinResult(
            status=fork_result.status,
            merged_output=merged_output,
            branch_count=len(branches),
            duration_ms=duration,
        )

    def _merge_all(self, branches: list[dict], step: dict[str, Any]) -> dict[str, Any]:
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
        for branch in branches:
            if "index" in branch:
                key = f"item_{branch['index']}"
                if key not in merged["branches"]:
                    merged["branches"][key] = {
                        "status": branch.get("status", "unknown"),
                        "output": branch.get("steps", [{}])[-1].get("output", {}) if branch.get("steps") else {},
                    }
        return merged

    def _merge_any(self, branches: list[dict], step: dict[str, Any]) -> dict[str, Any]:
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

    def _merge_race(self, branches: list[dict], step: dict[str, Any]) -> dict[str, Any]:
        return self._merge_any(branches, step)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "tool": "fork_join",
            "name": "Fork/Join Paralelo",
            "description": "Ejecuta pasos en paralelo con merge strategies",
            "actions": {
                "parallel": {
                    "name": "Parallel",
                    "description": "Ramas diferentes en paralelo",
                    "params": [
                        {"name": "branches", "type": "list", "required": True, "label": "Ramas (cada una con sus steps)"},
                        {"name": "merge_strategy", "type": "select", "options": ["all", "any", "race"], "default": "all", "label": "Estrategia de merge"},
                        {"name": "timeout", "type": "number", "default": 120, "label": "Timeout (segundos)"},
                    ],
                },
                "fork": {
                    "name": "Fork",
                    "description": "Mismos steps para cada item de una coleccion",
                    "params": [
                        {"name": "collection", "type": "string", "required": True, "label": "Coleccion (referencia $input.items)"},
                        {"name": "merge_strategy", "type": "select", "options": ["all", "any", "race"], "default": "all", "label": "Estrategia de merge"},
                        {"name": "max_concurrency", "type": "number", "default": 10, "label": "Max. concurrencia"},
                    ],
                },
            },
        }
