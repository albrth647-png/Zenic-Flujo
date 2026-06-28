# RunLedger — Campos Obligatorios por Tipo de Acción

> **Referencia**: `forge/templates/run_ledger.schema.json` (JSON Schema canónico)
> **Template**: `forge/templates/run_ledger.template.json` (ledger vacío)
> **Ejemplo**: `forge/templates/run_ledger.example.json` (ledger completo con refactor real)

---

## 📋 Estructura general

```json
{
  "run_id": "forge-<phase>-<topic>",
  "spec": "<SPEC en EARS notation>",
  "created_at": "<ISO 8601 UTC>",
  "updated_at": "<ISO 8601 UTC>",
  "actions": [...],
  "approvals": [...],
  "proof": [...],
  "final_status": "running | pass | fail | halted",
  "metadata": {...},
  "completed_at": "<ISO 8601 UTC | null>",
  "rolled_back": false,
  "rollback_reason": ""
}
```

---

## 🎬 Tipos de acción y campos obligatorios

### `edit_file` — Modificación de archivo existente

**Rollback obligatorio** ✅

```json
{
  "action_type": "edit_file",
  "permission": "allow",
  "target": "src/hat/level3_specialists/datos_auto/data_specialist.py",
  "diff_summary": "Refactor route_action: replace if/elif chain with _ROUTING_TABLE dict dispatch",
  "before_sha": "abc1234",
  "after_sha": "def5678",
  "rollback": "git checkout abc1234 -- src/hat/level3_specialists/datos_auto/data_specialist.py",
  "verified": true,
  "timestamp": "2026-06-27T13:15:00.000000+00:00",
  "stack": "python",
  "blast_radius": "low (single file, internal method)"
}
```

**Campos clave**:
- `before_sha` / `after_sha`: git SHA para revertir vía `git checkout <sha> -- <file>`
- `rollback`: comando exacto para deshacer. OBLIGATORIO (validado por RunLedger.add_action)
- `stack`: `python` | `typescript` | `both`
- `blast_radius`: estimación de impacto (`low`, `medium`, `high` + justificación)

### `create_file` — Archivo nuevo

```json
{
  "action_type": "create_file",
  "permission": "allow",
  "target": "src/security/sso/mapping.py",
  "diff_summary": "Facade re-exporting create_or_link_user and link_existing_user",
  "before_sha": "",
  "after_sha": "def5678",
  "rollback": "git rm src/security/sso/mapping.py",
  "verified": true,
  "timestamp": "2026-06-27T14:00:00.000000+00:00",
  "stack": "python",
  "blast_radius": "low (new file, no callers yet)"
}
```

**Campos clave**:
- `rollback`: típicamente `git rm <file>` o `rm <file>`
- `before_sha`: vacío (archivo no existía)

### `delete_file` — Eliminación de archivo

```json
{
  "action_type": "delete_file",
  "permission": "ask",
  "target": "src/security/sso.py",
  "diff_summary": "Legacy file conflicting with subpackage; moved to src/security/sso/service.py",
  "before_sha": "abc1234",
  "after_sha": "",
  "rollback": "git checkout abc1234 -- src/security/sso.py",
  "verified": true,
  "timestamp": "2026-06-27T14:05:00.000000+00:00",
  "stack": "python",
  "blast_radius": "medium (callers must import from new location)"
}
```

**Campos clave**:
- `permission`: `ask` (requiere confirmación humana) — las eliminaciones son irreversibles sin git
- `rollback`: `git checkout <sha> -- <file>` para restaurar
- `after_sha`: vacío (archivo eliminado)

### `refactor` — Refactor multi-archivo

**Rollback obligatorio** ✅

```json
{
  "action_type": "refactor",
  "permission": "ask",
  "target": "src/hat/level3_specialists/*",
  "diff_summary": "Refactor 3 route_action methods to dict dispatch pattern",
  "before_sha": "abc1234",
  "after_sha": "ghi9012",
  "rollback": "git revert ghi9012",
  "verified": true,
  "timestamp": "2026-06-27T15:00:00.000000+00:00",
  "stack": "python",
  "blast_radius": "high (3 files modified, 56 tests must pass)"
}
```

**Campos clave**:
- `target`: glob pattern (`src/hat/level3_specialists/*`) o commit SHA
- `rollback`: `git revert <sha>` para revertir todo el commit
- `blast_radius`: `high` + justificación (número de archivos, tests afectados)

### `git_commit` — Commit a git

**Rollback obligatorio** ✅

```json
{
  "action_type": "git_commit",
  "permission": "allow",
  "target": "git commit -m 'refactor: dict dispatch in route_action (CC 52->8)'",
  "diff_summary": "Commit with refactor",
  "before_sha": "abc1234",
  "after_sha": "def5678",
  "rollback": "git reset --hard abc1234",
  "verified": true,
  "timestamp": "2026-06-27T15:30:00.000000+00:00",
  "stack": "both"
}
```

