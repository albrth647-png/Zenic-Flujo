---
name: frontend-hooks
description: React hooks - 11 custom hooks for API, auth, agents, NLU, BPMN, SSE, pagination
load: on-demand
tokens: ~160
---

# Frontend Hooks

## Directory: `frontend/src/hooks/`
11 custom React hooks for state management and API integration.

### Hooks
- **useAuth** - Authentication state and login/logout
- **useApi** - Generic API client wrapper
- **useAgents** - AI agent management
- **useNlu** - NLU pipeline interface
- **useBpmn** - BPMN workflow operations
- **useTenants** - Multi-tenant management
- **useTheme** - Theme (light/dark) toggling
- **useToast** - Toast notification system
- **useConfirm** - Confirmation dialogs
- **useSSE** - Server-Sent Events streaming
- **usePagination** - Paginated data fetching

### Patterns
- All hooks follow React 18 conventions
- TypeScript strict mode
- Proper cleanup in useEffect returns
- Error handling with try/catch + toast

### Key Files
- `hooks/useAuth.ts` - Auth hook
- `hooks/useApi.ts` - API hook (core)
- `hooks/useSSE.ts` - SSE streaming
