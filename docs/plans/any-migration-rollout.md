# Plan de Migración Anti-`Any` — Zenic-Flujo

> **Objetivo**: Eliminar progresivamente el uso de `Any` en todo el código Python
> del proyecto **excepto `src/core/`**, aplicando la skill
> [`any-best-practices`](../../.opencode/skills/any-best-practices/SKILL.md).
>
> **Skill de referencia**: `.opencode/skills/any-best-practices/SKILL.md`
> **Documento fuente**: `docs/research/any-best-practices.md`
> **Stack**: Python 3.12, mypy strict mode global, Pydantic v2
> **Fecha de creación**: 2026-06-27
> **Baseline**: 1,919 ocurrencias de `Any` fuera de `src/core/`
> **Scope**: `src/**` excluyendo `src/core/**`

---

## 0. Resumen ejecutivo

El proyecto tiene **1,919 usos de `Any`** fuera de `src/core`, distribuidos en 27
módulos. El 41% se concentra en `src/connectors` (799), seguido de `src/api_v2`
(289), `src/hat` (135) y `src/sdk` (129). Mypy ya está en strict mode global,
pero 4 módulos grandes tienen `disallow_untyped_defs = false` como excepción
temporal: `connectors`, `agents`, `web`, `api_v2`.

La estrategia es **atacar en orden de riesgo creciente**: empezar por módulos
pequeños con tests y strict mode ya activo (orbital, nlu, i18n), escalar a
módulos críticos con baja deuda (security, tenant, compliance), luego a zonas
strict pendientes (hat, sdk), después a las capas permisivas (api_v2, mobile) y
finalmente al elefante (`connectors`) en lotes temáticos.

**Duración estimada**: 6-8 semanas con equipo parcial, 2-3 semanas full-time.

**Gate global de salida**: `mypy --strict src/` pasa sin errores y
`rg "\bAny\b" --type py src/ | grep -v "^src/core" | wc -l` ≤ 50 (excepciones
documentadas únicamente).

---

## 1. Principios de la migración

1. **Una fase = un PR por módulo** (o por lote temático en `connectors`). Nunca
   mezclar módulos en un mismo PR.
2. **Tests primero**: si un módulo tiene 0 tests, Fase 0 incluye añadir smoke
   tests antes de tocar tipos.
3. **Cada `Any` eliminado debe tener su alternativa justificada** según la tabla
   de la skill (`object`, `TypeVar`, `Protocol`, `Union`, tipo concreto).
4. **`Any` legítimos se documentan** con `# TODO: tipar` o `# type: ignore[código]`
   + razón. No se eliminan a ciegas.
5. **No breaking changes en APIs públicas** sin entry en `CHANGELOG.md` y bump
   semver minor.
6. **Rollback siempre definido**: cada PR es reversible vía `git revert`. Si
   un módulo rompe en producción, se revierte el PR específico.
7. **Métrica diaria**: ejecutar `scripts/audit_any.py` (ver Fase 0) en CI y
   publicar el count en el dashboard del PR.

---

## 2. Baseline de métricas (estado inicial, 2026-06-27)

### 2.1. Distribución por módulo (excluyendo `src/core`)

