---
name: airgap-isolation
description: Airgap mode - offline operation, isolated execution, no external dependencies
load: on-demand
tokens: ~120
---

# Airgap Isolation

## Module: `src/airgap.py`
Airgap mode for fully offline, isolated operation.

### Key Features
- **Offline Mode**: No external network calls
- **Local Execution**: All processing done locally
- **Security Isolation**: No data leaves the system
- **Fallback Logic**: Graceful degradation when offline

### Usage
```python
from src.airgap import AirgapMode
airgap = AirgapMode()
airgap.enable()
# All operations now use local-only resources
```

### Key File
- `src/airgap.py` - Airgap mode implementation
