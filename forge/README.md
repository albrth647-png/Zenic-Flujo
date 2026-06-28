# Code-Forge v1.0.1 — Zenic-Flujo Edition

**Framework de ingeniería para agentes de IA.** Sandbox, run ledger, memoria persistente, 12 gates de calidad bilingües (Python + TypeScript), y dashboard HTML.

> **Estado del rollout**: ✅ 8/8 fases COMPLETAS (Fase 0-8)
> **Progreso global**: 100%
> **Tests**: 216+ tests en `forge/tests/`
> **Reflexiones en memoria**: 33 (cross-session)

---

## 📖 Documentación

### Para empezar
- [**Quickstart**](docs/fase8/quickstart.md) — Setup en 10 minutos
- [**Workflow de desarrollo**](docs/fase8/workflow.md) — Ciclo completo: forge start → verify → fix → commit

### Ejemplos prácticos
- [Ejemplo 01: Fix de bug CRM](docs/fase8/examples/01-fix-bug-crm.md) — Bug fix con ciclo completo
- [Ejemplo 02: Añadir tool N4](docs/fase8/examples/02-add-tool.md) — SlackNotificationWorker paso a paso
- [Ejemplo 03: Refactor de módulo](docs/fase8/examples/03-refactor-module.md) — Dict dispatch con gates y rollback

### Reportes por fase del rollout
- [Fase 0 — Fundación](plan-code-forge-rollout.md) (en este archivo)
- [Fase 1 — Python Gates](docs/fase1-rollout.md)
- [Fase 2 — TypeScript Gates](docs/fase2-rollout.md)
- [Fase 3 — Sandbox](docs/fase3-rollout.md)
- [Fase 4 — RunLedger](docs/fase4-rollout.md)
- [Fase 5 — Memory](docs/fase5-rollout.md)
- [Fase 6 — Homologación por módulo](docs/fase6-rollout.md) (12 módulos)
- [Fase 7 — CI/CD](docs/fase7-rollout.md)
- [Fase 8 — Documentación](docs/fase8/) (este directorio)

### Homologación por módulo (Fase 6)
- [6.1-core](docs/fase6/6.1-core.md) | [6.2-orbital](docs/fase6/6.2-orbital.md) | [6.3-hat](docs/fase6/6.3-hat.md)
- [6.4-events](docs/fase6/6.4-events.md) | [6.5-nlu](docs/fase6/6.5-nlu.md) | [6.6-workflow](docs/fase6/6.6-workflow.md)
- [6.7-level5-tools](docs/fase6/6.7-level5-tools.md) | [6.8-web](docs/fase6/6.8-web.md) | [6.9-api-v2](docs/fase6/6.9-api-v2.md)
- [6.10-frontend](docs/fase6/6.10-frontend.md) | [6.11-connectors](docs/fase6/6.11-connectors.md) | [6.12-tools](docs/fase6/6.12-tools.md)

### Referencias
- [RunLedger — Campos por tipo de acción](templates/README.md)
- [Plan de rollout completo](plan-code-forge-rollout.md)
- [Referencias técnicas](references/) (run-ledger, sandbox, gates, phases, examples, best-practices)

---

## 🚀 Comandos CLI

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

## ¿Qué es?

Code-Forge es un prompting loop de 8 fases para implementar cambios en código con calidad de producción. Diseñado específicamente para Zenic-Flujo (Python + TypeScript) y basado en investigación académica y patrones industriales.

## 📚 Investigación y Fuentes

