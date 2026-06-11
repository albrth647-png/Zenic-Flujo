"""Zenic-Flijo Agent Framework — Phase 3.

Provides a complete agent framework with:
- BaseAgent: Abstract base for all agents
- AgentRuntime: Lifecycle management (spawn, pause, resume, terminate)
- AgentMemory: Short-term + long-term memory with vector similarity
- AgentTools: Tool integration with orbital context
- MultiAgentOrchestrator: Multi-agent coordination patterns
"""

from src.agents.base import BaseAgent, AgentState, AgentCapability
from src.agents.runtime import AgentRuntime
from src.agents.memory import AgentMemory, MemoryEntry
from src.agents.tools import AgentToolRegistry
from src.agents.orchestrator import MultiAgentOrchestrator, OrchestrationPattern

__all__ = [
    "BaseAgent",
    "AgentState",
    "AgentCapability",
    "AgentRuntime",
    "AgentMemory",
    "MemoryEntry",
    "AgentToolRegistry",
    "MultiAgentOrchestrator",
    "OrchestrationPattern",
]
