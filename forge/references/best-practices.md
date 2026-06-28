# Code-Forge: Guía de Mejores Prácticas

Basada en investigación académica (TDAD, Reflexion), patrones industriales (Run Ledger, Architect/Editor, Canary Fix, Sandboxing) y análisis de fallos (88% de agentes no llegan a producción).

---

## 1. 🎯 Cuándo USAR Code-Forge (DO)

### 1.1 Cambios en archivos de producción

**Por qué:** Los archivos de producción afectan a usuarios reales. Un error puede costar dinero, datos, o reputación. Code-Forge asegura que cada cambio sea reversible (rollback), verificado (gates), y auditable (ledger).

**Ejemplos:**
- ✅ Modificar un endpoint de API
- ✅ Cambiar lógica de autenticación
- ✅ Actualizar una query de base de datos
- ✅ Modificar un pipeline de facturación

### 1.2 Tareas multi-archivo

**Por qué:** Cuando tocas 2+ archivos, el riesgo de error de coordinación aumenta exponencialmente. El canary fix (1 archivo a la vez) aísla problemas.

**Ejemplos:**
- ✅ Refactor que mueve lógica entre módulos (ej: extraer auth de main.py a auth_service.py)
- ✅ Feature cross-stack: API + Frontend (Python + TypeScript)
- ✅ Cambio que requiere actualizar modelos, servicios y tests

### 1.3 Cross-stack (Python + TypeScript)

**Por qué:** El stack bilingüe de Zenic-Flujo requiere verificación en ambos lados. Los 12 gates se ejecutan en paralelo para ambos stacks.

**Ejemplos:**
- ✅ Añadir campo a API (Python) y mostrarlo en UI (TypeScript)
- ✅ Cambiar validación en backend y reflejarlo en frontend

### 1.4 Bugs críticos (auth, billing, datos)

**Por qué:** Estos sistemas no admiten errores. El Run Ledger con rollback obligatorio asegura que cada cambio se pueda deshacer instantáneamente.

**Ejemplos:**
- ✅ Fix en lógica de permisos
- ✅ Corrección en cálculo de facturación
- ✅ Parche en sincronización de datos

### 1.5 Refactors con blast radius grande (>5 archivos)

**Por qué:** El blast radius grande requiere descomposición en tasks atómicas con DAG de dependencias. Code-Forge fuerza esta descomposición en Fase 3 (TASKS).

**Ejemplos:**
- ✅ Renombrar un módulo completo
- ✅ Migrar de una librería a otra
- ✅ Reestructurar una jerarquía de clases

### 1.6 Trabajo multi-agente/humano

**Por qué:** El Run Ledger sirve como documento de handoff. Un agente puede retomar donde otro dejó sin perder contexto.

**Ejemplos:**
- ✅ Sesiones de Codebuff que continúan al día siguiente
- ✅ Handoff entre agente de día y agente de noche
- ✅ Revisión humana después de implementación de agente

---

## 2. ❌ Cuándo NO usar Code-Forge (DON'T)

### 2.1 Cambios triviales (1 línea, typos, docs)

**Por qué:** La ceremonia del loop (8 fases, human checkpoints, 12 gates) cuesta tiempo y tokens. Para cambios triviales, el overhead supera el beneficio.

**Ejemplos:**
- ❌ Corregir un typo en un comentario
- ❌ Actualizar una línea en documentación
- ❌ Renombrar una variable local
- ❌ Formatear código (linters ya lo hacen)

**Alternativa:** Editar directamente, sin gates ni ledger.

### 2.2 Exploración o análisis sin implementación

**Por qué:** No hay código que cambiar, verificar, ni deshacer. Code-Forge requiere al menos un archivo modificado.

**Ejemplos:**
- ❌ "Entiende cómo funciona este módulo"
- ❌ "Analiza por qué este test falla"
- ❌ "Encuentra dónde se define esta función"

**Alternativa:** Usar skills de Layer 1-2 (planning, research, debugging).

