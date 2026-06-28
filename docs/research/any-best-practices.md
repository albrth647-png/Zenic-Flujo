# Any Type: Buenas Prácticas y Alternativas

> **Propósito**: Guía de referencia para el equipo de Zenic-Flujo sobre cuándo usar `Any`, cuándo evitarlo, y cómo reemplazarlo correctamente.
> **Basado en**: Python typing oficial, mypy docs, mejores prácticas de la comunidad.
> **Fecha**: 2026-06-27

---

## 1. ¿Qué es `Any`?

`Any` es un tipo especial en el sistema de typing de Python. Cuando una variable se anota como `Any`, el type checker **desactiva completamente la verificación de tipos** para esa variable:

```python
x: Any = "hola"
x = 42        # ✅ no error
x.inexistente()  # ✅ no error (el type checker no dice nada)
```

Esto significa que `Any` **es un agujero de seguridad en el sistema de tipos**. Cada `Any` que introduces reduce la cobertura de mypy y permite que bugs pasen desapercibidos.

---

## 2. Cuándo SÍ usar `Any`

### 2.1. Datos dinámicos externos (JSON, API responses)

Cuando recibes datos de una fuente externa y el tipo no se conoce hasta runtime:

```python
def parse_response(data: Any) -> MyModel:
    """Recibe JSON sin tipar, retorna modelo validado."""
    return MyModel(**data)
```

**Mejor aún**: usa `json.loads` y luego un validador (Pydantic, msgspec).

### 2.2. Decoradores y wrappers genéricos

```python
from functools import wraps
from collections.abc import Callable

F = TypeVar("F", bound=Callable[..., Any])

def log_calls(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        print(f"Llamando {func.__name__}")
        return func(*args, **kwargs)
    return wrapper  # type: ignore[return-value]
```

En `*args: Any, **kwargs: Any` es aceptable porque los argumentos pueden ser de cualquier tipo.

### 2.3. Código legacy en migración

Cuando estás migrando un código base grande sin tipos, `Any` sirve como **tipo temporal** durante la transición. Pero debe reemplazarse progresivamente.

### 2.4. Cuando el tipo es literalmente imposible de expresar

Casos muy raros. Por ejemplo, `pickle.loads()` retorna `Any` porque puede deserializar cualquier objeto.

---

## 3. Cuándo NO usar `Any` (y qué usar en su lugar)

### 3.1. ❌ `Any` en parámetros que aceptan "cualquier cosa"

Usa `object` en su lugar:

```python
# ❌ MAL: acepta Any, desactiva type checking
def print_value(x: Any) -> None:
    print(x)

# ✅ BIEN: acepta object, obliga a usar isinstance
def print_value(x: object) -> None:
    if isinstance(x, (int, float)):
        print(f"{x:.2f}")
    else:
        print(x)
```

`object` es el **verdadero "cualquier tipo"** : fuerza al llamante a pasar valores válidos y al implementador a hacer type narrowing.

### 3.2. ❌ `Any` como tipo de retorno cuando se conoce el tipo concreto

```python
# ❌ MAL: el que llama no sabe qué recibe
def get_user() -> Any:
    return {"id": 1, "name": "Alice"}

# ✅ BIEN: tipo concreto
def get_user() -> dict[str, str | int]:
    return {"id": 1, "name": "Alice"}

# ✅ MEJOR: modelo con nombre
class User(TypedDict):
    id: int
    name: str

def get_user() -> User: ...
```

### 3.3. ❌ `Any` para colecciones genéricas sin parámetros

```python
# ❌ MAL: dict sin parámetros de tipo
def process(data: dict) -> None: ...

# ✅ BIEN: dict con parámetros
def process(data: dict[str, Any]) -> None: ...

# ✅ MEJOR: tipado más estricto
def process(data: dict[str, str | int]) -> None: ...
```

### 3.4. ❌ `Any` cuando se puede usar `TypeVar`

Cuando necesitas que el tipo se preserve a través de una función:

```python
from typing import TypeVar

T = TypeVar("T")

# ❌ MAL: retorna Any, pierde la info del tipo
def first(items: list[Any]) -> Any:
    return items[0] if items else None

# ✅ BIEN: preserva el tipo
def first(items: list[T]) -> T | None:
    return items[0] if items else None

x = first([1, 2, 3])  # x es int | None, no Any
```

### 3.5. ❌ `Any` en variables de clase sin inicialización

```python
class MyService:
    # ❌ MAL: Any desactiva type checking
    client: Any = None

    # ✅ BIEN: Optional con tipo concreto
    client: HTTPClient | None = None
```

---

## 4. Alternativas a `Any` (ordenadas de más a menos estrictas)

| Alternativa | Cuándo usarla |
|------------|---------------|
| **Tipo concreto** (`str`, `int`, `HTTPClient`) | Cuando sabes exactamente qué tipo es |
| **`object`** | Cuando aceptas cualquier valor pero necesitas type safety |
| **`TypeVar`** | Cuando necesitas preservar la relación entre input y output |
| **`Protocol`** | Cuando aceptas cualquier objeto que tenga ciertos métodos/atributos |
| **`Union` / `X \| Y`** | Cuando el valor puede ser uno de varios tipos conocidos |
| **`Optional[X]` / `X \| None`** | Cuando el valor puede ser X o None |
| **`Any`** | **Último recurso**: datos externos sin schema, decoradores, migración temporal |

### Protocol (duck typing seguro)

```python
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None: ...

def render(obj: Drawable) -> None:
    obj.draw()  # ✅ mypy sabe que tiene método draw()
```

### TypeVar con bound

```python
from typing import TypeVar

T = TypeVar("T", bound="BaseModel")

def save_all(models: list[T]) -> list[T]:
    for m in models:
        m.save()
    return models
```

---

## 5. Reglas para Zenic-Flujo

Basado en el estado actual del proyecto (mypy strict mode, 145+ errores en `src/core/`):

### 5.1. NUEVO código: prohibido `Any` sin justificación documentada

```python
# ❌ Rechazado en code review
def process(data: dict) -> None: ...

# ✅ Aprobado
def process(data: dict[str, int]) -> None: ...
```

### 5.2. CÓDIGO existente: reemplazar `Any` progresivamente

Prioridad:
1. `_initialized: Any` → `_initialized: bool`
2. `dict` / `tuple` sin parámetros → `dict[str, X]` / `tuple[X, ...]`
3. Retornos `-> Any` → tipo concreto o `TypeVar`
4. Parámetros `Any` → `object` o tipo específico

### 5.3. Excepciones documentadas

Solo se permite `Any` en:
- Decoradores genéricos (`*args: Any, **kwargs: Any`)
- Callbacks donde el tipo es dinámico
- Datos externos sin schema (antes de Pydantic validation)
- **Cada uso debe tener un comentario `# TODO: tipar` o `# type: ignore[arg-type]`**

### 5.4. Preferir siempre la alternativa más específica

```
Any → object → TypeVar → Protocol → Union → Tipo concreto
(menos seguro)                         (más seguro)
```

---

## 6. Referencias

- [Python Typing Best Practices - Oficial](https://typing.python.org/en/latest/reference/best_practices.html)
- [mypy docs: Any vs object](https://mypy.readthedocs.io/en/stable/dynamic_typing.html)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [Python docs: typing.Any](https://docs.python.org/3/library/typing.html#typing.Any)
