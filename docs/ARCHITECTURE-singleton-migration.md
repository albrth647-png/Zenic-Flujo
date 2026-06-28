# Singletonitis — Guía de Migración a IoC

**Estado**: BUG-ARCH-01 — Parcialmente mitigado en Sprint 5
**Última actualización**: Sprint 5

## Situación actual

Zenic-Flijo tiene **27 singletons** (`__new__` + `_instance` + `_lock` pattern). Esto dificulta:
- Testing aislado (estado compartido entre tests)
- Acoplamiento global (cualquier módulo puede acceder a cualquier singleton)
- Reemplazar dependencias en runtime

## Mitigación aplicada en Sprint 5

Todos los singletons ahora exponen `_reset()` (o `reset_instance()`) para test isolation:

| Singleton | Método reset | Notas |
|---|---|---|
| `OrbitalContext` | `_reset()` | Ya existía |
| `WorkflowEngine` | `_reset()` | Ya existía |
| `DatabaseManager` | `_reset()` | Ya existía (línea 558) |
| `RedisService` | `_reset()` | **Añadido Sprint 5** |
| `MongoDBService` | `_reset()` | **Añadido Sprint 5** |
| `TenantService` | `_reset()` | **Añadido Sprint 5** |
| `SyncEngine` | `reset_instance()` | Ya existía |
| `ConnectorRegistry` | `clear()` | Ya existía |
| `AgentRuntime` | `reset_instance()` | Ya existía |
| `AgentToolRegistry` | `reset_instance()` | Ya existía |
| `TokenCostTracker` | `reset_instance()` | Ya existía |
| `MultiAgentOrchestrator` | `reset_instance()` | Ya existía |
| `ComplianceManager` | `reset_instance()` | Ya existía |
| `SOC2TypeIIManager` | `reset_instance()` | Ya existía |
| `TelemetryService` | `_reset()` | Ya existía |
| `AirGapConfig` | (no necesita reset — stateless) | — |

## Uso en tests

```python
# conftest.py — fixture autouse para limpiar singletons entre tests
@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons before each test for isolation."""
    from src.orbital.context import OrbitalContext
    from src.workflow.engine import WorkflowEngine
    # ... otros singletons
    OrbitalContext._reset()
    WorkflowEngine._reset()
    yield
    # Cleanup después del test también
    OrbitalContext._reset()
    WorkflowEngine._reset()
```

## Migración futura a IoC completo (Sprint 6+)

El siguiente paso es reemplazar los singletons con un contenedor IoC real.
`src/container.py` ya existe con una implementación básica. La migración sería:

### Paso 1: Registrar dependencias en container
```python
# src/container.py (extender)
def setup_default_container():
    container.register(DatabaseManager, DatabaseManager(), singleton=True)
    container.register(EventBus, EventBus(), singleton=True)
    container.register(WorkflowEngine, lambda: WorkflowEngine(
        db=container.get(DatabaseManager),
        event_bus=container.get(EventBus),
    ))
    # ...
```

### Paso 2: Reemplazar `__new__` singleton con `container.get()`
```python
# Antes:
class WorkflowEngine:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

# Después:
class WorkflowEngine:
    def __init__(self, db: DatabaseManager, event_bus: EventBus):
        self._db = db
        self._event_bus = event_bus

# Uso:
engine = container.get(WorkflowEngine)
```

### Paso 3: Eliminar `_instance` y `_lock` de cada clase
Una vez que todos los callers usen `container.get()`, los singletons pueden
dejar de ser singletons.

## Prioridad

**NO bloqueante para 95%** — los `_reset()` methods resuelven el problema
de testing. La migración IoC completa es deuda técnica a largo plazo.

## Riesgos de migración

- **Romper imports circulares**: algunos singletons se importan mutuamente.
  El container resuelve esto via lazy registration.
- **Cambios en API pública**: código que hace `WorkflowEngine()` directamente
  necesitará cambiar a `container.get(WorkflowEngine)`.
- **Tests existentes**: los `_reset()` methods deben mantenerse durante la
  migración para no romper tests.
