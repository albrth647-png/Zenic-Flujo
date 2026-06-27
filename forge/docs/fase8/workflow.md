# Workflow de Desarrollo con Code-Forge

> **Tiempo de lectura**: 10 minutos

---

## 🔄 Ciclo de vida de un cambio

```
SPECIFY → PLAN → TASKS → IMPLEMENT → VERIFY → [CRITIQUE → FIX] → FINAL_VERIFY → ENTREGA
```

Cada fase tiene un propósito específico y tools asociadas. Abajo se detalla cada una.

---

## Fase 1: SPECIFY

**Objetivo**: Definir qué se va a hacer y por qué.

### Pasos
1. Crear un ledger para el cambio:
   ```bash
   python -m forge ledger init .forge/my-feature --run-id "feature-add-auth"
   ```

2. Escribir la SPEC en el ledger (notación EARS recomendada):
   ```python
   from forge import RunLedger
   ledger = RunLedger(".forge/my-feature", run_id="feature-add-auth")
   ledger.set_spec("""
   Feature: Añadir autenticación OAuth2 a la API v2.

   Requisitos (EARS):
   - WHEN el usuario envía un request sin token, THE SYSTEM SHALL devolver 401.
   - IF el token es válido, THE SYSTEM SHALL inyectar user_id en el request.
   - WHILE el token no haya expirado, THE SYSTEM SHALL permitir el acceso.

   Criterio de salida:
   - tests_pass: 100% tests pasan
   - no_security_issues: 0 HIGH
   - lint_clean: ruff clean
   """)
   ```

3. Registrar approval:
   ```python
   ledger.add_approval("specify", approved_by="human", notes="SPEC confirmada")
   ```

---

## Fase 2: PLAN

**Objetivo**: Detectar stack, blast radius, y crear plan de implementación.

### Pasos
1. Detectar qué archivos se verán afectados:
   ```bash
   # Python
   rg -l "auth" src/api_v2/ src/security/

   # TypeScript
   rg -l "auth" frontend/src/hooks/
   ```

2. Estimar blast radius:
   - **Low**: 1 archivo aislado, sin dependientes
   - **Medium**: 2-5 archivos, tests existentes
   - **High**: >5 archivos o módulos core (src/core/, src/orbital/)

3. Registrar en ledger:
   ```python
   ledger.add_action(
       action_type="run_test",
       target="plan-detection",
       diff_summary="Stack: python+typescript, blast_radius: medium (3 archivos)",
       rollback="",
   )
   ledger.add_approval("plan", approved_by="human", notes="Plan aprobado")
   ```

---

## Fase 3: TASKS

**Objetivo**: Descomponer en tasks atómicas con rollback por task.

### Pasos
1. Crear tasks atómicas (1 archivo a la vez = canary fix):
   ```
   Task 1: Crear src/security/oauth2.py (nuevo archivo)
   Task 2: Modificar src/api_v2/dependencies.py (añadir get_current_user)
   Task 3: Modificar src/api_v2/routers/auth_routes.py (añadir /oauth2/callback)
   Task 4: Añadir tests en src/tests/test_oauth2.py
   ```

2. Registrar cada task en el ledger con rollback:
   ```python
   ledger.add_action(
       action_type="edit_file",
       target="src/security/oauth2.py",
       diff_summary="Crear OAuth2Handler con authorize/callback",
       before_sha="abc123",
       after_sha="def456",
       rollback="git rm src/security/oauth2.py",
   )
   ```

3. Registrar approval:
   ```python
   ledger.add_approval("tasks", approved_by="auto", notes="4 tasks atómicas")
   ```

---

## Fase 4: IMPLEMENT

**Objetivo**: Implementar cada task (contextual TDD, canary fix).

### Pasos
1. Para cada task:
   - Hacer el cambio en el archivo
   - Registrar la acción en el ledger:
     ```python
     ledger.add_action(
         action_type="edit_file",
         target="src/security/oauth2.py",
         diff_summary="Implement OAuth2Handler.authorize()",
         before_sha="abc123",
         after_sha="def456",
         rollback="git checkout abc123 -- src/security/oauth2.py",
     )
     ```
   - Ejecutar tests del módulo afectado:
     ```bash
     python -m pytest src/tests/test_oauth2.py -x -q
     ```

2. Tras cada archivo, ejecutar `forge verify --quick` para detectar regresiones temprano.

3. Registrar approval:
   ```python
   ledger.add_approval("implement", approved_by="auto", notes="4 tasks implementadas")
   ```

---

## Fase 5: VERIFY

