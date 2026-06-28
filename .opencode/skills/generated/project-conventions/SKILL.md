---
name: project-conventions
description: Project conventions and patterns for Zenic-Flujo OpenCode setup
load: on-demand
tokens: ~120
---

# Project Conventions - Zenic-Flujo

## OpenCode Config
- Config file: `~/.config/opencode/opencode.jsonc`
- Plugin: `oh-my-openagent` (swarm removed)
- MCP: `superpowers` (disabled by default, enable on demand)
- Compaction: `prune=true, auto=true, model=deepseek-v4-flash-free`

## Codebase
- Working directory: `/root/Zenic-Flujo`
- Plans stored in: `.omo/plans/`
- Backups stored in: `.omo/backups/`

## Skills Loading
- All project skills use `load: on-demand` frontmatter
- Explicitly invoke by name when needed
- Never auto-load at session start
