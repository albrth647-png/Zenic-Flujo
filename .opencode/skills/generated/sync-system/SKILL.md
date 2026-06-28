---
name: sync-system
description: Data synchronization - cross-device, offline, conflict resolution
load: on-demand
tokens: ~120
---

# Sync System

## Module: `src/sync/` (3 files)
Data synchronization system for multi-device and offline scenarios.

### Key Features
- **Sync Engine**: Bidirectional data sync
- **Conflict Resolution**: Merge strategy for conflicts
- **Offline Queue**: Offline operation queuing
- **Delta Sync**: Incremental synchronization

### Key Files
- `src/sync/engine.py` - Sync engine
- `src/sync/conflicts.py` - Conflict resolution
