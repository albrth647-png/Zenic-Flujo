"""Multi-Agent Orchestrator — Coordination patterns for agent teams.

Implements multiple orchestration patterns for coordinating multiple agents:
- SEQUENTIAL: Agents execute one after another in a pipeline
- PARALLEL: Agents execute concurrently with result aggregation
- HIERARCHICAL: Manager-delegate pattern with task decomposition
- DEBATE: Agents argue different perspectives, a judge decides
- ROUND_ROBIN: Agents take turns in a cyclic pattern
- MAP_REDUCE: Map tasks across agents, reduce results centrally

Integrates with the orbital context for emergent coordination dynamics.
"""

from __future__ import annotations

import threading
import time
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from src.core.logging import get_logger
from src.hat.agents_legacy.base import AgentConfig, BaseAgent
from src.hat.agents_legacy.runtime import AgentRuntime

logger = get_logger("agent.orchestrator")


class AgentRunResult(TypedDict, total=False):
    """Resultado de un paso de agente en una orquestación.

    total=False porque los campos varían según el patrón de orquestación.
    El campo ``perspective`` es usado por DebateStrategy.
    """
    agent_id: str
    name: str
    step: int
    role: str
    subtask_index: int
    round: int
    turn: int
    phase: str
    output: object
    perspective: object
    status: str
    error: str
    agent_name: str


class OrchestratorStats(TypedDict):
    """Estadísticas del orquestador multi-agente."""
    total_orchestrations: int
    successful: int
    failed: int
    by_pattern: dict[str, int]
    avg_duration_ms: float


class OrchestrationPattern(Enum):
    """Supported multi-agent orchestration patterns."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    DEBATE = "debate"
    ROUND_ROBIN = "round_robin"
    MAP_REDUCE = "map_reduce"


@dataclass
class OrchestrationPlan:
    """Plan describing how agents will be coordinated."""

    plan_id: str = ""
    pattern: OrchestrationPattern = OrchestrationPattern.SEQUENTIAL
    agent_configs: list[AgentConfig] = field(default_factory=list)
    agent_classes: list[type[BaseAgent]] = field(default_factory=list)
    input_data: object = None
    max_rounds: int = 5
    timeout_seconds: float = 600.0
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id:
            self.plan_id = f"plan-{uuid.uuid4().hex[:8]}"


@dataclass
class OrchestrationResult:
    """Result of a multi-agent orchestration execution."""

    plan_id: str = ""
    pattern: OrchestrationPattern = OrchestrationPattern.SEQUENTIAL
    final_result: object = None
    agent_results: list[AgentRunResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    rounds_completed: int = 0
    success: bool = True
    error: str | None = None


class OrchestrationStrategy(ABC):
    """Abstract base for orchestration strategies."""

    @abstractmethod
    def execute(
        self,
        runtime: AgentRuntime,
        plan: OrchestrationPlan,
    ) -> OrchestrationResult:
        """Execute the orchestration strategy."""

    @abstractmethod
    def pattern(self) -> OrchestrationPattern:
        """Return the pattern this strategy implements."""


class SequentialStrategy(OrchestrationStrategy):
    """Sequential pipeline: each agent's output feeds the next agent's input."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.SEQUENTIAL

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        current_input = plan.input_data

        for i, (agent_class, config) in enumerate(zip(plan.agent_classes, plan.agent_configs, strict=True)):
            try:
                agent = runtime.spawn(agent_class, config)
                output = agent.run(current_input)
                result.agent_results.append({
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "step": i + 1,
                    "output": output,
                    "status": "success",
                })
                current_input = output
            except Exception as exc:
                result.agent_results.append({
                    "step": i + 1,
                    "status": "error",
                    "error": str(exc),
                })
                result.success = False
                result.error = str(exc)
                break

        result.final_result = current_input
        result.total_duration_ms = (time.time() - start_time) * 1000
        result.rounds_completed = len(result.agent_results)
        return result


