# Las 8 Fases del Prompting Loop

El prompting loop de Code-Forge consta de 8 fases. Específicamente diseñado para el stack bilingüe Python + TypeScript de Zenic-Flujo.

## 📚 Fuentes Académicas por Fase

Cada fase está basada en investigación validada empíricamente:

| Fase | Fuente | Concepto |
|------|--------|----------|
| **1. SPECIFY** | SDD (BCMS 2026), EARS notation | Normalización de requisitos en patrones testables |
| **2. PLAN** | DigitalApplied (88% Failure Analysis) | Blast radius previene scope creep (34% de fallos) |
| **3. TASKS** | Google SRE Canary Pattern | Descomposición atómica para aislamiento de fallos |
| **4. IMPLEMENT** | TDAD (arXiv:2603.17973) | Contextual TDD > procedural. AST-scan previo |
| **5. VERIFY** | SRE Gates, Anthropic Sandboxing | 12 gates en paralelo con sandbox dual |
| **6. CRITIQUE** | Reflexion (NeurIPS 2023) | Verbal reinforcement learning, 91% pass@1 |
| **7. FIX** | Aider Architect/Editor (Sep 2024) | Separar razonamiento de edición, SOTA 85% |
| **8. FINAL_VERIFY** | Google SRE, integration testing | Test suite completo con rollback por task |

**Referencia completa:** `forge/references/best-practices.md` — guía DO/DON'T, paradoja TDD, y 7 patrones de fracaso.

---

## Diagrama de flujo

```
SPEC (usuario)
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 1: SPECIFY   (LLM haiku)                  │
│  • EARS notation + data readiness               │
│  • Human checkpoint                             │
│  → spec.md + run_ledger inicial                  │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 2: PLAN      (LLM sonnet)                 │
│  • Stack detection + blast radius               │
│  • Human checkpoint                             │
│  → plan.md                                       │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 3: TASKS     (LLM sonnet)                 │
│  • Atomic tasks + DAG + rollback por task       │
│  • Human checkpoint                             │
│  → tasks.json + ledger por task                  │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 4: IMPLEMENT (LLM sonnet)                  │
│  • Contextual TDD (AST-scan previo)              │
│  • Canary fix application (1 archivo a la vez)   │
│  • Run ledger actualizado                        │
│  → Código modificado + tests                     │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 5: VERIFY    (workflow, sin LLM)           │
│  • 12 gates en paralelo (8 workers)              │
│  • Bilingüe: Python + TypeScript                 │
│  • Sandboxed                                     │
│  → Gate results + score                          │
└─────────────────────────────────────────────────┘
    ↓
    ├── ALL pass → FASE 8                          │
    │                                               │
    └── Fail → ┌─────────────────────────────────┐
               │  FASE 6: CRITIQUE (LLM sonnet)   │
               │  • Reflexión verbal               │
               │  • Top-5 memory (Jaccard)         │
               │  → memory.json actualizado        │
               └─────────────────────────────────┘
                    ↓
               ┌─────────────────────────────────┐
               │  FASE 7: FIX (LLM sonnet)        │
               │  • Architect/Editor pattern       │
               │  • Canary + ledger               │
               │  • Veto rules                     │
               │  → Diffs aplicados                │
               └─────────────────────────────────┘
                    ↓
               ┌─────────────────────────────────┐
               │  (volver a FASE 5)               │
               └─────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│  FASE 8: FINAL_VERIFY (workflow, sin LLM)        │
│  • Test suite COMPLETO Python + TypeScript       │
│  • Rollback por task si falla                   │
│  → Entrega o HALT                               │
└─────────────────────────────────────────────────┘
    ↓
ENTREGA (solo si todos los checks pasan)
```

---

## Fase 1: SPECIFY

**Modelo:** haiku (barato, solo parsea requirements)
**Tipo:** agent
**Human checkpoint:** ✅ Sí
**LLM calls:** 1
**Output:** `spec.md` + `run_ledger.json` inicial

