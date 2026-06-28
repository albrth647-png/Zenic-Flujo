---
name: dcl-optimization
description: Dynamic Context Loading optimization for token efficiency
load: on-demand
tokens: ~150
---

# DCL Optimization

## Key Settings
- Compaction: `auto=true, prune=true` in `experimental.compaction`
- Thresholds: `token_threshold=60000, context_threshold=0.60, min_messages=5, reserved=10000`
- Compaction model: `opencode/deepseek-v4-flash-free` (fast + free)

## Memory
- `memory-server` MCP server for persistent RAG across sessions (remember/recall/forget)
- Reduces context reload on session start

## MCP Strategy
- `superpowers` disabled by default (saves ~2-5K tokens/session)
- Enable only when needed for specific tasks

## Token Budget
| Component | Tokens |
|-----------|--------|
| Compaction overhead | ~500 |
| Skills (unloaded) | ~0 |
| Skills (loaded) | ~120-150 each |
| Memory query | ~200 |
| Superpowers (disabled) | ~0 |