class ParallelStrategy(OrchestrationStrategy):
    """Parallel execution: all agents work on the same input simultaneously."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.PARALLEL

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        agents = []
        for agent_class, config in zip(plan.agent_classes, plan.agent_configs, strict=True):
            try:
                agent = runtime.spawn(agent_class, config)
                agents.append(agent)
            except Exception as exc:
                result.agent_results.append({
                    "name": config.name,
                    "status": "error",
                    "error": str(exc),
                })

        # Execute all agents in parallel
        with ThreadPoolExecutor(max_workers=len(agents)) as executor:
            futures = {
                executor.submit(agent.run, plan.input_data): agent
                for agent in agents
            }

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    output = future.result(timeout=plan.timeout_seconds)
                    result.agent_results.append({
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "output": output,
                        "status": "success",
                    })
                except Exception as exc:
                    result.agent_results.append({
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "status": "error",
                        "error": str(exc),
                    })

        # Aggregate results
        result.final_result = {
            "aggregated": [r.get("output") for r in result.agent_results if r.get("status") == "success"],
            "agent_count": len(agents),
        }
        result.total_duration_ms = (time.time() - start_time) * 1000
        result.rounds_completed = 1
        return result


class HierarchicalStrategy(OrchestrationStrategy):
    """Manager-delegate pattern: a manager agent decomposes tasks and delegates to workers."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.HIERARCHICAL

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        if not plan.agent_classes:
            result.success = False
            result.error = "No agents provided"
            return result

        # First agent is the manager, rest are workers
        manager_class = plan.agent_classes[0]
        manager_config = plan.agent_configs[0]

        try:
            manager = runtime.spawn(manager_class, manager_config)
            manager_decision = manager.run(plan.input_data)

            result.agent_results.append({
                "agent_id": manager.agent_id,
                "name": manager.name,
                "role": "manager",
                "output": manager_decision,
                "status": "success",
            })

            # Manager produces subtasks for workers
            subtasks = manager_decision if isinstance(manager_decision, list) else [manager_decision]

            # Delegate to worker agents
            worker_results = []
            for i, subtask in enumerate(subtasks):
                worker_idx = (i % max(len(plan.agent_classes) - 1, 1)) + 1
                if worker_idx >= len(plan.agent_classes):
                    worker_idx = 1

                worker_class = plan.agent_classes[worker_idx]
                worker_config = plan.agent_configs[worker_idx]
                worker_config.custom_config["subtask"] = subtask

                try:
                    worker = runtime.spawn(worker_class, worker_config, parent_id=manager.agent_id)
                    worker_output = worker.run(subtask)
                    worker_results.append({
                        "agent_id": worker.agent_id,
                        "name": worker.name,
                        "role": "worker",
                        "subtask_index": i,
                        "output": worker_output,
                        "status": "success",
                    })
                except Exception as exc:
                    worker_results.append({
                        "role": "worker",
                        "subtask_index": i,
                        "status": "error",
                        "error": str(exc),
                    })

            result.agent_results.extend(worker_results)
            result.final_result = {
                "manager_decision": manager_decision,
                "worker_results": [r.get("output") for r in worker_results if r.get("status") == "success"],
            }

        except Exception as exc:
            result.success = False
            result.error = str(exc)

        result.total_duration_ms = (time.time() - start_time) * 1000
        result.rounds_completed = 1
        return result


