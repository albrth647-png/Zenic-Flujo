---
name: frontend-orbital-ui
description: ORBITAL visualizer - TorMatrix, RCC, tick history, cache, variables, cycles
load: on-demand
tokens: ~160
---

# Frontend ORBITAL UI

## Directory: `frontend/src/components/orbital/`
Visual interface for the ORBITAL shared context system (13 components).

### Components
- **OrbitalVisualizer** - Main visualization component
- **TorMatrix** - Task-Operation-Result matrix display
- **VariablesTab** / **VariableCard** / **VariableDialog** - Variable management
- **HistoryTab** / **TickHistoryCard** - Time-series tick history
- **CacheTab** - Context cache viewer
- **RccTab** - RCC (Runtime Context Control) tab
- **CycleCard** / **CycleDialog** - Orbital cycle management
- **helpers.ts** - Utility functions for orbital components

### Integration
Connects to ORBITAL API endpoints for real-time context visualization.

### Key Files
- `OrbitalVisualizer.tsx` - Main component
- `TorMatrix.tsx` - TOR matrix viewer
- `TickHistoryCard.tsx` - History timeline