| Módulo | Any | mypy strict | Tests | Riesgo | Fase |
|--------|----:|:-----------:|------:|:------:|:----:|
| `src/connectors` | 799 | NO | 1 | 🔴 Muy alto | 6 |
| `src/api_v2` | 289 | NO | 0 | 🔴 Alto | 5 |
| `src/hat` | 135 | MIXTO | 3 | 🟡 Medio | 3 |
| `src/sdk` | 129 | SÍ | 0 | 🟡 Medio | 4 |
| `src/agents` | 59 | NO | 0 | 🟡 Medio | 7 |
| `src/orbital` | 57 | SÍ | 16 | 🟢 Bajo | 3 |
| `src/mobile` | 54 | SÍ | 0 | 🟠 Medio-alto | 5 |
| `src/compliance` | 48 | SÍ | 0 | 🟡 Medio | 2 |
| `src/tests` | 44 | NO | — | 🟢 Bajo | 7 |
| `src/workflow` | 42 | SÍ | 4 | 🟢 Bajo | 7 |
| `src/marketplace` | 40 | SÍ | 0 | 🟡 Medio | 7 |
| `src/cli` | 34 | SÍ | 0 | 🟢 Bajo | 7 |
| `src/observability` | 29 | SÍ | 0 | 🟡 Medio | 2 |
| `src/security` | 28 | SÍ | 2 | 🟡 Medio | 2 |
| `src/data` | 20 | SÍ | 2 | 🟡 Medio | 2 |
| `src/tenant` | 19 | SÍ | 2 | 🟡 Medio | 2 |
| `src/partnership` | 18 | SÍ | 1 | 🟢 Bajo | 7 |
| `src/sync` | 16 | SÍ | 0 | 🟡 Medio | 7 |
| `src/tools` | 14 | SÍ | 5 | 🟢 Bajo | 7 |
| `src/nlu` | 10 | SÍ | 21 | 🟢 Bajo | 1 |
| `src/bpmn` | 10 | SÍ | 0 | 🟢 Bajo | 1 |
| `src/container.py` | 10 | SÍ | 1 | 🟢 Bajo | 1 |
| `src/airgap.py` | 6 | SÍ | 1 | 🟢 Bajo | 1 |
| `src/events` | 4 | SÍ | 0 | 🟢 Bajo | 1 |
| `src/i18n` | 3 | SÍ | 0 | 🟢 Bajo | 1 |
| `src/web` | 2 | NO | 1 | 🟢 Bajo | 1 |
| **TOTAL** | **1,919** | — | — | — | — |

### 2.2. Top antipatrones detectados

| Antipatrón | Ocurrencias | Reemplazo canónico |
|------------|------------:|--------------------|
| `dict` sin parametrizar (`: dict,` / `: dict =`) | 300 | `dict[str, X]` |
| Retornos `-> Any` | 132 | Tipo concreto o `TypeVar` |
| Atributos `: Any = None` | 31 | `X \| None = None` |
| `list` sin parametrizar | 18 | `list[X]` |

### 2.3. Top 10 archivos con más deuda

| Archivo | Any |
|---------|----:|
| `src/mobile/api.py` | 38 |
| `src/api_v2/models.py` | 38 |
| `src/api_v2/routers/marketplace.py` | 31 |
| `src/api_v2/routers/workflows.py` | 29 |
| `src/api_v2/routers/agents.py` | 28 |
| `src/api_v2/routers/tenants.py` | 27 |
| `src/api_v2/routers/compliance.py` | 27 |
| `src/api_v2/routers/connectors.py` | 26 |
| `src/connectors/mongo_connector.py` | 23 |
| `src/sdk/schema.py` | 22 |

---

## 3. Plan por fases

### Fase 0 — Setup y baseline (1 día)

**Objetivo**: sembrar infraestructura de medición y gobernanza antes de tocar código.

**Tareas**:
- [ ] Crear `scripts/audit_any.py` que genera un CSV con: `module, file, line, context, antipattern_type`.
- [ ] Añadir hook `pre-commit` que rechace commits con nuevos `Any` no justificados (comentario `# TODO: tipar` o `# type: ignore[...]` obligatorio en la misma línea).
- [ ] Añadir job de CI `any-audit` que publique el count de `Any` en el dashboard del PR y bloquee el merge si sube.
- [ ] Documentar convención de comentarios en `docs/research/any-best-practices.md` (extender sección 5.3).
- [ ] Etiquetar el commit de baseline con tag `any-baseline-2026-06-27`.
- [ ] Crear rama larga `chore/any-migration` como integration branch.

**Gate de salida**:
- `scripts/audit_any.py` reporta 1,919 ± 5 ocurrencias.
- Pre-commit hook bloquea un commit de prueba con `Any` no justificado.
- CI job verde.

**Riesgo**: ninguno — solo infraestructura.

---

### Fase 1 — Quick wins (3-4 días)

**Objetivo**: probar el workflow end-to-end en módulos pequeños con buena cobertura
de tests y mypy strict ya activo. Generar momentum y templates de PR.

**Módulos** (45 Any en total):

| Módulo | Any | Estrategia |
|--------|----:|-----------|
| `src/web` | 2 | Tipar responses Flask con `dict[str, object]` |
| `src/i18n` | 3 | Añadir smoke test, tipar catálogos |
| `src/events` | 4 | Tipar bus y handlers con `Protocol` |
| `src/airgap.py` | 6 | Tipar manifest y bundle |
| `src/bpmn` | 10 | Añadir test de round-trip XML→Model→XML |
| `src/container.py` | 10 | Reemplazar `dict` sin parámetros por `dict[str, Provider]` |
| `src/nlu` | 10 | Ya tiene 21 tests — straightforward |