### Acción
1. Recibe SPEC del usuario
2. Verifica data readiness (¿los datos necesarios existen?)
3. Verifica scope (¿es 1 bug o feature atómica? NO scope creep)
4. Verifica rollback possibility (¿se puede deshacer el cambio?)
5. Normaliza a EARS notation (5 patrones testables)
6. Crea `run_ledger.json` con `run_id` + `spec`
7. Human checkpoint

### Production check
```
ANTES de aprobar el spec, verificar:
1. ¿El spec toca 1 bug o feature atómica? (NO scope creep)
2. ¿Los datos necesarios existen y son consistentes?
3. ¿El rollback es posible? (escribir el undo path)
4. ¿Hay tests existentes que puedan verificar el fix?
Si cualquiera falla → NO aprobar, pedir clarificación al humano.
```

---

## Fase 2: PLAN

**Modelo:** sonnet (razonamiento)
**Tipo:** agent
**Human checkpoint:** ✅ Sí
**LLM calls:** 1
**Output:** `plan.md` con stack + blast_radius + dependencias

### Acción
1. Lee `spec.md`
2. Detecta stack de cada target_file (Python/TS/ambos)
3. Calcula blast_radius via project_index (importers)
4. Si blast_radius > 20 → decompose en sub-tasks
5. Identifica archivos a crear/modificar
6. Human checkpoint

### Production check
```
ANTES de aprobar el plan, verificar:
1. Stack detectado: Python (src/), TypeScript (frontend/src/), o ambos
2. Blast radius: cuántos archivos se tocan + cuántos dependen de ellos
3. Si blast_radius > 20 archivos → decompose en sub-tasks atómicas
4. Si toca 2+ archivos no triviales → delegation trigger
```

---

## Fase 3: TASKS

**Modelo:** sonnet
**Tipo:** agent
**Human checkpoint:** ✅ Sí
**LLM calls:** 1
**Output:** `tasks.json` con DAG + `run_ledger` por task

### Acción
1. Descompone en atomic tasks (max 3 archivos por task — canary)
2. Para cada task:
   - Archivos afectados
   - Funciones públicas tocadas (AST-scan)
   - Tests existentes que deben seguir pasando
   - Rollback path explícito
   - Stack de cada archivo
3. Human checkpoint

### Formato de cada task
```json
{
  "id": "task-001",
  "description": "Fix list_leads cuando BD vacía",
  "files": ["src/tools/crm/service.py"],
  "stack": "python",
  "public_functions": ["list_leads"],
  "existing_tests": ["tests/test_crm.py::test_list_leads"],
  "rollback": "git checkout src/tools/crm/service.py",
  "dependencies": []
}
```

---

## Fase 4: IMPLEMENT

**Modelo:** sonnet
**Tipo:** agent + workflow
**Human checkpoint:** ❌ No
**LLM calls:** 1
**Output:** código + tests + `run_ledger` actualizado

### Pre-IMPLEMENT (workflow)
1. Detectar stack de cada target_file
2. AST-scan para identificar funciones públicas
3. Buscar test files existentes (bilingüe)
4. Calcular blast_radius (importers)
5. Inyectar en prompt:
   - Tests que existen y deben seguir pasando
   - Funciones públicas afectadas (contratos)
   - Archivos que importan los afectados

### IMPLEMENT con canary
1. Aplicar fix al PRIMER archivo (orden dependencias bottom-up)
   - Python: models → repositories → services → blueprints → tests
   - TypeScript: types → hooks → components → pages → tests
2. Actualizar `run_ledger` con `before_sha` + `after_sha` + `rollback`
3. Si toca 2+ archivos → delegation trigger (usar writer + review)
4. Tras cada archivo, verificar gates sobre ese archivo solo
5. Si pasa → siguiente archivo. Si falla → rollback + HALT ese task

---

## Fase 5: VERIFY

**Modelo:** none (workflow determinista)
**Tipo:** workflow
**Human checkpoint:** ❌ No
**LLM calls:** 0
**Paralelo:** ✅ Sí (8 workers)
**Sandboxed:** ✅ Sí

### Acción
Ejecuta 12 gates en paralelo. Cada gate detecta stack automáticamente.

Ver `forge/references/gates.md` para la lista completa.

