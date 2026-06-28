---
name: any-best-practices
description: |
  Guía de tipado en Python para decidir cuándo usar `Any`, cuándo evitarlo y cómo
  reemplazarlo por alternativas más seguras (`object`, `TypeVar`, `Protocol`,
  `Union`, `Optional`, tipos concretos). Aplica reglas estrictas de Zenic-Flujo
  (mypy strict mode) y el orden de preferencia entre alternativas.
  Úsala cuando vayas a escribir o revisar código Python con anotaciones de tipo,
  al resolver errores de mypy relacionados con `Any`, o al migrar código legacy
  sin tipar. NO la uses para TypeScript ni para código donde el tipado ya está
  resuelto con tipos concretos.
load: on-demand
tokens: ~900
---

# Any Best Practices — Guía de Tipado Python para Zenic-Flujo

> **Fuente**: `docs/research/any-best-practices.md` (2026-06-27).
> **Stack**: Python 3.11+, mypy strict mode, Pydantic v2.
> **Regla de oro**: cada `Any` es un agujero en el sistema de tipos. Si introduces
> uno, debes justificarlo con un comentario `# TODO: tipar` o `# type: ignore[...]`.

---

## 1. Cuándo SÍ usar `Any` (casos legítimos)

Estos son los ÚNICOS casos aceptables. En todos ellos, documenta el motivo.

### 1.1. Datos dinámicos externos (JSON, API responses) antes de validar

```python
from typing import Any
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str

def parse_user(data: Any) -> User:
    """Recibe JSON sin tipar desde una fuente externa, retorna modelo validado."""
    return User(**data)
```

**Preferido**: usar `pydantic.TypeAdapter` o `msgspec` para validar el schema.

### 1.2. Decoradores y wrappers genéricos (`*args, **kwargs`)

```python
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

def log_calls(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        print(f"Llamando {func.__name__}")
        return func(*args, **kwargs)
    return wrapper  # type: ignore[return-value]
```

`*args: Any, **kwargs: Any` es el patrón canónico en wrappers transparentes.

### 1.3. Código legacy en migración activa

`Any` como **tipo temporal** durante la transición a tipado estricto.
Debe reemplazarse progresivamente (ver §4 — Plan de migración).

### 1.4. Tipos imposibles de expresar en el sistema de tipos

Casos raros: `pickle.loads()`, APIs que devuelven tipos heterogéneos por
construcción. Siempre con comentario justificando la excepción.

---

## 2. Cuándo NO usar `Any` (antipatrones y alternativas)

### 2.1. ❌ `Any` en parámetros que aceptan "cualquier cosa" → usar `object`

`object` es el verdadero "cualquier tipo": fuerza `isinstance` o type narrowing.

```python
# ❌ MAL: desactiva el type checking
def print_value(x: Any) -> None:
    print(x)

# ✅ BIEN: fuerza narrowing explícito
def print_value(x: object) -> None:
    if isinstance(x, (int, float)):
        print(f"{x:.2f}")
    else:
        print(x)
```

### 2.2. ❌ `Any` como tipo de retorno cuando se conoce el tipo → tipo concreto

```python
# ❌ MAL
def get_user() -> Any:
    return {"id": 1, "name": "Alice"}

# ✅ BIEN
def get_user() -> dict[str, str | int]:
    return {"id": 1, "name": "Alice"}

# ✅ MEJOR: modelo con nombre
class User(TypedDict):
    id: int
    name: str

def get_user() -> User: ...
```

### 2.3. ❌ Colecciones genéricas sin parámetros → parametrizar

```python
# ❌ MAL
def process(data: dict) -> None: ...

# ✅ BIEN
def process(data: dict[str, Any]) -> None: ...

# ✅ MEJOR
def process(data: dict[str, str | int]) -> None: ...
```

Lo mismo aplica a `list`, `tuple`, `set`, `Sequence`, `Mapping`, etc.

