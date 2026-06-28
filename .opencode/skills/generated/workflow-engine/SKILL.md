---
name: workflow-engine
description: Workflow definitions, execution engine, state management, transitions
load: on-demand
tokens: ~160
---

# Workflow Engine

## Module: `src/workflow/` (29 files)
Deterministic workflow engine powering business process automation.

### Key Components
- **WorkflowDefinition**: Schema for workflow creation
- **WorkflowExecutor**: Runtime execution engine
- **StateManager**: Workflow state persistence
- **TransitionEngine**: State transition logic
- **WorkflowValidator**: Pre-execution validation

### Usage
```python
from src.workflow import WorkflowEngine
engine = WorkflowEngine()
result = engine.execute(workflow_id, context)
```

### Key Files
- `src/workflow/engine.py` - Main engine
- `src/workflow/models.py` - Data models
- `src/workflow/executor.py` - Execution logic
