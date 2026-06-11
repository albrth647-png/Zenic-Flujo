# Ruff Scan Report — Zenic-Flujo

**Fecha:** Junio 10, 2026
**Ruff versión:** 0.15.14

---

## Resumen Ejecutivo

| Categoría | Total |
|-----------|-------|
| **Bugs iniciales (E9 + F)** | **227 errores** |
| **Corregidos con `ruff --fix`** | **205** ✅ |
| **Restantes** | **22** |
| **Total inicial (todas categorías)** | **10,257 errores** |

La mayoría de los errores son **F401 (imports no utilizados)** — código que importa módulos/clases que nunca se usan. No se encontraron errores de sintaxis (E9) ni de runtime.

**Nota:** Los 22 errores restantes son en su mayoría imports en archivos de test donde Ruff no puede determinar estáticamente si son necesarios (fixtures de pytest, conftest, etc.).

---

## 1. 🔴 Bugs Críticos (E9 — Syntax/Runtime)

**0 errores.** No hay errores de sintaxis ni runtime.

---

## 2. 🟡 Bugs Funcionales (F — Pyflakes)

### 2.1 F401 — Imports No Utilizados (más comunes)

| Archivo | Línea | Import |
|---------|-------|--------|
| `src/workflow/engine.py` | — | Múltiples imports de `orbital.models`, `orbital.context` |
| `src/workflow/step_executor.py` | — | `math`, imports de `orbital` |
| `src/workflow/condition_evaluator.py` | — | `math` |
| `src/workflow/error_handler.py` | — | `Any` |
| `src/workflow/branch_handler.py` | — | `Any` |
| `src/workflow/loop_handler.py` | — | `Any` |
| `src/workflow/fork_handler.py` | — | `Any` |
| `src/nlu/pipeline.py` | — | `Token`, `Entity`, `IntentMatch`, `Slot` de `entities.base` |
| `src/nlu/tokenizer.py` | — | `re` |
| `src/nlu/language_router.py` | — | `re` |
| `src/nlu/ai_config.py` | — | `field` de `dataclasses` |
| `src/events/bus.py` | — | `VariableOrbital`, `DEFAULT_THRESHOLD` |
| `src/events/schedule_worker.py` | — | `time`, `timedelta` |
| `src/events/work_queue.py` | — | `Any`, `secrets` |
| `src/events/worker_manager.py` | — | `Any` |
| `src/data/backup_engine.py` | — | `shutil`, `time` |
| `src/data/database_manager.py` | — | `DB_WAL_MODE` |
| `src/main.py` | — | `sys`, `threading`, `time`, `webbrowser`, `datetime` |
| `src/config.py` | — | `os`, `secrets`, `warnings`, `Path`, `base64`, `hashlib` |
| `src/orbital/*.py` | — | 30+ imports sin usar (principalmente `math`, `typing.Any`) |

### 2.2 F841 — Variables No Utilizadas

| Archivo | Línea | Variable |
|---------|-------|----------|
| `src/events/file_watcher.py` | 95 | `method` |
| `src/orbital/orbital_compiler.py` | 235 | `template_scores` |
| `src/workflow/error_handler.py` | 135 | `orbital_theta` |
| `src/workflow/error_handler.py` | 223 | `error_var_result` |
| `src/workflow/fork_handler.py` | 116 | `step_id` |

### 2.3 F541 — F-strings sin Placeholders

| Archivo | Línea |
|---------|-------|
| `src/events/bus.py` | 418 |
| `src/orbital/cod.py` | 409 |
| `src/orbital/espectro.py` | 360, 364 |
| `src/workflow/engine.py` | 631 |

### 2.4 F601 — Keys Duplicadas en Diccionario

| Archivo | Línea | Detalle |
|---------|-------|---------|
| `src/nlu/entities/quantity.py` | 31 | `"less than"` definido 2 veces en `OPERATOR_WORDS_QTY` |

### 2.5 F811 — Redefinición de Imports No Utilizados

| Archivo | Detalle |
|---------|---------|
| `src/tests/test_integrations.py` | `GmailService`, `SheetsService`, `TelegramService`, `SlackService` importados múltiples veces |

---

## 3. 🟢 Errores de Estilo (no incluidos en total de bugs)

Ruff encontró ~10,000 errores adicionales de estilo (E, W, etc.). Los más comunes:

| Código | Descripción | Frecuencia |
|--------|-------------|------------|
| E501 | Línea demasiado larga (>88 chars) | Muy alta |
| W291 | Espacios en blanco al final de línea | Alta |
| E302 | Faltan 2 líneas en blanco entre clases/funciones | Alta |
| E731 | Asignación lambda en vez de def | Media |
| E402 | Import al interior del módulo (no al inicio) | Media |
| W292 | Falta newline al final del archivo | Baja |

---

## 4. 📊 Distribución por Directorio

| Directorio | Bugs (E9+F) | Archivos afectados |
|------------|-------------|-------------------|
| `src/` (raíz) | ~15 | main.py, config.py |
| `src/workflow/` | ~30 | engine, executor, evaluator, handlers |
| `src/nlu/` | ~20 | pipeline, tokenizer, ai_config |
| `src/events/` | ~25 | bus, queue, workers |
| `src/data/` | ~10 | backup, database |
| `src/orbital/` | ~40 | ovc, tor, rcc, cod, compiler |
| `src/tools/` | ~15 | api_connector, services |
| `src/tests/` | ~60 | todos los archivos de test |

---

## 5. 🎯 Recomendaciones

1. **Prioridad alta:** Corregir los **bugs funcionales** (F601 key duplicada en quantity.py, F841 variables sin usar)
2. **Prioridad media:** Limpiar **F401 imports no utilizados** en producción (no tests) — ~100 issues
3. **Prioridad baja:** F-strings sin placeholders (F541) y redefiniciones en tests (F811)
4. **Opcional:** Aplicar `ruff check --fix` para correcciones automáticas de estilo

---

*Generado con Ruff v0.15.14*