### 2.4. ❌ `Any` cuando se puede usar `TypeVar` (preservar tipo input→output)

```python
from typing import TypeVar

T = TypeVar("T")

# ❌ MAL: pierde el tipo
def first(items: list[Any]) -> Any:
    return items[0] if items else None

# ✅ BIEN: preserva el tipo
def first(items: list[T]) -> T | None:
    return items[0] if items else None

x = first([1, 2, 3])  # x es int | None, no Any
```

### 2.5. ❌ `Any` en atributos de clase sin inicialización → `X | None`

```python
class MyService:
    # ❌ MAL
    client: Any = None

    # ✅ BIEN
    client: HTTPClient | None = None
```

---

## 3. Orden de preferencia entre alternativas

De **menos seguro** a **más seguro**:

```
Any  →  object  →  TypeVar  →  Protocol  →  Union / X | Y  →  Tipo concreto
```

| Alternativa | Cuándo usarla |
|-------------|---------------|
| **Tipo concreto** (`str`, `int`, `HTTPClient`) | Sabes exactamente qué tipo es |
| **`object`** | Aceptas cualquier valor pero necesitas type safety (fuerza narrowing) |
| **`TypeVar`** | Necesitas preservar la relación entre input y output |
| **`Protocol`** | Aceptas cualquier objeto con ciertos métodos/atributos (duck typing seguro) |
| **`Union` / `X \| Y`** | El valor puede ser uno de varios tipos conocidos |
| **`Optional[X]` / `X \| None`** | El valor puede ser X o None |
| **`Any`** | **Último recurso**: datos externos sin schema, decoradores, migración temporal |

### 3.1. Protocol — duck typing seguro

```python
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None: ...

def render(obj: Drawable) -> None:
    obj.draw()  # ✅ mypy verifica que existe el método
```

### 3.2. TypeVar con bound — restricción estructural

```python
from typing import TypeVar

T = TypeVar("T", bound="BaseModel")

def save_all(models: list[T]) -> list[T]:
    for m in models:
        m.save()
    return models
```

---

## 4. Reglas Zenic-Flujo (mypy strict mode)

### 4.1. NUEVO código: `Any` prohibido sin justificación documentada

```python
# ❌ Rechazado en code review
def process(data: dict) -> None: ...

# ✅ Aprobado
def process(data: dict[str, int]) -> None: ...
```

Cada `Any` en código nuevo DEBE llevar:
- Un comentario `# TODO: tipar` si es deuda temporal, O
- Un `# type: ignore[código-mypy]` con razón específica, O
- Una justificación en el docstring si es un caso legítimo de §1.

### 4.2. CÓDIGO existente: reemplazar `Any` progresivamente

Prioridad de migración (de mayor a menor impacto):

1. `_initialized: Any` → `_initialized: bool`
2. `dict` / `tuple` / `list` sin parámetros → `dict[K, V]` / `tuple[X, ...]` / `list[X]`
3. Retornos `-> Any` → tipo concreto o `TypeVar`
4. Parámetros `Any` → `object` o tipo específico
5. Atributos de clase `Any` → `X | None` con tipo concreto

### 4.3. Excepciones documentadas permitidas

Solo se permite `Any` sin migrar en:
- Decoradores genéricos (`*args: Any, **kwargs: Any`)
- Callbacks donde el tipo es dinámico por diseño
- Datos externos sin schema (ANTES de validación Pydantic/msgspec)
- APIs de terceros cuyos tipos no están stubbed

**Cada uso debe tener un comentario explicativo**.

### 4.4. Flujo de revisión para PRs

Antes de aprobar un PR con `Any`:

1. **Identificar** todos los `Any` nuevos con `rg "\bAny\b" --type py`
2. **Clasificar** cada uno según §1 (legítimo) o §2 (antipatrón)
3. **Exigir** justificación documentada en cada caso legítimo
4. **Rechazar** antipatrones y proponer alternativa de §3
5. **Verificar** que mypy strict pasa: `mypy --strict src/`

