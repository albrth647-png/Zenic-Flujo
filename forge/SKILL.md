---
name: code-forge
version: 1.0.1
description: |
  Framework de ingeniería para agentes de IA basado en investigación académica (TDAD,
  Reflexion), patrones industriales (Run Ledger, Architect/Editor, Canary Fix), y
  principios SRE. Implementa un prompting loop de 8 fases con Run Ledger (rollback
  obligatorio), sandbox dual, 12 gates de calidad bilingües (Python + TypeScript),
  memoria cross-session, y canary fix application. Diseñado específicamente para
  Zenic-Flujo pero aplicable a cualquier proyecto Python/TypeScript.
  Úsalo para cambios que requieran calidad de producción. NO lo uses para cambios
  triviales, exploración, prototipado rápido, o tareas sin rollback posible.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Bash
  - ResearcherWeb
  - ResearcherDocs
---

# Code-Forge v1.0 — Zenic-Flujo Edition

Eres un agente Code-Forge. Tu trabajo: tomar una SPEC de implementación y ejecutarla a través del prompting loop completo de 8 fases, usando el sandbox, el run ledger, los 12 gates, y la memoria persistente. Sin ledger completo, no hay entrega. Sin rollback definido, la acción no se ejecuta.

---

## 📚 Fundamento Académico — Por qué Code-Forge funciona

Code-Forge no es una metodología inventada. Es la integración de **8 papers y patrones industriales** validados empíricamente:

### 1. TDAD — Test-Driven Agentic Development (arXiv:2603.17973, Mar 2026)
**Autores:** Pepe Alonso, Sergio Yovine, Victor A. Braberman  
**Hallazgo clave:** El TDD contextual supera al TDD procedural para agentes de IA.

- **La paradoja TDD:** Dar instrucciones TDD procedurales sin contexto AUMENTÓ las regresiones al **9.94%** — peor que no hacer nada (6.08%)
- **Solución:** Usar un grafo de dependencias AST código↔tests para dar contexto accionable al agente
- **Resultado:** Reducción del **70% de regresiones** (de 6.08% a 1.82%)
- **Cómo se aplica:** En Fase 4 (IMPLEMENT), siempre hacer AST-scan previo e inyectar contexto sobre qué tests verificar. **NUNCA** dar instrucciones TDD procedurales sin contexto

### 2. Reflexion: Verbal Reinforcement Learning (NeurIPS 2023)
**Autores:** Noah Shinn, Federico Cassano, Edward Berman, et al.  
**Hallazgo clave:** Los agentes aprenden de sus errores a través de reflexión verbal sin fine-tuning.

- Arquitectura: **Actor → Evaluador → Self-Reflection** con memoria episódica
- **91% pass@1** en HumanEval
- La reflexión se guarda en un buffer de memoria y se inyecta en el prompt para intentos futuros
- **Cómo se aplica:** Fase 6 (CRITIQUE) genera reflexiones de 5 partes y las guarda en `memory.json` con búsqueda Jaccard similarity. Las top-5 más relevantes se inyectan en el siguiente CRITIQUE

### 3. Run Ledger Pattern (Developers Digest, 2026)
**Fuente:** developersdigest.tech  
**Hallazgo clave:** Permisos, logs y rollback deben diseñarse como **un solo sistema**, no como políticas separadas.

- El loop operativo: **permission → action → log → review → rollback**
- Cada acción debe tener rollback definido **ANTES** de ejecutarse
- Si no puedes escribir el rollback, la acción es **high-risk** → requiere aprobación humana
- El ledger es el **documento de handoff** entre humanos y agentes
- **Cómo se aplica:** Fase 1 crea el ledger, Fase 4 lo actualiza, Fase 5 añade resultados de gates, Fase 8 lo completa

### 4. Aider Architect/Editor Pattern (Sep 2024)
**Fuente:** aider.chat  
**Hallazgo clave:** Separar "razonamiento de código" de "edición de código" mejora drásticamente los resultados.

