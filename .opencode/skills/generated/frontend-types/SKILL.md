---
name: frontend-types
description: TypeScript types - 22 type definition files covering all domains
load: on-demand
tokens: ~160
---

# Frontend Types

## Directory: `frontend/src/types/`
22 TypeScript type definition files covering the entire domain model.

### Type Modules
- **auth.ts** - Authentication types
- **workflow.ts** - Workflow engine types
- **bpmn.ts** - BPMN diagram types
- **invoice.ts** - Invoice/fiscal types
- **crm.ts** - CRM types
- **inventory.ts** - Inventory types
- **admin.ts** - Admin panel types
- **agents.ts** - AI agent types
- **nlu.ts** - NLU pipeline types
- **orbital.ts** - ORBITAL context types
- **tenants.ts** - Multi-tenant types
- **compliance.ts** - Compliance types
- **airgap.ts** - Airgap mode types
- **sync.ts** - Sync system types
- **license.ts** - License management types
- **partners.ts** - Partnership types
- **monitoring.ts** - Observability types
- **reports.ts** - Report types
- **theme.ts** - Theme types
- **notifications.ts** - Notification types
- **component-ui.ts** - UI component types
- **versioning.ts** - Versioning types

### Convention
- All types exported as interfaces or type aliases
- Strict null checks
- Consistent naming: `XxxData`, `XxxRequest`, `XxxResponse`
