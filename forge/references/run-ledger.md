# Run Ledger — Protocolo Completo

El Run Ledger es el registro de auditoría que viaja con cada task del agente. Cada acción debe tener rollback definido ANTES de ejecutarse. Sin ledger completo, no hay entrega.

**Basado en:** developersdigest "Permissions, Logs, Rollback for AI Coding Agents"

---

## API

```python
from forge import RunLedger

ledger = RunLedger("/tmp/workdir", run_id="mi-fix-001")
```

### Constructor

```python
RunLedger(workdir: str | Path, run_id: str | None = None)
```

- `workdir`: Directorio donde se crea `run_ledger.json`
- `run_id`: Opcional. Si no se provee, genera: `zenic-fix-<YYYYMMDD_HHMMSS>`

Si ya existe un ledger en `workdir`, lo carga y verifica integridad. Si está corrupto, lanza `RuntimeError`.

### Métodos

| Método | Descripción |
|--------|-------------|
| `set_spec(spec)` | Registra la SPEC original |
| `add_action(type, target, permission, diff_summary, before_sha, after_sha, rollback)` | Registra una acción. Lanza `ValueError` si rollback falta en acciones de alto riesgo |
| `mark_verified(action_index)` | Marca una acción como verificada |
| `record_rollback(action_index, reason)` | Registra que se ejecutó un rollback |
| `record_canary_fix(file_path)` | Registra un canary fix aplicado |
| `add_approval(phase, approved_by, notes)` | Registra una aprobación de fase |
| `add_gate_result(gate_name, passed, evidence, stack)` | Registra resultado de un gate |
| `set_soft_score(score)` | Score ponderado de soft goals (0-10) |
| `is_high_risk(action_index)` | True si la acción no tiene rollback |
| `complete(status)` | Marca el ledger como completo. Retorna summary |
| `summary()` | Resumen del ledger |
| `verify_integrity()` | Verifica que el ledger no esté corrupto |

### Estados

| Estado | Significado |
|--------|-------------|
| `running` | En ejecución (default) |
| `pass` | Completado exitosamente |
| `fail` | Falló pero no crítico |
| `halted` | Detenido por condición crítica |

### Permisos

| Permission | Significado |
|------------|-------------|
| `allow` | Acción permitida sin aprobación humana |
| `ask` | Requiere aprobación humana |
| `deny` | Acción denegada |

---

## Ejemplo completo

```python
from forge import RunLedger

ledger = RunLedger("/tmp/workdir")
ledger.set_spec("Fix paginación en list_leads cuando hay menos de 10 resultados")

# Fase 1: SPECIFY
ledger.add_approval("specify", "human", notes="Spec OK")

# Fase 4: IMPLEMENT
action = ledger.add_action(
    action_type="edit_file",
    target="src/tools/crm/service.py",
    permission="allow",
    diff_summary="+15 líneas (manejo de lista vacía)",
    before_sha="abc123",
    after_sha="def456",
    rollback="git checkout src/tools/crm/service.py"
)
ledger.mark_verified(0)
ledger.record_canary_fix("src/tools/crm/service.py")

# Fase 5: VERIFY
ledger.add_gate_result("tests_pass", True,
    "15 tests passed, 0 failed", "python")
ledger.add_gate_result("lint_clean", True, "No issues", "python")

# Fase 8: FINAL
ledger.set_soft_score(9.2)
summary = ledger.complete("pass")
print(summary)
# {
#   "run_id": "zenic-fix-20260626_120000",
#   "final_status": "pass",
#   "hard_gates_passed": 6,
#   "soft_score": 9.2,
#   ...
# }
```

---

## Reglas

1. **Cada acción debe tener rollback definido ANTES de ejecutarse.** Si no puedes escribir el rollback, la acción es high-risk y requiere aprobación humana.

2. **Ledger se escribe a disco tras cada acción** (no solo al final). Esto asegura que si el proceso se interrumpe, el ledger no se pierde.

3. **Si el ledger se corrompe, HALT inmediato.** No continuar a ciegas.

4. **Rollback obligatorio para** `edit_file` y `git_commit`. Para otros tipos (`run_test`, `install_dep`), el rollback es opcional.

5. **Hard gates tracked automáticamente.** Cuando llamas `add_gate_result` con un gate que está en la lista de hard gates y passed=True, se incrementa `hard_gates_passed`.

---

## Integridad

`verify_integrity()` verifica:
1. Que existan todas las keys requeridas: `run_id`, `spec`, `actions`, `approvals`, `proof`, `final_status`
2. Que cada acción de tipo `edit_file` o `git_commit` tenga rollback definido

Si alguna verificación falla, retorna `False`. El agente debe hacer HALT inmediato.
