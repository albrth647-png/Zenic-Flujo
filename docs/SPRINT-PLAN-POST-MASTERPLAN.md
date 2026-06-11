# 🚀 Plan de Sprints Post-Masterplan
## Workflow Determinista — Evolución Competitiva

**Fecha inicio:** Junio 2026
**Referencia:** "Más Allá del Workflow Determinista" (PDF análisis estratégico)
**Objetivo:** Cerrar la brecha con n8n y plataformas industriales

---

## 📋 Resumen Ejecutivo

| Sprint | Estado | Descripción | Tests |
|--------|--------|-------------|-------|
| **Sprint 5** | ✅ COMPLETADO | Capa de IA Opcional | 45 tests |
| **Sprint 6** | ✅ COMPLETADO | Code Node (Python sandbox seguro) | 34 tests |
| **Sprint 7** | ✅ COMPLETADO | Integraciones (Gmail, Sheets, Telegram, Slack) | 37 tests |
| **TOTAL** | — | 14 archivos nuevos, ~1500+ líneas | **116 tests** |

---

## ✅ SPRINT 5: CAPA DE IA OPCIONAL — COMPLETADO

### Objetivo
Permitir que un LLM genere workflows JSON a partir de texto libre, manteniendo la ejecución 100% determinista.

### Archivos creados
| Archivo | Descripción | Líneas |
|---------|-------------|--------|
| `src/nlu/ai_config.py` | Configuración multi-proveedor (Ollama, OpenAI, Anthropic) | ~180 |
| `src/nlu/ai_generator.py` | WorkflowAIGenerator con prompt template y validación | ~280 |
| `src/tests/test_nlu_ai_config.py` | Tests de configuración | ~200 |
| `src/tests/test_nlu_ai_generator.py` | Tests del generador | ~250 |

### Archivos modificados
| Archivo | Cambio |
|---------|--------|
| `src/nlu/pipeline.py` | Etapa 13: `ai_generate()` + función `ai_generate_workflow()` |
| `src/web/app.py` | Endpoint `/api/nlu/ai-generate` (3 modos: ai, hybrid, deterministic) |

### Arquitectura
```
USUARIO escribe texto libre
       ↓
┌──────────────────────────────┐
│  Pipeline NLU (etapas 1-12)  │  ← Determinista, sin IA
└──────────────────────────────┘
       ↓ (si falla o usuario pide IA)
┌──────────────────────────────┐
│  WorkflowAIGenerator         │  ← LLM genera JSON
│  - Prompt template seguro    │
│  - Validación post-generación│
│  - Fallback al compilador    │
└──────────────────────────────┘
       ↓
WORKFLOW JSON LISTO
```

### Proveedores soportados
- **Ollama** (preferido): 100% local, sin datos a terceros
- **OpenAI**: GPT-4o-mini en la nube
- **Anthropic**: Claude en la nube

### Modos del endpoint
- `deterministic`: Solo compilador NLU (sin IA)
- `ai`: Solo LLM (requiere proveedor configurado)
- `hybrid`: Determinista primero → fallback a IA

### Tests: 45/45 ✅

---

## ✅ SPRINT 6: CODE NODE (Python) — COMPLETADO

### Objetivo
Permitir al usuario escribir código Python custom dentro de un paso del workflow, con sandbox seguro.

### Archivos creados
| Archivo | Descripción | Líneas |
|---------|-------------|--------|
| `src/tools/code_runner/__init__.py` | Package init | ~5 |
| `src/tools/code_runner/sandbox.py` | Sandbox seguro con __import__ restringido, signal.SIGALRM | ~250 |
| `src/tools/code_runner/service.py` | CodeRunnerTool (run_python + validate) | ~170 |
| `src/tests/test_code_runner.py` | 34 tests de sandbox, seguridad y service | ~280 |

### Archivos modificados
| Archivo | Cambio |
|---------|--------|
| `src/main.py` | Registrar CodeRunnerTool en el engine |
| `src/nlu/compiler.py` | Agregar "code_runner" a KNOWN_TOOLS |
| `src/nlu/validator.py` | Agregar actions de code_runner |

### Seguridad del sandbox
- **Imports restringidos**: Solo módulos seguros (math, json, datetime, re, collections, etc.)
- **Builtins bloqueados**: eval, exec, compile, open, __import__, breakpoint, exit, quit, input, globals, locals
- **__import__ restringido**: Función safe_import que solo permite SAFE_MODULES
- **Timeout**: signal.SIGALRM con cleanup en finally
- **Reserved keys**: input_vars no puede sobreescribir __builtins__, __import__, eval, exec, compile
- **Validación AST**: Detecta imports de módulos no seguros

