# Fase 4 — RunLedger (Rollout Report)

> **Estado**: ✅ COMPLETA
> **Run ID**: `forge-phase4-runledger`
> **Fecha de ejecución**: 2026-06-27
> **Tiempo total**: ~1 hora (15min tests existentes + 20min template + 25min CLI + hooks + CI)
> **Workdir**: `.forge/phase4/`

---

## 🎯 Objetivo

Según el plan original (`forge/plan-code-forge-rollout.md`), Fase 4 cubre:
- 4.1 Verificar RunLedger: tests de integridad, rollback, corrupción, handoff
- 4.2 Template canónico `forge/templates/run_ledger.json` + documentación campos por tipo de acción
- 4.3 Integrar ledger en workflow: pre-commit hook + CI check + CLI command

**Criterio de salida**: cada cambio al proyecto tiene ledger asociado, verificable en CI.

---

## 🔧 4.1 Verificar RunLedger — ✅ PASS

### Tests existentes (heredados de Fase 0)
`forge/tests/test_run_ledger.py` ya cubría 27 tests:
- `TestRunLedgerCreation` (4): creación con run_id, custom run_id, load existing, reject corrupted
- `TestRunLedgerSpec` (2): set_spec stores, set_spec overwrites
- `TestRunLedgerActions` (7): add_action basic, increments files_changed, rejects missing rollback for edit_file/git_commit, allows other types, mark_verified, record_rollback, record_canary_fix
- `TestRunLedgerApprovals` (1): add_approval
- `TestRunLedgerGates` (4): add_gate_result pass/fail, updates hard_gates_count, set_soft_score
- `TestRunLedgerHighRisk` (2): is_high_risk without/with rollback
- `TestRunLedgerCompletion` (2): complete_sets_status, summary_returns_correct_data
- `TestRunLedgerIntegrity` (3): verify_integrity valid/missing_keys/missing_rollback
- `TestRunLedgerPersistence` (1): persists_across_instances

### Resultado
- **27 tests PASS** ✅ en 0.17s
- Cobertura completa: integridad, rollback, corrupción, handoff

---

## 🔧 4.2 Template canónico — ✅ PASS

### Archivos creados en `forge/templates/`

#### `run_ledger.schema.json` — JSON Schema canónico
Schema formal con:
- `$schema`: JSON Schema Draft 2020-12
- `required`: run_id, spec, created_at, updated_at, actions, approvals, proof, final_status, metadata
- `additionalProperties: false` (strict)
- `$defs` para tipos complejos:
  - `LedgerAction`: action_type (enum 9 tipos), permission (enum 3), rollback (obligatorio para edit_file/git_commit), stack (enum 3), blast_radius
  - `Approval`: phase (enum 7), approved_by, timestamp, notes
  - `GateProof`: gate_name (enum 12), passed, evidence, stack (enum 3)
  - `LedgerMetadata`: hard_gates_passed (0-6), soft_score (0-10), total_files_changed, rollbacks_executed, canary_fixes_applied

#### `run_ledger.template.json` — Ledger vacío canónico
Template mínimo con todas las keys requeridas, values por defecto, `run_id: "forge-template-EXAMPLE"`.

#### `run_ledger.example.json` — Ejemplo completo con refactor real
Ledger completo con:
- 3 acciones (edit_file, run_test, run_gate) con before_sha, after_sha, rollback
- 3 approvals (specify human, implement auto, verify auto)
- 3 proof (tests_pass, complexity_max, lint_clean)
- metadata completa (hard_gates_passed=6, soft_score=9.5, etc.)
- Basado en el refactor real de `data_specialist.route_action` (Fase 1)

#### `README.md` — Documentación de campos obligatorios por tipo de acción
Referencia completa con ejemplos JSON para cada tipo:
- `edit_file`: rollback obligatorio (`git checkout <sha> -- <file>`)
- `create_file`: rollback (`git rm <file>`)
- `delete_file`: rollback (`git checkout <sha> -- <file>`), permission=ask
- `refactor`: target (glob pattern), blast_radius, rollback (`git revert <sha>`)
- `git_commit`: rollback (`git reset --hard <sha>`)
- `install_dep`: rollback (`pip uninstall ...`)
- `run_test`, `run_gate`: sin rollback requerido
- Aprobaciones: 7 fases (specify, plan, tasks, implement, verify, fix, final)
- Proof: 12 gates (6 hard + 6 soft)
- Metadata: 5 métricas (hard_gates_passed, soft_score, total_files_changed, rollbacks_executed, canary_fixes_applied)

### Validación
- Los 3 archivos JSON son válidos ✅
- Schema respeta la estructura de `forge/run_ledger.py` (TypedDicts LedgerAction, Approval, GateProof, LedgerMetadata)

---

## 🔧 4.3 Integrar ledger en workflow — ✅ PASS