| Fuente | Año | Concepto | Impacto |
|--------|-----|----------|---------|
| [TDAD (arXiv:2603.17973)](https://arxiv.org/abs/2603.17973) | 2026 | Contextual TDD > procedural | Fase 4: AST-scan previo, NO instrucciones TDD procedurales |
| [Reflexion (NeurIPS 2023)](https://arxiv.org/abs/2303.11366) | 2023 | Verbal reinforcement learning | Fase 6: CRITIQUE con memoria episódica |
| [Run Ledger](https://developersdigest.tech/blog/permissions-logs-rollback-ai-coding-agents) | 2026 | Permission→Action→Log→Review→Rollback | RunLedger + filosofía de auditoría |
| [Aider Architect/Editor](https://aider.chat/2024/09/26/architect.html) | 2024 | Separar razonamiento de edición | Fase 7: Architect→Editor→Validator |
| [Anthropic Sandboxing](https://dev.to/rams901/anthropic-self-hosted-sandboxes) | 2025 | Sandbox dual | ForgeSandbox con rlimits + env |
| [Google SRE Canary](https://sre.google) | - | Canary release | Fase 4+7: 1 archivo a la vez |
| [gentle-ai Delegación](https://github.com/Gentleman-Programming/gentle-ai) | 2026 | 6 reglas de delegación | Delegation Triggers |
| [SDD (BCMS)](https://thebcms.com/blog/spec-driven-development) | 2026 | Spec-driven Development | Fase 1: EARS notation |
| [88% Failure Analysis](https://digitalapplied.com/blog/88-percent-ai-agents-never-reach-production) | 2025-2026 | 7 patrones de fracaso | Production checks preventivos |
| [Meta Harness](https://medium.com/@saehwanpark/from-tool-calling-loops-to-repository-contracts) | 2026 | Repository-level contracts | Workflows como documentación versionada |
| [ForgeCode](https://forgecode.dev/docs/) | 2026 | Multi-provider harness | Multi-modelo en una sesión |
| [ai-whisper](https://github.com/ai-creed/ai-whisper) | 2026 | Multi-agent relay | Baton-passing entre agentes |

### Hallazgos clave de la investigación

1. **La paradoja TDD:** Dar instrucciones TDD procedurales a agentes AUMENTA regresiones 9.94% vs 6.08% baseline. El contexto sobre qué tests verificar las REDUCE a 1.82% (TDAD paper).

2. **88% de proyectos de agentes fracasan** antes de producción. Las causas principales: scope creep (34%), data quality (27%), security blocker (14%) — todos prevenibles con SPECIFY disciplinado.

3. **Reflexión verbal** es más efectiva que fine-tuning para agentes (91% pass@1 HumanEval). Las reflexiones cross-session evitan que el agente repita errores.

4. **El Run Ledger** unifica permisos, logs y rollback en un solo artefacto revisable. Sin ledger completo, no hay entrega.

5. **Separar razonamiento de edición** (Architect/Editor) produce SOTA 85% en benchmarks de edición de código.

---

## Instalación

Este skill ya viene incluido en el proyecto Zenic-Flujo en `forge/`. No requiere instalación adicional.

Si quieres usar Code-Forge en otro proyecto, copia la carpeta `forge/` a tu proyecto:

```bash
cp -r forge/ /ruta/de/tu/proyecto/forge/
```

Luego instala las dependencias:

```bash
pip install pytest mypy ruff mutmut radon pytest-cov pytest-mock pytest-asyncio  # Python gates
npm install -D vitest eslint typescript madge @stryker-mutator/core @vitest/coverage-v8  # TypeScript gates
```

Ver el [Quickstart](docs/fase8/quickstart.md) para instrucciones detalladas.

---

## Cómo se usa

### Desde CLI

```bash
# Inicializar ledger para un cambio
python -m forge ledger init .forge/my-feature --run-id "feature-xyz"

# Ejecutar gates
python -m forge verify --quick

# Verificar integridad del ledger
python -m forge ledger verify .forge/my-feature/run_ledger.json

# Generar dashboard
python -m forge dashboard
```

### Desde Python

```python
from forge import RunLedger, PersistentMemory, ForgeSandbox, GateRunner

# 1. Crear ledger
ledger = RunLedger(".forge/my-feature", run_id="mi-fix-001")
ledger.set_spec("Implementar X")

# 2. Crear sandbox + ejecutar gates dentro
with ForgeSandbox("/ruta/del/proyecto") as sb:
    runner = GateRunner("/ruta/del/proyecto", sandbox=sb, memory=PersistentMemory("forge/data"))
    report = runner.run_all()
    runner.print_report()

# 3. Guardar reflexiones (automático si un gate falla)
mem = PersistentMemory("forge/data")
mem.add_reflection("iter-1", "Resumen", "Reflexión...", score=8.0)
```

---

## Las 8 Fases

```
TAREA ENTRANTE
    ↓
[FASE 1: SPECIFY] Spec en EARS + data readiness + run_ledger inicial
    ↓  (human checkpoint)
[FASE 2: PLAN] Stack detection + blast radius + plan.md
    ↓  (human checkpoint)
[FASE 3: TASKS] Atomic tasks + DAG + rollback por task
    ↓  (human checkpoint)
[FASE 4: IMPLEMENT] Contextual TDD + canary fix + ledger actualizado
    ↓
[FASE 5: VERIFY] 12 gates en paralelo (8 workers, sandboxed)
    ↓  (si falla → FASE 6-7)
[FASE 6: CRITIQUE] Reflexión verbal + memory cross-session
    ↓
[FASE 7: FIX] Architect/Editor + canary + ledger
    ↓
[FASE 8: FINAL_VERIFY] Test suite completo Python + TypeScript
    ↓
ENTREGA (solo si 6/6 hard gates + score ≥ 8/10 + FINAL_VERIFY pass + ledger completo)
```

---

## Estructura del proyecto

```
forge/
├── __init__.py          # Entry point (exporta RunLedger, PersistentMemory, ForgeSandbox, GateRunner)
├── run_ledger.py        # Run Ledger: permission → action → log → review → rollback
├── memory.py            # Memoria cross-session con Jaccard similarity
├── sandbox.py           # Sandbox dual: filesystem + network allowlist + rlimits + airgap
├── gates.py             # 12 gates de calidad (6 hard + 6 soft) + SecurityScanner + memory integration
├── ledger_cli.py        # CLI subcomando: forge ledger init/verify/show/list
├── dashboard.py         # DashboardGenerator: HTML report con score por módulo + trends
├── cli.py               # CLI principal: forge init/verify/check-module/report/self-test/dashboard/ledger
├── __main__.py          # Entry point: python -m forge
├── SKILL.md             # Skill definition (Codebuff lo lee) — v1.0.1
├── README.md            # Esta documentación
├── README.es.md         # Documentación en español
├── plan-code-forge-rollout.md  # Plan de rollout (9 fases, estado global)
├── templates/           # Templates canónicos de RunLedger
│   ├── run_ledger.schema.json   # JSON Schema
│   ├── run_ledger.template.json # Ledger vacío
│   ├── run_ledger.example.json  # Ejemplo completo
│   └── README.md                # Docs campos por tipo de acción
├── data/
│   └── memory.json      # 33 reflexiones cross-session
├── docs/                # Documentación por fase del rollout
│   ├── fase1-rollout.md   # Python Gates
│   ├── fase2-rollout.md   # TypeScript Gates
│   ├── fase3-rollout.md   # Sandbox
│   ├── fase4-rollout.md   # RunLedger
│   ├── fase5-rollout.md   # Memory
│   ├── fase6-rollout.md   # Homologación por módulo
│   ├── fase6/             # 12 docs (uno por módulo)
│   ├── fase7-rollout.md   # CI/CD + Dashboard
│   └── fase8/             # Quickstart + Workflow + 3 ejemplos
├── tests/               # 216+ tests
│   ├── test_gates.py
│   ├── test_run_ledger.py
│   ├── test_memory.py
│   ├── test_sandbox.py
│   ├── test_sandbox_phase3.py
│   ├── test_ledger_cli.py
│   ├── test_memory_gate_integration.py
│   └── test_dashboard.py
└── references/          # Referencias técnicas
    ├── run-ledger.md    # Protocolo Run Ledger detallado
    ├── sandbox.md       # Sandbox dual detallado
    ├── gates.md         # 12 gates detallados
    ├── phases.md        # 8 fases detalladas
    ├── examples.md      # Ejemplos de uso
    └── best-practices.md # Guía DO/DON'T con investigación
```

---

## 📊 Estado del rollout (8/8 fases COMPLETAS)

| Fase | Estado | Score |
|---|---|---|
| Fase 0 — Fundación | ✅ COMPLETA | 10/10 |
| Fase 1 — Python Gates | ✅ COMPLETA | 6.1/10 (4/7 gates PASS) |
| Fase 2 — TypeScript Gates | ✅ COMPLETA | Hard 5/5 + Soft 3.5/10 |
| Fase 3 — Sandbox | ✅ COMPLETA | 38 tests + integración GateRunner + airgap |
| Fase 4 — RunLedger | ✅ COMPLETA | 188 tests + CLI + pre-commit + CI |
| Fase 5 — Memory | ✅ COMPLETA | 30+ reflexiones + integración GateRunner |
| Fase 6 — Homologación | ✅ COMPLETA | 12/12 módulos (score 8.05) |
| Fase 7 — CI/CD | ✅ COMPLETA | workflow + pre-commit + dashboard HTML |
| Fase 8 — Documentación | ✅ COMPLETA | quickstart + workflow + 3 ejemplos |

**Progreso global**: ✅ 100% del rollout completo

---

## Licencia

Propietaria — Zenic-Flujo.
