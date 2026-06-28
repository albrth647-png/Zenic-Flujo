---
name: sdk-development
description: SDK for building on Zenic-Flujo - client lib, API wrapper, extension API
load: on-demand
tokens: ~150
---

# SDK Development

## Module: `src/sdk/` (32 files)
Software Development Kit for building extensions and integrations on Zenic-Flujo.

### Key Components
- **Client Library**: HTTP client for Zenic-Flujo API
- **API Wrapper**: High-level Python API
- **Extension API**: Plugin/extension system
- **Webhook Handler**: Incoming webhook processing
- **Auth Helper**: SDK authentication

### Usage
```python
from src.sdk import ZenicClient
client = ZenicClient(api_key="sk-...", tenant="my-tenant")
invoices = client.invoices.list(status="pending")
```

### Key Files
- `src/sdk/client.py` - Main client
- `src/sdk/api.py` - API wrapper
- `src/sdk/extensions.py` - Extension system
