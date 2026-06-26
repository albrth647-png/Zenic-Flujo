# Ejemplos de Code-Forge v1.0

Ejemplos de uso del prompting loop en diferentes escenarios.

---

## Ejemplo 1: Fix simple en Python (CRM)

**SPEC:** "Fix error en list_leads cuando la BD está vacía — debe retornar lista vacía en vez de lanzar excepción"

### Fase 1: SPECIFY

**EARS notation:**
- **Ubiquitous:** "The system shall return an empty list when `list_leads()` is called and the database has no leads"
- **Ubiquitous:** "The system shall not raise exceptions during normal query execution"
- **Event-driven:** "When `db.query(Lead).all()` returns an empty result set, the system shall return `[]`"
- **Unwanted:** "If a database connection error occurs, the system shall raise a `DatabaseError` (not crash)"

**Data readiness check:**
- ✅ Existe `src/tools/crm/service.py` con función `list_leads()`
- ✅ Existe `tests/test_crm.py` con `test_list_leads`
- ✅ Rollback posible: `git checkout src/tools/crm/service.py`
- ✅ Atomic: 1 bug, 1 archivo, 1 rollback

**Ledger inicial:**
```python
from forge import RunLedger
ledger = RunLedger("/tmp/workdir", run_id="fix-list-leads-empty")
ledger.set_spec("Fix list_leads cuando BD vacía — retornar [] en vez de excepción")
```

### Fase 2: PLAN

**Stack detection:** Python (`src/tools/crm/service.py`)
**Blast radius:** 1 archivo (solo service.py)
**Archivos a modificar:** `src/tools/crm/service.py`

### Fase 3: TASKS

```json
[{
  "id": "task-001",
  "description": "Add empty list guard to list_leads()",
  "files": ["src/tools/crm/service.py"],
  "stack": "python",
  "public_functions": ["list_leads"],
  "existing_tests": ["tests/test_crm.py::test_list_leads_empty",
                      "tests/test_crm.py::test_list_leads_with_data"],
  "rollback": "git checkout src/tools/crm/service.py",
  "dependencies": []
}]
```

### Fase 4: IMPLEMENT

Canary fix — 1 archivo:

```python
# ANTES
def list_leads():
    return db.query(Lead).all()

# DESPUÉS
def list_leads():
    leads = db.query(Lead).all()
    return leads if leads is not None else []
```

**Ledger:**
```python
ledger.add_action("edit_file", "src/tools/crm/service.py",
                  permission="allow",
                  diff_summary="+3 líneas: guard para None",
                  rollback="git checkout src/tools/crm/service.py")
ledger.record_canary_fix("src/tools/crm/service.py")
```

### Fase 5: VERIFY

```python
from forge import GateRunner
runner = GateRunner("/ruta/del/proyecto")
report = runner.run_all(stacks=["python"])
runner.print_report()
# ✅ 6/6 hard gates pass
# 🎯 Soft score: 9.2/10
```

---

## Ejemplo 2: Fix cross-stack (Python API + TypeScript frontend)

**SPEC:** "Añadir campo 'last_login' al perfil de usuario en la API y mostrarlo en la página de perfil del frontend"

### Fase 1: SPECIFY

**EARS notation:**
- **Ubiquitous:** "The system shall expose a `last_login` field in the user profile API response"
- **Ubiquitous:** "The system shall display the `last_login` timestamp on the user profile page"
- **State-driven:** "While the user has never logged in, the system shall display 'Never' instead of a timestamp"

### Fase 2: PLAN

**Stack detection:** AMBOS
- Python: `src/api_v2/user.py` (API endpoint)
- TypeScript: `frontend/src/pages/ProfilePage.tsx` (frontend)

**Blast radius:** 3 archivos (user model → user endpoint → profile page)

### Fase 3: TASKS