**Campos clave**:
- `rollback`: `git reset --hard <sha>` (destructivo) o `git revert <sha>` (crea commit inverso)

### `install_dep` — Instalación de dependencia

```json
{
  "action_type": "install_dep",
  "permission": "ask",
  "target": "pip install ruff mypy radon",
  "diff_summary": "Install Python gate tools",
  "before_sha": "",
  "after_sha": "",
  "rollback": "pip uninstall ruff mypy radon",
  "verified": true,
  "timestamp": "2026-06-27T12:00:00.000000+00:00",
  "stack": "python"
}
```

### `run_test` — Ejecución de tests

```json
{
  "action_type": "run_test",
  "permission": "allow",
  "target": "pytest src/tests/hat/hardened/test_datos_auto_specialists.py -v",
  "diff_summary": "56 tests passed in 7.73s",
  "before_sha": "",
  "after_sha": "",
  "rollback": "",
  "verified": true,
  "timestamp": "2026-06-27T13:20:00.000000+00:00",
  "stack": "python"
}
```

### `run_gate` — Ejecución de gate individual

```json
{
  "action_type": "run_gate",
  "permission": "allow",
  "target": "radon cc src/hat/level3_specialists/datos_auto/data_specialist.py",
  "diff_summary": "route_action CC: 52 -> 8 (rank F -> rank C)",
  "before_sha": "",
  "after_sha": "",
  "rollback": "",
  "verified": true,
  "timestamp": "2026-06-27T13:25:00.000000+00:00",
  "stack": "python"
}
```

---

## ✅ Approvals (Aprobaciones de fase)

```json
{
  "phase": "specify | plan | tasks | implement | verify | fix | final",
  "approved_by": "human | auto",
  "timestamp": "2026-06-27T13:00:00.000000+00:00",
  "notes": "Notas adicionales"
}
```

**Fases**:
- `specify`: SPEC confirmada (responde qué, por qué, criterio de salida)
- `plan`: Plan de implementación aprobado (stack detection, blast radius)
- `tasks`: Tasks atómicas con DAG y rollback por task
- `implement`: Implementación completada
- `verify`: Gates ejecutados, resultados evaluados
- `fix`: Fix de gates fallidos aplicado
- `final`: Run completo, ledger íntegro

**approved_by**:
- `human`: aprobación manual (checkpoint humano)
- `auto`: aprobación automática (gate PASS, etc.)

---

## 🎯 Proof (Resultados de gates)

```json
{
  "gate_name": "tests_pass | tests_deterministic | no_security_issues | no_broken_imports | no_circular_imports | integration_smoke | coverage_branch | lint_clean | types_clean | mutation_score | complexity_max | test_quality",
  "passed": true | false,
  "evidence": "stdout resumen o error (max 500 chars)",
  "stack": "python | typescript | ambos",
  "timestamp": "2026-06-27T13:20:00.000000+00:00"
}
```

**Hard gates** (deben pasar TODOS):
- `tests_pass`, `tests_deterministic`, `no_security_issues`, `no_broken_imports`, `no_circular_imports`, `integration_smoke`

**Soft goals** (score ponderado ≥ 8/10):
- `coverage_branch`, `lint_clean`, `types_clean`, `mutation_score` (peso 2×), `complexity_max`, `test_quality`

---

## 📊 Metadata (Métricas del run)

```json
{
  "hard_gates_passed": 6,        // max 6
  "soft_score": 9.5,             // 0-10, threshold 8.0
  "total_files_changed": 1,      // incrementado por cada edit_file
  "rollbacks_executed": 0,       // acciones rolled back
  "canary_fixes_applied": 1      // fixes 1-archivo-a-la-vez
}
```

---

## 🔒 Validaciones de integridad

`RunLedger.verify_integrity()` valida:

1. **Keys requeridas**: `run_id`, `spec`, `actions`, `approvals`, `proof`, `final_status`
2. **Rollback en acciones high-risk**: cada `edit_file` y `git_commit` debe tener `rollback` no vacío
3. **JSON válido**: si el archivo está corrupto → `RuntimeError("RUN LEDGER CORRUPTED")`

**Comportamiento ante corrupción**: HALT inmediato. No se puede continuar sin ledger íntegro.

---

## 🚀 Uso desde CLI

```bash
# Inicializar ledger en directorio actual
python -m forge init --dir .

# Verificar integridad del ledger
python -m forge ledger verify --dir .

# Crear ledger desde template
cp forge/templates/run_ledger.template.json .forge/run_ledger.json
```

---

## 📝 Ejemplos de uso real

- `.forge/phase1/run_ledger.json` — Fase 1 (Python Gates) con 7 gate results
- `.forge/phase2/run_ledger.json` — Fase 2 (TypeScript Gates) con 10 gate results
- `.forge/phase3/run_ledger.json` — Fase 3 (Sandbox) con 1 approval
- `.forge/phase4/run_ledger.json` — Fase 4 (este run)
- `forge/templates/run_ledger.example.json` — Ejemplo completo con refactor real
