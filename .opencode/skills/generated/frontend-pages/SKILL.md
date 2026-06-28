---
name: frontend-pages
description: React pages - 26 page components, routing, lazy loading
load: on-demand
tokens: ~170
---

# Frontend Pages

## Directory: `frontend/src/pages/`
26 page components covering all application features.

### Pages
- **Dashboard**: Main dashboard
- **Invoices**: Invoice management (Facturación Electrónica)
- **CRM**: Client management
- **Inventory**: Stock control
- **Workflows**: BPMN workflow editor
- **Agents**: AI agent management
- **NLU**: Natural language processing
- **Orbital**: ORBITAL context system
- **Tenants**: Multi-tenant management
- **Compliance**: GDPR/HIPAA dashboard
- **Integrations**: Third-party connectors
- **Deployments**: Deployment management
- **Chat**: Interactive chat
- **Settings**: Application settings
- **Plugins**: Extension management
- **Reports**: Analytics reports
- **Sync/Cloud**: Cloud synchronization
- **Airgap**: Offline mode control
- **Partners**: Partnership management
- **Admin**: Admin panel
- **BPMN**: BPMN diagram editor
- **Editor**: Content editor
- **Mi Negocio**: Business profile
- **Login**: Authentication
- **NotFound**: 404 page

### Routing
- `frontend/src/router/routes.tsx` - Route definitions
- `frontend/src/router/paths.ts` - Path constants
- Lazy loaded via `LazyRoute` component
