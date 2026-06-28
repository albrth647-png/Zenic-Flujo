"""Result data classes for workflow execution.

Contains ExecutionResult (engine), ForkResult, and JoinResult (fork_handler).
"""

from __future__ import annotations
from typing import Any


class ExecutionResult:
    """Resultado completo de una ejecucion de workflow (compatible + enriquecido)."""

    def __init__(
        self,
        execution_id: int,
        workflow_id: int,
        status: str,
        duration_ms: int,
        step_results: list[dict] | None = None,
        error_message: str | None = None,
        orbital_espectro: dict[str, Any] | None = None,
        orbital_variables: int = 0,
        orbital_resonance: float = 0.0,
    ):
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.status = status
        self.duration_ms = duration_ms
        self.step_results = step_results or []
        self.error_message = error_message
        self.orbital_espectro = orbital_espectro
        self.orbital_variables = orbital_variables
        self.orbital_resonance = orbital_resonance

    def to_dict(self) -> dict[str, Any]:
        d = {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "step_results": self.step_results,
            "error_message": self.error_message,
        }
        if self.orbital_espectro:
            d["orbital"] = {
                "espectro": self.orbital_espectro,
                "variables": self.orbital_variables,
                "resonance": self.orbital_resonance,
            }
        return d


class ForkResult:
    """Resultado de la ejecucion de un fork/parallel."""

    def __init__(
        self,
        status: str,
        branches: list[dict],
        merge_strategy: str = "all",
        duration_ms: int = 0,
        error_message: str | None = None,
    ):
        self.status = status  # 'completed' | 'partial' | 'failed'
        self.branches = branches
        self.merge_strategy = merge_strategy
        self.duration_ms = duration_ms
        self.error_message = error_message


class JoinResult:
    """Resultado de la union de ramas paralelas."""

    def __init__(
        self,
        status: str,
        merged_output: dict[str, Any],
        branch_count: int,
        duration_ms: int = 0,
        error_message: str | None = None,
    ):
        self.status = status
        self.merged_output = merged_output
        self.branch_count = branch_count
        self.duration_ms = duration_ms
        self.error_message = error_message