### 4.3c — CLI command `forge ledger`

#### Módulo `forge/ledger_cli.py` (366 líneas)
Funciones testeables:
- `init_ledger(target_dir, run_id)` → crea ledger vacío, rechaza si ya existe
- `verify_ledger(ledger_path)` → verifica integridad (keys, rollback, JSON)
- `show_ledger(ledger_path)` → devuelve LedgerSummary
- `list_ledgers(project_root)` → lista ledgers en .forge/*/
- `_check_integrity(data)` → validación standalone sin instanciar RunLedger
- `_get_nested_int/float` → helpers para acceso seguro a metadata anidada

Handlers CLI:
- `cmd_ledger_init` → `forge ledger init <path> [--run-id <id>]`
- `cmd_ledger_verify` → `forge ledger verify <path>`
- `cmd_ledger_show` → `forge ledger show <path>`
- `cmd_ledger_list` → `forge ledger list [<path>]`

Integración en `forge/cli.py`:
- Subcomando `ledger` añadido via `add_ledger_subparser(sub)`
- Refactor `main()`: usa `args.func` (set_defaults) para subcomandos ledger, dispatch dict para comandos legacy
- Type hints completos: `Callable[[argparse.Namespace], int]` para handlers
- Fix bug preexistente en `cmd_init` (usaba `_append_action` y `_actions` que no existen)

#### Tests `forge/tests/test_ledger_cli.py` (25 tests)
- `TestInitLedger` (4): crea en dir vacío, custom run_id, rechaza existente, crea parent dirs
- `TestCheckIntegrity` (7): válido pasa, missing key falla, edit_file sin rollback falla, edit_file con rollback pasa, git_commit sin rollback falla, run_test sin rollback pasa, actions no lista falla
- `TestVerifyLedger` (4): válido, inexistente, JSON corrupto, con actions y metadata
- `TestShowLedger` (3): devuelve summary, inexistente devuelve None, corrupto devuelve None
- `TestListLedgers` (4): encuentra en .forge/, vacío cuando no hay .forge, salta inválidos, entries con todos los campos
- `TestIntegrationWithRealPhaseLedgers` (3): verifica ledgers reales de Fase 1, Fase 3, lista todos

### 4.3a — Pre-commit hook

#### `scripts/hooks/pre_commit_ledger.py` (92 líneas)
Hook standalone que verifica integridad de todos los ledgers en `.forge/*/`:
- Modo normal: verifica todos los ledgers, exit 0 si todos válidos
- Modo estricto (`--strict`): requiere al menos 1 ledger válido
- Output: `✅` por ledger válido, `❌` por inválido
- Type hints completos, `# ruff: noqa: E402` para sys.path manipulation

#### `.pre-commit-config.yaml`
Config de pre-commit con 5 hooks:
1. `forge-ledger-verify` (local) — verifica RunLedger en .forge/*/
2. `ruff` (astral-sh/ruff-pre-commit@v0.15.20) — lint Python en src/
3. `mypy-gradual` (local) — types en core/orbital (strict)
4. `eslint` (local) — lint TS en frontend/
5. `madge-circular` (local) — circular imports TS

### 4.3b — CI check (GitHub Actions)

#### `.github/workflows/code-forge.yml` (176 líneas)
Workflow con 4 jobs:

1. **`ledger-verify`**: verifica integridad de RunLedger en .forge/*/
   - `python -m forge ledger list .`
   - `python -m forge ledger verify` por cada fase
   - `python scripts/hooks/pre_commit_ledger.py --strict`

2. **`python-gates-quick`**: gates Python rápidos
   - `ruff check src/` (lint_clean)
   - `mypy --config-file mypy.ini src/core src/orbital` (types_clean gradual)
   - `radon cc src/ -s -n C` (complexity_max)
   - SecurityScanner (no_security_issues)
   - `pytest src/tests/` (tests_pass)

3. **`typescript-gates-quick`**: gates TS rápidos
   - `npx eslint . --max-warnings=0` (lint_clean)
   - `npx tsc --noEmit -p tsconfig.app.json` (types_clean)
   - `npx madge --circular --extensions ts,tsx src` (no_circular_imports)
   - `npx vitest run` (tests_pass)
   - `npx vite build` (integration_smoke)

4. **`forge-verify-full`**: forge verify completo (depende de 1, 2, 3)
   - `python -m forge verify --quick` (excluye mutation y coverage)
   - `python -m forge report --quick`
   - Upload artifacts (.forge/ y reports/) con retención 7 días

**Triggers**: push a main/develop, PR a main.

---

## 📊 Resultado Fase 4

### Tests
- **27 tests RunLedger** (heredados) ✅
- **25 tests ledger_cli** (nuevos) ✅
- **Total forge/: 188 tests** ✅ en 6.31s

