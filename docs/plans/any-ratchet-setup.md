# Any Ratchet — Setup & Troubleshooting

> Anti-deuda para `typing.Any` en Zenic-Flujo: pre-commit hook local + CI global.

## Índice

1. [Qué es el ratchet y por qué se usa](#1-qué-es-el-ratchet-y-por-qué-se-usa)
2. [Instalación local](#2-instalación-local)
3. [Cómo funciona](#3-cómo-funciona)
4. [Bypass](#4-bypass)
5. [Actualizar el baseline](#5-actualizar-el-baseline)
6. [Justificaciones válidas e inválidas](#6-justificaciones-válidas-e-inválidas)
7. [Troubleshooting](#7-troubleshooting)
8. [Referencias](#8-referencias)

---

## 1. Qué es el ratchet y por qué se usa

Un **ratchet** (trinquete) es un patrón de mejora gradual de calidad: la deuda
técnica existente se "congela" en un snapshot (baseline), y se prohíbe que
crezca. Solo puede bajar. Cada vez que se reduce legítimamente, se actualiza
el baseline al nuevo valor más bajo — el trinquete avanza y no puede retroceder.

### ¿Por qué no "eliminar todos los Any de una vez"?

La investigación profunda (ver `docs/research/any-best-practices.md` y el
worklog Task 3) demostró que la migración big-bang de `Any` con IA no funciona:

- **TypyBench (ICML 2025):** incluso Claude 3.5 Sonnet produce 127–466 errores
  Mypy por repo en benchmarks.
- **Casos reales:** Dropbox (4M LOC en 3 años), Zulip (50K en 6 meses),
  Eightfold (4M LOC con MonkeyType en prod) — todos incrementales.
- **Conectores fiscales LATAM:** no tienen OpenAPI spec; `dict[str, Any]` en
  boundaries de APIs externas es aceptado por la industria (Stripe, Slack,
  langchain, boto3).

**Meta realista:** ~50–100 `Any` justificados en boundaries, no 0 `Any`.

### Las dos capas del ratchet

| Capa | Dónde | Qué hace | Cuándo |
|------|-------|----------|--------|
| **Local** | `scripts/hooks/pre_commit_any_ratchet.py` | Bloquea commits que introduzcan `Any` **nuevos** sin justificación en archivos modificados | Al hacer `git commit` |
| **Global** | `.github/workflows/any-audit.yml` | Ejecuta `any_audit.py run --enforce` sobre todo `src/`, compara contra baseline, bloquea merge si el count sube | En cada PR y push a `main`/`develop` |

La capa local es **rápida y preventiva** (evita que la deuda entre). La capa
global es ** exhaustiva y de puerta** (verifica el estado completo del repo).

### Referencia a la skill

La clasificación de antipatrones y las justificaciones siguen la skill
`.opencode/skills/any-best-practices/SKILL.md`. Ver también
`docs/research/any-best-practices.md`.

---

## 2. Instalación local

### Requisitos

- Python ≥ 3.12
- `pre-commit` (instalable vía `pip install pre-commit`)
- Git (el hook usa `git show` para comparar staged vs HEAD)

### Pasos

```bash
# 1. Instalar pre-commit (si no está)
pip install pre-commit

# 2. Instalar los hooks en .git/hooks/
cd /path/to/Zenic-Flujo
pre-commit install

# 3. (Opcional) Ejecutar sobre todos los archivos una primera vez
pre-commit run --all-files
```

Después de `pre-commit install`, cada `git commit` ejecutará automáticamente
todos los hooks definidos en `.pre-commit-config.yaml`, incluyendo
`any-ratchet`.

### Ejecutar el hook standalone (sin pre-commit)

```bash
# Sobre archivos específicos
python3 scripts/hooks/pre_commit_any_ratchet.py src/foo.py src/bar.py

# Vía stdin
git diff --cached --name-only | python3 scripts/hooks/pre_commit_any_ratchet.py
```

---

## 3. Cómo funciona

### Hook local (`pre_commit_any_ratchet.py`)

1. **Recibe archivos** vía argv (pre-commit con `pass_filenames: true`) o stdin.
2. **Filtra** solo `.py` bajo `src/` excluyendo `src/core/` y `src/tests/`.
3. **Lee el contenido staged** con `git show :<file>` (lo que será commiteado).
4. **Lee el contenido en HEAD** con `git show HEAD:<file>`. Si el archivo es
   nuevo, todas las líneas se consideran "nuevas".
5. **Calcula líneas nuevas/modificadas** con `difflib.SequenceMatcher`
   (bloques `insert` y `replace`).
6. **Parsea el contenido staged con `ast`** y detecta ocurrencias de `Any`
   (params, retornos, atributos, vars, `cast(Any, ...)`, imports, y colecciones
   bare `dict`/`list`/`tuple`/`set`).
7. **Filtra**: solo ocurrencias en líneas nuevas **Y** sin justificación.
8. **Si hay violaciones**: imprime un mensaje claro con archivo, línea,
   antipatrón, contexto y sugerencia de reemplazo. Sale con código 1.

### CI global (`.github/workflows/any-audit.yml`)

1. **Triggers**: `pull_request` (opened/synchronize/reopened) y `push` a
   `main`/`develop`.
2. **Job** en `ubuntu-latest` con Python 3.12.
3. **Ejecuta**: `python3 scripts/any_audit/any_audit.py run --baseline .any-baseline.json --enforce`.
4. **Compara** el count actual contra `total_occurrences` del baseline.
5. **Si count > baseline**: el script sale con código 1 → el job falla → el
   merge se bloquea (con `--enforce`).
6. **Publica un comment** en el PR con el reporte markdown
   (`scripts/any_audit/reports/any_audit.md`), creado o actualizado vía
   `peter-evans/find-comment` + `peter-evans/create-or-update-comment`.
7. **Sube artifacts**: `any_audit.csv`, `any_audit.json`, `any_audit.md`
   (retención 30 días).
8. **Cache**: los reports se cachean entre runs para comparación incremental.

---

## 4. Bypass

Hay tres mecanismos de bypass, uno por capa.

### 4.1 Bypass local: env var `ANY_RATCHET_ALLOW=1`

```bash
ANY_RATCHET_ALLOW=1 git commit -m "wip: explorando API externa"
```

El hook emite un warning a stderr pero permite el commit. **Úsalo solo para
WIP/exploración** — el CI global seguirá verificando en el PR.

### 4.2 Bypass CI: label `any-bypass` en el PR

1. Crea/abre el PR.
2. Añade el label `any-bypass`.
3. El workflow detecta el label y omite `--enforce` (corre la auditoría pero
   no bloquea el merge). El comment del bot mostrará:
   `⚠️ Label any-bypass activo — --enforce omitido.`

**Úsalo solo cuando haya acuerdo explícito del reviewer** (e.g. integración de
un conector externo que requiere `dict[str, Any]` en el boundary).

### 4.3 Bypass permanente: justificar el `Any`

Si el `Any` es legítimo (e.g. boundary de API externa sin schema), añade un
comentario de justificación en la misma línea o en la anterior:

```python
def parse_webhook(payload: dict[str, Any]) -> str:  # legítimo: payload de API externa sin schema
    ...
```

El hook y la auditoría global marcan la ocurrencia como `justified` y no la
reportan como violación (aunque sigue contando en el total del baseline).

---

## 5. Actualizar el baseline

Cuando se haya reducido el count de `Any` legítimamente (e.g. se tiparon
varias funciones, se eliminaron imports muertos), actualiza el baseline para
"fijar" el nuevo techo:

```bash
# 1. Verificar que el count actual es menor que el baseline
python3 scripts/any_audit/any_audit.py run --baseline .any-baseline.json

# 2. Generar el nuevo baseline
python3 scripts/any_audit/any_audit.py baseline --out .any-baseline.json

# 3. Revisar el diff
git diff .any-baseline.json

# 4. Commitear
git add .any-baseline.json
git commit -m "chore(any): baseline snapshot — reducción de N ocurrencias"
```

> ⚠️ **Nunca subas el baseline manualmente** para "hacer pasar" un PR con
> regresión. El baseline solo debe bajar. Si sube, es una regresión que debe
> justificarse (label `any-bypass` + revisión) o revertirse.

### Flujo de reducción recomendado

1. Tipa un módulo o subconjunto de archivos.
2. Corre la auditoría localmente: `python3 scripts/any_audit/any_audit.py`.
3. Verifica que el count bajó.
4. Actualiza el baseline (pasos de arriba).
5. Abre un PR separado solo para el baseline (referencia el PR de tipado).

---

## 6. Justificaciones válidas e inválidas

### Marcadores reconocidos

El hook y la auditoría buscan estos marcadores como **subcadena** en la misma
línea del `Any` o en la inmediatamente anterior:

| Marker | Cuándo usarlo |
|--------|---------------|
| `# legítimo: <razón>` | El `Any` es necesario y justificado (e.g. boundary de API externa). |
| `# legitimo: <razón>` | Variante sin tilde (mismo efecto). |
| `# TODO: tipar` | Deuda reconocida que se tipará después. Se cuenta como justificada pero **debe** tener issue/PR asociado. |
| `# type: ignore` | Suppress de mypy/pyright. El `Any` puede ser inferido por el checker. |

### ✅ Justificaciones válidas

```python
# Boundary de API externa sin OpenAPI spec
def parse_stripe_webhook(payload: dict[str, Any]) -> str:  # legítimo: payload de Stripe, sin schema estable
    ...

# Decorador genérico que preserva la firma
from typing import Any, Callable, TypeVar
T = TypeVar("T")
def log_calls(fn: Callable[..., T]) -> Callable[..., T]:  # legítimo: preserva firma arbitraria
    def wrapper(*args: Any, **kwargs: Any) -> T:  # legítimo: args/kwargs genéricos
        return fn(*args, **kwargs)
    return wrapper

# TODO con issue asociado
def legacy_handler(data: Any) -> None:  # TODO: tipar — ver issue #1234
    ...
```

### ❌ Justificaciones inválidas (el hook las bloquea)

```python
# Sin justificación
def process(data: Any) -> Any:  # ❌ bloqueado
    ...

# Marker en línea NO adyacente (2+ líneas arriba)
# legítimo: esto es un boundary  ← demasiado lejos
def other():
    pass

def process(data: Any) -> None:  # ❌ bloqueado (el marker está a 3 líneas)
    ...

# Comentario que no es un marker reconocido
def process(data: Any) -> None:  # esto debería ser dict
    ...  # ❌ bloqueado (no usa un marker de la lista)

# Marker vacío sin razón
def process(data: Any) -> None:  # legítimo:
    ...  # ❌ bloqueado: el marker requiere una razón legible
```

> **Convención:** los markers `# legítimo:` y `# TODO: tipar` deben ir seguidos
> de una razón o referencia a issue. Un marker vacío se considera inválido en
> revisión (aunque el hook no lo valide sintácticamente — es una convención
> humana).

---

## 7. Troubleshooting

### `git show :<file>` falla con "fatal: ... no such path"

**Causa:** el archivo no está staged o el hook se ejecuta fuera del repo root.

**Solución:**
- Verifica que el archivo está staged: `git diff --cached --name-only | grep <file>`.
- Si ejecutas el hook standalone, usa `--project-root /path/to/repo`.
- Pre-commit siempre ejecuta desde el repo root, así que esto no debería pasar
  en el flujo normal.

### El hook reporta violaciones en líneas que no modifiqué

**Causa:** el hook compara contra `HEAD`. Si hiciste `git commit` previo sin
ejecutar el hook (e.g. `--no-verify`), las líneas de ese commit ya están en
`HEAD` y no se reportan. Pero si el archivo se reformateó (e.g. ruff-format
movió líneas), `difflib` puede marcar líneas como "modificadas" aunque el
contenido semántico no cambió.

**Solución:**
- Reformatea en un commit separado (sin cambios lógicos) para aislar el
  ruido del ratchet.
- O justifica los `Any` afectados con `# legítimo:` si son preexistentes.

### El CI falla pero localmente el hook pasa

**Causa:** el hook local solo chequea archivos modificados; el CI audita todo
`src/`. Si alguien commiteó `Any` sin justificación usando `--no-verify` o
antes de que el hook existiera, el CI lo detectará al comparar contra el
baseline.

**Solución:**
- Revisa el reporte markdown del comment del PR para ver qué archivos
  aportaron al count.
- Si el count subió por un commit previo (no por tu PR), el `--enforce`
  bloqueará tu PR aunque no hayas tocado esos archivos. En ese caso:
  - O bien tipa/reduce los `Any` nuevos (solución correcta).
  - O bien usa label `any-bypass` con justificación (solución temporal).
  - O bien actualiza el baseline (solo si la subida es legítima y acordada).

### `pre-commit install` no instala el hook

**Causa:** pre-commit no encuentra el hook o hay un error de sintaxis en
`.pre-commit-config.yaml`.

**Solución:**
```bash
# Valida el YAML
python3 -c "import yaml; yaml.safe_load(open('.pre-commit-config.yaml'))"

# Valida la config de pre-commit
pre-commit validate-config

# Reinstala
pre-commit uninstall
pre-commit install
```

### El hook es lento en archivos grandes

**Causa:** `difflib.SequenceMatcher` es O(n²) en el peor caso.

**Solución:**
- El hook solo procesa archivos staged, así que el impacto es bajo en commits
  normales.
- Si un archivo tiene miles de líneas modificadas, considera dividir el
  commit en partes más pequeñas (buena práctica de todos modos).

### Quiero excluir un archivo del ratchet

**Opciones:**
1. **Moverlo a `src/core/` o `src/tests/`** (excluidos por defecto).
2. **Ajustar `exclude` en `.pre-commit-config.yaml`** (afecta a todo el equipo):
   ```yaml
   - id: any-ratchet
     exclude: ^src/(core|tests|legacy)/.*\.py$
   ```
3. **Justificar los `Any` con `# legítimo:`** (preferido — no excluye el
   archivo, solo marca las ocurrencias como aceptadas).

---

## 8. Referencias

- **Skill:** `.opencode/skills/any-best-practices/SKILL.md`
- **Script de auditoría:** `scripts/any_audit/any_audit.py`
- **Hook local:** `scripts/hooks/pre_commit_any_ratchet.py`
- **CI workflow:** `.github/workflows/any-audit.yml`
- **Baseline:** `.any-baseline.json`
- **Investigación:** `docs/research/any-best-practices.md`
- **Plan de migración:** `docs/plans/any-migration-rollout.md`
- **Informe zero humo:** `download/any-migration-research-zero-humo.md`

---

*Mantenido por el equipo de plataforma. Última actualización: alineado con
Task 2+3 del worklog.*