**Objetivo**: Ejecutar los 12 gates en paralelo.

### Pasos
1. Ejecutar todos los gates:
   ```bash
   python -m forge verify
   ```

2. Si algún gate falla, registrar el resultado en el ledger:
   ```python
   ledger.add_gate_result("tests_pass", passed=False, evidence="2 tests failed in test_oauth2.py")
   ```

3. Si todos pasan, registrar approval:
   ```python
   ledger.add_approval("verify", approved_by="auto", notes="6/6 hard gates PASS")
   ```

---

## Fase 6: CRITIQUE (si algún gate falla)

**Objetivo**: Reflexión verbal + memoria cross-session.

### Pasos
1. Buscar reflexiones similares en la memoria:
   ```python
   from forge import PersistentMemory
   mem = PersistentMemory("forge/data")
   similares = mem.find_similar("oauth2 token validation failure", top_n=5)
   for r in similares:
       print(f"- {r['summary']}")
       print(f"  Learnings: {r['key_learnings']}")
   ```

2. Reflexionar sobre la causa raíz:
   ```python
   mem.add_reflection(
       iteration_id="oauth2-fix-001",
       summary="OAuth2 token validation falló por expiración no manejada",
       verbal_reflection="El gate tests_pass falló porque el token de test expiraba antes de...",
       score=3.0,
       root_cause="Token expiración no validada en test fixture",
       files_affected=["src/tests/test_oauth2.py"],
       key_learnings=[
           "Usar tokens con expiración larga en tests (>1h)",
           "Mockear time.time() en tests de token expiry",
       ],
   )
   ```

---

## Fase 7: FIX

**Objetivo**: Architect/Editor + canary fix.

### Pasos
1. Aplicar el fix (1 archivo a la vez):
   ```python
   ledger.add_action(
       action_type="edit_file",
       target="src/tests/test_oauth2.py",
       diff_summary="Fix: usar token con expiración 24h en test fixture",
       before_sha="def456",
       after_sha="ghi789",
       rollback="git checkout def456 -- src/tests/test_oauth2.py",
   )
   ledger.record_canary_fix("src/tests/test_oauth2.py")
   ```

2. Re-ejecutar tests:
   ```bash
   python -m pytest src/tests/test_oauth2.py -x -q
   ```

---

## Fase 8: FINAL_VERIFY

**Objetivo**: Test suite completo Python + TypeScript.

### Pasos
1. Ejecutar forge verify completo:
   ```bash
   python -m forge verify
   ```

2. Verificar que todos los gates pasan:
   ```bash
   python -m forge report
   ```

3. Completar el ledger:
   ```python
   ledger.set_soft_score(9.0)
   summary = ledger.complete(status="pass")
   print(f"Run completo: {summary}")
   ```

4. Verificar integridad del ledger:
   ```bash
   python -m forge ledger verify .forge/my-feature/run_ledger.json
   ```

---

## 🚀 Entrega

### Pre-commit
```bash
git add -A
git commit -m "feat: add OAuth2 authentication (ledger: .forge/my-feature)"
```

El pre-commit hook verifica automáticamente:
- Integridad de todos los ledgers en `.forge/`
- ruff (Python lint)
- mypy (Python types, módulos core)
- eslint (TypeScript lint)
- madge (TypeScript circular imports)

### Push
```bash
git push origin feature/add-oauth2
```

GitHub Actions ejecuta automáticamente:
1. `ledger-verify`: verifica integridad de ledgers
2. `python-gates-quick`: ruff + mypy + radon + security + tests
3. `typescript-gates-quick`: eslint + tsc + madge + vitest + vite build
4. `forge-verify-full`: forge verify --quick completo

### Dashboard
```bash
python -m forge dashboard
# Abre reports/dashboard.html para ver el score actualizado
```

---

## 📊 Checkpoint de calidad

Antes de marcar un cambio como completo, verificar:

- [ ] Ledger creado y SPEC escrita
- [ ] Todas las acciones registradas con rollback
- [ ] 6/6 hard gates PASS
- [ ] Soft score ≥ 8.0/10
- [ ] Tests pasan (Python + TypeScript)
- [ ] `forge ledger verify` pasa
- [ ] `forge dashboard` generado
- [ ] Commit message incluye referencia al ledger

---

## ➡️ Ejemplos prácticos

- [Ejemplo 01: Fix de bug CRM](examples/01-fix-bug-crm.md)
- [Ejemplo 02: Añadir tool N4](examples/02-add-tool.md)
- [Ejemplo 03: Refactor de módulo](examples/03-refactor-module.md)