class DebateStrategy(OrchestrationStrategy):
    """Debate pattern: agents argue different perspectives, rounds of back-and-forth."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.DEBATE

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        agents = []
        for agent_class, config in zip(plan.agent_classes, plan.agent_configs, strict=True):
            try:
                agent = runtime.spawn(agent_class, config)
                agents.append(agent)
            except Exception as exc:
                logger.error("Failed to spawn debate agent: %s", exc)

        if len(agents) < 2:
            result.success = False
            result.error = "Debate requires at least 2 agents"
            result.total_duration_ms = (time.time() - start_time) * 1000
            return result

        current_topic = plan.input_data
        perspectives: list[dict[str, Any]] = []

        for round_num in range(plan.max_rounds):
            for agent in agents:
                try:
                    perspective = agent.run(current_topic)
                    perspectives.append({
                        "round": round_num + 1,
                        "agent_id": agent.agent_id,
                        "agent_name": agent.name,
                        "perspective": perspective,
                    })
                    # Next agent sees the previous perspective
                    current_topic = perspective
                except Exception as exc:
                    perspectives.append({
                        "round": round_num + 1,
                        "agent_id": agent.agent_id,
                        "error": str(exc),
                    })

        result.agent_results = perspectives
        result.rounds_completed = plan.max_rounds
        result.final_result = {
            "topic": plan.input_data,
            "perspectives": perspectives,
            "total_rounds": plan.max_rounds,
        }
        result.total_duration_ms = (time.time() - start_time) * 1000
        return result


class RoundRobinStrategy(OrchestrationStrategy):
    """Round-robin: agents take turns processing in a cycle."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.ROUND_ROBIN

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        agents = []
        for agent_class, config in zip(plan.agent_classes, plan.agent_configs, strict=True):
            try:
                agent = runtime.spawn(agent_class, config)
                agents.append(agent)
            except Exception as exc:
                logger.error("Failed to spawn round-robin agent: %s", exc)

        if not agents:
            result.success = False
            result.error = "No agents available"
            return result

        current_input = plan.input_data
        turn_results: list[dict[str, Any]] = []

        for round_num in range(plan.max_rounds):
            for i, agent in enumerate(agents):
                try:
                    output = agent.run(current_input)
                    turn_results.append({
                        "round": round_num + 1,
                        "agent_id": agent.agent_id,
                        "agent_name": agent.name,
                        "turn": i + 1,
                        "output": output,
                        "status": "success",
                    })
                    current_input = output
                except Exception as exc:
                    turn_results.append({
                        "round": round_num + 1,
                        "agent_id": agent.agent_id,
                        "turn": i + 1,
                        "status": "error",
                        "error": str(exc),
                    })

        result.agent_results = turn_results
        result.rounds_completed = plan.max_rounds
        result.final_result = current_input
        result.total_duration_ms = (time.time() - start_time) * 1000
        return result


class MapReduceStrategy(OrchestrationStrategy):
    """Map-Reduce: map tasks across agents, reduce results centrally."""

    def pattern(self) -> OrchestrationPattern:
        return OrchestrationPattern.MAP_REDUCE

    def execute(self, runtime: AgentRuntime, plan: OrchestrationPlan) -> OrchestrationResult:
        start_time = time.time()
        result = OrchestrationResult(
            plan_id=plan.plan_id,
            pattern=self.pattern(),
        )

        if not plan.agent_classes:
            result.success = False
            result.error = "No agents provided"
            return result

        # Last agent is the reducer, rest are mappers
        mapper_classes = plan.agent_classes[:-1]
        mapper_configs = plan.agent_configs[:-1]
        reducer_class = plan.agent_classes[-1]
        reducer_config = plan.agent_configs[-1]

        # Split input data for mappers
        input_data = plan.input_data
        if isinstance(input_data, list):
            chunks = [input_data[i::len(mapper_classes)] for i in range(len(mapper_classes))]
        else:
            chunks = [input_data] * len(mapper_classes)

        # Map phase: each mapper processes a chunk
        map_results = []
        with ThreadPoolExecutor(max_workers=len(mapper_classes)) as executor:
            futures = {}
            for i, (agent_class, config) in enumerate(zip(mapper_classes, mapper_configs, strict=True)):
                chunk = chunks[i] if i < len(chunks) else input_data
                try:
                    agent = runtime.spawn(agent_class, config)
                    futures[executor.submit(agent.run, chunk)] = agent
                except Exception as exc:
                    map_results.append({
                        "phase": "map",
                        "status": "error",
                        "error": str(exc),
                    })

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    output = future.result(timeout=plan.timeout_seconds)
                    map_results.append({
                        "phase": "map",
                        "agent_id": agent.agent_id,
                        "output": output,
                        "status": "success",
                    })
                except Exception as exc:
                    map_results.append({
                        "phase": "map",
                        "agent_id": agent.agent_id,
                        "status": "error",
                        "error": str(exc),
                    })

        # Reduce phase: single reducer aggregates all map results
        try:
            reducer = runtime.spawn(reducer_class, reducer_config)
            reduce_output = reducer.run(map_results)
            result.agent_results.append({
                "phase": "reduce",
                "agent_id": reducer.agent_id,
                "output": reduce_output,
                "status": "success",
            })
            result.final_result = reduce_output
        except Exception as exc:
            result.agent_results.append({
                "phase": "reduce",
                "status": "error",
                "error": str(exc),
            })
            result.success = False

        result.agent_results.extend(map_results)
        result.rounds_completed = 2  # map + reduce
        result.total_duration_ms = (time.time() - start_time) * 1000
        return result