### Tests: 34/34 ✅

### Ejemplo de uso en workflow
```json
{
    "id": 5,
    "tool": "code_runner",
    "action": "run_python",
    "params": {
        "code": "result = sum([item['price'] * item['qty'] for item in items])",
        "input_vars": {"items": "$input.carrito"},
        "output_var": "total"
    }
}
```

---

## ✅ SPRINT 7: INTEGRACIONES — COMPLETADO

### Objetivo
Agregar 4 integraciones nativas como tools registradas en el sistema.

### Integraciones
| Integración | API | Autenticación |
|-------------|-----|---------------|
| **Gmail** | Gmail API v1 | OAuth2 |
| **Google Sheets** | Sheets API v4 | Service Account |
| **Telegram** | Bot API | Bot Token |
| **Slack** | Web API | Bot Token |

### Archivos a crear
| Archivo | Descripción |
|---------|-------------|
| `src/tools/integrations/__init__.py` | Package init |
| `src/tools/integrations/gmail_service.py` | Gmail API |
| `src/tools/integrations/sheets_service.py` | Google Sheets |
| `src/tools/integrations/telegram_service.py` | Telegram Bot |
| `src/tools/integrations/slack_service.py` | Slack Web API |
| `src/tests/test_integrations.py` | 25 tests mockeados |

### Archivos a modificar
| Archivo | Cambio |
|---------|--------|
| `src/main.py` | Registrar integraciones (solo si configuradas) |
| `src/web/app.py` | Endpoints CRUD para credenciales |
| `src/web/templates/settings.html` | Panel de integraciones |
| `src/data/database_manager.py` | Tabla `integration_credentials` |

### Tests planificados: 25 tests
- Cada integración: 5-7 tests mockeados
- Validación de credenciales
- Envío/recepción de datos
- Manejo de errores HTTP
- Autenticación OAuth2 (mock)

---

## 📊 ESTADO ACTUAL DEL PROYECTO

### Tests totales
```
Sprint 5 (IA):              45 tests ✅
Sprint 6 (Code Node):       34 tests ✅
Sprint 7 (Integraciones):   37 tests ✅
─────────────────────────────────────
Total nuevos:              116 tests

Tests existentes:          122+ tests ✅
Grand total:              ~238+ tests
```

### Archivos del proyecto
```
src/
├── nlu/
│   ├── ai_config.py          ← NUEVO (Sprint 5)
│   ├── ai_generator.py       ← NUEVO (Sprint 5)
│   ├── pipeline.py           ← MODIFICADO (etapa 13)
│   └── ...
├── tools/
│   ├── code_runner/          ← NUEVO (Sprint 6)
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── sandbox.py
│   ├── integrations/         ← NUEVO (Sprint 7)
│   │   ├── __init__.py
│   │   ├── gmail_service.py
│   │   ├── sheets_service.py
│   │   ├── telegram_service.py
│   │   └── slack_service.py
│   └── ...
├── web/
│   └── app.py               ← MODIFICADO (endpoint AI)
└── tests/
    ├── test_nlu_ai_config.py     ← NUEVO (Sprint 5)
    ├── test_nlu_ai_generator.py  ← NUEVO (Sprint 5)
    ├── test_code_runner.py       ← NUEVO (Sprint 6)
    └── test_integrations.py      ← NUEVO (Sprint 7)
```

---

## 🎯 PRÓXIMOS PASOS

1. **Completar Sprint 6** — Code Node con sandbox seguro
2. **Completar Sprint 7** — 4 integraciones nativas
3. **Rate limiting** — Agregar al endpoint AI
4. **UI updates** — Toggle IA en chat, CodeMirror en editor
5. **Documentación** — Actualizar README con nuevas features
6. **Pruebas físicas** — Instalador en Windows/Linux

---

## 📅 CRONOGRAMA

```
SEMANA 1:
  ✅ Sprint 5: Capa IA completado
  ✅ Sprint 6: Code Node completado
  ✅ Sprint 7: Integraciones completado

SEMANA 2:
  ⏳ Rate limiting + UI updates
  ⏳ Documentación + Instalador

SEMANA 3:
  ⏳ Sprint 7: Sheets + Slack
  ⏳ Tests finales + Code Review

SEMANA 4:
  ⏳ Documentación
  ⏳ Pruebas de instalador
  ⏳ Preparación para lanzamiento
```

---

*Última actualización: Sprint 7 completado — Junio 2026*
