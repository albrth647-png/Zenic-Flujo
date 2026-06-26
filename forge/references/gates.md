# 12 Gates de Calidad — Bilingüe (Python + TypeScript)

6 Hard Gates (DEBEN pasar TODOS) + 6 Soft Goals (score ponderado ≥ 8/10).

---

## API

```python
from forge import GateRunner
from forge.gates import SecurityScanner

# Auto-detecta stacks
runner = GateRunner("/ruta/del/proyecto")
report = runner.run_all()
runner.print_report()

# Especificar stacks manualmente
report = runner.run_all(stacks=["python", "typescript"])

# Con sandbox
from forge import ForgeSandbox
with ForgeSandbox("/ruta/del/proyecto") as sb:
    report = runner.run_all(sandbox=sb)
```

### Constructor

```python
GateRunner(project_root: str | Path, sandbox: ForgeSandbox | None = None, max_workers: int = 8)
```

- `project_root`: Raíz del proyecto (busca `src/` para Python, `frontend/src/` para TypeScript)
- `sandbox`: Opcional. Si se provee, ejecuta gates dentro del sandbox
- `max_workers`: Paralelismo (default: 8)

### Métodos

| Método | Descripción |
|--------|-------------|
| `run_all(stacks, sandbox)` | Ejecuta todos los gates en paralelo |
| `evaluate()` | Evalúa resultados (hard gates + soft score) |
| `print_report()` | Imprime reporte formateado |
| `detect_stack(file_path)` | Detecta stack de un archivo (python/typescript) |

### Propiedades

| Propiedad | Descripción |
|-----------|-------------|
| `has_python` | True si existe `src/` |
| `has_typescript` | True si existe `frontend/src/` |

---

## Hard Gates

| # | Gate | Python | TypeScript |
|---|------|--------|------------|
| 1 | `tests_pass` | `pytest -x -q --tb=short src/tests/` | `npx vitest run --reporter=verbose` |
| 2 | `tests_deterministic` | 3 runs pytest (mismo exit code) | 3 runs vitest (mismo exit code) |
| 3 | `no_security_issues` | AST scan: eval, exec, __import__, pickle, subprocess(shell=True), secrets | AST scan: eval, innerHTML, dangerouslySetInnerHTML, document.write, secrets |
| 4 | `no_broken_imports` | `python -c "import sys; sys.path.insert(0, '.'); print('OK')"` | `npx tsc --noEmit` |
| 5 | `no_circular_imports` | AST DFS scan (skip, usa madge para TS) | `npx madge --circular frontend/src/` |
| 6 | `integration_smoke` | `python -c "import sys; sys.path.insert(0, '.'); print('OK')"` | `npx vite build` |

**Regla:** Si un solo hard gate falla, NO hay entrega. Punto.

---

## Soft Goals

| # | Gate | Python | TypeScript | Weight |
|---|------|--------|------------|--------|
| 1 | `coverage_branch >= 85%` | `pytest --cov=src/ --cov-branch` | `vitest --coverage --provider=v8` | 1.0 |
| 2 | `lint_clean` | `ruff check src/` | `npx eslint frontend/src/ --max-warnings=0` | 1.0 |
| 3 | `types_clean` | `mypy --strict src/` | `npx tsc --strict --noEmit` | 1.0 |
| 4 | `mutation_score >= 80%` | `mutmut run` | `npx stryker run` | **2.0** |
| 5 | `complexity_max <= 10` | `radon cc src/ -s -n C` | `npx eslint --rule 'complexity: [error, 10]'` | 1.0 |
| 6 | `test_quality >= 30%` | Ratio test/src files | Ratio test/src files | 1.0 |

**Regla:** Score ponderado = suma(score_i * weight_i) / suma(weight_i). Umbral: 8.0/10.

**Nota:** `mutation_score` tiene weight 2.0 porque es el indicador más confiable de calidad de tests.

---

## SecurityScanner (AST)

Escáner de seguridad vía AST para Python y TypeScript.

```python
from forge.gates import SecurityScanner

# Python
issues = SecurityScanner.scan_python(Path("src/tools/crm/service.py"))

# TypeScript
issues = SecurityScanner.scan_typescript(Path("frontend/src/App.tsx"))
```

### Python: detecta

| Severidad | Patrón |
|-----------|--------|
| **high** | `eval()` — Evaluación dinámica |
| **high** | `exec()` — Ejecución dinámica |
| **high** | `__import__()` — Importación dinámica |
| **high** | `subprocess.*(shell=True)` — Shell injection |
| **high** | Secrets hardcodeados (16+ chars, patrones `API_KEY`, `SECRET`, `TOKEN`, `PASSWORD`) |
| **medium** | `import pickle` — Deserialización insegura |
| **medium** | `import subprocess` — Subprocesos |
| **medium** | `import shutil` — Operaciones de archivo |

### TypeScript: detecta

| Severidad | Patrón |
|-----------|--------|
| **high** | `eval()` — Evaluación dinámica |
| **high** | `innerHTML =` — XSS risk |
| **high** | `dangerouslySetInnerHTML` — XSS risk |
| **high** | `document.write()` — XSS risk |
| **high** | Secrets hardcodeados (16+ chars) |

---

## Stack Detection Automática

```python
runner = GateRunner("/ruta/del/proyecto")

# Auto-detecta
print(runner.has_python)      # True si existe src/
print(runner.has_typescript)  # True si existe frontend/src/

# Por archivo
runner.detect_stack("src/service.py")          # "python"
runner.detect_stack("frontend/src/App.tsx")    # "typescript"
runner.detect_stack("src/main.ts")             # "typescript" (por .ts)
```

Reglas:
- `.py` → python
- `.ts`, `.tsx` → typescript
- `src/` en path → python (default para archivos sin extensión reconocible)
- `frontend/` en path → typescript

---

## Reporte de ejemplo

```
============================================================
  FORGE — GATES REPORT
============================================================

  📊 HARD GATES (6/6)
    ✅ tests_pass                | python       |  12.3s
    ✅ tests_deterministic       | python       |  34.1s
    ✅ no_security_issues        | python       |   3.2s
    ✅ no_broken_imports         | python       |   0.5s
    ✅ no_circular_imports       | python       |   1.1s
    ✅ integration_smoke         | python       |   0.8s

  🎯 SOFT GOALS (score: 9.2/10)
    ✅ coverage_branch           | python       | score= 8.5 |  45.2s
    ✅ lint_clean                | python       | score=10.0 |   2.1s
    ✅ types_clean               | python       | score=10.0 |   8.4s
    ❌ mutation_score            | python       | score= 6.0 | 120.0s
    ✅ complexity_max            | python       | score=10.0 |   1.5s
    ✅ test_quality              | python       | score=10.0 |   0.3s

  🏁 VERDICT: ❌ FAIL
     Hard: PASS | Soft: FAIL (9.2/10)
     Mutation score below threshold: 60.0% < 80.0%

============================================================
```