### 2.3 Prototipado rápido / "vibe coding"

**Por qué:** La velocidad de iteración se pierde en gates y human checkpoints. Para prototipos, la meta es velocidad, no calidad de producción.

**Ejemplos:**
- ❌ "Crea un PoC de este concepto"
- ❌ "Prueba 3 enfoques diferentes rápidamente"
- ❌ "Haz un experimento para ver si funciona"

**Alternativa:** Prototipar sin Code-Forge, luego aplicar el prompting loop para la versión de producción.

### 2.4 Tareas de solo investigación

**Por qué:** No hay código que cambiar ni rollback que definir.

**Ejemplos:**
- ❌ "Investiga qué librería es mejor para X"
- ❌ "Lee la documentación de esta API"
- ❌ "Compara estas 3 alternativas"

**Alternativa:** Usar `researcher-web` y `researcher-docs`.

### 2.5 Rollback imposible

**Por qué:** Esta es una regla de ORO. Si no puedes deshacer el cambio, es high-risk. Code-Forge requiere rollback definido para cada acción.

**Ejemplos:**
- ❌ Modificar datos en producción sin snapshot previo
- ❌ Ejecutar script de migración sin revert path
- ❌ Llamar a API externa sin idempotencia

**Alternativa:** Obtener aprobación humana explícita + definir plan de contingencia.

### 2.6 Sin tests existentes

**Por qué:** Los 12 gates verifican contra tests. Sin tests, no hay ground truth para VERIFY y FINAL_VERIFY.

**Ejemplos:**
- ❌ Proyecto nuevo sin tests
- ❌ Feature en módulo sin cobertura

**Alternativa:** Escribir tests primero (puede ser sin Code-Forge), luego aplicar el loop.

### 2.7 Scope multi-dominio sin descomponer

**Por qué:** El 34% de los fallos de agentes son por scope creep. Code-Forge requiere SPECIFY atómico.

**Señales de alerta:**
- La spec menciona 3+ dominios de workflow diferentes
- El requirements doc usa frases como "inteligentemente decide", "maneja cualquier cosa"
- Stakeholders de 3+ departamentos reclaman el agente
- Nadie ha escrito lo que el agente NO hará

**Alternativa:** Descomponer en specs independientes y ejecutar Code-Forge para cada una.

---

## 3. 🧠 La Paradoja TDD: Contexto > Procedimiento

**Este es el hallazgo más importante del paper TDAD (arXiv:2603.17973).**

### El error común

La mayoría de los frameworks de agentes le dicen al modelo: "Usa TDD, escribe tests primero, luego código."

### Lo que dice la evidencia

| Enfoque | Regresiones |
|---------|-------------|
| Agente vanilla (sin instrucciones) | 6.08% |
| Agente con instrucciones TDD procedurales | **9.94%** ⬆️ |
| Agente con contexto TDD contextual | **1.82%** ⬇️ |

**Las instrucciones TDD procedurales EMPEORARON los resultados en un 64%.**

### Por qué

Los modelos (especialmente los que corren en hardware de consumo como Qwen3-Coder 30B) se distraen con instrucciones procedurales complejas. En lugar de mejorar, gastan atención en seguir el proceso en vez de resolver el problema.

### La solución

NO dar instrucciones de "cómo" hacer TDD. En su lugar:
1. Hacer AST-scan del código afectado
2. Identificar qué tests existen y qué funciones públicas se tocan
3. Inyectar en el prompt: "Estos tests existen, estas funciones son contratos, estos archivos importan lo que tocas"

**Esto REDUJO regresiones un 70%** en el benchmark SWE-bench Verified.

### Cómo se aplica en Code-Forge

En Fase 4 (IMPLEMENT), el workflow pre-IMPLEMENT:
1. Detecta stack de cada target_file
2. Hace AST-scan para identificar funciones públicas
3. Busca test files correspondientes
4. Encuentra importers (blast radius)
5. **Inyecta contexto** en el prompt del LLM