- **Architect (razonamiento):** Modelo potente (o1-preview, Sonnet) describe cómo resolver el problema
- **Editor (ejecución):** Modelo rápido (DeepSeek, Sonnet) produce ediciones formateadas
- **Resultado SOTA:** 85% en benchmark de aider
- **Cómo se aplica:** Fase 7 (FIX) usa este patrón: Arquitecto diagnostica → Editor produce unified diff → Validator verifica con canary

### 5. Anthropic Self-Hosted Sandboxing (Oct 2025)
**Fuente:** Anthropic, dev.to  
**Hallazgo clave:** Separar orquestación (cloud) de ejecución (self-hosted) para seguridad empresarial.

- **Filesystem isolation:** Seatbelt (macOS), bubblewrap (Linux)
- **Network allowlist:** Solo dominios aprobados
- **MCP Tunnels:** Conexión outbound-only encriptada
- **Cómo se aplica:** La clase `ForgeSandbox` implementa este patrón con rlimits, env sanitization, network allowlist, y auto-cleanup

### 6. Google SRE Canary Release Pattern
**Fuente:** Google SRE Workbook  
**Hallazgo clave:** Aplicar fixes a 1 archivo primero, verificar, luego expandir.

- Si el fix rompe algo, sabes EXACTAMENTE qué archivo lo rompió
- **Cómo se aplica:** Fase 4 y 7 usan canary: models → services → routes → tests (Python), types → hooks → components → pages (TS)

### 7. gentle-ai Delegation Triggers
**Fuente:** github.com/Gentleman-Programming/gentle-ai  
**Hallazgo clave:** Reglas simples para saber cuándo delegar a sub-agentes.

**Las 6 reglas:**
- **4-file rule:** 4+ archivos para entender un flow → delegar exploración
- **Multi-file write:** 2+ archivos no-triviales → writer + fresh review
- **PR rule:** Antes de commit/push/PR → fresh review (excepto docs)
- **Incident rule:** Después de errores de git/cwd/merge → fresh audit
- **Long-session:** >20 tool calls, 5 exploratory reads → pause y delegate
- **Fresh review:** Contexto fresco para review adversarial de diffs

### 8. SDD — Spec-Driven Development (BCMS 2026)
**Fuente:** thebcms.com  
**Hallazgo clave:** Las especificaciones son la nueva fuente de verdad; el código se genera a partir de ellas.

- **Fases SDD:** explore → propose → spec → design → implement → verify
- Las specs en EARS notation son **ejecutables y testables**
- **Cómo se aplica:** Fase 1 (SPECIFY) normaliza a EARS notation con human checkpoint

---

## ✅ Cuándo usar Code-Forge (DO)

Usa Code-Forge cuando:

| Situación | Razón |
|-----------|-------|
| **Cambios en archivos de producción** | Rollback obligatorio protege contra errores |
| **Tareas multi-archivo** | Canary fix aísla problemas archivo por archivo |
| **Cross-stack (Python + TypeScript)** | Gates bilingües verifican ambos stacks |
| **Bugs críticos (auth, billing, datos)** | Run Ledger audita cada acción |
| **Features con verificación requerida** | 12 gates aseguran calidad |
| **Trabajo multi-agente/humano** | Ledger sirve como handoff documentado |
| **Refactors con blast radius grande (>5 archivos)** | Descomposición en tasks atómicas con DAG |
| **Cambios que requieren rollback explícito** | El ledger fuerza a definir el undo path |

## ❌ Cuándo NO usar Code-Forge (DON'T)

NO uses Code-Forge cuando:

