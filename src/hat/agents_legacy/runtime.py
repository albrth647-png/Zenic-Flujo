"""Agent Runtime — Lifecycle manager for agent instances.

Spawns, monitors, and terminates agents. Manages execution pools,
health checks, and resource limits. Integrates with the orbital context
for agent state synchronization.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from src.core.logging import get_logger
from src.hat.agents_legacy.base import AgentConfig, AgentMessage, AgentState, AgentStatus, BaseAgent

logger = get_logger("agent.runtime")


@dataclass
class RuntimeStats:
    """Aggregate statistics for the agent runtime."""

    total_spawned: int = 0
    total_terminated: int = 0
    total_errors: int = 0
    active_count: int = 0
    peak_active: int = 0
    total_iterations: int = 0


class RuntimeStatus(TypedDict):
    """Estado del runtime (retorno de get_stats())."""
    total_spawned: int
    total_terminated: int
    total_errors: int
    active_count: int
    peak_active: int
    total_iterations: int
    agents_by_state: dict[str, int]


class AgentRuntime:
    """Centralized runtime for managing agent lifecycles.

    Responsibilities:
    - Spawn and register agent instances
    - Monitor agent health (heartbeat checks)
    - Enforce resource limits (max concurrent agents, timeouts)
    - Provide agent discovery and lookup
    - Thread-safe agent registry with lifecycle hooks

    Usage:
        runtime = AgentRuntime.get_instance()
        agent = runtime.spawn(MyAgent, config)
        status = runtime.get_agent_status(agent.agent_id)
        runtime.terminate_agent(agent.agent_id)
    """

    _instance: AgentRuntime | None = None
    _lock = threading.Lock()

    def __init__(self, max_agents: int = 50, heartbeat_interval: float = 30.0) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._agent_lock = threading.Lock()
        self._max_agents = max_agents
        self._heartbeat_interval = heartbeat_interval
        self._stats = RuntimeStats()
        self._hooks: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._running = False
        self._heartbeat_thread: threading.Thread | None = None

    @classmethod
    def get_instance(cls, **kwargs: Any) -> AgentRuntime:  # type: ignore[no-untyped-def]
        """Get or create the singleton AgentRuntime."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    # ── Lifecycle ───────────────────────────────────────────

    def spawn(
        self,
        agent_class: type[BaseAgent],
        config: AgentConfig | None = None,
        parent_id: str | None = None,
    ) -> BaseAgent:
        """Spawn a new agent instance and register it in the runtime.

        Args:
            agent_class: The concrete BaseAgent subclass to instantiate.
            config: Agent configuration. If None, a default is created.
            parent_id: Optional parent agent ID for hierarchy.

        Returns:
            The newly created agent instance.

        Raises:
            RuntimeError: If max agent limit is reached.
        """
        with self._agent_lock:
            if len(self._agents) >= self._max_agents:
                msg = f"Max agent limit reached ({self._max_agents})"
                raise RuntimeError(msg)

            if config is None:
                config = AgentConfig()

            agent = agent_class(config)
            agent._parent_id = parent_id

            # Register parent-child relationship
            if parent_id and parent_id in self._agents:
                self._agents[parent_id]._child_ids.append(agent.agent_id)

            self._agents[agent.agent_id] = agent
            self._stats.total_spawned += 1
            self._stats.active_count = len(self._agents)
            self._stats.peak_active = max(self._stats.peak_active, self._stats.active_count)

            self._fire_hook("on_spawn", agent)
            logger.info("Agent spawned: %s (%s)", agent.name, agent.agent_id)
            return agent

    def terminate_agent(self, agent_id: str, force: bool = False) -> bool:
        """Terminate an agent by ID.

        Args:
            agent_id: The agent to terminate.
            force: If True, force-terminate even if agent is in an active state.

        Returns:
            True if termination was successful.
        """
        with self._agent_lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return False

            if force:
                agent.force_state(AgentState.TERMINATED)
            else:
                if not agent.terminate():
                    logger.warning("Cannot terminate agent %s in state %s", agent_id, agent.state)
                    return False

            # Terminate all children first
            for child_id in list(agent._child_ids):
                self.terminate_agent(child_id, force=True)

            self._fire_hook("on_terminate", agent)
            del self._agents[agent_id]
            self._stats.total_terminated += 1
            self._stats.active_count = len(self._agents)
            logger.info("Agent terminated: %s", agent_id)
            return True

    def pause_agent(self, agent_id: str) -> bool:
        """Pause an active agent."""
        agent = self._agents.get(agent_id)
        if agent and agent.pause():
            self._fire_hook("on_pause", agent)
            return True
        return False

    def resume_agent(self, agent_id: str) -> bool:
        """Resume a paused agent."""
        agent = self._agents.get(agent_id)
        if agent and agent.resume():
            self._fire_hook("on_resume", agent)
            return True
        return False

    # ── Lookup ──────────────────────────────────────────────

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(
        self,
        state: AgentState | None = None,
        capability: str | None = None,
    ) -> list[BaseAgent]:
        """List agents, optionally filtered by state or capability.

        Args:
            state: Filter by agent state.
            capability: Filter by capability name.

        Returns:
            List of matching agents.
        """
        agents = list(self._agents.values())
        if state is not None:
            agents = [a for a in agents if a.state == state]
        if capability is not None:
            agents = [a for a in agents if any(c.value == capability for c in a.capabilities)]
        return agents

    def get_agent_status(self, agent_id: str) -> AgentStatus | None:
        """Get detailed status for an agent."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        return agent.get_status()

    # ── Messaging ───────────────────────────────────────────

    def route_message(self, message: AgentMessage) -> bool:
        """Route a message to the target agent.

        Args:
            message: AgentMessage con recipient_id.

        Returns:
            True if the message was delivered successfully.
        """
        recipient_id = getattr(message, "recipient_id", None)
        if recipient_id is None:
            logger.warning("Message has no recipient_id")
            return False

        agent = self._agents.get(recipient_id)
        if agent is None:
            logger.warning("Recipient agent not found: %s", recipient_id)
            return False

        agent.receive_message(message)
        return True

    def broadcast(self, sender_id: str, content: str | dict | list, message_type: str = "broadcast") -> int:
        """Broadcast a message to all active agents except the sender.

        Returns:
            Number of agents that received the message.
        """
        delivered = 0
        for agent in self._agents.values():
            if agent.agent_id != sender_id and agent.is_active:
                msg = agent.send_message(agent.agent_id, content, message_type)
                agent.receive_message(msg)
                delivered += 1
        return delivered

    # ── Health Monitoring ───────────────────────────────────

    def start_heartbeat(self) -> None:
        """Start the background heartbeat monitor."""
        if self._running:
            return
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="agent-heartbeat"
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat monitor."""
        self._running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        """Background loop checking agent health."""
        while self._running:
            try:
                self._check_agents_health()
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)
            time.sleep(self._heartbeat_interval)

    def _check_agents_health(self) -> None:
        """Check health of all registered agents."""
        now = time.time()
        stale_threshold = 300.0  # 5 minutes

        for agent_id, agent in list(self._agents.items()):
            if agent.state == AgentState.ERROR:
                self._stats.total_errors += 1
                logger.warning("Agent %s in ERROR state", agent_id)

            # Check for stale agents (no activity for threshold)
            if now - agent._last_active > stale_threshold and agent.state not in {
                AgentState.PAUSED,
                AgentState.TERMINATED,
            }:
                logger.warning("Agent %s appears stale (last active %.0fs ago)", agent_id, now - agent._last_active)

    # ── Hooks ───────────────────────────────────────────────

    def register_hook(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a lifecycle hook callback.

        Events: on_spawn, on_terminate, on_pause, on_resume, on_error
        """
        self._hooks[event].append(callback)

    def _fire_hook(self, event: str, agent: BaseAgent) -> None:
        """Fire all registered callbacks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                callback(agent)
            except Exception as exc:
                logger.error("Hook %s error: %s", event, exc)

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> RuntimeStatus:
        """Get runtime statistics."""
        return {
            "total_spawned": self._stats.total_spawned,
            "total_terminated": self._stats.total_terminated,
            "total_errors": self._stats.total_errors,
            "active_count": self._stats.active_count,
            "peak_active": self._stats.peak_active,
            "total_iterations": sum(a._iteration_count for a in self._agents.values()),
            "agents_by_state": self._agents_by_state(),
        }

    def _agents_by_state(self) -> dict[str, int]:
        """Count agents by current state."""
        counts: dict[str, int] = defaultdict(int)
        for agent in self._agents.values():
            counts[agent.state.value] += 1
        return dict(counts)

    def shutdown(self) -> None:
        """Gracefully shut down the runtime and terminate all agents."""
        self.stop_heartbeat()
        for agent_id in list(self._agents.keys()):
            self.terminate_agent(agent_id, force=True)
        logger.info("AgentRuntime shutdown complete")
