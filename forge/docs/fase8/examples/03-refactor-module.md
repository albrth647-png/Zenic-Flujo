# Ejemplo 03: Refactor de Módulo con Gates y Rollback

> **Tiempo estimado**: 1 hora
> **Stack**: Python
> **Blast radius**: High (3 archivos modificados, 56 tests afectados)

---

## 🎯 Objetivo

Refactorizar `data_specialist.route_action` (CC=52, rank F) usando dict dispatch pattern. Este es el refactor real aplicado en Fase 1 del rollout.

---

## Fase 1: SPECIFY

```bash
python -m forge ledger init .forge/refactor-data-specialist --run-id "refactor-route-action"
```

```python
from forge import RunLedger
ledger = RunLedger(".forge/refactor-data-specialist", run_id="refactor-route-action")
ledger.set_spec("""
Refactor: data_specialist.route_action (CC=52, rank F) → dict dispatch (target CC<10).

Causa: Cadena if/elif sobre keywords de descripción hace la función crecer indefinidamente.

Fix: Extraer _ROUTING_TABLE (tuple de tuplas) + métodos _match_action/_match_tool.

Criterio de salida:
- complexity_max: route_action CC<10
- tests_pass: 56 tests existentes pasan sin cambios
- lint_clean: ruff clean
- no_security_issues: 0 HIGH
""")
ledger.add_approval("specify", approved_by="human")
```

---

## Fase 2: PLAN

### Análisis del código actual

```python
# ANTES (CC=52):
def route_action(self, subtask):
    desc = subtask.get("description", "").lower()
    if any(kw in desc for kw in ["postgres", "postgresql", "sql"]):
        if any(kw in desc for kw in ["listar tablas"]):
            return "postgresql", "list_tables", params
        if any(kw in desc for kw in ["esquema"]):
            return "postgresql", "get_schema", params
        # ... 20+ más branches
    if any(kw in desc for kw in ["drive"]):
        if any(kw in desc for kw in ["subir"]):
            return "drive", "upload", params
        # ... más branches
    # ... 3 más bloques if
```

### Estrategia: Dict Dispatch

```python
# DESPUÉS (CC≈8):
_ROUTING_TABLE = (
    (("postgres", "postgresql", "sql"), [
        (("listar tablas",), "list_tables"),
        (("esquema",), "get_schema"),
        # ...
    ], "query", "postgresql"),
    # ...
)

def route_action(self, subtask):
    desc = subtask.get("description", "").lower()
    for tool_keywords, actions, default, tool_name in self._ROUTING_TABLE:
        if any(kw in desc for kw in tool_keywords):
            action_name = self._match_action(desc, actions, default)
            return tool_name, action_name, params
    return "data_keeper", "list_collections", params
```

```python
ledger.add_action(
    action_type="run_test",
    target="plan-detection",
    diff_summary="Stack: python, blast_radius: high (1 archivo refactor, 56 tests deben pasar)",
    rollback="",
)
ledger.add_approval("plan", approved_by="human", notes="Patrón dict dispatch probado en invoice_specialist")
```

---

## Fase 3-4: TASKS + IMPLEMENT (Canary Fix)

### Task 1: Añadir `_ROUTING_TABLE` y métodos auxiliares

```python
# src/hat/level3_specialists/datos_auto/data_specialist.py

class DataSpecialist(SpecialistAgent):
    # Tabla de routing por tool (refactorizado de CC=52 a CC≈8)
    _ROUTING_TABLE: tuple[tuple[
        tuple[str, ...],
        list[tuple[tuple[str, ...], str]],
        str,
        str,
    ], ...] = (
        (
            ("postgres", "postgresql", "sql", "base datos", "base de datos", "consulta sql"),
            [
                (("listar tablas", "list tables", "ver tablas"), "list_tables"),
                (("esquema", "schema", "estructura tabla"), "get_schema"),
                (("insertar", "crear registro", "alta", "insert"), "insert"),
                (("actualizar", "modificar", "update"), "update"),
                (("ejecutar", "execute", "ddl", "alter", "create table"), "execute"),
            ],
            "query",
            "postgresql",
        ),
        # ... 3 más entradas (drive, sheets, data_keeper)
    )

    def _match_action(self, desc: str, actions: list[tuple[tuple[str, ...], str]], default: str) -> str:
        """Devuelve la primera action cuyas keywords matcheen, sino default."""
        for keywords, action_name in actions:
            if any(kw in desc for kw in keywords):
                return action_name
        return default

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask.

        Refactorizado (Forge Fase 1.4) dividiendo en _ROUTING_TABLE + _match_action.
        Antes CC=52, ahora CC≈8.
        """
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        for tool_keywords, actions, default_action, tool_name in self._ROUTING_TABLE:
            if any(kw in desc for kw in tool_keywords):
                action_name = self._match_action(desc, actions, default_action)
                return tool_name, action_name, params

        return "data_keeper", "list_collections", params
```