**Estrategia específica**:
- Un PR por módulo (7 PRs en total).
- Cada PR debe reducir el count de `Any` del módulo a 0, o justificar los
  residuales con `# TODO: tipar` + ticket.
- Aplicar la cheatsheet de la skill literalmente: antipatrón → reemplazo.

**Gate de salida por módulo**:
- `mypy --strict src/<modulo>/` pasa sin errores.
- Tests existentes + smoke tests nuevos en verde.
- Count de `Any` del módulo = 0 (o justificado).
- Code review por al menos 1 revisor.

**Gate de salida de la fase**: los 7 módulos mergeados. Documentar plantilla de
PR y lecciones aprendidas en `docs/plans/any-migration-rollout.md` (este archivo).

**Riesgo**: bajo. Si algo se rompe, revertir el PR del módulo.

---

### Fase 2 — Seguridad, datos y compliance (1 semana)

**Objetivo**: limpiar módulos críticos para auditoría (GDPR, HIPAA, SOC2) y
multi-tenant. Aquí los `Any` no son solo deuda técnica, son **riesgo de
compliance**.

**Módulos** (144 Any en total):

| Módulo | Any | Acción previa |
|--------|----:|---------------|
| `src/security` | 28 | Ampliar `test_security_redteam.py` con casos de type confusion |
| `src/tenant` | 19 | Ampliar `test_tenant_split.py` |
| `src/data` | 20 | Ampliar `test_data_keeper.py` |
| `src/compliance` | 48 | Crear `test_compliance_smoke.py` (GDPR/HIPAA/SOC2 mínimo) |
| `src/observability` | 29 | Crear `test_observability_smoke.py` |

**Estrategia específica**:
- **Tests antes que tipos**: cada módulo empieza con un PR que solo añade tests
  (smoke + casos borde de type confusion). Solo cuando los tests están verdes,
  se abre el PR de migración de tipos.
- Para `src/security` y `src/compliance`: revisión adicional por el equipo de
  security (si existe) o por un revisor senior con firma explícita en el PR.
- Para `src/data`: prestar atención a `Any` en repositorios que manejan PII —
  reemplazar por `Mapping[str, object]` + validador Pydantic en el límite.

**Gate de salida por módulo**:
- `mypy --strict src/<modulo>/` pasa.
- Cobertura de tests del módulo ≥ 70%.
- Sin `Any` en funciones que toquen PII o credenciales.
- Aprobación explícita de security reviewer.

**Riesgo**: medio. Mitigación: tests primero + revert por módulo.

---

### Fase 3 — Zonas strict pendientes (1 semana)

**Objetivo**: completar los módulos que ya están en `mypy strict` pero que
todavía tienen `Any` residuales. Son los que más ruido generan en CI hoy.

**Módulos** (~200 Any en total):

| Módulo | Any | Notas |
|--------|----:|-------|
| `src/orbital` | 57 | 16 tests, mypy strict — el mejor punto de partida de esta fase |
| `src/hat/level1_orchestrator` | ~80 | mypy strict, crítico para dispatch |
| `src/hat/bootstrap` | parte del 135 | mypy strict |
| `src/agents` | 59 | mypy NO strict → **subir a strict en esta fase** |

**Estrategia específica**:
- **`src/orbital`**: empezar por aquí. Los modelos físicos (Lyapunov, Conley,
  Haken, FEP) tienen tipos naturales — reemplazar `Any` por tipos concretos
  del dominio (`State`, `Manifold`, `Trajectory`).
- **`src/hat/level1_orchestrator`**: el dispatcher es el corazón del sistema.
  Migrar en sub-PRs por submódulo: `routing/`, `intent/`, `ledger/`,
  `anti_duplication/`, `fsm/`, `observability/`, `api/`, `response_synthesizer.py`.
  **Orden**: empezar por `intent/` y `anti_duplication/` (más aislados), dejar
  `routing/` y `response_synthesizer.py` para el final (más acoplados).
- **`src/hat/level4_workers` y `level5_tools`**: están en `disallow_untyped_defs = false`.
  En esta fase, **subirlos a strict** después de migrar sus `Any`.