# ── Strategy Registry ───────────────────────────────────────

STRATEGIES: dict[OrchestrationPattern, type[OrchestrationStrategy]] = {
    OrchestrationPattern.SEQUENTIAL: SequentialStrategy,
    OrchestrationPattern.PARALLEL: ParallelStrategy,
    OrchestrationPattern.HIERARCHICAL: HierarchicalStrategy,
    OrchestrationPattern.DEBATE: DebateStrategy,
    OrchestrationPattern.ROUND_ROBIN: RoundRobinStrategy,
    OrchestrationPattern.MAP_REDUCE: MapReduceStrategy,
}


class MultiAgentOrchestrator:
    """Central orchestrator for multi-agent coordination.

    Manages orchestration plans, selects strategies, executes them,
    and tracks results. Thread-safe with singleton pattern.

    Usage:
        orchestrator = MultiAgentOrchestrator.get_instance()
        plan = OrchestrationPlan(
            pattern=OrchestrationPattern.SEQUENTIAL,
            agent_classes=[AgentA, AgentB],
            agent_configs=[config_a, config_b],
            input_data="Process this",
        )
        result = orchestrator.orchestrate(plan)
    """

    _instance: MultiAgentOrchestrator | None = None
    _lock = threading.Lock()

    def __init__(self, runtime: AgentRuntime | None = None) -> None:
        self._runtime = runtime or AgentRuntime.get_instance()
        self._history: list[OrchestrationResult] = []
        self._history_lock = threading.Lock()
        self._max_history = 100

    @classmethod
    def get_instance(cls, **kwargs: object) -> MultiAgentOrchestrator:
        """Get or create the singleton orchestrator."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            cls._instance = None

    def orchestrate(self, plan: OrchestrationPlan) -> OrchestrationResult:
        """Execute an orchestration plan.

        Args:
            plan: The orchestration plan describing agents, pattern, and input.

        Returns:
            An OrchestrationResult with outputs from all agents.
        """
        strategy_class = STRATEGIES.get(plan.pattern)
        if strategy_class is None:
            return OrchestrationResult(
                plan_id=plan.plan_id,
                pattern=plan.pattern,
                success=False,
                error=f"Unknown pattern: {plan.pattern}",
            )

        strategy = strategy_class()
        logger.info(
            "Orchestrating plan %s with pattern %s (%d agents)",
            plan.plan_id,
            plan.pattern.value,
            len(plan.agent_classes),
        )

        result = strategy.execute(self._runtime, plan)

        with self._history_lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        return result

    def get_history(self, limit: int = 20) -> list[OrchestrationResult]:
        """Get recent orchestration results."""
        with self._history_lock:
            return list(self._history[-limit:])

    def get_stats(self) -> OrchestratorStats:
        """Get orchestrator statistics."""
        with self._history_lock:
            total = len(self._history)
            success = sum(1 for r in self._history if r.success)
            by_pattern: dict[str, int] = {}
            for r in self._history:
                key = r.pattern.value
                by_pattern[key] = by_pattern.get(key, 0) + 1

        return OrchestratorStats(
            total_orchestrations=total,
            successful=success,
            failed=total - success,
            by_pattern=by_pattern,
            avg_duration_ms=(
                sum(r.total_duration_ms for r in self._history) / max(total, 1)
            ),
        )