```json
[
  {
    "id": "task-001",
    "description": "Añadir campo last_login al modelo User y serializador",
    "files": ["src/api_v2/models.py", "src/api_v2/serializers.py"],
    "stack": "python",
    "dependencies": []
  },
  {
    "id": "task-002",
    "description": "Añadir last_login al endpoint de profile API",
    "files": ["src/api_v2/user.py"],
    "stack": "python",
    "dependencies": ["task-001"]
  },
  {
    "id": "task-003",
    "description": "Mostrar last_login en ProfilePage del frontend",
    "files": ["frontend/src/pages/ProfilePage.tsx"],
    "stack": "typescript",
    "dependencies": ["task-002"]
  }
]
```

### Fase 4: IMPLEMENT

Canary: models → serializers → endpoint → frontend

### Fase 5: VERIFY

```python
runner = GateRunner("/ruta/del/proyecto")
report = runner.run_all(stacks=["python", "typescript"])
# Ambos stacks en paralelo (16 gates totales)
```

---

## Ejemplo 3: Refactor grande con canary

**SPEC:** "Extraer lógica de autenticación de `main.py` a un módulo separado `auth_service.py`"

### Fase 1: SPECIFY

**Data readiness check:**
- ✅ Existe `src/main.py` con lógica de auth
- ✅ Tests existentes para auth
- ⚠️ Blast radius potencialmente grande (muchos importers de main.py)
- **Decisión:** Decomponer en 3 sub-tasks atómicas

### Fase 3: TASKS

```json
[
  {
    "id": "task-001",
    "description": "Crear src/auth_service.py con funciones de auth extraídas",
    "files": ["src/auth_service.py"],
    "stack": "python",
    "rollback": "rm src/auth_service.py",
    "dependencies": []
  },
  {
    "id": "task-002",
    "description": "Actualizar main.py para importar de auth_service",
    "files": ["src/main.py"],
    "stack": "python",
    "rollback": "git checkout src/main.py",
    "dependencies": ["task-001"]
  },
  {
    "id": "task-003",
    "description": "Actualizar tests para reflejar nueva estructura",
    "files": ["tests/test_auth.py"],
    "stack": "python",
    "rollback": "git checkout tests/test_auth.py",
    "dependencies": ["task-002"]
  }
]
```

### Fase 4: IMPLEMENT

Canary application:
1. Task-001: Crear `auth_service.py` ✅ → VERIFY pasa
2. Task-002: Modificar `main.py` ✅ → VERIFY pasa
3. Task-003: Actualizar tests ✅ → VERIFY pasa

### Fase 8: FINAL_VERIFY

```python
from forge.sandbox import ForgeSandbox
with ForgeSandbox("/ruta/del/proyecto") as sb:
    result = sb.run(["python3", "-m", "pytest", "src/tests/", "-x", "-q"])
    # ✅ All tests pass
```

---

## Ejemplo 4: HALT por rollback no definido

**SPEC:** "Optimizar query de leads usando raw SQL"

**Fase 1 detecta:** rollback no posible porque `raw SQL` no tiene undo path definido

```
RUN LEDGER: rollback no definido para edit_file en src/crm/service.py.
Si no puedes escribir el rollback, la acción es high-risk → NO ejecutar.
```

**Decisión:** HALT. Pedir al humano que defina el rollback antes de continuar.

---

## Ejemplo 5: CRITIQUE + FIX loop

**SPEC:** "Añadir validación de email al crear lead"

**VERIFY falla:**
```
❌ tests_pass: 1 test failed
  test/test_crm.py::test_create_lead_invalid_email
  AssertionError: no se lanzó ValidationError
```

**CRITIQUE genera reflexión:**
1. **ANALYZE:** La validación de email no se ejecuta porque `validate_email()` se llama después de `db.commit()`
2. **WHY DIDN'T IT WORK LAST TIME:** Primera vez
3. **HYPOTHESIS:** Mover `validate_email()` antes de `db.session.add()`
4. **RISK:** Bajo — solo cambia orden de operaciones
5. **REFLEXION:** Siempre validar antes de persistir

**FIX aplica diff:**
```python
# ANTES
db.session.add(lead)
validate_email(lead.email)  # ❌ después de add
db.session.commit()

# DESPUÉS
validate_email(lead.email)  # ✅ antes de add
db.session.add(lead)
db.session.commit()
```

**VERIFY pasa en segunda iteración.**
