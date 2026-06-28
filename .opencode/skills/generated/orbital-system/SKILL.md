---
name: orbital-system
description: ORBITAL context system - shared context, variables, tick history, TOR matrix
load: on-demand
tokens: ~150
---

# Orbital System

## Module: `src/orbital/` (20 files)
ORBITAL shared context system that crosses all architecture levels.

### Key Components
- **OrbitalContext**: Singleton shared context
- **Variable Manager**: Orbital variable storage
- **Tick History**: Time-series event recording
- **TOR Matrix**: Task-Operation-Result tracking
- **Cycle Manager**: Orbital cycle orchestration

### Architecture
ORBITAL is a cross-cutting context layer used by ALL levels (N0-N4).

### Usage
```python
from src.orbital import OrbitalContext
ctx = OrbitalContext()
ctx.set("current_invoice", invoice_data)
history = ctx.get_tick_history()
```

### Key Files
- `src/orbital/context.py` - Main context
- `src/orbital/variables.py` - Variable management
- `src/orbital/tor.py` - TOR matrix
