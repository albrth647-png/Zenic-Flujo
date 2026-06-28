---
name: frontend-contexts
description: React contexts - AuthContext, ThemeContext, global state providers
load: on-demand
tokens: ~120
---

# Frontend Contexts

## Directory: `frontend/src/contexts/`
React context providers for global application state.

### Contexts
- **AuthContext** - Authentication state (user, token, permissions)
- **ThemeContext** - Theme mode (light/dark) with ThemeContextValue type

### Architecture
```
App
└─ AuthProvider
   └─ ThemeProvider
      └─ Routes
```

### Usage
```tsx
import { useAuth } from '../contexts/AuthContext'
const { user, login, logout } = useAuth()

import { useTheme } from '../contexts/ThemeContext'
const { theme, toggleTheme } = useTheme()
```

### Key Files
- `AuthContext.tsx` - Auth provider + hook
- `ThemeContext.tsx` - Theme provider + hook
- `ThemeContextValue.ts` - Theme type definition
