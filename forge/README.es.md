# Code-Forge v1.0 — Zenic-Flujo Edition

**[Read in English](README.md)**

**Framework de ingeniería para agentes de IA.** Sandbox, run ledger, memoria persistente, y 12 gates de calidad bilingües (Python + TypeScript).

---

## ¿Qué es?

Code-Forge es un prompting loop de 8 fases para implementar cambios en código con calidad de producción. Diseñado específicamente para Zenic-Flujo (Python + TypeScript) y basado en 15+ fuentes académicas e industriales.

### Las 8 fases

```
TAREA → SPECIFY → PLAN → TASKS → IMPLEMENT → VERIFY → [CRITIQUE → FIX] → FINAL_VERIFY → ENTREGA
```

Cada fase tiene un propósito específico, herramientas asociadas, y puntos de control.

---

## Instalación

El skill ya viene incluido en el proyecto. No requiere instalación.

Para usarlo, simplemente invoca el skill en Codebuff:

```
Usa el skill code-forge para implementar [tu tarea aquí]
```

---

## Componentes del framework

| Componente | Propósito |
|-----------|-----------|
| **RunLedger** | Registro de auditoría con rollback obligatorio |
| **PersistentMemory** | Memoria cross-session con búsqueda Jaccard |
| **ForgeSandbox** | Sandbox dual (filesystem + network + rlimits) |
| **GateRunner** | 12 gates de calidad (6 hard + 6 soft) |

---

## Estructura del proyecto

```
forge/
├── __init__.py          # Entry point
├── run_ledger.py        # Run Ledger
├── memory.py            # Memoria persistente
├── sandbox.py           # Sandbox dual
├── gates.py             # 12 gates de calidad
├── SKILL.md             # Definición del skill (Codebuff lo lee)
├── README.md            # Documentación (inglés)
├── README.es.md         # Documentación (español)
└── references/
    ├── run-ledger.md    # Protocolo Run Ledger
    ├── sandbox.md       # Sandbox dual
    ├── gates.md         # 12 gates detallados
    ├── phases.md        # 8 fases detalladas
    └── examples.md      # Ejemplos de uso
```

---

## Uso básico

### Desde Python

```python
from forge import RunLedger, ForgeSandbox, GateRunner

# 1. Crear ledger
ledger = RunLedger("/tmp/workdir")
ledger.set_spec("Implementar feature X")

# 2. Ejecutar en sandbox
with ForgeSandbox("/ruta/del/proyecto") as sb:
    result = sb.run(["python3", "script.py"])

# 3. Ejecutar gates
runner = GateRunner("/ruta/del/proyecto")
report = runner.run_all()
runner.print_report()
```

### Como skill de Codebuff

```
@code-forge implementa validación de email en el formulario de registro
```

El skill ejecutará automáticamente el prompting loop completo.

---

## Licencia

Propietaria — Zenic-Flujo.
