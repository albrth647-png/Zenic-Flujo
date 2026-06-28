---
name: agents-ai
description: AI agents - base agent, memory, orchestrator, runtime, token tracking, tools
load: on-demand
tokens: ~150
---

# AI Agents

## Module: `src/agents/` (7 files)
AI agent framework for autonomous task execution.

### Key Components
- **Base Agent**: Abstract agent class
- **Memory**: Agent memory management
- **Orchestrator**: Multi-agent coordination
- **Runtime**: Agent execution runtime
- **Token Tracking**: Token usage monitoring
- **Tools**: Agent tool definitions

### Usage
```python
from src.agents import AgentOrchestrator
orc = AgentOrchestrator()
result = orc.run_task("generate_invoice_report", params={...})
```

### Key Files
- `src/agents/base.py` - Base agent class
- `src/agents/orchestrator.py` - Agent orchestrator
- `src/agents/memory.py` - Agent memory
- `src/agents/token_tracking.py` - Token tracking