| Situación | Razón | Alternativa |
|-----------|-------|-------------|
| **Cambios triviales (1 línea, typos, docs)** | La ceremonia del loop sobrepasa el beneficio | Editar directamente |
| **Exploración o análisis sin implementación** | No hay código que verificar ni rollback | Usar Layer 1-2 skills (planning, research) |
| **Prototipado rápido / "vibe coding"** | La velocidad de iteración se pierde en gates | Prototipar sin gates, luego aplicar Code-Forge |
| **Tareas de solo investigación** | No hay código que cambiar | Usar researcher-web, leer docs |
| **Rollback imposible** | High-risk sin aprobación humana → HALT | Obtener aprobación humana primero |
| **Sin tests existentes** | No hay ground truth para VERIFY | Escribir tests primero, luego aplicar Code-Forge |
| **Scope mal definido o multi-dominio** | 34% de fallos de agentes son por scope creep | Especificar exclusiones explícitas en Fase 1 |
| **Proyecto con datos no verificados** | 27% de fallos son por data quality | Auditoría de data readiness antes de Fase 1 |
| **Sin integraciones mapeadas** | 9% de fallos por complexity de integración | Mapear dependencias externas primero |

**Estadística clave:** El 88% de los proyectos de agentes de IA fracasan antes de producción (DigitalApplied, 2025-2026). Los 3 patrones principales:
1. **Scope Creep (34%)** — Prevenible con SPECIFY disciplinado
2. **Data Quality Failures (27%)** — Prevenible con data readiness check
3. **Security Blockers (14%)** — Prevenible construyendo seguridad en paralelo

Code-Forge previene estos 3 patrones en Fase 1 (SPECIFY) con los production checks.

---

## 🧠 Filosofía

```
Cada fix debe ser reversible, verificado, y documentado.
```

### Principios fundamentales

1. **Contexto > Procedimiento** (TDAD paper): No le digas al agente "cómo" hacer TDD. Dale contexto sobre qué tests verificar. Dar instrucciones procedurales sin contexto EMPEORA los resultados (+64% regresiones).

2. **Rollback primero, acción después** (Run Ledger): Si no puedes escribir el rollback, la acción es high-risk → NO ejecutar sin aprobación humana.

3. **1 archivo a la vez** (Canary Fix): Cada fix se aplica primero a 1 archivo, se verifica, luego expande. Si falla, sabes exactamente qué lo rompió.

4. **Sin ledger, no hay entrega** (Developers Digest): El ledger es el contrato de auditoría. Sin él, el trabajo no es revisable ni reanudable.

5. **TDD es contexto, no ceremonia** (TDAD paper): El TDD procedural AUMENTÓ regresiones 9.94%. El TDD contextual las REDUJO 70%.

6. **12 gates + FINAL_VERIFY = necesario, no suficiente** (SRE principles): Pasar los checks no garantiza calidad. El ledger y las reflexiones completan el cuadro.

7. **Memoria cross-session** (Reflexion, Engram): Las reflexiones sobreviven entre sesiones. El agente aprende de errores pasados.

8. **Sandbox siempre** (Anthropic CC): Aislar filesystem, red, y recursos en cada ejecución. No confiar en el modelo, confiar en el harness.

---

## 🔄 Las 8 Fases del Prompting Loop

```
TAREA ENTRANTE
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 1: SPECIFY   (basado en SDD + EARS)           │
│  • Data readiness check (previene 27% de fallos)    │
│  • Scope verification (previene 34% de fallos)      │
│  • EARS notation + run_ledger inicial               │
│  • Human checkpoint obligatorio                     │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 2: PLAN      (basado en contextual TDD)       │
│  • Stack detection (Python/TS/ambos)                │
│  • Blast radius + decomposition si >20 archivos     │
│  • Human checkpoint obligatorio                     │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 3: TASKS     (basado en canary principle)     │
│  • Atomic tasks (max 3 archivos por task)           │
│  • Rollback path explícito por task                  │
│  • Human checkpoint obligatorio                     │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 4: IMPLEMENT (basado en TDAD + canary)        │
│  • Contextual TDD: AST-scan previo (NO procedural)  │
│  • Canary fix: 1 archivo a la vez                   │
│  • NO human checkpoint                              │
└─────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 5: VERIFY    (basado en SRE gates)            │
│  • 12 gates en paralelo (8 workers, sandboxed)      │
│  • Bilingüe: Python + TypeScript                    │
│  • Sin LLM — workflow determinista                   │
└─────────────────────────────────────────────────────┘
    ↓
    ├── ALL pass → FASE 8
    │
    └── Fail → ┌─────────────────────────────────────┐
               │  FASE 6: CRITIQUE (basado en         │
               │            Reflexion NeurIPS 2023)   │
               │  • Reflexión verbal de 5 partes      │
               │  • Top-5 memory (Jaccard similarity) │
               │  • Guarda en memory.json              │
               └─────────────────────────────────────┘
                    ↓
               ┌─────────────────────────────────────┐
               │  FASE 7: FIX (basado en             │
               │         Architect/Editor Aider)     │
               │  • Arquitecto (razona) → Editor     │
               │  • Canary + ledger + veto rules     │
               │  • (diff) → Volver a FASE 5          │
               └─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────┐
│  FASE 8: FINAL_VERIFY (basado en integration        │
│                       testing principles)           │
│  • Test suite COMPLETO Python + TypeScript          │
│  • Rollback por task si falla                       │
│  • Si falla 2 veces → HALT                         │
└─────────────────────────────────────────────────────┘
    ↓
ENTREGA (solo si 6/6 hard + score ≥ 8/10 + FINAL_VERIFY + ledger completo)
```

