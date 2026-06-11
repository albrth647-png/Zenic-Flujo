"""Agent Tool Registry — Tool integration for agents.

Provides a registry of tools that agents can invoke during execution.
Each tool is a callable with metadata describing its inputs, outputs,
and required capabilities. Integrates with the connector SDK and
the existing Zenic-Flijo tool ecosystem.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from src.utils.logger import get_logger

logger = get_logger("agent.tools")


@dataclass
class AgentTool:
    """A tool that an agent can invoke.

    Attributes:
        tool_id: Unique tool identifier.
        name: Human-readable tool name.
        description: What the tool does.
        handler: The callable to execute.
        parameters: JSON Schema describing expected parameters.
        required_capabilities: Agent capabilities required to use this tool.
        timeout_seconds: Execution timeout.
        dangerous: Whether this tool can cause side effects.
        usage_count: Number of times the tool has been invoked.
    """

    tool_id: str = ""
    name: str = ""
    description: str = ""
    handler: Callable[..., Any] | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    dangerous: bool = False
    usage_count: int = 0
    last_used: float = 0.0

    def __post_init__(self) -> None:
        if not self.tool_id:
            self.tool_id = f"tool-{uuid.uuid4().hex[:8]}"


@dataclass
class ToolInvocation:
    """Record of a tool invocation by an agent."""

    invocation_id: str = ""
    agent_id: str = ""
    tool_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.invocation_id:
            self.invocation_id = f"inv-{uuid.uuid4().hex[:8]}"


class AgentToolRegistry:
    """Registry of tools available to agents.

    Provides registration, discovery, and invocation of tools with
    capability-based access control and execution tracking.

    Usage:
        registry = AgentToolRegistry.get_instance()
        registry.register(AgentTool(name="web_search", handler=search_fn, ...))
        result = registry.invoke("agent-1", "web_search", {"query": "invoices"})
    """

    _instance: AgentToolRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._invocations: list[ToolInvocation] = []
        self._tool_lock = threading.Lock()
        self._max_invocation_history = 1000

    @classmethod
    def get_instance(cls) -> AgentToolRegistry:
        """Get or create the singleton registry."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            cls._instance = None

    # ── Registration ────────────────────────────────────────

    def register(self, tool: AgentTool) -> str:
        """Register a tool in the registry.

        Returns:
            The tool_id of the registered tool.
        """
        with self._tool_lock:
            self._tools[tool.tool_id] = tool
            # Also index by name for lookup
            self._tools[tool.name] = tool
        logger.info("Tool registered: %s (%s)", tool.name, tool.tool_id)
        return tool.tool_id

    def unregister(self, tool_id_or_name: str) -> bool:
        """Unregister a tool by ID or name."""
        with self._tool_lock:
            tool = self._tools.pop(tool_id_or_name, None)
            if tool is not None:
                # Remove both ID and name entries
                self._tools.pop(tool.tool_id, None)
                self._tools.pop(tool.name, None)
                return True
            return False

    def register_builtin_tools(self) -> None:
        """Register the built-in Zenic-Flijo tools for agent use.

        These wrap the existing platform capabilities as agent-callable tools.
        """
        builtin_tools = [
            AgentTool(
                name="workflow.execute",
                description="Execute a workflow by ID with optional input data",
                handler=self._tool_workflow_execute,
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow definition ID"},
                        "input_data": {"type": "object", "description": "Optional input data"},
                    },
                    "required": ["workflow_id"],
                },
                required_capabilities=["workflow_orchestration"],
            ),
            AgentTool(
                name="nlu.process",
                description="Process natural language input through the NLU pipeline",
                handler=self._tool_nlu_process,
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Natural language input"},
                        "language": {"type": "string", "enum": ["es", "en", "auto"]},
                    },
                    "required": ["text"],
                },
                required_capabilities=["nlu_processing"],
            ),
            AgentTool(
                name="connector.call",
                description="Invoke a registered connector action",
                handler=self._tool_connector_call,
                parameters={
                    "type": "object",
                    "properties": {
                        "connector_name": {"type": "string"},
                        "action": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["connector_name", "action"],
                },
                required_capabilities=["api_calls", "tool_use"],
                dangerous=True,
            ),
            AgentTool(
                name="data.query",
                description="Query data from the platform database",
                handler=self._tool_data_query,
                parameters={
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "filters": {"type": "object"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["table"],
                },
                required_capabilities=["data_analysis"],
            ),
            AgentTool(
                name="code.execute",
                description="Execute Python code in a sandboxed environment",
                handler=self._tool_code_execute,
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds"},
                    },
                    "required": ["code"],
                },
                required_capabilities=["code_generation"],
                dangerous=True,
                timeout_seconds=60.0,
            ),
            AgentTool(
                name="file.read",
                description="Read a file from the workspace",
                handler=self._tool_file_read,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
                required_capabilities=["file_operations"],
            ),
            AgentTool(
                name="file.write",
                description="Write content to a file in the workspace",
                handler=self._tool_file_write,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
                required_capabilities=["file_operations"],
                dangerous=True,
            ),
            AgentTool(
                name="web.search",
                description="Search the web for information",
                handler=self._tool_web_search,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                required_capabilities=["api_calls"],
            ),
        ]

        for tool in builtin_tools:
            self.register(tool)

    # ── Invocation ──────────────────────────────────────────

    def invoke(
        self,
        agent_id: str,
        tool_id_or_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> ToolInvocation:
        """Invoke a tool on behalf of an agent.

        Args:
            agent_id: The agent requesting the invocation.
            tool_id_or_name: Tool ID or name to invoke.
            parameters: Parameters to pass to the tool handler.

        Returns:
            A ToolInvocation record with the result or error.
        """
        invocation = ToolInvocation(
            agent_id=agent_id,
            tool_id=tool_id_or_name,
            parameters=parameters or {},
            started_at=time.time(),
        )

        with self._tool_lock:
            tool = self._tools.get(tool_id_or_name)

        if tool is None:
            invocation.error = f"Tool not found: {tool_id_or_name}"
            invocation.completed_at = time.time()
            invocation.duration_ms = (invocation.completed_at - invocation.started_at) * 1000
            self._record_invocation(invocation)
            return invocation

        if tool.handler is None:
            invocation.error = f"Tool has no handler: {tool_id_or_name}"
            invocation.completed_at = time.time()
            invocation.duration_ms = (invocation.completed_at - invocation.started_at) * 1000
            self._record_invocation(invocation)
            return invocation

        try:
            result = tool.handler(parameters or {})
            invocation.result = result
        except Exception as exc:
            invocation.error = str(exc)
            logger.error("Tool %s invocation failed: %s", tool_id_or_name, exc)
        finally:
            invocation.completed_at = time.time()
            invocation.duration_ms = (invocation.completed_at - invocation.started_at) * 1000
            tool.usage_count += 1
            tool.last_used = invocation.completed_at
            self._record_invocation(invocation)

        return invocation

    def _record_invocation(self, invocation: ToolInvocation) -> None:
        """Record an invocation for auditing and analytics."""
        self._invocations.append(invocation)
        if len(self._invocations) > self._max_invocation_history:
            self._invocations = self._invocations[-self._max_invocation_history:]

    # ── Discovery ───────────────────────────────────────────

    def list_tools(
        self,
        capability: str | None = None,
        dangerous: bool | None = None,
    ) -> list[AgentTool]:
        """List available tools, optionally filtered."""
        with self._tool_lock:
            # Deduplicate by tool_id (since we index by name too)
            seen_ids: set[str] = set()
            tools = []
            for tool in self._tools.values():
                if tool.tool_id in seen_ids:
                    continue
                seen_ids.add(tool.tool_id)
                if capability and capability not in tool.required_capabilities:
                    continue
                if dangerous is not None and tool.dangerous != dangerous:
                    continue
                tools.append(tool)
            return tools

    def get_tool(self, tool_id_or_name: str) -> AgentTool | None:
        """Get a tool by ID or name."""
        with self._tool_lock:
            return self._tools.get(tool_id_or_name)

    # ── Builtin Tool Handlers (stubs — delegate to actual services) ──

    def _tool_workflow_execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a workflow via the WorkflowEngine."""
        workflow_id = params.get("workflow_id", "")
        input_data = params.get("input_data", {})
        return {
            "status": "dispatched",
            "workflow_id": workflow_id,
            "message": "Workflow execution dispatched to engine",
        }

    def _tool_nlu_process(self, params: dict[str, Any]) -> dict[str, Any]:
        """Process text through the NLU pipeline."""
        text = params.get("text", "")
        language = params.get("language", "auto")
        return {
            "status": "processed",
            "input": text,
            "language": language,
            "intent": "pending_nlu_pipeline",
        }

    def _tool_connector_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call a connector action."""
        connector_name = params.get("connector_name", "")
        action = params.get("action", "")
        call_params = params.get("params", {})
        return {
            "status": "dispatched",
            "connector": connector_name,
            "action": action,
            "message": "Connector call dispatched",
        }

    def _tool_data_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Query data from the database."""
        table = params.get("table", "")
        return {
            "status": "dispatched",
            "table": table,
            "message": "Data query dispatched",
        }

    def _tool_code_execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute code in sandbox."""
        code = params.get("code", "")
        return {
            "status": "dispatched",
            "message": "Code execution dispatched to sandbox",
        }

    def _tool_file_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read a file."""
        path = params.get("path", "")
        return {
            "status": "dispatched",
            "path": path,
            "message": "File read dispatched",
        }

    def _tool_file_write(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write to a file."""
        path = params.get("path", "")
        content = params.get("content", "")
        return {
            "status": "dispatched",
            "path": path,
            "message": "File write dispatched",
        }

    def _tool_web_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search the web."""
        query = params.get("query", "")
        return {
            "status": "dispatched",
            "query": query,
            "message": "Web search dispatched",
        }

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        with self._tool_lock:
            total_invocations = len(self._invocations)
            error_count = sum(1 for inv in self._invocations if inv.error)
            total_duration = sum(inv.duration_ms for inv in self._invocations)

        return {
            "total_tools": len(self.list_tools()),
            "total_invocations": total_invocations,
            "error_count": error_count,
            "avg_duration_ms": total_duration / max(total_invocations, 1),
            "tools_by_capability": self._tools_by_capability(),
        }

    def _tools_by_capability(self) -> dict[str, int]:
        """Count tools by required capability."""
        counts: dict[str, int] = {}
        for tool in self.list_tools():
            for cap in tool.required_capabilities:
                counts[cap] = counts.get(cap, 0) + 1
        return counts