### Registrar acción en ledger

```python
import subprocess
before_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()

# ... aplicar el cambio ...

ledger.add_action(
    action_type="edit_file",
    target="src/hat/level3_specialists/datos_auto/data_specialist.py",
    diff_summary="Refactor route_action: CC=52 → CC≈8 con _ROUTING_TABLE dict dispatch",
    before_sha=before_sha,
    after_sha="def456",
    rollback=f"git checkout {before_sha} -- src/hat/level3_specialists/datos_auto/data_specialist.py",
    stack="python",
    blast_radius="high (3 archivos dependientes, 56 tests afectados)",
)
```

---

## Fase 5: VERIFY

### Canary: ejecutar tests del módulo afectado PRIMERO

```bash
python -m pytest src/tests/hat/hardened/test_datos_auto_specialists.py -v
```

**Salida**: `56 passed in 7.73s` ✅

### Ejecutar gates completos

```bash
python -m forge check-module src/hat/level3_specialists/datos_auto/
```

### Verificar complexity

```bash
radon cc src/hat/level3_specialists/datos_auto/data_specialist.py -s -n C
```

**Salida esperada**: `route_action` ya no aparece (CC<6, rank B o mejor)

```python
ledger.add_gate_result("tests_pass", passed=True, evidence="56 tests passed in 7.73s")
ledger.add_gate_result("complexity_max", passed=True, evidence="route_action CC=8 (was 52)")
ledger.add_gate_result("lint_clean", passed=True, evidence="ruff: 0 issues")
ledger.add_approval("verify", approved_by="auto", notes="3/3 gates PASS, CC 52→8")
```

---

## Fase 6-7: CRITIQUE + FIX (si necesario)

Si algún gate fallara, buscar en memoria patrones similares:

```python
from forge import PersistentMemory
mem = PersistentMemory("forge/data")
similares = mem.find_similar("dict dispatch complexity refactor", top_n=3)
# → encuentra "forge-phase1-complexity-refactor" con learnings sobre _ROUTING_TABLE
```

En este caso, todos los gates pasaron, así que se omite CRITIQUE/FIX.

---

## Fase 8: FINAL_VERIFY + Entrega

```python
ledger.set_soft_score(9.5)
summary = ledger.complete(status="pass")
print(f"✅ Refactor completado: {summary}")
```

```bash
python -m forge ledger verify .forge/refactor-data-specialist/run_ledger.json

git add -A
git commit -m "refactor: route_action CC 52→8 via dict dispatch (ledger: .forge/refactor-data-specialist)"
git push origin refactor/route-action
```

---

## 📊 Resultado

| Métrica | Antes | Después | Δ |
|---|---|---|---|
| CC route_action | 52 (rank F) | 8 (rank C) | **-44** ✅ |
| Tests | 56 pasan | 56 pasan | 0 (sin regresiones) |
| Gates PASS | — | 6/6 hard | ✅ |
| Score | — | 9.5/10 | ✅ |
| Rollback | — | `git checkout <sha>` | ✅ definido |

---

## 🔄 Rollback (si algo fallara en producción)

Si el refactor introdujera un bug no detectado por tests:

```bash
# Rollback usando el comando registrado en el ledger
git checkout abc123 -- src/hat/level3_specialists/datos_auto/data_specialist.py

# Registrar rollback en ledger
python -c "
from forge import RunLedger
ledger = RunLedger('.forge/refactor-data-specialist')
ledger.record_rollback(0, reason='Bug en producción: route_action no maneja caso edge X')
"
```

---

## 🎓 Lección registrada en memoria

```python
mem.add_reflection(
    iteration_id="refactor-route-action-dict-dispatch",
    summary="Refactor route_action CC=52→8 con dict dispatch _ROUTING_TABLE",
    verbal_reflection="El patrón dict dispatch con _ROUTING_TABLE redujo CC drásticamente...",
    score=9.5,
    key_learnings=[
        "Dict dispatch (_ROUTING_TABLE) es superior a if/elif para routing con >5 branches",
        "Tuple[tuple[A,B,C,D], ...] es preferible a list[tuple[...]] para class attributes (RUF012)",
        "Métodos auxiliares _match_action/_match_tool separan concerns y reducen CC",
        "Canary fix: ejecutar tests del módulo afectado PRIMERO antes de forge verify completo",
        "Blast radius high requiere rollback definido por archivo, no por commit",
    ],
)
```

Esta reflexión ya está en `forge/data/memory.json` y será encontrada por `find_similar("dict dispatch complexity refactor")` en futuras sesiones.
