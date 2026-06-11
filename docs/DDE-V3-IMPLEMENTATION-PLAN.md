# 🗺️ DDE v3 — Plan de Implementación

## Pipeline de 12 etapas — 4 Sprints de 3-4 días cada uno

**Inicio:** Junio 2026
**Skills base:** `api-and-interface-design`, `source-driven-development`, `incremental-implementation`, `test-driven-development`
**MCPs disponibles:** `expert-mcp`, `filesystem`, `memory`, `sqlite`, `github`, `context7`, `sequential-thinking`, `analyzer`, `semgrep`

---

## 📋 Inventario de MCPs en Codebuff

| MCP | Comando | Propósito |
|---|---|---|
| `expert-mcp` | `node /root/mcp-server/dist/index.js` | Validar diseños complejos |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | Leer/escribir archivos del proyecto |
| `memory` | `@modelcontextprotocol/server-memory` | Knowledge graph de decisiones |
| `sqlite` | `mcp-sqlite` | Consultar/explorar la DB existente |
| `github` | `@ama-mcp/github` | Commits, PRs |
| `context7` | `https://mcp.context7.com/mcp` | Web research contextual |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking` | Razonamiento paso a paso |
| `analyzer` | `mcp-server-analyzer` | Analizar código existente |
| `semgrep` | `semgrep-mcp` | Seguridad: detectar eval(), malas prácticas |

---

## 🏃 SPRINT 1: "NLU BÁSICO FUNCIONAL" (Días 1-3)

**Objetivo:** Pipeline mínimo de 4 etapas (Normalizer → Tokenizer → EntityExtractor → IntentClassifier) con la nueva arquitectura.

**Skills:** `api-and-interface-design`, `source-driven-development`, `incremental-implementation`, `test-driven-development`

**MCPs a usar:** `context7` (research stemmer), `sequential-thinking` (diseño contrato), `analyzer` (código existente), `sqlite` (explorar DB), `semgrep` (seguridad), `code-reviewer-deepseek-flash` (review)

### Tareas

| # | Tarea | Archivos | Tests |
|---|---|---|---|
| 1 | Crear `src/nlu/` + `entities/` + contrato dataclasses frozen | `src/nlu/__init__.py`, `src/nlu/entities/__init__.py`, `src/nlu/entities/base.py` | `test_nlu_contract.py` |
| 2 | Normalizer con NFKD + expansión números | `src/nlu/normalizer.py` | `test_normalizer.py` (15+ tests) |
| 3 | Tokenizer + Stemmer ES/EN | `src/nlu/tokenizer.py` | `test_tokenizer.py` (20+ tests) |
| 4 | LanguageRouter (hereda de bilingual_router) | `src/nlu/language_router.py` | `test_language_router.py` |
| 5 | EntityExtractor nueva arquitectura | `src/nlu/entities/email.py`, `phone.py`, `date_time.py`, `number.py` | `test_entity_basic.py` |
| 6 | IntentClassifier v2 con tokens | `src/nlu/intent_classifier.py` | `test_intent_classifier.py` |
| 7 | Pipeline orquestador básico | `src/nlu/pipeline.py` | `test_pipeline.py` |

---

## 🏃 SPRINT 2: "TF-IDF + ENTIDADES AVANZADAS" (Días 4-7)

**Objetivo:** Reemplazar keyword matching con TF-IDF. Agregar 4 extractores nuevos.

**Skills:** `doubt-driven-development`, `test-driven-development`, `security-and-hardening`, `incremental-implementation`

**MCPs a usar:** `expert-mcp` (TF-IDF validation), `sequential-thinking` (algoritmo), `sqlite` (vectores IDF), `semgrep` (seguridad), `thinker-gpt` (adversarial review), `code-reviewer-deepseek-flash` (review)

### Tareas

| # | Tarea | Archivos | Tests |
|---|---|---|---|
| 1 | TF-IDF IntentClassifier | `src/nlu/intent_classifier.py` (reemplazo) | 30+ tests + golden dataset |
| 2 | MoneyExtractor con operadores | `src/nlu/entities/money.py` | 15 tests |
| 3 | QuantityExtractor | `src/nlu/entities/quantity.py` | 15 tests |
| 4 | DurationExtractor (cron) | `src/nlu/entities/duration.py` | 20 tests |
| 5 | ConditionExtractor (AST seguro, sin eval) | `src/nlu/entities/condition.py` | 15 tests |
| 6 | SlotFiller | `src/nlu/slot_filler.py` | 15 tests |
| 7 | Fragmentos componibles | `src/nlu/fragments.py` (reemplaza templates.py) | — |
| 8 | Golden tests 60+ frases | — | Determinismo verificado |

---

## 🏃 SPRINT 3: "DIÁLOGO + COMPILACIÓN" (Días 8-12)

**Objetivo:** ClarifyDialog, WorkflowCompiler, Explainer. Sistema pregunta y compila.

**Skills:** `frontend-ui-engineering`, `doubt-driven-development`, `security-and-hardening`

**MCPs a usar:** `sequential-thinking` (FSM), `expert-mcp` (edge cases), `browser-use` (probar UI), `sqlite` (diálogo persistente), `thinker-gpt` (adversarial review)

### Tareas

| # | Tarea | Archivos | Tests |
|---|---|---|---|
| 1 | Disambiguator | `src/nlu/disambiguator.py` | 10 tests |
| 2 | ClarifyDialog (FSM 5 estados) | `src/nlu/clarify_dialog.py` | 20 tests |
| 3 | WorkflowCompiler | `src/nlu/compiler.py` | 20 tests |
| 4 | Validator (tipos, refs, ciclos) | `src/nlu/validator.py` | 15 tests |
| 5 | Explainer | `src/nlu/explainer.py` | 15 tests |
| 6 | Golden tests 100+ frases | — | Determinismo verificado |

---

## 🏃 SPRINT 4: "DRY-RUN + APRENDIZAJE + FINAL" (Días 13-15)

**Objetivo:** DryRunSimulator, SynonymLearner, Pipeline completo, Endpoint API.

**Skills:** `code-review-and-quality`, `security-and-hardening`, `browser-testing-with-devtools`

**MCPs a usar:** `semgrep` (seguridad dry-run), `sqlite` (DB migration), `browser-use` (flujo completo), `memory` (lecciones), `github` (commit final)

### Tareas

| # | Tarea | Archivos | Tests |
|---|---|---|---|
| 1 | DryRunSimulator (modo simulate) | `src/nlu/dry_run.py` | 15 tests |
| 2 | SynonymLearner + tabla nlp_synonyms | `src/nlu/synonym_learner.py` | 10 tests |
| 3 | DB migration (nlp_synonyms, nlp_intent_vectors, nlu_traces) | `src/data/database_manager.py` | — |
| 4 | Pipeline orquestador 12 etapas | `src/nlu/pipeline.py` (completar) | 15 tests |
| 5 | Endpoint `/api/nlu/understand` | `src/web/app.py` | Tests API |
| 6 | Golden tests 200+ frases | — | Determinismo final |
| 7 | Auditoría de seguridad final | — | `semgrep` scan |

---

## 📊 Mapa MCPs x Sprint

```
                    SPRINT 1    SPRINT 2    SPRINT 3    SPRINT 4