- **`src/agents`**: subir a strict al final de la fase. Añadir fixtures de test
  para `orchestrator.py`, `runtime.py`, `base.py`, `memory.py`, `tools.py`,
  `token_tracking.py`.

**Gate de salida por submódulo**:
- `mypy --strict src/hat/level1_orchestrator/<sub>/` pasa.
- Tests HAT existentes (`test_hat_*.py`) en verde.
- `disallow_untyped_defs = false` eliminado de `mypy.ini` para el submódulo.

**Riesgo**: medio-alto en `hat` por el acoplamiento. Mitigación: sub-PRs
granulares + canary deploy por submódulo.

---

### Fase 4 — SDK público (1 semana)

**Objetivo**: limpiar la interfaz pública del SDK. Estos tipos son contrato con
desarrolladores externos que escriben conectores — cualquier cambio es
**breaking**.

**Módulos** (129 Any en total):

| Submódulo | Any | Acción |
|-----------|----:|--------|
| `src/sdk/schema.py` | 22 | Definir `Protocol` para `Connector`, `Action`, `Trigger` |
| `src/sdk/exceptions.py` | 21 | Reemplazar `Any` en context por `Mapping[str, object]` |
| `src/sdk/http_client.py` | 20 | Tipar response con `TypeVar` genérico |
| `src/sdk/base.py` + `base/` | ~25 | Revisar contrato público |
| `src/sdk/auth/*` | ~15 | Tipar credenciales con `TypedDict` |
| `src/sdk/decorators/*` | ~15 | `*args: Any, **kwargs: Any` es legítimo — documentar |
| `src/sdk/crypto/*` | ~10 | Tipar certificados con `bytes \| str` |
| `src/sdk/registry.py` | resto | Tipar registry con `dict[str, type[Connector]]` |

**Estrategia específica**:
- **Bump semver minor** al final de la fase (ej. `3.2.0` → `3.3.0`).
- **CHANGELOG obligatorio** con cada cambio de signature pública.
- **Tests contractuales**: crear `src/tests/sdk/test_contract.py` que ejercite
  cada tipo público expuesto. Si un conector externo usa `BaseConnector`,
  el test debe pasar sin modificaciones.
- Para `src/sdk/decorators/*`: los `*args: Any, **kwargs: Any` en wrappers son
  legítimos (skill §1.2). Marcar con comentario `# legítimo: wrapper transparente`
  y dejarlos. El objetivo no es eliminar 100%, es eliminar lo injustificado.

**Gate de salida**:
- `mypy --strict src/sdk/` pasa.
- Tests contractuales en verde.
- CHANGELOG actualizado.
- Bump de versión merged.

**Riesgo**: alto por breaking changes. Mitigación: mantener aliases de tipos
antiguos con `# DEPRECATED: usar X` + `DeprecationWarning` si es necesario.

---

### Fase 5 — API v2 + Mobile (1.5 semanas)

**Objetivo**: limpiar la capa HTTP. Los modelos Pydantic ya validan en runtime,
así que los `Any` aquí son menos peligrosos, pero dificultan el autocompletado
y la generación de OpenAPI.

**Módulos** (343 Any en total):

| Archivo/submódulo | Any | Estrategia |
|-------------------|----:|-----------|
| `src/api_v2/models.py` | 38 | Reemplazar `Any` por `dict[str, object]` o modelos Pydantic anidados |
| `src/api_v2/routers/marketplace.py` | 31 | Tipar request/response models |
| `src/api_v2/routers/workflows.py` | 29 | Igual |
| `src/api_v2/routers/agents.py` | 28 | Igual |
| `src/api_v2/routers/tenants.py` | 27 | Igual |
| `src/api_v2/routers/compliance.py` | 27 | Igual |
| `src/api_v2/routers/connectors.py` | 26 | Igual |
| `src/api_v2/routers/auth_routes.py` | 20 | Igual |
| Resto de `src/api_v2/routers/*` | ~63 | Igual |
| `src/mobile/api.py` | 38 | Mismo enfoque que api_v2 |
| Resto `src/mobile` | 16 | Igual |

**Estrategia específica**:
- **Tests de router primero**: cada router debe tener un test que ejercite al
  menos los endpoints CRUD. `src/api_v2` tiene 0 tests hoy — esto es
  **bloqueador**. PR 5.0 añade `src/tests/api_v2/test_routers_smoke.py`.