NUNCA se le dice al modelo "usa TDD" o "escribe tests primero".

---

## 4. 📊 Los 7 Patrones de Fracaso de Agentes de IA

Basado en el análisis de DigitalApplied (2025-2026): **88% de los proyectos de agentes de IA fallan antes de producción.**

| # | Patrón | % | Cómo lo previene Code-Forge |
|---|--------|---|-----------------------------|
| 1 | **Scope Creep** | 34% | Fase 1 (SPECIFY): exclusiones explícitas, atomicidad, human checkpoint |
| 2 | **Data Quality Failures** | 27% | Fase 1 (SPECIFY): data readiness check antes de implementar |
| 3 | **Security Blockers** | 14% | Gate `no_security_issues` + env sanitization en sandbox |
| 4 | **Integration Complexity** | 9% | Fase 2 (PLAN): blast radius + mapeo de dependencias |
| 5 | **Cost Overruns** | 7% | Budget de 2M tokens + HALT conditions |
| 6 | **Governance Gaps** | 5% | Run Ledger completo + human checkpoints |
| 7 | **Organizational Resistance** | 4% | SPECIFY con human checkpoint, reportes de HALT |

**Dato clave:** Las organizaciones que aplican evaluación estructurada de modos de fallo ANTES de desarrollar reducen su tasa de fracaso de 88% a **menos del 15%**.

---

## 5. 🔄 Reglas de Delegación (gentle-ai)

| # | Cuándo delegar | Qué hacer | Ejemplo |
|---|----------------|-----------|---------|
| 1 | **4-file rule:** Necesitas leer 4+ archivos para entender un flow | Delegar exploración a sub-agente | "Explora cómo funciona el pipeline de facturación" |
| 2 | **Multi-file write:** Vas a tocar 2+ archivos no-triviales (>50 líneas cambiadas) | Usar writer + requerir fresh review | Refactor que toca service, repository y tests |
| 3 | **PR rule:** Antes de commit, push, o PR | Run fresh review (excepto docs) | Revisar diff antes de commit |
| 4 | **Incident rule:** Después de errores (wrong cwd, git accident, merge recovery) | Run fresh audit antes de continuar | "Acabo de hacer git reset --hard, ¿está todo bien?" |
| 5 | **Long-session:** >20 tool calls o 5 exploratory reads | Pause y delegate, re-plan, o justifica | "Llevamos 30 iteraciones, re-planifiquemos" |
| 6 | **Fresh review:** Review adversarial de diffs | Usar contexto fresco (nuevo agente/sesión) | El mismo agente no ve sus propios errores |

---

## 6. 🏗️ Arquitectura del Run Ledger

### El loop operativo

```
permission → action → log → review → rollback
```

### Las 5 preguntas gate para cualquier acción

Antes de que el agente ejecute una acción consecuente, responder:

1. **¿Puede hacer esto?** — ¿Tiene permiso?
2. **¿Qué va a cambiar exactamente?** — ¿Archivos, datos, config?
3. **¿Quién lo aprobó?** — ¿Humano o auto-aprobado?
4. **¿Dónde está el log?** — ¿Dónde se registró?
5. **¿Cómo lo deshacemos?** — ¿Cuál es el rollback?

Si el sistema no puede responder estas 5 preguntas, la acción no debería ser automática.

### Permisos por job, no por tool

No asignes "GitHub access" como blob. Desglosa:

```
read issues          → ✅ siempre
read code            → ✅ siempre
create branch        → ✅ ramas agent/*
push commits         → ✅ ramas agent/*
open PR              → ❌ ask (requiere aprobación)
merge PR             → ❌ deny (nunca)
trigger workflows    → ❌ deny
read secrets         → ❌ deny
```

### Ejemplo de permission file

