"""Zenic-Flijo Agent Framework — Phase 3.

Provides a complete agent framework with:
- BaseAgent: Abstract base for all agents
- AgentRuntime: Lifecycle management (spawn, pause, resume, terminate)
- AgentMemory: Short-term + long-term memory with vector similarity
- AgentTools: Tool integration with orbital context
- MultiAgentOrchestrator: Multi-agent coordination patterns
"""

from src.agents.base import AgentCapability, AgentState, BaseAgent
from src.agents.memory import AgentMemory, MemoryEntry
from src.agents.orchestrator import MultiAgentOrchestrator, OrchestrationPattern
from src.agents.runtime import AgentRuntime
from src.agents.tools import AgentToolRegistry

__all__ = [
    "AgentCapability",
    "AgentMemory",
    "AgentRuntime",
    "AgentState",
    "AgentToolRegistry",
    "BaseAgent",
    "MemoryEntry",
    "MultiAgentOrchestrator",
    "OrchestrationPattern",
]