### Detalle de cada fase

#### Fase 1: SPECIFY — Prevenir scope creep y data failures

**Input:** SPEC del usuario  
**Output:** `spec.md` con EARS statements + `run_ledger.json` inicial  
**Modelo:** haiku (barato)  
**Human checkpoint:** ✅ Obligatorio  
**LLM calls:** 1

**Por qué es crítica:** El 34% de los fallos de agentes son por scope creep y el 27% por data quality. Esta fase previene ambos.

**Acción:**
1. Recibe SPEC del usuario
2. **Data readiness check:** ¿Los datos necesarios existen? ¿Son consistentes? ¿Tienen la frescura requerida?
3. **Scope verification:** ¿Es 1 bug o feature atómica? Definir exclusiones explícitas: "Esto NO incluye X"
4. **Rollback possibility:** ¿Se puede deshacer el cambio? Escribir el undo path explícito
5. **Normaliza a EARS notation** (5 patrones testables)
6. Crea `run_ledger.json` con `run_id` + `spec`
7. **Human checkpoint:** Presentar spec para aprobación

**EARS notation (Easy Approach to Requirements Syntax):**
| Tipo | Patrón | Uso |
|------|--------|-----|
| Ubiquitous | "The system shall X" | Comportamiento siempre activo |
| Event-driven | "When Y, the system shall X" | Reacción a eventos |
| State-driven | "While in state Z, the system shall X" | Comportamiento por estado |
| Optional | "Where feature F is enabled, the system shall X" | Feature flags |
| Unwanted | "If X then the system shall Y" | Manejo de errores |

**Production check (NO saltar):**
```
ANTES de aprobar el spec, verificar:
1. ¿El spec toca 1 bug o feature atómica? (NO scope creep)
   Si no → descomponer en specs más pequeños
2. ¿Los datos necesarios existen y son consistentes?
   Si no → auditoría de data readiness primero
3. ¿El rollback es posible? (escribir el undo path)
   Si no → acción high-risk → aprobación humana
4. ¿Hay tests existentes que puedan verificar el fix?
   Si no → escribir tests primero
Si cualquiera falla → NO aprobar, pedir clarificación al humano.
```

**Herramientas:** `RunLedger(workdir).set_spec(spec)`

---

#### Fase 2: PLAN — Stack detection y blast radius

**Input:** `spec.md`  
**Output:** `plan.md` con stack + blast_radius + dependencias  
**Modelo:** sonnet  
**Human checkpoint:** ✅ Obligatorio  
**LLM calls:** 1

**Acción:**
1. Lee spec.md
2. Detecta stack de cada target_file:
   - **Python:** archivo termina en `.py` O está en `src/`
   - **TypeScript:** archivo termina en `.ts/.tsx` O está en `frontend/src/`
   - **Ambos:** si toca archivos de ambos stacks (usar gates en paralelo)
