"""Agent API Routes — REST endpoints for the Agent Framework.

Provides HTTP API for:
- Agent lifecycle management (spawn, pause, resume, terminate)
- Agent execution (run with input data)
- Agent messaging (send, broadcast)
- Multi-agent orchestration
- Token/cost tracking analytics
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.agents.base import AgentCapability, AgentConfig, AgentState, BaseAgent
from src.agents.orchestrator import (
    MultiAgentOrchestrator,
    OrchestrationPattern,
    OrchestrationPlan,
)
from src.agents.runtime import AgentRuntime
from src.agents.token_tracking import TokenCostTracker
from src.api_v2.dependencies import require_permission

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Simple concrete agent for API-driven usage ──────────────


class APIAgent(BaseAgent):
    """Generic agent for API-driven execution.

    Accepts think/act functions via config for maximum flexibility.
    """

    def think(self, observation: Any) -> Any:
        think_fn = self.config.custom_config.get("think_fn")
        if think_fn:
            return think_fn(observation)
        return {"observation": observation, "decision": "proceed"}

    def act(self, decision: Any) -> Any:
        act_fn = self.config.custom_config.get("act_fn")
        if act_fn:
            return act_fn(decision)
        return {"decision": decision, "result": "completed", "done": True}


# ── Agent Lifecycle ─────────────────────────────────────────


@router.post("/spawn", summary="Spawn a new agent")
async def spawn_agent(
    config: AgentConfig,
    _: Any = Depends(require_permission("agents", "create")),
) -> dict[str, Any]:
    """Spawn a new agent with the given configuration."""
    runtime = AgentRuntime.get_instance()
    try:
        agent = runtime.spawn(APIAgent, config)
        return agent.get_status()
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/list", summary="List active agents")
async def list_agents(
    state: str | None = Query(None, description="Filter by state"),
    capability: str | None = Query(None, description="Filter by capability"),
    _: Any = Depends(require_permission("agents", "read")),
) -> dict[str, Any]:
    """List active agents with optional filters."""
    runtime = AgentRuntime.get_instance()
    agent_state = AgentState(state) if state else None
    agents = runtime.list_agents(state=agent_state, capability=capability)
    return {
        "agents": [a.get_status() for a in agents],
        "count": len(agents),
    }


@router.get("/{agent_id}", summary="Get agent status")
async def get_agent_status(
    agent_id: str,
    _: Any = Depends(require_permission("agents", "read")),
) -> dict[str, Any]:
    """Get detailed status for a specific agent."""
    runtime = AgentRuntime.get_instance()
    status = runtime.get_agent_status(agent_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return status


@router.post("/{agent_id}/run", summary="Execute an agent")
async def run_agent(
    agent_id: str,
    input_data: dict[str, Any] | None = None,
    _: Any = Depends(require_permission("agents", "execute")),
) -> dict[str, Any]:
    """Run an agent with the given input data."""
    runtime = AgentRuntime.get_instance()
    agent = runtime.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    if not agent.is_active:
        raise HTTPException(status_code=400, detail=f"Agent not active: {agent.state.value}")

    result = agent.run(input_data)
    return {"agent_id": agent_id, "result": result, "status": agent.get_status()}


@router.post("/{agent_id}/pause", summary="Pause an agent")
async def pause_agent(
    agent_id: str,
    _: Any = Depends(require_permission("agents", "update")),
) -> dict[str, Any]:
    """Pause a running agent."""
    runtime = AgentRuntime.get_instance()
    success = runtime.pause_agent(agent_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause agent")
    return {"agent_id": agent_id, "status": "paused"}


@router.post("/{agent_id}/resume", summary="Resume a paused agent")
async def resume_agent(
    agent_id: str,
    _: Any = Depends(require_permission("agents", "update")),
) -> dict[str, Any]:
    """Resume a paused agent."""
    runtime = AgentRuntime.get_instance()
    success = runtime.resume_agent(agent_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume agent")
    return {"agent_id": agent_id, "status": "resumed"}


@router.delete("/{agent_id}", summary="Terminate an agent")
async def terminate_agent(
    agent_id: str,
    force: bool = Query(False, description="Force termination"),
    _: Any = Depends(require_permission("agents", "delete")),
) -> dict[str, Any]:
    """Terminate an agent."""
    runtime = AgentRuntime.get_instance()
    success = runtime.terminate_agent(agent_id, force=force)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot terminate agent")
    return {"agent_id": agent_id, "status": "terminated"}


# ── Multi-Agent Orchestration ───────────────────────────────


@router.post("/orchestrate", summary="Orchestrate multi-agent execution")
async def orchestrate_agents(
    plan: OrchestrationPlan,
    _: Any = Depends(require_permission("agents", "execute")),
) -> dict[str, Any]:
    """Execute a multi-agent orchestration plan."""
    orchestrator = MultiAgentOrchestrator.get_instance()
    result = orchestrator.orchestrate(plan)
    return {
        "plan_id": result.plan_id,
        "pattern": result.pattern.value,
        "final_result": result.final_result,
        "agent_results": result.agent_results,
        "total_duration_ms": result.total_duration_ms,
        "rounds_completed": result.rounds_completed,
        "success": result.success,
        "error": result.error,
    }


# ── Runtime Stats ───────────────────────────────────────────


@router.get("/runtime/stats", summary="Get runtime statistics")
async def get_runtime_stats(
    _: Any = Depends(require_permission("agents", "read")),
) -> dict[str, Any]:
    """Get agent runtime statistics."""
    runtime = AgentRuntime.get_instance()
    return runtime.get_stats()


# ── Token/Cost Tracking ─────────────────────────────────────


@router.get("/token-usage/summary", summary="Get token usage summary")
async def get_token_usage_summary(
    tenant_id: str = Query("default"),
    _: Any = Depends(require_permission("agents", "read")),
) -> dict[str, Any]:
    """Get token usage and cost summary for a tenant."""
    tracker = TokenCostTracker.get_instance()
    return tracker.get_usage_summary(tenant_id=tenant_id)


@router.get("/token-usage/daily", summary="Get daily token usage")
async def get_daily_token_usage(
    tenant_id: str = Query("default"),
    days: int = Query(30, description="Number of days"),
    _: Any = Depends(require_permission("agents", "read")),
) -> list[dict[str, Any]]:
    """Get daily token usage for the last N days."""
    tracker = TokenCostTracker.get_instance()
    return tracker.get_daily_usage(tenant_id=tenant_id, days=days)


@router.post("/token-usage/budget", summary="Set token usage budget")
async def set_token_budget(
    tenant_id: str,
    daily_limit: float | None = None,
    monthly_limit: float | None = None,
    total_limit: float | None = None,
    _: Any = Depends(require_permission("agents", "manage")),
) -> dict[str, Any]:
    """Set budget limits for a tenant."""
    tracker = TokenCostTracker.get_instance()
    tracker.set_budget(
        tenant_id=tenant_id,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        total_limit=total_limit,
    )
    return {"status": "budget_set", "tenant_id": tenant_id}