- **Pydantic primero**: si un endpoint recibe JSON dinámico, definir un
  `BaseModel` con `model_config = ConfigDict(extra='allow')` en lugar de `Any`.
- **OpenAPI diff**: después de la migración, comparar el schema OpenAPI generado
  con el de antes. Cualquier breaking change en la API HTTP debe documentarse.
- **Subir `disallow_untyped_defs` a `true`** para `src/api_v2.*` al final de
  la fase.

**Gate de salida por router**:
- `mypy --strict src/api_v2/routers/<router>.py` pasa.
- Test smoke del router en verde.
- Sin `Any` en signatures públicas (request/response models).
- OpenAPI diff revisado y aprobado.

**Riesgo**: medio. Los modelos Pydantic amortiguan los errores de tipo en
runtime, pero un cambio en el schema OpenAPI puede romper clientes frontend.

---

### Fase 6 — Connectors: batch masivo (2-3 semanas)

**Objetivo**: liquidar el elefante. 799 `Any` en 60+ conectores, la mayoría con
`disallow_untyped_defs = false` y solo 1 test de muestra.

**Estrategia**: dividir en 6 lotes temáticos. Cada lote = 1 semana aprox.
Cada conector = 1 PR independiente dentro del lote.

### Lote 6.1 — Conectores de IA/chat (3-4 días)

| Conector | Any | Notas |
|----------|----:|-------|
| `connectors/openai_v2.py` | ~15 | Prioridad alta — muy usado |
| `connectors/anthropic.py` | ~10 | |
| `connectors/deepseek.py` | ~10 | |
| `connectors/huggingface.py` | ~8 | |

**Patrón de migración** (aplicable a todos los conectores IA):
- Definir `Protocol ChatCompletion` con métodos `complete()`, `stream()`.
- Reemplazar `response: Any` por `response: ChatCompletion`.
- Tipar `messages: list[ChatMessage]` con `ChatMessage = TypedDict`.

### Lote 6.2 — Conectores CRM (3-4 días)

`salesforce.py`, `hubspot.py`, `pipedrive.py`, `zoho_crm.py`. Definir
`Protocol CRMConnector` con `create_contact`, `get_deal`, `update_account`.

### Lote 6.3 — Conectores de mensajería (3-4 días)

`whatsapp.py`, `twilio.py`, `teams.py`, `discord.py`, `intercom.py`,
`freshdesk.py`, `zendesk.py`. Definir `Protocol MessagingConnector`.

### Lote 6.4 — Facturación electrónica LATAM (4-5 días) ⚠️ CRÍTICO

`afip_argentina.py`, `dian_colombia.py`, `sat_mexico.py`, `sri_ecuador.py`,
`sunat_peru.py`, `dte_chile.py`, `nfe.py`, `pix_brazil.py`.

**Riesgo especial**: estos conectores manejan XML fiscal firmado. Un error de
tipo puede invalidar un DTE. Revisión doble obligatoria:
1. Revisión técnica (tipos).
2. Revisión funcional (casos de prueba con XML reales de cada país).

### Lote 6.5 — Almacenamiento y base de datos (3-4 días)

`aws_s3.py`, `azure_blob.py`, `gcs.py`, `dropbox.py`, `mongo_connector.py`,
`mysql_connector.py`, `elastic.py`. Definir `Protocol StorageConnector`.

### Lote 6.6 — Resto de conectores (4-5 días)

`github.py`, `gitlab.py`, `jira.py`, `trello.py`, `asana.py`, `monday.py`,
`notion.py`, `confluence.py`, `airtable.py`, `typeform.py`, `mailchimp.py`,
`marketo.py`, `shopify.py`, `woocommerce.py`, `mercadolibre.py`, `square.py`,
`paypal.py`, `quickbooks.py`, `xero.py`, `wise.py`, `pagerduty.py`,
`datadog.py`, `new_relic.py`, `grafana.py`, `splunk.py`, `sumologic.py`,
`sentry.py`, `okta.py`, `azure_ad.py`, `vault.py`, `sendgrid.py`,
`mailgun.py`, `ruv.py`, `totvs.py`.

**Gate de salida por lote**:
- `mypy --strict src/connectors/<lote>/` pasa.
- Smoke test del conector en verde (mínimo: init + 1 llamada mock).
- `disallow_untyped_defs = false` se elimina progresivamente de `mypy.ini` por
  lote.