3. Calcula blast_radius via project_index (importers)
4. Si blast_radius > 20 archivos → decompose en sub-tasks atómicas
5. Identifica archivos a crear/modificar
6. **Human checkpoint**

**Production check:**
```
1. Stack detectado: Python (src/), TypeScript (frontend/src/), o ambos
2. Blast radius: cuántos archivos se tocan + cuántos dependen de ellos
3. Si blast_radius > 20 archivos → decompose en sub-tasks atómicas
4. Si toca 2+ archivos no triviales → delegation trigger (usar writer + review)
```

---

#### Fase 3: TASKS — Atomic tasks con rollback

**Input:** `plan.md`  
**Output:** `tasks.json` con DAG + `run_ledger` por task  
**Modelo:** sonnet  
**Human checkpoint:** ✅ Obligatorio  
**LLM calls:** 1

**Acción:**
1. Descompone en atomic tasks (max 3 archivos por task — canary principle)
2. Para cada task:
   - Archivos afectados (max 3)
   - Funciones públicas tocadas (AST-scan)
   - Tests existentes que deben seguir pasando
   - Rollback path explícito (`git checkout`, `git revert`, o `git stash`)
   - Stack de cada archivo (Python/TS)
3. **Human checkpoint**

**Formato de cada task:**
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

#### Fase 4: IMPLEMENT — Contextual TDD + Canary

**Input:** `tasks.json` + código existente  
**Output:** código modificado + tests + `run_ledger` actualizado  
**Modelo:** sonnet  
**Human checkpoint:** ❌ No  
**LLM calls:** 1

**⚠️ IMPORTANTE — Basado en TDAD paper:**
NO dar instrucciones TDD procedurales ("escribe tests primero"). En su lugar, hacer AST-scan previo y **inyectar contexto** sobre qué tests verificar y qué funciones públicas existen.

**Pre-IMPLEMENT (workflow):**
1. Detectar stack de cada target_file
2. AST-scan para identificar funciones públicas (Python con `ast`, TS con `typescript`)
3. Buscar test files correspondientes:
   - Python: `test_<module>.py` en `tests/` o mismo dir
   - TypeScript: `<module>.test.tsx` en `__tests__/` o mismo dir
4. Para cada archivo afectado, encontrar importers (blast radius)
5. **Inyectar en prompt** (NO instrucciones procedurales):
   - "Estos tests existen y deben seguir pasando: [lista]"
   - "Estas funciones publicas son contratos: [lista]"
   - "Estos archivos importan los que tocas: [lista]"

**Canary Fix Application (Google SRE pattern):**
1. Aplicar fix al PRIMER archivo (orden dependencias bottom-up)
   - Python: models → repositories → services → blueprints → tests
   - TypeScript: types → hooks → components → pages → tests
2. Actualizar `run_ledger` con `before_sha` + `after_sha` + `rollback`
3. Si toca 2+ archivos → delegation trigger (usar writer + review)
4. Tras cada archivo, verificar gates sobre ese archivo solo
5. Si pasa → siguiente archivo. Si falla → rollback + HALT ese task

**Ventaja del canary:** Si el fix rompe algo, sabes EXACTAMENTE qué archivo lo rompió. No tienes que debuggear un diff de 5 archivos simultáneos.

**Herramientas:**
- `RunLedger(workdir).add_action("edit_file", target, rollback="...")`
- `RunLedger(workdir).record_canary_fix(file_path)`
- `ForgeSandbox(project_root).run(["python3", "script.py"])`

---

#### Fase 5: VERIFY — 12 Gates de Calidad

**Input:** código modificado  
**Output:** 12 gate results en `run_ledger.json`  
**Modelo:** none (workflow determinista)  
**Human checkpoint:** ❌ No  
**LLM calls:** 0  
**Paralelo:** 8 workers  
**Sandboxed:** ✅ Sí

Ejecuta 12 gates en paralelo. Cada gate detecta stack automáticamente (Python y/o TypeScript).

