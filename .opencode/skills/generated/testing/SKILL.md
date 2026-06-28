---
name: testing
description: Testing strategy - pytest, vitest, QA gates, coverage
load: on-demand
tokens: ~150
---

# Testing

## Module: `src/tests/` (169 files) + `frontend/__tests__/` (6 files)
Comprehensive testing framework for Python and TypeScript.

### Python Tests
- **Framework**: pytest 9.1.1
- **Coverage**: pytest-cov with branch coverage
- **Mutation Testing**: mutmut 3.6.0
- **Quality**: radon complexity, mypy types
- **Tests**: 169 test files

### TypeScript Tests
- **Framework**: vitest ^2.1.9
- **Coverage**: v8 provider
- **Tests**: 6 test files

### Running Tests
```bash
# Python
pytest src/tests/ -x -q --tb=short

# TypeScript
cd frontend && npx vitest run

# Gates (via forge)
python3 -c "from forge import GateRunner; GateRunner('.').run_all()"
```

### Key Files
- `src/tests/` - All Python tests
- `frontend/src/__tests__/` - All TS tests
- `forge/gates.py` - QA gate runner
