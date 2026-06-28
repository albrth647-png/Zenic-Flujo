---
name: tenant-multitenant
description: Multi-tenancy - tenant isolation, onboarding, configuration per tenant
load: on-demand
tokens: ~130
---

# Tenant / Multitenant

## Module: `src/tenant/` (9 files)
Multi-tenancy infrastructure for isolated customer deployments.

### Key Features
- **Tenant Isolation**: Data separation per tenant
- **Onboarding Flow**: New tenant provisioning
- **Tenant Config**: Per-tenant configuration
- **Rate Limiting**: Per-tenant API limits
- **Tenant Switching**: Context-aware routing

### Usage
```python
from src.tenant import TenantManager
tm = TenantManager()
tenant = tm.create_tenant(name="Empresa X", plan="enterprise")
config = tm.get_config(tenant_id)
```

### Key Files
- `src/tenant/manager.py` - Tenant management
- `src/tenant/isolation.py` - Isolation logic
- `src/tenant/config.py` - Tenant config