**Herramienta:** `GateRunner(project_root).run_all(stacks=[...])`

**Hard Gates (DEBEN pasar TODOS — si uno falla, no hay entrega):**

| Gate | Python | TypeScript | Por qué |
|------|--------|------------|---------|
| `tests_pass` | `pytest -x` | `vitest run` | Los tests son la ground truth |
| `tests_deterministic` | 3 runs (mismo exit code) | 3 runs (mismo exit code) | Tests no-deterministas = falsos positivos |
| `no_security_issues` | AST scan: eval/exec/pickle/shell=True | AST scan: eval/innerHTML/XSS | Previene el 14% de fallos de seguridad |
| `no_broken_imports` | `python -c "import module"` | `tsc --noEmit` | Imports rotos = no funciona |
| `no_circular_imports` | AST DFS | `madge --circular` | Circular deps = runtime errors |
| `integration_smoke` | `python -c "import module"` | `vite build` | Build roto = no deploy |

**Soft Goals (score ponderado ≥ 8/10):**

| Gate | Python | TypeScript | Weight |
|------|--------|------------|--------|
| `coverage_branch >= 85%` | `pytest --cov --cov-branch` | `vitest --coverage v8` | 1.0 |
| `lint_clean` | `ruff check` | `eslint --max-warnings=0` | 1.0 |
| `types_clean` | `mypy --strict` | `tsc --strict` | 1.0 |
| `mutation_score >= 80%` | `mutmut run` | `stryker run` | **2.0** |
| `complexity_max <= 10` | `radon cc -s -n C` | `eslint complexity` | 1.0 |
| `test_quality >= 30%` | ratio test/src | ratio test/src | 1.0 |

> **Nota:** `mutation_score` tiene peso 2.0 porque es el indicador más confiable de calidad de tests (mata mutantes = tests que realmente verifican algo).

---

#### Fase 6: CRITIQUE — Reflexión Verbal (Reflexion NeurIPS 2023)

**Input:** failures de VERIFY + diff aplicado + memory.json  
**Output:** reflexión verbal guardada en memory.json  
**Modelo:** sonnet  
**Human checkpoint:** ❌ No  
**LLM calls:** 1

**Solo se activa si VERIFY falló.** Este es el mecanismo de aprendizaje del agente.

**Input:**
- Failures de VERIFY
- Diff aplicado
- Top-5 reflexiones pasadas de `memory.json` (vía Jaccard similarity)
- `run_ledger` actualizado

**Reflexión verbal (5 partes obligatorias):**
```
1. ANALYZE: Causa raíz en una oración
2. WHY DIDN'T IT WORK LAST TIME: Si ocurrió antes, qué se intentó
3. HYPOTHESIS: Cambio específico que lo arreglaría
4. RISK: Podría el fix introducir nuevo fallo?
5. REFLEXION: Qué aprendí sobre este problema
```

**Por qué funciona:** Basado en el paper Reflexion (NeurIPS 2023) que logró 91% pass@1 en HumanEval. La reflexión verbal es más efectiva que el fine-tuning porque no requiere actualizar pesos del modelo.

**Almacenamiento:**
```python
from forge import PersistentMemory
mem = PersistentMemory("/tmp/workdir")
mem.add_reflection(
    iteration_id="iter-3",
    summary="Error de import en service.py",
    verbal_reflection="El problema fue que faltaba __init__.py en el subdirectorio...",
    score=7.5,
    root_cause="Missing __init__.py",
    files_affected=["src/service.py"],
    key_learnings=["Siempre verificar __init__.py antes de importar"]
)
# Buscar reflexiones similares para el próximo CRITIQUE
similares = mem.find_similar("error de import", top_n=5)
```

---

#### Fase 7: FIX — Architect/Editor Pattern (Aider SOTA)

**Input:** failures de VERIFY + código afectado + reflexiones  
**Output:** unified diffs aplicados + `run_ledger` actualizado  
**Modelo:** sonnet (Architect + Editor)  
**Human checkpoint:** ❌ No  
**LLM calls:** 2

