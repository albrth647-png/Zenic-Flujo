---
name: api-v2
description: API REST v2 with routers for agents, auth, bpmn, compliance, crm, fiscal, inventory, marketplace, nlu, whatsapp, workflows
load: on-demand
tokens: ~170
---

# API v2

## Module: `src/api_v2/` (20 files)
REST API version 2 with domain-specific routers.

### Routers
- `agents.py` - Agent management
- `auth_routes.py` - Authentication
- `bpmn.py` - BPMN process modeling
- `compliance.py` - Compliance operations
- `connectors.py` - External connectors
- `crm.py` - CRM endpoints
- `fiscal.py` - Fiscal/Invoice endpoints
- `inventory.py` - Inventory management
- `invoices_v2.py` - Invoice v2
- `marketplace.py` - Marketplace
- `nlu.py` - NLU processing
- `tenants.py` - Multi-tenant
- `whatsapp.py` - WhatsApp integration
- `workflows.py` - Workflow execution

### Key Files
- `src/api_v2/app.py` - Main Flask app
- `src/api_v2/auth.py` - Auth handlers
- `src/api_v2/routers/` - All routers
