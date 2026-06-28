---
name: core-infrastructure
description: Config, IoC container, paths, secrets, services, validation
load: on-demand
tokens: ~150
---

# Core Infrastructure

## Module: `src/core/` (74 files)
Foundation layer providing configuration, dependency injection, and system services.

### Key Components
- **Config**: Global configuration management
- **Container**: IoC dependency injection container
- **Paths**: System path constants
- **Secrets**: SESSION_SECRET, LICENSE_SECRET_KEY management
- **Services**: SMTP, Ollama, web config
- **Validation**: Config validation utilities

### Usage
```python
from src.core.config import Config
from src.core.container import Container
cfg = Config()
container = Container(cfg)
```

### Key Files
- `src/core/config/__init__.py` - Main config
- `src/core/container.py` - IoC container
- `src/core/config/secrets.py` - Secrets management
