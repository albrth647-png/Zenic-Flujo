# Code-Forge Quickstart

> **Tiempo de lectura**: 5 minutos
> **Tiempo de setup**: 10 minutos

---

## ¿Qué es Code-Forge?

Code-Forge es un framework de ingeniería para agentes de IA que implementa un prompting loop de 8 fases con:
- **RunLedger**: registro de auditoría con rollback obligatorio
- **PersistentMemory**: memoria cross-session con búsqueda Jaccard
- **ForgeSandbox**: sandbox dual (filesystem + network + rlimits)
- **GateRunner**: 12 gates de calidad (6 hard + 6 soft) bilingües Python/TypeScript
- **Dashboard**: HTML report con score por módulo y tendencias

---

## 📦 Instalación

### Prerrequisitos
- Python 3.12+
- Node.js 20+ (para gates TypeScript)
- Git

### 1. Clonar el repositorio
```bash
git clone https://github.com/albrth647-png/Zenic-Flujo.git
cd Zenic-Flujo
```

### 2. Instalar dependencias Python
```bash
pip install --break-system-packages ruff mypy radon mutmut pytest-cov pytest-mock pytest-asyncio
pip install -r requirements.txt
```

### 3. Instalar dependencias frontend
```bash
cd frontend && npm install --legacy-peer-deps && cd ..
```

### 4. Verificar que todo está listo
```bash
python -m forge verify --quick
```

**Salida esperada**:
```
======================================================================
  FORGE — GATES REPORT
======================================================================

  📊 HARD GATES (6/6)
    ✅ tests_pass                | python       |   2.2s
    ✅ tests_deterministic       | python       |   3.9s
    ✅ no_security_issues        | python       |   0.0s
    ✅ no_broken_imports         | python       |   0.1s
    ✅ no_circular_imports       | python       |   0.0s
    ✅ integration_smoke         | python       |   0.1s

  🎯 SOFT GOALS (score: 8.5/10)
    ✅ lint_clean                | python       | score=10.0 |   0.5s
    ✅ types_clean               | python       | score= 5.0 |  45.2s
    ...

  🏁 VERDICT: ✅ PASS
```

---

## 🚀 Primeros pasos

### Crear un ledger para tu cambio
```bash
python -m forge ledger init .forge/my-feature --run-id "feature-add-auth"
```

### Ejecutar gates sobre un módulo específico
```bash
python -m forge check-module src/core/
```

### Verificar integridad de un ledger
```bash
python -m forge ledger verify .forge/my-feature/run_ledger.json
```

### Listar todos los ledgers del proyecto
```bash
python -m forge ledger list .
```

### Generar dashboard HTML
```bash
python -m forge dashboard
# Abre reports/dashboard.html en tu navegador
```

---

## 📚 Documentación

| Documento | Descripción |
|---|---|
| [Workflow de desarrollo](workflow.md) | Ciclo completo: forge start → verify → fix → commit |
| [Ejemplo 01: Fix de bug](examples/01-fix-bug-crm.md) | Fix de bug con ciclo completo de 8 fases |
| [Ejemplo 02: Añadir tool](examples/02-add-tool.md) | Añadir una tool N4 paso a paso |
| [Ejemplo 03: Refactor de módulo](examples/03-refactor-module.md) | Refactor con gates y rollback |

### Documentación por fase del rollout
- [Fase 1 — Python Gates](../fase1-rollout.md)
- [Fase 2 — TypeScript Gates](../fase2-rollout.md)
- [Fase 3 — Sandbox](../fase3-rollout.md)
- [Fase 4 — RunLedger](../fase4-rollout.md)
- [Fase 5 — Memory](../fase5-rollout.md)
- [Fase 6 — Homologación por módulo](../fase6-rollout.md) (12 módulos)
- [Fase 7 — CI/CD](../fase7-rollout.md)

### Referencias
- [RunLedger — Campos por tipo de acción](../templates/README.md)
- [Plan de rollout completo](../plan-code-forge-rollout.md)

---

## 🛠️ Comandos CLI disponibles

```bash
python -m forge init                    # Inicializa ledger en directorio actual
python -m forge verify [--quick]        # Corre 12 gates sobre el proyecto
python -m forge check-module <path>     # Gates sobre un módulo específico
python -m forge report [--quick]        # Genera reporte de estado
python -m forge self-test               # Auto-test de gates en directorio temporal
python -m forge dashboard               # Genera dashboard HTML con score por módulo
python -m forge ledger init <path>      # Inicializa ledger en path específico
python -m forge ledger verify <path>    # Verifica integridad de un ledger
python -m forge ledger show <path>      # Muestra resumen de un ledger
python -m forge ledger list [<path>]    # Lista ledgers en .forge/*/
```

---

## ❓ FAQ

### ¿Cuándo usar `--quick`?
`--quick` excluye los gates expensive (`mutation_score` y `coverage_branch`). Úsalo para feedback rápido en desarrollo local. Sin `--quick` para CI/CD completo.

### ¿Qué hacer si un gate falla?
1. Revisa el `evidence` del gate en el reporte
2. Busca reflexiones similares en la memoria: `python -c "from forge import PersistentMemory; m = PersistentMemory('forge/data'); print(m.find_similar('<gate_name> failure'))"`
3. Aplica el fix
4. Re-ejecuta: `python -m forge verify`

### ¿Cómo añadir un nuevo gate?
1. Añade el método `gate_<name>` a `GateRunner` en `forge/gates.py`
2. Añade el nombre a `HARD_GATES` o `SOFT_GOALS`
3. Si es soft, añade su peso a `SOFT_WEIGHTS`
4. Crea tests en `forge/tests/test_gates.py`

### ¿Cómo marcar un falso positivo de seguridad?
Añade el comentario `# forge-ignore-security` en la misma línea del código marcado:
```python
exec(code, context)  # forge-ignore-security: sandbox exec, AST-validated code
```

---

## ➡️ Siguiente paso

Lee el [Workflow de desarrollo](workflow.md) para ver el ciclo completo de un cambio con Code-Forge.