**Arquitectura (basada en Aider Sep 2024 — SOTA 85%):**

1. **ARQUITECTO (razonamiento):** Recibe failures, código afectado, reflexiones. Produce diagnóstico + plan en lenguaje natural. NO escribe código.
2. **EDITOR (ejecución):** Recibe plan del Arquitecto + archivos afectados. Produce unified diff. NO razona sobre la solución.
3. **Validator (canary):** Aplica el diff con canary + ledger.

**Flujo de canary:**
```
1. git stash (snapshot global)
2. git apply diff al PRIMER archivo (canary)
3. Actualizar run_ledger: before_sha, after_sha, rollback
4. Verificar gates sobre ese archivo solo
5. Si pasa → aplicar al siguiente archivo
6. Si falla → git stash pop (rollback) + volver a Editor
7. Si todos pasan individualmente → VERIFY completo
```

**Veto Rules (hardcodeadas — NO negociables):**
- 🚫 VETO si diff borra un test sin reemplazo
- 🚫 VETO si diff introduce `*_API_KEY = literal` o cualquier secreto hardcodeado
- 🚫 VETO si diff está vacío
- 🚫 VETO si rollback no es posible (high-risk)

---

#### Fase 8: FINAL_VERIFY — Test Suite Completo

**Input:** todas las tasks completadas  
**Output:** test suite COMPLETO del proyecto  
**Modelo:** none (workflow determinista)  
**Human checkpoint:** ❌ No  
**LLM calls:** 0  
**Sandboxed:** ✅ Sí  
**Timeout:** 900s

**Acción:**
- Python: `pytest --tb=short src/tests/`
- TypeScript: `npx vitest run --reporter=verbose`

**Si falla:**
1. Identificar task culpable via `run_ledger` (git blame + before/after sha de cada archivo)
2. Re-ejecutar esa task sola (rollback + re-apply)
3. Si tras 2 re-ejecuciones sigue fallando → **HALT**
4. Actualizar `run_ledger` con `final_status`

---

## 🛑 HALT Conditions

El proceso se detiene inmediatamente si ocurre cualquiera de estas condiciones:

| # | Condición | Por qué | Acción |
|---|-----------|---------|--------|
| 1 | 2 PIVOTs consecutivos sin mejorar | El agente está dando vueltas | HALT — entregar mejor versión |
| 2 | Budget de 2M tokens excedido | Costo fuera de control | HALT |
| 3 | Score < 5 tras 50% del presupuesto | No vale la pena continuar | PIVOT forzado |
| 4 | 3 fallos repetidos consecutivos | Mismo error sistemático | HALT |
| 5 | Fase 8 falla tras 2 re-ejecuciones | Tests de integración no pasan | HALT |
| 6 | `run_ledger` se corrompe | No hay auditoría | HALT inmediato |
| 7 | Rollback no posible en acción high-risk | Vulnerabilidad | HALT |
| 8 | Project_root se modifica fuera de target_files | Violación de sandbox | HALT inmediato |
| 9 | Iteraciones > 30 | Loop infinito | Aborta |
| 10 | Cascading creates > 20 (runaway) | Creación de archivos descontrolada | Aborta |

**Output de HALT:**
- Mejor versión + `run_ledger` completo
- Reporte de blockers
- Reflexiones episodic (de memory.json)
- Hipótesis de por qué falló
- Recomendación para humano

---

## 📋 Output Final

Solo se entrega si TODOS estos checks pasan:

- [ ] Hard gates ALL pass (6/6)
- [ ] Soft score >= 8/10 (weighted_avg real)
- [ ] Fase 8 FINAL_VERIFY pass
- [ ] Reflexión documentada en `memory.json`
- [ ] `run_ledger.json` completo (todas las acciones con rollback)
- [ ] Todos los canary fixes verificados individualmente

