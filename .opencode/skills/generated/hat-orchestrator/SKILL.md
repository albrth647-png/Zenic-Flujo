---
name: hat-orchestrator
description: HATRouter, FSM Orbital, RCC routing, Anti-Dedup, Intent Hasher - core orchestration
load: on-demand
tokens: ~180
---

# HAT Orchestrator

## Module: `src/hat/` (151 files)
Core orchestration layer of the HAT-ORBITAL architecture.

### Key Components
- **HATRouter**: Main FSM orchestrator, entry point N0
- **FSM Orbital**: Finite State Machine with orbital context
- **RCC**: Routing, Control, Circulation
- **Anti-Dedup**: Anti-duplication system
- **Intent Hasher**: Intent routing and hashing

### Architecture Level
N0 - Orchestrator layer. Single entry point for all requests.

### Usage
```python
from src.hat import HATRouter
router = HATRouter()
response = router.route(intent, context)
```

### Key Files
- `src/hat/router.py` - Main router
- `src/hat/fsm/` - FSM implementation
- `src/hat/rcc/` - RCC system
- `src/hat/antidup/` - Anti-duplication
- `src/hat/intent/` - Intent processing