---

## Fase 6: CRITIQUE

**Modelo:** sonnet
**Tipo:** agent
**Human checkpoint:** ❌ No
**LLM calls:** 1
**Input:** failures de VERIFY + diff + top-5 memory
**Output:** reflexión verbal en `memory.json`

### Solo si VERIFY falló

Recibe:
- Failures de VERIFY
- Diff aplicado
- Top-5 reflexiones pasadas de `memory.json` (Jaccard similarity)
- `run_ledger` actualizado

### Reflexión verbal (5 partes)
1. **ANALYZE:** Causa raíz en una oración
2. **WHY DIDN'T IT WORK LAST TIME:** Si ocurrió antes, qué se intentó
3. **HYPOTHESIS:** Cambio específico que lo arreglaría
4. **RISK:** Podría el fix introducir nuevo fallo?
5. **REFLEXION:** Qué aprendí sobre este problema

### Almacenamiento
```python
from forge import PersistentMemory
mem = PersistentMemory("/tmp/workdir")
mem.add_reflection("iter-3", "Summary", "Reflexión verbal...", score=7.5,
    root_cause="Missing __init__.py",
    files_affected=["src/service.py"],
    key_learnings=["Siempre verificar __init__.py antes de importar"])
```

---

## Fase 7: FIX

**Modelo:** sonnet (Architect + Editor)
**Tipo:** agent + workflow
**Human checkpoint:** ❌ No
**LLM calls:** 2
**Output:** unified diffs aplicados + ledger actualizado

### Architect/Editor pattern
**ARQUITECTO** recibe: failures, código afectado, reflexiones → produce diagnóstico + plan
**EDITOR** recibe: plan, archivos afectados → produce unified diff

### Canary application
1. `git stash` (snapshot global)
2. `git apply diff` al PRIMER archivo (canary)
3. Actualizar `run_ledger`: `before_sha`, `after_sha`, `rollback`
4. Verificar gates sobre ese archivo solo
5. Si pasa → siguiente archivo
6. Si falla → `git stash pop` (rollback) + volver a Editor
7. Si todos pasan → verificación conjunta (VERIFY completo)

### Veto rules
- VETO si diff borra un test sin reemplazo
- VETO si diff introduce `*_API_KEY = literal`
- VETO si diff está vacío
- VETO si rollback no es posible (high-risk)

---

## Fase 8: FINAL_VERIFY

**Modelo:** none (workflow determinista)
**Tipo:** workflow
**Human checkpoint:** ❌ No
**LLM calls:** 0
**Sandboxed:** ✅ Sí
**Timeout:** 900s

### Acción
Ejecuta test suite COMPLETO del proyecto:
- Python: `pytest --tb=short src/tests/`
- TypeScript: `npx vitest run --reporter=verbose`

### Si falla
1. Identificar task culpable via `run_ledger` (git blame + before/after sha)
2. Re-ejecutar esa task sola
3. Si tras 2 re-ejecuciones sigue fallando → HALT
4. Actualizar `run_ledger` con `final_status`

---

## HALT Conditions

El proceso se detiene inmediatamente si ocurre cualquiera de estas condiciones:

| # | Condición | Acción |
|---|-----------|--------|
| 1 | 2 PIVOTs consecutivos sin mejorar | HALT |
| 2 | Total budget tokens excedido (2M) | HALT |
| 3 | Score < 5 tras 50% del presupuesto | PIVOT forzado |
| 4 | 3 fallos repetidos consecutivos | HALT |
| 5 | Fase 8 falla tras 2 re-ejecuciones | HALT |
| 6 | `run_ledger` se corrompe | HALT inmediato |
| 7 | Rollback no posible en acción high-risk | HALT |
| 8 | Project_root se modifica fuera de target_files | HALT inmediato |
| 9 | Iteraciones > 30 | Aborta |
| 10 | Cascading creates > 20 (runaway) | Aborta |

### Output de HALT
- Mejor versión + `run_ledger` completo
- Reporte de blockers
- Reflexiones episodic
- Hipótesis de por qué falló
- Recomendación para humano
