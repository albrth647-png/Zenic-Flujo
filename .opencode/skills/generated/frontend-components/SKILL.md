---
name: frontend-components
description: React components - admin, dashboard, editor, UI system, layout, protected routes
load: on-demand
tokens: ~180
---

# Frontend Components

## Directory: `frontend/src/components/`
React component library organized by domain.

### Component Groups
- **ui/**: 22 shadcn-based primitives (button, card, dialog, table, toast, etc.)
- **orbital/**: ORBITAL visualizer, TorMatrix, Cache/Variables/TickHistory/RCC tabs
- **workflows/**: EnvironmentsTab, PromotionDialog
- **admin/**: Admin sub-components
- **dashboard/**: Dashboard cards and panels
- **editor/**: Workflow/content editor components
- **settings/**: Settings panel components

### Shared
- `AppLayout.tsx` - Main app shell with navigation
- `ErrorBoundary.tsx` - React error boundary
- `LazyRoute.tsx` - Code-split route wrapper
- `ProtectedRoute.tsx` - Auth guard
- `StatusBadge.tsx` - Status indicator

### Stack
- React 18 + TypeScript
- shadcn/ui (Radix primitives)
- CSS Modules / Tailwind