**Gate de salida de la fase 6 completa**:
- Línea `[[tool.mypy.overrides]] module = "src.connectors.*"` eliminada de
  `mypy.ini`.
- `mypy --strict src/connectors/` pasa.
- Cobertura de smoke tests ≥ 80% de conectores.

**Riesgo**: alto. Mitigación: PRs granulares por conector, canary deploy por
lote, rollback por conector vía feature flag si es posible.

---

### Fase 7 — Resto del código (1 semana)

**Objetivo**: limpiar los módulos restantes no críticos.

**Módulos** (208 Any en total):

| Módulo | Any | Notas |
|--------|----:|-------|
| `src/workflow` | 42 | 4 tests existentes |
| `src/marketplace` | 40 | Añadir smoke tests de publish/certify |
| `src/cli` | 34 | Tipar argumentos con `argparse.Namespace` subclasses |
| `src/tests` | 44 | Baja prioridad — mypy NO strict para tests |
| `src/partnership` | 18 | |
| `src/sync` | 16 | Añadir smoke tests |
| `src/tools` | 14 | 5 tests existentes |
| `src/agents` | 59 | Si no se migró en Fase 3, aquí |

**Estrategia**:
- Tratar cada módulo como en Fase 1 (un PR por módulo).
- Para `src/tests`: solo migrar `Any` en fixtures compartidos y helpers, no en
  casos de test individuales ( ROI bajo ).

**Gate de salida**: `rg "\bAny\b" --type py src/ | grep -v "^src/core" | wc -l`
≤ 80 (residuales solo en tests o documentados).

---

### Fase 8 — Hardening final (3-5 días)

**Objetivo**: cerrar el ciclo activando las flags de mypy más estrictas y
documentando lecciones.

**Tareas**:
- [ ] Eliminar las 4 excepciones de `mypy.ini`:
  ```ini
  # ELIMINAR:
  [[tool.mypy.overrides]] module = "src.connectors.*"  disallow_untyped_defs = false
  [[tool.mypy.overrides]] module = "src.agents.*"      disallow_untyped_defs = false
  [[tool.mypy.overrides]] module = "src.web.*"         disallow_untyped_defs = false
  [[tool.mypy.overrides]] module = "src.api_v2.*"      disallow_untyped_defs = false
  ```
- [ ] Activar a nivel global:
  ```ini
  disallow_any_explicit = true   # prohibe Any explícito salvo # type: ignore
  disallow_any_generics = true   # obliga a parametrizar dict/list/...
  disallow_any_unimported = true # prohibe Any de módulos sin stub
  ```
- [ ] `mypy --strict src/` pasa sin errores.
- [ ] Actualizar la skill `any-best-practices` con casos reales encontrados
  durante la migración (añadir sección "Casos del proyecto").
- [ ] Publicar retrospectiva en `docs/research/any-best-practices-retrospective.md`.
- [ ] Cerrar tag `any-migration-complete-<fecha>`.

**Gate de salida global**:
- `mypy --strict src/` verde en CI.
- `rg "\bAny\b" --type py src/ | grep -v "^src/core" | wc -l` ≤ 50.
- Las 50 (o menos) ocurrencias restantes tienen comentario `# legítimo:` o
  `# TODO: tipar` + ticket asociado.

---

## 4. Plantilla de PR por módulo

```markdown
## Any Migration: <módulo>

### Scope
- Módulo: `src/<modulo>/`
- Any antes: <N>
- Any después: <M> (justificados con `# TODO: tipar` o `# type: ignore`)

### Antipatrones corregidos
- [ ] `<N1>` × `dict` sin parametrizar → `dict[str, X]`
- [ ] `<N2>` × `-> Any` → tipo concreto / `TypeVar`
- [ ] `<N3>` × `: Any = None` → `X | None = None`
- [ ] `<N4>` × `Any` en parámetros → `object` / `Protocol` / tipo concreto

### Tests
- [ ] Tests existentes en verde
- [ ] Smoke tests añadidos: <lista>
- [ ] Cobertura módulo: <X>% → <Y>%

### mypy
- [ ] `mypy --strict src/<modulo>/` pasa
- [ ] Sin nuevos `# type: ignore` sin justificación

### Breaking changes
- [ ] No hay / [ ] Sí (detallar en CHANGELOG)

### Rollback
- `git revert <sha>` restaura el estado anterior.