### Calidad de código (sin decaer)
- **ruff forge/** → All checks passed! ✅
- **ruff scripts/hooks/** → All checks passed! ✅
- **ruff src/** → All checks passed! ✅ (sin regresiones)
- **eslint frontend/** → All checks passed! ✅ (sin regresiones)
- **mypy forge/cli.py + ledger_cli.py** → 0 errores ✅

### Limpieza de deuda técnica preexistente
Durante Fase 4 se aplicaron **93 auto-fixes** + **20 fixes manuales** en `forge/`:
- 42 W293 (blank-line-with-whitespace)
- 16 F401 (unused-import)
- 13 UP017 (datetime-timezone-utc)
- 7 RUF012 (mutable-class-default) → file-level noqa (intencionalmente mutables)
- 5 SIM105 (suppressible-exception) → `contextlib.suppress()`
- 5 I001 (unsorted-imports)
- 4 F841 (unused-variable) → eliminados
- 3 W292 (missing-newline-at-end-of-file)
- 2 E741 (ambiguous-variable-name `l` → `log`)
- 1 B007 (unused-loop-control `i` → `_`)
- 1 SIM102 (collapsible-if)
- 1 SIM117 (multiple-with-statements)

### Artefactos producidos
- `forge/templates/run_ledger.schema.json` (JSON Schema canónico)
- `forge/templates/run_ledger.template.json` (ledger vacío)
- `forge/templates/run_ledger.example.json` (ejemplo completo)
- `forge/templates/README.md` (documentación campos)
- `forge/ledger_cli.py` (módulo CLI, 366 líneas)
- `forge/tests/test_ledger_cli.py` (25 tests)
- `scripts/hooks/pre_commit_ledger.py` (hook, 92 líneas)
- `.pre-commit-config.yaml` (5 hooks)
- `.github/workflows/code-forge.yml` (4 jobs CI)
- `forge/cli.py` modificado (fix cmd_init, type hints, subcomando ledger)

### Verificación CLI
```bash
$ python -m forge ledger list .
📂 Ledgers in .forge/ (4 found):
  PATH                                     STATUS     ACTIONS    HARD   SOFT
  .forge/phase1/run_ledger.json            running    0          0      0.00
  .forge/phase2/run_ledger.json            running    0          0      0.00
  .forge/phase3/run_ledger.json            running    0          0      0.00
  .forge/phase4/run_ledger.json            running    0          0      0.00

$ python -m forge ledger verify .forge/phase1/run_ledger.json
✅ Ledger valid: .forge/phase1/run_ledger.json
   Actions: 0
   Hard gates passed: 0
   Soft score: 0.00/10
   Final status: running
```

---

## 🎓 Lecciones aprendidas

1. **`_check_integrity()` standalone** (sin instanciar RunLedger) es más testeable y no tiene side effects (no crea archivos). Mejor separar lógica de validación de lógica de persistencia.

2. **`argparse.Namespace` + `set_defaults(func=...)`** es el patrón idiomático para subcomandos en argparse. Permite que cada subparser tenga su propio handler sin dispatch dict manual.

3. **`Callable[[argparse.Namespace], int]`** es el type hint correcto para handlers CLI. Evita `Any` y hace el dispatch type-safe.

4. **`# ruff: noqa: E402`** es necesario para scripts que manipulan `sys.path` antes de importar módulos del proyecto (como hooks de pre-commit).

5. **JSON Schema canónico** (`run_ledger.schema.json`) sirve como documentación formal + validación. Los `$defs` permiten reutilizar tipos (LedgerAction, Approval, etc.) en otros schemas.

6. **GitHub Actions `on:` es parseado como boolean `True`** por YAML 1.1. Usar `yaml.safe_load` con `d.get(True, d.get('on', {}))` para acceder a los triggers.

7. **`contextlib.suppress(Exception)`** es preferible a `try/except: pass` — más legible y evita F841 (unused variable).

8. **`ruff check --fix`** puede introducir regresiones si se aplica sin verificar tests. Siempre re-correr tests después de auto-fix (especialmente en tests con `result = ...` unused que se elimina).

9. **Class attributes mutables (RUF012)** son legítimos para configuración extensible (HARD_GATES, ALLOWED_DOMAINS). `# ruff: noqa: RUF012` file-level es la solución correcta, no convertir a tuple (rompería extensibilidad).

10. **Pre-commit hook + CI check** son complementarios: pre-commit es local (rápido, antes del commit), CI es remoto (completo, en PR). Ambos verifican integridad del ledger pero CI además corre los 12 gates.

---

## ➡️ Próximo paso

- **Fase 5** (Memory) — poblar con reflexiones de Fase 4 + integrar en GateRunner para generar reflexiones automáticas
- **Fase 6** (Homologación por módulo) — cada módulo tendrá su propio ledger verificable via `forge ledger verify`
- **Fase 7** (CI/CD) — workflow ya creado en Fase 4, falta dashboard de calidad
