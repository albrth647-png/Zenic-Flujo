# Code-Forge v1.0.1 — Zenic-Flujo Edition

**Framework de ingeniería para agentes de IA.** Sandbox, run ledger, memoria persistente, y 12 gates de calidad bilingües (Python + TypeScript).

---

## ¿Qué es?

Code-Forge es un prompting loop de 8 fases para implementar cambios en código con calidad de producción. Diseñado específicamente para Zenic-Flujo (Python + TypeScript) y basado en investigación académica y patrones industriales.

## 📚 Investigación y Fuentes

Code-Forge integra las siguientes fuentes:

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

2. **88% de proyectos de agentes fracasan** antes de producción. Las causas principales: scope creep (34%), data quality (27%), security blockers (14%) — todos prevenibles con SPECIFY disciplinado.

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
pip install pytest mypy ruff mutmut radon  # Python gates
npm install -D vitest eslint typescript madge @stryker-mutator/core  # TypeScript gates
```

---

## Cómo se usa

### Como skill de Codebuff

Cuando necesites implementar un cambio, invoca el skill:

```
Usa el skill code-forge para implementar [tu SPEC aquí]
```

O:

```
@code-forge [tu SPEC aquí]
```

El skill ejecutará automáticamente las 8 fases del prompting loop.

### Directamente desde Python

```python
from forge import RunLedger, PersistentMemory, ForgeSandbox, GateRunner

# 1. Crear ledger
ledger = RunLedger("/tmp/workdir", run_id="mi-fix-001")
ledger.set_spec("Implementar X")

# 2. Crear sandbox
with ForgeSandbox("/ruta/del/proyecto") as sb:
    result = sb.run(["python3", "script.py"])

# 3. Ejecutar gates
runner = GateRunner("/ruta/del/proyecto")
report = runner.run_all()
runner.print_report()

# 4. Guardar reflexiones
mem = PersistentMemory("/tmp/workdir")
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
├── memory.py            # Persistente memory cross-session con Jaccard similarity
├── sandbox.py           # Sandbox dual: filesystem isolation + network allowlist + rlimits
├── gates.py             # 12 gates de calidad (6 hard + 6 soft) bilingües Python/TS
├── SKILL.md             # Skill definition (Codebuff lo lee) — v1.0.1
├── README.md            # Esta documentación
├── README.es.md         # Documentación en español
└── references/
    ├── run-ledger.md    # Protocolo Run Ledger detallado
    ├── sandbox.md       # Sandbox dual detallado
    ├── gates.md         # 12 gates detallados
    ├── phases.md        # 8 fases detalladas
    ├── examples.md      # Ejemplos de uso
    └── best-practices.md # Guía DO/DON'T con investigación 📘
```

---

## Archivos relacionados

- `docs/prompting-loops/code_forge_v1.0_zenic_flujo.md` — Especificación completa del prompting loop
- `forge/SKILL.md` — Skill definition que lee Codebuff (v1.0.1)
- `forge/references/best-practices.md` — Guía DO/DON'T con investigación 📘
- `src/tests/hat/test_f0_d*_verify.py` — Tests de verificación del protocolo Code-Forge

---

## Licencia

Propietaria — Zenic-Flujo.
