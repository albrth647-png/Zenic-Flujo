---
name: frontend-testing
description: Frontend tests - vitest, React Testing Library, test utilities
load: on-demand
tokens: ~120
---

# Frontend Testing

## Files: `frontend/src/__tests__/` (6 files) + `frontend/src/test/`
TypeScript/React testing with vitest.

### Stack
- **vitest** ^2.1.9 with v8 coverage
- **React Testing Library** for component tests
- jsdom environment

### Running Tests
```bash
cd frontend
npx vitest run
npx vitest run --coverage
```

### Test Files
- `src/__tests__/` - Main test suite
- `src/test/` - Test utilities and setup
- `vitest.config.ts` - Vitest configuration

### Coverage Targets
- Unit tests for hooks and utils
- Component rendering tests
- Page integration tests