```yaml
agent: coding-fix-agent
scope:
  branches:
    writable: [agent/*]
    denied: [main]
  files:
    read: [app/**, lib/**]
    write: [app/**, lib/**]
    deny: [.env*, .github/workflows/**]
  commands:
    allow: [pnpm test, pnpm lint, pnpm typecheck]
    ask: [pnpm install, git push]
    deny: [rm -rf *, sudo *]
```

---

## 7. 🏜️ Sandbox: Reglas de Aislamiento

### Filesystem

- **workdir:** Writable en `/tmp/forge_<run_id>/`
- **project_root:** Read-only (solo lectura del código fuente)
- **snapshot/restore:** Vía git stash

### Network

Solo estos dominios permitidos:
- `pypi.org` — pip install
- `files.pythonhosted.org` — Python packages
- `registry.npmjs.org` — npm install
- `github.com` — git fetch (solo lectura)
- `raw.githubusercontent.com` — raw content

### Environment

Eliminar: `*_SECRET`, `*_TOKEN`, `*_API_KEY`, `*_PASSWORD`, `*_KEY`

Inyectar:
- `NODE_ENV=test`
- `PYTHONUNBUFFERED=1`
- `WFD_DATA_DIR=/tmp/forge_<run_id>/data`

### Resource Limits

| Recurso | Límite |
|---------|--------|
| CPU | 1800s (30 min) |
| RAM | 12 GB (configurable) |
| Filesize | 500 MB |
| Procesos | 200 |
| File Descriptors | 1024 |
| Core dumps | 0 (deshabilitado) |

---

## 8. ⚡ Consejos Prácticos

### Para sesiones largas

- Hacer snapshot del ledger periódicamente
- Usar `ledger.summary()` para verificar estado
- Si la sesión excede 30 minutos, considerar delegar a sub-agente

### Para debugging de gates fallidos

1. Ver primero `no_broken_imports` — si los imports fallan, todo lo demás fallará
2. Luego `tests_pass` — si los tests no pasan, revisar el diff
3. Si todo lo demás pasa pero `mutation_score` falla, los tests no son efectivos

### Para optimizar velocidad

- En Fase 5, ejecutar solo los gates del stack afectado
- Si solo tocas Python, no ejecutes gates de TypeScript
- Usar `runner.run_all(stacks=["python"])` para limitar

### Para maximizar calidad

- Siempre ejecutar los 12 gates completos antes de entrega
- Incluso si el cambio es pequeño, `integration_smoke` detecta problemas de build
- `no_security_issues` es el gate más importante: nunca saltarlo

---

## 9. 📚 Referencias

| Fuente | Enlace | Concepto clave |
|--------|--------|----------------|
| TDAD Paper | https://arxiv.org/abs/2603.17973 | Contextual TDD reduce regresiones 70% |
| Reflexion | https://arxiv.org/abs/2303.11366 | Verbal reinforcement learning, 91% HumanEval |
| Run Ledger | https://developersdigest.tech/blog/permissions-logs-rollback-ai-coding-agents | Permission→Action→Log→Review→Rollback |
| Aider Architect/Editor | https://aider.chat/2024/09/26/architect.html | Separar razonamiento de edición, SOTA 85% |
| Anthropic Sandboxing | https://dev.to/rams901/anthropic-self-hosted-sandboxes | Sandbox dual enterprise |
| gentle-ai | https://github.com/Gentleman-Programming/gentle-ai | Delegación, SDD, Engram |
| 88% Failure Analysis | https://digitalapplied.com/blog/88-percent-ai-agents-never-reach-production | 7 patrones de fracaso |
| SDD (BCMS) | https://thebcms.com/blog/spec-driven-development | Spec-driven Development |
| Meta Harness | https://medium.com/@saehwanpark/from-tool-calling-loops-to-repository-contracts | Repository-level contracts |
| ForgeCode | https://forgecode.dev/docs/ | Multi-provider coding harness |
| ai-whisper | https://github.com/ai-creed/ai-whisper | Multi-agent relay |
| Google SRE | https://sre.google | Canary release pattern |
