"""Data models for durable workflow execution.

Models extracted from durable.py to keep the file under 200 lines.
Includes EventType, WorkflowEvent, WorkflowState, HeartbeatInfo, and constants.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

# ── Configuracion via variables de entorno ────────────────────

DURABLE_ENABLED: bool = os.environ.get("WFD_DURABLE_EXECUTION", "false").lower() == "true"
HEARTBEAT_INTERVAL_SECONDS: int = int(os.environ.get("WFD_HEARTBEAT_INTERVAL_SECONDS", "30"))
HEARTBEAT_TIMEOUT_SECONDS: int = int(os.environ.get("WFD_HEARTBEAT_TIMEOUT_SECONDS", "300"))
SNAPSHOT_INTERVAL_STEPS: int = int(os.environ.get("WFD_SNAPSHOT_INTERVAL_STEPS", "5"))


# ── Tipos de eventos ─────────────────────────────────────────


class EventType:
    """Tipos de eventos del log de eventos."""

    WORKFLOW_STARTED = "WorkflowStarted"
    WORKFLOW_COMPLETED = "WorkflowCompleted"
    STEP_STARTED = "StepStarted"
    STEP_COMPLETED = "StepCompleted"
    STEP_FAILED = "StepFailed"


# ── Modelos de datos ─────────────────────────────────────────


@dataclass
class WorkflowEvent:
    """Evento inmutable en el log de eventos."""

    id: int | None = None
    execution_id: int = 0
    event_type: str = ""
    step_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowState:
    """Estado completo de una ejecucion de workflow."""

    workflow_id: int = 0
    execution_id: int = 0
    current_step_index: int = 0
    variables: dict[str, Any] = field(default_factory=dict)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, recovering
    trigger_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowState:
        return cls(
            workflow_id=data.get("workflow_id", 0),
            execution_id=data.get("execution_id", 0),
            current_step_index=data.get("current_step_index", 0),
            variables=data.get("variables", {}),
            step_results=data.get("step_results", []),
            status=data.get("status", "pending"),
            trigger_data=data.get("trigger_data", {}),
            error_message=data.get("error_message"),
        )


@dataclass
class HeartbeatInfo:
    """Informacion de heartbeat de un worker."""

    execution_id: int = 0
    step_id: int = 0
    worker_id: str = ""
    last_heartbeat: str = ""
    progress: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