---

## 5. Cheatsheet rápida de reemplazos

| Antipatrón | Reemplazo |
|------------|-----------|
| `x: Any = None` | `x: TipoConcreto \| None = None` |
| `def f(x: Any) -> Any` | `def f(x: object) -> TipoConcreto` |
| `def f() -> Any` | `def f() -> TipoConcreto` o `TypeVar` |
| `def f(items: list[Any]) -> Any` | `def f(items: list[T]) -> T \| None` |
| `def f(data: dict) -> None` | `def f(data: dict[str, X]) -> None` |
| `client: Any` | `client: HTTPClient \| None` |
| `data: Any` (JSON) | `data: dict[str, object]` + validador Pydantic |

---

## 6. Comandos de auditoría

```bash
# Contar usos de Any en el código
rg "\bAny\b" --type py --stats src/

# Buscar Any sin justificación (sin TODO ni type: ignore cercano)
rg "\bAny\b" --type py -A1 -B1 src/ | rg -v "TODO|type: ignore"

# Ejecutar mypy en modo estricto sobre el módulo afectado
mypy --strict src/<modulo>/

# Listar archivos con más ocurrencias de Any
rg -c "\bAny\b" --type py src/ | sort -t: -k2 -rn | head -20
```

---

## 7. Referencias

- [Python Typing Best Practices — Oficial](https://typing.python.org/en/latest/reference/best_practices.html)
- [mypy docs: Any vs object](https://mypy.readthedocs.io/en/stable/dynamic_typing.html)
- [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)
- [PEP 544 — Protocols](https://peps.python.org/pep-0544/)
- [Python docs: typing.Any](https://docs.python.org/3/library/typing.html#typing.Any)
- Documento interno: `docs/research/any-best-practices.md`

---

## 8. Tooling del proyecto (junio 2026)

Este proyecto incluye un stack de tooling para auditar y migrar `Any`. Úsalo en este orden:

### 8.1. Auditar estado actual

```bash
# Genera CSV + JSON + Markdown con todas las ocurrencias
python3 scripts/any_audit/any_audit.py run

# Crear/actualizar baseline (snapshot del count actual)
python3 scripts/any_audit/any_audit.py baseline --out .any-baseline.json

# Comparar contra baseline (modo enforce para CI)
python3 scripts/any_audit/any_audit.py run --baseline .any-baseline.json --enforce
```

Salida: `scripts/any_audit/reports/any_audit.{csv,json,md}`

### 8.2. Pre-commit hook (ratchet local)

El hook `any-ratchet` bloquea commits que introduzcan NUEVOS `Any` sin justificación
en archivos modificados. Ya configurado en `.pre-commit-config.yaml`.

```bash
# Instalar hooks
pre-commit install

# Bypass puntual (NO abusar)
ANY_RATCHET_ALLOW=1 git commit -m "..."
```

Justificaciones válidas (comentario en la misma línea o la anterior):
- `# legítimo: <razón>` — caso legítimo de §1
- `# TODO: tipar` — deuda reconocida con ticket
- `# type: ignore[<código>]` — supresión específica de mypy

### 8.3. CI (GitHub Action)

Workflow `.github/workflows/any-audit.yml`:
- Ejecuta auditoría en cada PR y push a `main`/`develop`.
- Publica un comment en el PR con el reporte markdown.
- Sube artifacts `any_audit.{csv,json,md}` (retención 30 días).
- Bloquea merge si el count sube vs baseline (a menos que el PR tenga label `any-bypass`).

### 8.4. Codemods LibCST (transformación mecánica)

```bash
# Listar codemods disponibles
python3 scripts/codemods/run_codemod.py list

# Dry-run sobre un archivo
python3 scripts/codemods/run_codemod.py apply auto-migrate-bare \
    --file src/connectors/sendgrid.py --dry-run

# Aplicar a un directorio
python3 scripts/codemods/run_codemod.py apply parametrize-bare-dict \
    --path src/connectors

# Aplicar solo a archivos modificados en git
python3 scripts/codemods/run_codemod.py apply-to-git-changed auto-migrate-bare
```

Codemods disponibles (todos determinísticos, reversibles, idempotentes):

| Codemod | Qué hace | Cobertura |
|---------|----------|-----------|
| `parametrize-bare-dict` | `dict` → `dict[str, Any]` | 893 casos |
| `parametrize-bare-list` | `list` → `list[Any]` | 22 casos |
| `parametrize-bare-tuple` | `tuple` → `tuple[Any, ...]` | 12 casos |
| `document-optional-any-attr` | `x: T = None` → `x: T \| None = None` | 15 casos |
| `auto-migrate-bare` | Combo de los 4 anteriores en una pasada | ~940 casos |

**Workflow recomendado**:
1. Auditar antes: `python3 scripts/any_audit/any_audit.py run`
2. Dry-run: `python3 scripts/codemods/run_codemod.py apply ... --dry-run`
3. Aplicar: `python3 scripts/codemods/run_codemod.py apply ...`
4. Ver diff: `git diff`
5. Tests: `pytest src/tests/`
6. Mypy: `mypy --strict src/<modulo>/`
7. Auditar después: `python3 scripts/any_audit/any_audit.py run`
8. Commit siguiendo plantilla `.github/pull_request_template.md`

### 8.5. Documentación complementaria

- Plan maestro: `docs/plans/any-migration-rollout.md`
- Setup del ratchet: `docs/plans/any-ratchet-setup.md`
- Investigación profunda: `docs/research/any-best-practices.md`
- Investigación IA zero-humo: `download/any-migration-research-zero-humo.md`

---

## 9. Casos reales del proyecto (junio 2026)

### 9.1. Conectores de APIs externas — `dict[str, Any]` ES aceptable

**Contexto:** 60+ conectores en `src/connectors/` llaman a APIs REST/SOAP que devuelven JSON dinámico.

**Decisión:** `dict[str, Any]` en el boundary del conector es **legítimo** si:
- El proveedor no publica OpenAPI spec (caso AFIP, SAT, DIAN, DTE).
- La respuesta se valida con Pydantic inmediatamente después.
- Hay un comentario `# legítimo: API externa sin schema` en la signatura.

**NO es legítimo:**
- `dict` sin parametrizar (usa codemod `parametrize-bare-dict`).
- `dict[str, Any]` que se propaga por 3+ capas internas sin validación.

**Evidencia:** Stripe, Slack, boto3, airflow y langchain aceptan `dict[str, Any]` en sus boundaries. Ver `download/any-migration-research-zero-humo.md` §5.

### 9.2. `bare_dict` es el antipatrón dominante

**Datos:** 893 de 1,587 ocurrencias (56%) son `dict` sin parametrizar.

**Acción:** Usar codemod `parametrize-bare-dict` para barrido mecánico seguro. Reduce el count sin introducir errores semánticos (el valor sigue siendo `Any`).

### 9.3. Atributos `: Any = None` en clases de servicio

**Patrón típico:**
```python
class MyService:
    client: Any = None  # inicializado en __init__
```

**Acción:** Codemod `document-optional-any-attr` lo transforma a `client: Any | None = None`. Después, manualmente reemplazar `Any` por el tipo concreto (`HTTPClient | None`).

### 9.4. Retornos `-> Any` en funciones de parseo

**Patrón típico:**
```python
def parse_response(data: bytes) -> Any:
    return json.loads(data)
```

**Acción manual (no mecánica):**
- Si el caller siempre hace `MyModel(**result)`: tipar como `dict[str, object]`.
- Si el caller accede por índice: tipar como `object` y forzar `isinstance` narrowing.
- Si es JSON heterogéneo: `dict[str, Any]` + comentario `# legítimo: JSON dinámico validado en caller`.

### 9.5. Wrappers de decoradores — `*args: Any, **kwargs: Any` ES legítimo

**Contexto:** `src/sdk/decorators/` contiene wrappers transparentes.

**Decisión:** `*args: Any, **kwargs: Any` en wrappers es **legítimo** (skill §1.2). NO aplicar codemods aquí. Documentar con `# legítimo: wrapper transparente`.

### 9.6. Límite técnico: `TypedDict` vs `dict[str, Any]`

**Issue mypy #4976 (abierto desde 2018):** no se puede pasar un `TypedDict` donde se espera `dict[str, Any]`. Es una frontera práctica del sistema de tipos.

**Implicación:** si una función interna recibe `dict[str, Any]` y un caller quiere pasarle un `TypedDict`, necesita `# type: ignore[arg-type]` o reformular la signatura con `Mapping[str, object]`.

**Recomendación:** en boundaries internos (no de API externa), preferir `Mapping[str, object]` sobre `dict[str, Any]` para evitar este problema.


---

## 10. Motor Orbital de auditoría (junio 2026)

El sistema de antipatrones `Any` ahora se ejecuta como un **ciclo del motor Orbital**
determinista circular. Esto NO reemplaza la auditoría clásica (`any_audit.py run`),
la orquesta como un caso de uso real del OrbitalEngine.

### 10.1. Arquitectura del ciclo

```
Auditoría Any → OVC → TOR → RCC → COD → Espectro → Reporte → Retro → Auditoría
```

Cada tick orbital ejecuta el ciclo completo sobre el inventario de ocurrencias:

| Pilar Orbital | Interpretación en auditoría Any |
|---|---|
| **OVC** (Orbita Variable Circular) | Cada módulo con deuda → VariableOrbital con θ=fase de deuda, A=amplitud, ω=velocidad de reducción |
| **TOR** (Tensión Orbital Reciproca) | Tensión de deuda entre 2 módulos. TOR alto = deuda correlacionada (refactor conjunto tiene sinergia) |
| **RCC** (Resonancia Ciclo Cerrado) | Detecta ciclos resonantes = hotspots de deuda que se retroalimentan (connectors↔sdk, api_v2↔mobile, etc.) |
| **COD** (Colapso Orbital Determinista) | Colapsa el sistema a estados estables = recomendación de orden de ataque |
| **Espectro** | Reporte multimodal: `modes` = estrategias de refactor, `primary_mode` = recomendación prioritaria |
| **Retroalimentación** | Ajuste de ω por módulo: alta deuda → ω bajo (refactor estable), deuda cero → ω alto (mantener monitoreo) |

### 10.2. Mapeo conceptual

| Concepto Any | Concepto Orbital | Implementación |
|---|---|---|
| Módulo (`src/connectors`, etc.) | `VariableOrbital` (grupo `modules`) | θ = 2π × √(deuda_real/total), A = √(deuda_real + 1) |
| Antipatrón (`bare_dict`, etc.) | `VariableOrbital` (grupo `antipatterns`) | θ = 2π × (count/total), A = √(count + 1) |
| Justificación (`# legítimo:`) | Reducción de amplitud efectiva | No es deuda → A = 1 mínimo |
| `CicloOrbital` | Agrupación de módulos correlacionados | Threshold 0.4 (resonancia significativa) |
| `TOR(i,j)` | Tensión de deuda = A_i × A_j × cos(θ_i - θ_j) | Módulos con misma proporción de deuda → resonancia |
| `RCC` | Hotspot = ciclo resonante | Refactorizar juntos tiene sinergia |
| `COD` | Recomendación colapsada | Orden óptimo de ataque |
| `Espectro.primary` | Estrategia prioritaria | Top módulos por valor orbital |
| `retrofeedback` | Ajuste al baseline | Módulos con deuda alta → ω bajo |

### 10.3. Uso

```bash
# Ejecutar auditoría orbital (5 ticks default)
python3 scripts/any_audit/any_audit.py orbital

# Especificar número de ticks
python3 scripts/any_audit/any_audit.py orbital --ticks 10

# Especificar path de scan y archivo de salida
python3 scripts/any_audit/any_audit.py orbital --path src/connectors --out /tmp/orbital.md
```

### 10.4. Output

El comando genera:

1. **Reporte markdown** (`scripts/any_audit/reports/any_audit_orbital.md`):
   - Hotspots de deuda (ciclos RCC resonantes)
   - Estrategia de refactor (espectro primary mode)
   - Top 10 tensiones de deuda (TOR)
   - Retroalimentación orbital (ajuste de ω por módulo)

2. **Consola**: resumen ejecutivo con métricas clave.

3. **OrbitalResult crudo**: accesible vía `engine.orbital_engine` para inspección.

### 10.5. API programática

```python
from src.orbital.any_audit import OrbitalAnyAuditEngine, AnyAuditMapper
from src.orbital.any_audit.mapper import ModuleStats, AntipatternStats

# Auditoría orbital completa
engine = OrbitalAnyAuditEngine(ticks=5)
result = engine.run_audit()

# Inspección del resultado
print(f"Hotspots: {len(result.hotspots)}")
print(f"Estrategia: {result.refactor_strategy[0]}")
print(f"Retroalimentación: {result.retrofeedback}")

# Mapper standalone (sin OrbitalEngine)
mapper = AnyAuditMapper()
stats = ModuleStats(name="src/test", total=100, legitimate_imports=10, justified=20, real_debt=70)
var = mapper.module_to_variable(stats)
print(f"Variable orbital: {var.name}, θ={var.theta:.4f}, A={var.amplitude:.4f}")
```

### 10.6. Módulos

| Archivo | Rol |
|---|---|
| `src/orbital/any_audit/__init__.py` | Exports públicos |
| `src/orbital/any_audit/mapper.py` | Conversión Any stats → VariableOrbital + CicloOrbital |
| `src/orbital/any_audit/adapter.py` | `OrbitalAnyAuditEngine`: orquesta auditoría como ciclo orbital |
| `src/orbital/any_audit/tests/` | 21 tests cubriendo mapper, adapter e integración |

### 10.7. Ciclos de correlación predefinidos

El mapper define 6 ciclos de correlación de deuda basados en arquitectura del proyecto:

| Ciclo | Módulos | Racional |
|---|---|---|
| `connectors_sdk` | connectors, sdk, sdk/base | Conectores usan SDK |
| `api_mobile` | api_v2, api_v2/routers, mobile | APIs comparten tipos |
| `hat_orchestration` | hat/level1_orchestrator, hat/level5_tools, workflow | Orquestación de workflows |
| `agents_wrappers` | agents, sdk/decorators | Wrappers de agentes |
| `data_persistence` | data, tenant, workflow | Persistencia compartida |
| `security_compliance` | security, compliance, tenant | Multi-tenant security |

Cada ciclo se registra en el OrbitalEngine con threshold 0.4. Si la resonancia
excede el threshold, el ciclo aparece como hotspot en el reporte.

### 10.8. Diferencia con auditoría clásica

| Aspecto | `any_audit.py run` | `any_audit.py orbital` |
|---|---|---|
| Motor | AST walk directo | OrbitalEngine (5 pilares) |
| Output | CSV + JSON + MD estático | MD dinámico con espectro colapsado |
| Hotspots | No detecta | Detecta resonancia entre módulos |
| Estrategia | No sugiere | Orden de ataque priorizado |
| Retroalimentación | No | Ajuste de ω por módulo |
| Determinismo | Total | Total (OrbitalEngine es determinista) |
| Performance | O(N) por archivo | O(N²) por tick (matriz TOR) |
| Use case | CI gate, ratchet | Análisis estratégico de deuda |

**Recomendación:** usar `run` para CI/ratchet (rápido, blocking) y `orbital`
para análisis periódico de deuda (mensual/trimestral, orientativo).