expert-mcp              ✅          ✅          ✅          —
filesystem              ✅          ✅          ✅          ✅
memory                  —           —           —          ✅
sqlite                  ✅          ✅          ✅          ✅
github                  ✅          ✅          ✅          ✅
context7                ✅          —           —          —
sequential-thinking     ✅          ✅          ✅          —
analyzer                ✅          —           —          —
semgrep                 ✅          ✅          ✅          ✅
```

---

## 📈 Progresión de Golden Tests

```
Sprint 1:   30 frases → entidades básicas + intenciones por tokens
Sprint 2:   60 frases → entidades avanzadas + slots + TF-IDF
Sprint 3:  100 frases → diálogo + compilación + explicación
Sprint 4:  200 frases → pipeline completo, determinismo verificado
```

---

## 🚨 Riesgos

| Riesgo | Mitigación |
|---|---|
| TF-IDF sin sklearn | Fórmula manual con stdlib (math.log, math.sqrt). IDF precalculado en DB |
| ClarifyDialog complejo | FSM simple de 5 estados. Tests para cada transición |
| Stemmer sin NLTK | Diccionario de raíces + reglas de sufijos. Suficiente para ES/EN |
| Pipeline orquestador | Fallback: si falla etapa avanzada → cae a etapa simple. Nunca peor que hoy |
