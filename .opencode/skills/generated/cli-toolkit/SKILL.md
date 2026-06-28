---
name: cli-toolkit
description: CLI commands - init, info, list, publish, test, validate, version, parser, sandbox
load: on-demand
tokens: ~140
---

# CLI Toolkit

## Module: `src/cli/` (16 files)
Command-line interface for Zenic-Flujo management and operations.

### Commands
- `init` - Project initialization
- `info` - System information
- `list` - Resource listing
- `publish` - Publish workflows
- `test` - Run tests
- `validate` - Validate configurations
- `version` - Version info
- `parser` - Parse commands

### Usage
```bash
zenic-cli init my-project
zenic-cli validate workflow.yaml
zenic-cli publish workflow-id
```

### Key Files
- `src/cli/main.py` - CLI entry point
- `src/cli/commands/` - Command implementations
- `src/cli/sandbox.py` - Sandbox mode
