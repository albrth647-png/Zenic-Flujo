# Ejemplo 01: Fix de Bug en CRM

> **Tiempo estimado**: 30 minutos
> **Stack**: Python
> **Blast radius**: Low (1 archivo)

---

## 🐛 El bug

El método `CRMService.create_contact()` falla con `KeyError: 'email'` cuando se crea un contacto sin email. El campo email es opcional según el schema pero el código no lo valida.

```python
# src/tools/crm/service.py (línea 45)
def create_contact(self, name: str, email: str | None = None) -> dict:
    contact = {"name": name, "email": email}
    # Bug: si email es None, la validación falla
    if "@" not in email:  # ← KeyError cuando email=None
        raise ValueError("Invalid email")
    return self._repo.save(contact)
```

---

## Fase 1: SPECIFY

```bash
python -m forge ledger init .forge/fix-crm-email --run-id "fix-crm-email-none"
```

```python
from forge import RunLedger
ledger = RunLedger(".forge/fix-crm-email", run_id="fix-crm-email-none")
ledger.set_spec("""
Bug: CRMService.create_contact() falla con KeyError cuando email=None.

Causa raíz: La validación `if "@" not in email` no maneja email=None.

Fix: Añadir guard clause `if email is not None:` antes de la validación.

Criterio de salida:
- tests_pass: test_create_contact_without_email pasa
- lint_clean: ruff clean
- no_security_issues: 0 HIGH
""")
ledger.add_approval("specify", approved_by="human", notes="Bug confirmado, fix es claro")
```

---

## Fase 2: PLAN

```bash
# Detectar archivos afectados
rg -l "create_contact" src/
# Salida: src/tools/crm/service.py, src/tests/test_crm.py
```

```python
ledger.add_action(
    action_type="run_test",
    target="plan-detection",
    diff_summary="Stack: python, blast_radius: low (1 archivo + 1 test)",
    rollback="",
)
ledger.add_approval("plan", approved_by="auto", notes="Blast radius low, 1 archivo")
```

---

## Fase 3: TASKS

```
Task 1: Fix src/tools/crm/service.py (guard clause)
Task 2: Añadir test en src/tests/test_crm.py (test_create_contact_without_email)
```

---

## Fase 4: IMPLEMENT

### Task 1: Fix del bug

```python
# src/tools/crm/service.py — fix
def create_contact(self, name: str, email: str | None = None) -> dict:
    contact = {"name": name, "email": email}
    if email is not None and "@" not in email:  # ← Fix: guard clause
        raise ValueError("Invalid email")
    return self._repo.save(contact)
```

Registrar en ledger:
```python
import subprocess
before_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()

# ... hacer el cambio ...

after_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()  # o git hash-object

ledger.add_action(
    action_type="edit_file",
    target="src/tools/crm/service.py",
    diff_summary="Fix: añadir guard clause `if email is not None` antes de validación",
    before_sha=before_sha,
    after_sha=after_sha,
    rollback=f"git checkout {before_sha} -- src/tools/crm/service.py",
)
```

### Task 2: Añadir test

```python
# src/tests/test_crm.py — nuevo test
def test_create_contact_without_email():
    """Crear contacto sin email no debe fallar."""
    service = CRMService(repo=MockRepo())
    contact = service.create_contact(name="John Doe", email=None)
    assert contact["name"] == "John Doe"
    assert contact["email"] is None
```

```python
ledger.add_action(
    action_type="edit_file",
    target="src/tests/test_crm.py",
    diff_summary="Añadir test_create_contact_without_email",
    before_sha=before_sha,
    after_sha=after_sha,
    rollback=f"git checkout {before_sha} -- src/tests/test_crm.py",
)
ledger.add_approval("implement", approved_by="auto", notes="2 tasks implementadas")
```

---

## Fase 5: VERIFY

```bash
python -m forge verify --quick
```

```python
# Si todos pasan
ledger.add_approval("verify", approved_by="auto", notes="6/6 hard gates PASS")
```

---

## Fase 8: FINAL_VERIFY + Entrega

```python
ledger.set_soft_score(9.5)
summary = ledger.complete(status="pass")
print(f"✅ Fix completado: {summary}")
```

```bash
# Verificar integridad del ledger
python -m forge ledger verify .forge/fix-crm-email/run_ledger.json

# Commit
git add -A
git commit -m "fix: CRM create_contact handles email=None (ledger: .forge/fix-crm-email)"
git push origin fix/crm-email-none
```

---

## 📊 Resultado

| Métrica | Valor |
|---|---|
| Tiempo total | 15 min |
| Archivos modificados | 2 |
| Tests añadidos | 1 |
| Gates PASS | 6/6 hard + 5/6 soft |
| Score | 9.5/10 |
| Rollback definido | ✅ (para ambos archivos) |
| Memoria consultada | ✅ (buscó "KeyError None validation") |

---

## 🎓 Lección aprendida

Este fix se registró en `forge/data/memory.json` como reflexión:
```python
mem.add_reflection(
    iteration_id="fix-crm-email-none",
    summary="Fix: create_contact fallaba con KeyError cuando email=None",
    verbal_reflection="La validación `if '@' not in email` no manejaba email=None...",
    score=9.5,
    root_cause="Guard clause faltante para campo opcional",
    key_learnings=[
        "Validar None antes de operaciones de string en campos opcionales",
        "Tests deben cubrir el caso None explícitamente, no solo string vacío",
    ],
)
```

La próxima vez que un bug similar aparezca, `find_similar("None validation KeyError")` encontrará esta reflexión.