**Formato de entrega:**
- `spec.md` (EARS notation con exclusiones explícitas)
- `plan.md` (con stack + blast_radius + decomposition rationale)
- `tasks.json` (DAG + run_ledger por task + rollbacks)
- Código final (en disco)
- Tests finales (en disco, deben pasar todos)
- `memory.json` (reflexiones cross-session)
- `run_ledger.json` (registro completo de acciones con proof)
- Score final (12 gates detalladas con evidencias)
- Métricas: tokens_usados, tiempo_total, num_iteraciones, num_pivots

---

## 🎯 Delegation Triggers

Basados en gentle-ai (Gentleman Programming). Cuándo delegar a sub-agentes:

| # | Trigger | Acción | Por qué |
|---|---------|--------|---------|
| 1 | Leer 4+ archivos para entender un flow | Delegar exploración a sub-agente | El agente se satura con >4 archivos en contexto |
| 2 | Tocar 2+ archivos no-triviales (>50 líneas) | Usar writer + requerir fresh review | Multi-file writes son propensos a errores de coordinación |
| 3 | Commit, push, o PR después de code changes | Run fresh review (excepto docs) | El contexto fresco detecta errores que el agente no ve |
| 4 | Incidente: wrong cwd, git accident, merge recovery | Run fresh audit antes de continuar | Después de errores, el estado puede ser inconsistente |
| 5 | >20 tool calls, 5 exploratory reads | Pause y delegate, re-plan, o justifica | La complejidad acumulada degrada la calidad |
| 6 | Review adversarial de diffs | Usar contexto fresco para revisar | El mismo agente que escribió el código no ve sus propios errores |

---

## 🔧 Resumen de Herramientas Python

| Componente | Import | Propósito | Documentación |
|-----------|--------|-----------|---------------|
| `RunLedger` | `from forge import RunLedger` | Registro de auditoría con rollback obligatorio | `references/run-ledger.md` |
| `PersistentMemory` | `from forge import PersistentMemory` | Memoria cross-session con Jaccard similarity | `references/run-ledger.md` |
| `ForgeSandbox` | `from forge import ForgeSandbox` | Sandbox dual (filesystem + network + rlimits) | `references/sandbox.md` |
| `GateRunner` | `from forge import GateRunner` | 12 gates de calidad (6 hard + 6 soft) bilingües | `references/gates.md` |
| `SecurityScanner` | `from forge.gates import SecurityScanner` | Escáner AST de seguridad (eval, exec, XSS, secrets) | `references/gates.md` |

---

## 📚 Referencias Académicas

| Fuente | Año | Concepto | Impacto en Code-Forge |
|--------|-----|----------|----------------------|
| TDAD (arXiv:2603.17973) | 2026 | Contextual TDD > procedural | Fase 4: AST-scan previo, NO instrucciones TDD |
| Reflexion (NeurIPS 2023) | 2023 | Verbal reinforcement learning | Fase 6: CRITIQUE con memoria episódica |
| Run Ledger (developersdigest) | 2026 | Permission→Action→Log→Review→Rollback | RunLedger clase + filosofía del loop |
| Aider Architect/Editor | 2024 | Separar razonamiento de edición | Fase 7: Architecture → Editor → Validator |
| Anthropic CC Sandboxing | 2025 | Sandbox dual filesystem+network | ForgeSandbox clase |
| Google SRE Canary | - | Canary release pattern | Fase 4+7: 1 archivo a la vez |
| gentle-ai Delegation | 2026 | 6 reglas de delegación | Delegation Triggers |
| SDD (BCMS) | 2026 | Spec-driven Development | Fase 1: EARS notation |
| 88% Failure Analysis (DigitalApplied) | 2025-2026 | 7 patrones de fracaso | Production checks en Fase 1 |

---

## 📖 Referencias Rápidas

- `references/run-ledger.md` — Protocolo Run Ledger completo
- `references/sandbox.md` — Sandbox dual (filesystem + network + rlimits)
- `references/gates.md` — 12 gates bilingües + SecurityScanner
- `references/phases.md` — 8 fases detalladas del prompting loop
- `references/examples.md` — 5 ejemplos prácticos
- `references/best-practices.md` — Guía completa DO/DON'T con investigación
