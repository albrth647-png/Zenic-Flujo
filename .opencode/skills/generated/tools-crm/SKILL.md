---
name: tools-crm
description: CRM tools - leads, clients, opportunities, pipeline management
load: on-demand
tokens: ~150
---

# CRM Tools

## Module: `src/tools/crm/`
Customer Relationship Management tools for sales pipeline.

### Key Features
- **Lead Management**: Create, qualify, track leads
- **Client Management**: Client profiles and history
- **Opportunity Pipeline**: Deal stages and forecasting
- **Activity Tracking**: Calls, emails, meetings logging

### Usage
```python
from src.tools.crm import CrmTool
crm = CrmTool()
lead = crm.create_lead(name="Empresa X", source="web")
```

### Key Files
- `src/tools/crm/leads.py` - Lead operations
- `src/tools/crm/clients.py` - Client management
- `src/tools/crm/pipeline.py` - Pipeline stages