### Referencias
- Skill: `.opencode/skills/any-best-practices/SKILL.md`
- Doc: `docs/research/any-best-practices.md`
- Plan: `docs/plans/any-migration-rollout.md` (Fase <N>)
```

---

## 5. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|:------------:|:-------:|-----------|
| Breaking change en SDK público | Media | Alto | Bump semver + aliases deprecados + CHANGELOG |
| Type confusion en conectores fiscales LATAM | Media | Muy alto | Revisión funcional + tests con XML reales |
| Performance regression por validación extra | Baja | Medio | Benchmark antes/después en PRs críticos |
| Burnout del equipo por scope grande | Alta | Medio | Fases cortas, celebrar wins, rotar revisores |
| Conflictos de merge entre fases | Media | Bajo | Integration branch `chore/any-migration` + rebase diario |
| `Any` legítimos eliminados por error | Media | Alto | Code review + tests + justificación obligatoria en PR |

---

## 6. Métricas de éxito

| Métrica | Baseline | Target Fase 8 |
|---------|---------:|--------------:|
| `Any` count en `src/` (excl. `src/core`) | 1,919 | ≤ 50 |
| `mypy --strict src/` errores | alto | 0 |
| `dict` sin parametrizar en `src/` (excl. core) | 300 | 0 |
| `-> Any` en `src/` (excl. core) | 132 | ≤ 10 (solo wrappers) |
| `: Any = None` en `src/` (excl. core) | 31 | 0 |
| Cobertura de tests en módulos migrados | variable | ≥ 70% |
| Módulos con `disallow_untyped_defs = false` | 4 | 0 |
| Módulos con `disallow_any_explicit = true` | 0 | todos |

---

## 7. Cronograma resumen

| Fase | Duración | Any eliminados | Módulos |
|------|----------|---------------:|---------|
| 0 — Setup | 1 día | 0 | — |
| 1 — Quick wins | 3-4 días | ~45 | 7 módulos pequeños |
| 2 — Security/data/compliance | 1 semana | ~144 | 5 módulos críticos |
| 3 — Strict zones | 1 semana | ~200 | orbital, hat, agents |
| 4 — SDK público | 1 semana | 129 | sdk/* |
| 5 — API v2 + Mobile | 1.5 semanas | 343 | api_v2, mobile |
| 6 — Connectors | 2-3 semanas | 799 | 60+ conectores en 6 lotes |
| 7 — Resto | 1 semana | ~208 | workflow, marketplace, cli, tests, etc. |
| 8 — Hardening | 3-5 días | residuales | mypy.ini cleanup |
| **TOTAL** | **6-8 semanas** | **~1,870** | **todo `src/` excepto `core/`** |

---

## 8. Comandos de auditoría (operativos durante toda la migración)

```bash
# Count global (excluyendo core)
rg "\bAny\b" --type py src/ | grep -v "^src/core" | wc -l

# Count por módulo
rg -c "\bAny\b" --type py src/ | grep -v "^src/core" | \
  awk -F: '{split($1,p,"/"); print p[2]"/"p[3]}' | \
  awk -F: '{c[$1]+=$2} END {for(k in c) print k,c[k]}' | sort -k2 -rn

# Antipatrones específicos
rg "\:\s*dict\s*[\,\)\=\:]" --type py src/ | grep -v "^src/core" | wc -l   # dict sin params
rg "\->\s*Any" --type py src/ | grep -v "^src/core" | wc -l                # retornos Any
rg "\:\s*Any\s*=\s*None" --type py src/ | grep -v "^src/core" | wc -l      # attr Any = None

# mypy estricto por módulo
mypy --strict src/<modulo>/

# Buscar Any sin justificación (sin TODO ni type: ignore cercano)
rg "\bAny\b" --type py -B1 -A1 src/ | rg -v "TODO|type: ignore|legítimo|wrapper"
```

---

## 9. Referencias

- Skill: [`.opencode/skills/any-best-practices/SKILL.md`](../../.opencode/skills/any-best-practices/SKILL.md)
- Doc de investigación: [`docs/research/any-best-practices.md`](../research/any-best-practices.md)
- Config mypy: [`mypy.ini`](../../mypy.ini)
- PEP 484 — Type Hints: https://peps.python.org/pep-0484/
- PEP 544 — Protocols: https://peps.python.org/pep-0544/
- mypy strict mode: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
