"""Base Agent — Abstract foundation for all Zenic-Flijo agents.

Provides lifecycle management, state transitions, capability declarations,
orbital integration, and structured communication between agents.
"""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentState(Enum):
    """Agent lifecycle states following a strict state machine."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


class AgentCapability(Enum):
    """Capabilities an agent can declare."""

    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    CODE_GENERATION = "code_generation"
    DATA_ANALYSIS = "data_analysis"
    WORKFLOW_ORCHESTRATION = "workflow_orchestration"
    NLU_PROCESSING = "nlu_processing"
    FILE_OPERATIONS = "file_operations"
    API_CALLS = "api_calls"
    MEMORY_ACCESS = "memory_access"
    MULTI_AGENT_COORDINATION = "multi_agent_coordination"


# Valid state transitions
VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.THINKING, AgentState.TERMINATED},
    AgentState.THINKING: {AgentState.EXECUTING, AgentState.WAITING, AgentState.ERROR, AgentState.IDLE},
    AgentState.EXECUTING: {AgentState.THINKING, AgentState.WAITING, AgentState.ERROR, AgentState.IDLE},
    AgentState.WAITING: {AgentState.THINKING, AgentState.PAUSED, AgentState.ERROR, AgentState.IDLE},
    AgentState.PAUSED: {AgentState.THINKING, AgentState.TERMINATED},
    AgentState.ERROR: {AgentState.IDLE, AgentState.TERMINATED},
    AgentState.TERMINATED: set(),
}


@dataclass
class AgentMessage:
    """Structured message for inter-agent communication."""

    sender_id: str
    recipient_id: str
    content: Any
    message_type: str = "inform"
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""

    agent_id: str = ""
    name: str = ""
    description: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    max_iterations: int = 10
    timeout_seconds: float = 300.0
    memory_enabled: bool = True
    orbital_enabled: bool = True
    tools_enabled: bool = True
    custom_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id:
            self.agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        if not self.name:
            self.name = self.agent_id


class BaseAgent(ABC):
    """Abstract base class for all Zenic-Flijo agents.

    Implements lifecycle management, state transitions, capability declarations,
    and orbital context integration. Concrete agents must implement `think()`
    and `act()` methods.

    Usage:
        class MyAgent(BaseAgent):
            def think(self, observation):
                # reasoning logic
                return {"decision": "proceed"}

            def act(self, decision):
                # action logic
                return {"result": "done"}
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._state = AgentState.IDLE
        self._state_lock = threading.Lock()
        self._message_queue: list[AgentMessage] = []
        self._message_lock = threading.Lock()
        self._execution_history: list[dict[str, Any]] = []
        self._created_at = time.time()
        self._last_active = self._created_at
        self._iteration_count = 0
        self._error_count = 0
        self._parent_id: str | None = None
        self._child_ids: list[str] = []
        self._context: dict[str, Any] = {}

    # ── Properties ──────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def state(self) -> AgentState:
        with self._state_lock:
            return self._state

    @property
    def capabilities(self) -> list[AgentCapability]:
        return self.config.capabilities

    @property
    def is_active(self) -> bool:
        return self.state not in {AgentState.TERMINATED, AgentState.ERROR}

    @property
    def uptime(self) -> float:
        return time.time() - self._created_at

    @property
    def iteration_count(self) -> int:
        return self._iteration_count

    # ── State Machine ───────────────────────────────────────

    def transition_to(self, new_state: AgentState) -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._state_lock:
            if new_state not in VALID_TRANSITIONS.get(self._state, set()):
                return False
            self._state = new_state
            self._last_active = time.time()
            return True

    def force_state(self, new_state: AgentState) -> None:
        """Force a state transition regardless of rules (admin only)."""
        with self._state_lock:
            self._state = new_state
            self._last_active = time.time()

    # ── Lifecycle ───────────────────────────────────────────

    def run(self, input_data: Any = None) -> Any:
        """Execute the agent's think-act loop until completion or max iterations."""
        self.transition_to(AgentState.THINKING)
        result = None

        for iteration in range(self.config.max_iterations):
            self._iteration_count = iteration + 1

            try:
                # Think phase
                self.transition_to(AgentState.THINKING)
                decision = self.think(input_data if iteration == 0 else result)

                if decision is None:
                    self.transition_to(AgentState.IDLE)
                    break

                # Act phase
                self.transition_to(AgentState.EXECUTING)
                result = self.act(decision)

                # Record execution
                self._execution_history.append({
                    "iteration": iteration + 1,
                    "decision": decision,
                    "result": result,
                    "timestamp": time.time(),
                })

                # Check if agent should stop
                if self._should_stop(result):
                    self.transition_to(AgentState.IDLE)
                    break

            except Exception as exc:
                self._error_count += 1
                self._execution_history.append({
                    "iteration": iteration + 1,
                    "error": str(exc),
                    "timestamp": time.time(),
                })
                self.transition_to(AgentState.ERROR)
                raise

        return result

    def pause(self) -> bool:
        """Pause the agent execution."""
        return self.transition_to(AgentState.PAUSED)

    def resume(self) -> bool:
        """Resume a paused agent."""
        if self.state == AgentState.PAUSED:
            return self.transition_to(AgentState.THINKING)
        return False

    def terminate(self) -> bool:
        """Terminate the agent."""
        return self.transition_to(AgentState.TERMINATED)

    # ── Abstract Methods ────────────────────────────────────

    @abstractmethod
    def think(self, observation: Any) -> Any:
        """Reasoning phase — analyze input and produce a decision."""

    @abstractmethod
    def act(self, decision: Any) -> Any:
        """Action phase — execute based on the decision."""

    # ── Messaging ───────────────────────────────────────────

    def send_message(self, recipient_id: str, content: Any, message_type: str = "inform") -> AgentMessage:
        """Send a message to another agent."""
        msg = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            content=content,
            message_type=message_type,
        )
        return msg

    def receive_message(self, message: AgentMessage) -> None:
        """Receive and queue a message from another agent."""
        with self._message_lock:
            self._message_queue.append(message)

    def get_pending_messages(self) -> list[AgentMessage]:
        """Get and clear all pending messages."""
        with self._message_lock:
            messages = list(self._message_queue)
            self._message_queue.clear()
            return messages

    # ── Context ─────────────────────────────────────────────

    def set_context(self, key: str, value: Any) -> None:
        """Set a context variable."""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self._context.get(key, default)

    # ── Internal ────────────────────────────────────────────

    def _should_stop(self, result: Any) -> bool:
        """Determine if the agent should stop after an action."""
        if isinstance(result, dict):
            return result.get("_stop", False) or result.get("done", False)
        return False

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the agent."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.value,
            "capabilities": [c.value for c in self.capabilities],
            "iteration_count": self._iteration_count,
            "error_count": self._error_count,
            "uptime": self.uptime,
            "last_active": self._last_active,
            "pending_messages": len(self._message_queue),
            "parent_id": self._parent_id,
            "child_ids": self._child_ids,
        }
