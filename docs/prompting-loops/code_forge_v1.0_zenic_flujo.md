# ============================================================================
# Code-Forge v1.0 — Zenic-Flujo Edition
# ============================================================================
# Adaptado al proyecto Zenic-Flujo (Python + TypeScript bilingüe).
# Validado en sandbox con fixture real.
# Construido para producción a largo plazo — no para romperse en 3 días.
#
# Mejoras de producción añadidas tras investigación adicional:
#   - Run Ledger (developersdigest.tech): permission → action → log → review → rollback
#   - Canary fix application (Google SRE): fix a 1 archivo, verificar, expandir
#   - Scope discipline (88% AI agents fail): SPECIFY con EARS + data readiness
#   - Rollback obligatorio: si no hay rollback, la acción es high-risk
#
# Fuentes base (15+):
#   - TDAD paper (arxiv Mar 2026): TDD contextual > TDD procedural
#   - SDD workflow (BCMS 2026, GitHub Spec Kit, AWS Kiro, gentle-ai)
#   - Reflexion (NeurIPS 2023): verbal reinforcement
#   - Aider Architect/Editor (Sep 2024): SOTA code editing
#   - Anthropic CC Sandboxing (Oct 2025): dual filesystem+network
#   - Simon Willison Red/Green TDD (Feb 2026)
#   - gentle-ai delegation triggers (Gentleman Programming)
#   - LangChain Context Engineering: write/select/compress/isolate
#   - developersdigest: Run Ledger pattern
#   - digitalapplied: 88% failure patterns prevention
#   - Google SRE: canary release pattern aplicado a fixes
# ============================================================================

rol: Code-Forge Agent v1.0 — Zenic-Flujo Edition
objetivo: implementar {SPEC} con 12 gates pasando, score >= 8/10,
          FINAL_VERIFY pasando, y Run Ledger documentado
modelo_target: glm-5.2

# ----------------------------------------------------------------------------
# Filosofia: Producción a largo plazo
# ----------------------------------------------------------------------------
filosofia:
  principio: "Cada fix debe ser reversible, verificado, y documentado"
  reglas:
    - Si no puedes escribir el rollback, la acción es high-risk (NO ejecutar)
    - Cada fix se aplica primero a 1 archivo (canary), se verifica, luego expande
    - El Run Ledger viaja con cada task — sin ledger, no hay entrega
    - El sandbox aísla sin bloquear trabajo legitimo (allowlist, no bloqueo total)
    - TDD es contexto, no ceremonia (TDAD paper: procedural TDD +9.94% regresiones)
    - 12 gates pass + FINAL_VERIFY pass = necesario, no suficiente
    - Memoria cross-session obligatoria (memory.json sobrevive entre sesiones)

# ----------------------------------------------------------------------------
# SDD 4 fases como backbone (estandar 2026)
# ----------------------------------------------------------------------------
# Evidencia: BCMS 2026 — 3-10x first-pass success rate vs vibe coding
# Evidencia: digitalapplied — scoping disciplinado previene 61% de fallos

sdd_backbone:
  fases:
    specify:
      descripcion: "Spec en EARS notation + data readiness check"
      human_checkpoint: true
      model: haiku
      output: spec.md con EARS statements + data_dependencies
      produccion_check: |
        ANTES de aprobar el spec, verificar:
          1. ¿El spec toca 1 bug o feature atómica? (NO scope creep)
          2. ¿Los datos necesarios existen y son consistentes?
          3. ¿El rollback es posible? (escribir el undo path)
          4. ¿Hay tests existentes que puedan verificar el fix?
        Si cualquiera falla → NO aprobar, pedir clarificación al humano.

    plan:
      descripcion: "Derivation plan + architectural constraints + stack detection"
      human_checkpoint: true
      model: sonnet
      output: plan.md con dependencias + stack detectado
      produccion_check: |
        ANTES de aprobar el plan, verificar:
          1. Stack detectado: Python (src/), TypeScript (frontend/src/), o ambos
          2. Blast radius: cuántos archivos se tocan + cuántos dependen de ellos
          3. Si blast_radius > 20 archivos → decompose en sub-tasks atómicas
          4. Si toca 2+ archivos no triviales → delegation trigger (un writer + review)

    tasks:
      descripcion: "Atomic tasks breakdown con DAG + Run Ledger por task"
      human_checkpoint: true
      model: sonnet
      output: tasks.json con DAG + run_ledger por task
      produccion_check: |
        Cada task debe tener:
          1. Archivos afectados (max 3 por task — canary principle)
          2. Funciones publicas tocadas (de AST-scan)
          3. Tests existentes que deben seguir pasando
          4. Rollback path explícito (git checkout, git revert, o git stash)
          5. Stack de cada archivo (Python/TS) para cargar herramientas correctas

    implement:
      descripcion: "Code generation con contextual TDD + canary application"
      human_checkpoint: false
      model: sonnet
      output: codigo + tests + run_ledger actualizado

# EARS notation (Easy Approach to Requirements Syntax)
ears_notation:
  ubiquitous:    "The system shall X"
  event_driven:  "When Y, the system shall X"
  state_driven:  "While in state Z, the system shall X"
  optional:      "Where feature F is enabled, the system shall X"
  unwanted:      "If X then the system shall Y"

# ----------------------------------------------------------------------------
# Run Ledger (developersdigest.tech) — OBLIGATORIO para producción
# ----------------------------------------------------------------------------
# Evidencia: developersdigest "Permissions, Logs, Rollback for AI Coding Agents"
# "Si no puedes escribir el rollback, la acción es high-risk"

run_ledger:
  descripcion: |
    Registro compacto que viaja con cada task del agente.
    Vive en workdir/run_ledger.json y se actualiza tras cada acción.
    Sin ledger completo, NO hay entrega.

  estructura:
    run_id: "zenic-fix-<task_id>-<timestamp>"
    spec: "SPEC original en una línea"
    actions:
      - action_type: "edit_file | install_dep | run_test | git_commit"
        permission: "allow | ask | deny"
        target: "archivo o comando"
        diff_summary: "antes: X líneas → después: Y líneas"
        before_sha: "git sha antes de la acción"
        after_sha: "git sha después de la acción"
        rollback: "git checkout <file> | git revert <sha> | git stash pop"
        verified: true | false
    approvals:
      - phase: "specify | plan | tasks | implement | verify | fix"
        approved_by: "human | auto"
        timestamp: "ISO 8601"
    proof:
      - gate_name: "tests_pass | lint_clean | etc."
        passed: true | false
        evidence: "stdout resumen o error"
    final_status: "pass | fail | halted"

  reglas:
    - "Cada acción debe tener rollback definido ANTES de ejecutarse"
    - "Si rollback no es posible → acción es high-risk → pedir aprobación humana"
    - "Ledger se escribe a disco tras cada acción (no solo al final)"
    - "Si el ledger se corrompe → HALT inmediato (no continuar a ciegas)"

# ----------------------------------------------------------------------------
# Canary Fix Application (Google SRE pattern)
# ----------------------------------------------------------------------------
# Evidencia: Google SRE Workbook — canary release aplicado a fixes de código
# Aplicar fix a 1 archivo, verificar, luego expandir a los demás

canary_fix:
  descripcion: |
    Cuando un task toca múltiples archivos:
      1. Aplicar fix al archivo PRIMERO en orden de dependencias (bottom-up)
      2. Verificar gates sobre ese archivo solo
      3. Si pasa → aplicar al siguiente archivo
      4. Si falla → rollback ese archivo, NO continuar
      5. Si todos pasan individualmente → verificación conjunta (FINAL_VERIFY)

  orden_dependencias:
    python: "models → repositories → services → blueprints → tests"
    typescript: "types → hooks → components → pages → tests"

  ventaja: |
    Si el fix rompe algo, sabes EXACTAMENTE qué archivo lo rompió.
    No tienes que debuggear un diff de 5 archivos simultáneos.

# ----------------------------------------------------------------------------
# Contextual TDD (reemplaza TDD rígido)
# ----------------------------------------------------------------------------
# Evidencia: TDAD paper (arxiv Mar 2026)
# TDD prompting alone AUMENTÓ regresiones 9.94% en modelos pequeños.

contextual_tdd:
  filosofia: |
    NO decirle al modelo "usa TDD, escribe tests primero".
    SINO: antes de IMPLEMENT, AST-scan identifica:
      1. Que tests existen ya para los archivos afectados
      2. Que funciones publicas seran tocadas por el cambio
      3. Que archivos dependen de los archivos afectados (blast radius)
    Inyectar eso en el prompt de IMPLEMENT como CONTEXTO accionable.

  implementacion_bilingue: |
    Antes de fase IMPLEMENT:
      1. Detectar stack de cada target_file:
         - Python: si termina en .py o está en src/
         - TypeScript: si termina en .ts/.tsx o está en frontend/src/
      2. AST-scan de target_files (Python con ast, TS con typescript compiler API)
      3. Identificar funciones publicas (no _private en Python, no _prefixed en TS)
      4. Buscar test files correspondientes:
         - Python: test_<module>.py en tests/ o mismo dir
         - TS: <module>.test.tsx en __tests__/ o mismo dir
      5. Para cada archivo afectado, encontrar importers (blast radius)
      6. Inyectar en prompt:
         - "Estos tests existen y deben seguir pasando: [lista]"
         - "Estas funciones publicas son contratos: [lista]"
         - "Estos archivos importan los que tocas: [lista]"

# ----------------------------------------------------------------------------
# Delegation Triggers (4 reglas simples)
# ----------------------------------------------------------------------------
# Evidencia: gentle-ai (Gentleman Programming)

delegation_triggers:
  - trigger: "Leer 4+ archivos para entender un flow"
    accion: "Delegar exploracion a sub-agente o run exploration phase"

  - trigger: "Tocar 2+ archivos no-triviales (>50 líneas cambiadas)"
    accion: "Usar un writer + requerir fresh review antes de completion"

  - trigger: "Commit, push, o PR despues de code changes"
    accion: "Run fresh review a menos que el diff sea trivial (docs/text)"

  - trigger: "Long monolithic session con complejidad acumulada (>10 iteraciones)"
    accion: "Pause y delegate, re-plan, o justifica por que no delegar"

# ----------------------------------------------------------------------------
# Per-phase model assignment
# ----------------------------------------------------------------------------
# Evidencia: gentle-ai, OpenCode — optimiza costo/calidad

per_phase_models:
  specify:    haiku    # barato, solo parsea requirements
  plan:       sonnet   # razonamiento
  tasks:      sonnet   # descompone
  implement:  sonnet   # escribe codigo
  verify:     none     # sin LLM, determinista
  critique:   sonnet   # diagnostica
  fix:        none     # aplica diffs, sin LLM
  final:      none     # test suite, sin LLM

# ----------------------------------------------------------------------------
# Persistent memory simple (cross-session)
# ----------------------------------------------------------------------------
# Evidencia: Engram (Gentleman Programming) — simplificado para v1.0

persistent_memory:
  formato: "JSON file en workdir/memory.json"
  cross_session: true  # sobrevive entre sesiones

  estructura:
    reflections:
      - iteration_id
      - summary_300_tokens
      - verbal_reflection
      - key_learnings_5_max
      - score
      - root_cause
      - files_affected

  uso: |
    Antes de CRITIQUE:
      1. Cargar memory.json
      2. Jaccard similarity entre failures actuales y reflections pasadas
      3. Top-5 mas relevantes inyectadas en prompt de CRITIQUE
      4. Tras CRITIQUE, nueva reflexion se anade al JSON

# ----------------------------------------------------------------------------
# Sandbox dual bilingüe (Anthropic CC + Codex pattern)
# ----------------------------------------------------------------------------
# Evidencia: Anthropic CC Oct 2025 — 84% menos prompts de permiso
# Adaptado a Zenic-Flujo: Python (src/) + TypeScript (frontend/src/)

sandbox:
  tipo: subprocess + rlimits + env_sanitization + filesystem_isolation + network_allowlist

  filesystem:
    - workdir dedicado en /tmp/forge_<run_id>/ (writable)
    - project_root read-only (puede leer todo Zenic-Flujo, no modificar fuera de target_files)
    - snapshot/restore via git stash en project_root

  network:
    method: allowlist_proxy
    dominios_permitidos:
      - pypi.org          # pip install (Python deps)
      - registry.npmjs.org # npm install (TS deps)
      - github.com         # git fetch (solo lectura)
    todo_lo_demas: bloqueado
    implementacion: |
      Proxy Unix domain socket corre FUERA del sandbox.
      El sandbox monta /etc/resolv.conf apuntando al proxy.
      El proxy decide qué dominios permitir.
      Si una conexión sale a un dominio no autorizado → connection refused.

  rlimits:
    RLIMIT_CPU: 1800           # 30 min por gate
    RLIMIT_AS: 4_000_000_000   # 4 GB
    RLIMIT_FSIZE: 500_000_000  # 500 MB
    RLIMIT_NPROC: 200
    RLIMIT_NOFILE: 1024
    RLIMIT_CORE: 0

  env_sanitization:
    keep_only: [PATH, HOME, USER, LANG, PYTHONPATH, TMPDIR,
                NODE_ENV, VIRTUAL_ENV, PYTHONUNBUFFERED,
                WFD_DATA_DIR]  # Zenic-Flujo necesita WFD_DATA_DIR para SQLite
    strip_patterns: [*_SECRET, *_TOKEN, *_API_KEY, *_PASSWORD,
                     WFD_SESSION_SECRET, WFD_LICENSE_SECRET]
    inject:
      NODE_ENV: "test"
      PYTHONUNBUFFERED: "1"
      WFD_DATA_DIR: "/tmp/forge_<run_id>/data"

# ----------------------------------------------------------------------------
# 12 Gates (6 hard + 6 soft) — BILINGÜE
# ----------------------------------------------------------------------------
# Cada gate detecta stack automáticamente y usa la herramienta correcta.

hard_gates:  # TODAS deben pasar. Si una falla, no hay entrega.
  - tests_pass              # Python: pytest -x | TS: vitest run
  - tests_deterministic     # 3 runs, exit codes identicos
  - no_security_issues      # AST: eval/exec/pickle/shell=True + secrets + SQL injection
  - no_broken_imports       # Python: import check | TS: tsc --noEmit
  - no_circular_imports     # Python: AST DFS | TS: madge --circular
  - integration_smoke       # Python: python -c import | TS: vite build

soft_goals:  # Score 0-10, umbral 8 ponderado
  - coverage_branch >= 85   # Python: pytest --cov | TS: vitest --coverage v8
  - lint_clean              # Python: ruff (incluye dead code, TODO) | TS: eslint
  - types_clean             # Python: mypy --strict | TS: tsc --strict
  - mutation_score >= 80    # Python: mutmut | TS: stryker (weight=2)
  - complexity_max <= 10    # Python: radon cc | TS: eslint complexity
  - test_quality            # ratio behavior-tests/src >= 30%

# ----------------------------------------------------------------------------
# Stack detection automática (bilingüe)
# ----------------------------------------------------------------------------

stack_detection:
  python:
    trigger: "archivo termina en .py O está en src/"
    herramientas:
      test_runner: pytest
      linter: ruff
      type_checker: mypy --strict
      coverage: pytest --cov --cov-branch
      mutation: mutmut
      circular_deps: AST DFS scan
      build: python -c "import module"

  typescript:
    trigger: "archivo termina en .ts/.tsx O está en frontend/src/"
    herramientas:
      test_runner: vitest
      linter: eslint
      type_checker: tsc --strict
      coverage: vitest --coverage --provider=v8
      mutation: "@stryker-mutator/core + @stryker-mutator/vitest-runner"
      circular_deps: madge --circular
      build: vite build

  ambos:
    trigger: "task toca archivos Python Y TypeScript (ej: fix API + frontend)"
    comportamiento: "correr gates Python sobre src/ Y gates TS sobre frontend/src/ en paralelo"

# ----------------------------------------------------------------------------
# 4 tipos de tests (no 8) — simplificación pragmática
# ----------------------------------------------------------------------------

tipos_de_tests:
  static:
    descripcion: "TypeScript/eslint, Python/mypy"
    costo: "muy bajo"
    confianza: "baja"
  unit:
    descripcion: "Funcion/hook aislado con mocks"
    costo: "bajo"
    confianza: "media"
  integration:
    descripcion: "Componente con hijos reales + interacciones"
    costo: "medio"
    confianza: "alta"
    filosofia: "Mostly integration (Kent C. Dodds)"
  e2e:
    descripcion: "Test suite completo (FINAL_VERIFY)"
    costo: "alto"
    confianza: "maxima"

# ----------------------------------------------------------------------------
# 5 Capas de rigurosidad (con evidencia + producción hardening)
# ----------------------------------------------------------------------------

capas_rigurosidad:

  capa_1_contextual_tdd:
    evidencia: "TDAD paper Mar 2026 - contextual > procedural"
    descripcion: |
      AST-scan identifica tests existentes y funciones publicas afectadas.
      Se inyecta en el prompt como CONTEXTO accionable.
      Bilingüe: detecta Python y TypeScript automáticamente.

  capa_2_reflexion_verbal_episodic:
    evidencia: "Reflexion NeurIPS 2023 - 91% pass@1 HumanEval"
    descripcion: |
      Tras cada fallo, LLM genera reflexion verbal (200-400 tokens).
      Se guarda en memory.json (cross-session).
      Top-5 relevantes inyectadas en CRITIQUE.

  capa_3_sandbox_dual:
    evidencia: "Anthropic CC Oct 2025 - 84% menos prompts"
    descripcion: |
      Filesystem isolation (workdir writable, project_root read-only)
      + network allowlist proxy (pypi, npmjs, github)
      + rlimits + env_sanitization.

  capa_4_run_ledger:
    evidencia: "developersdigest - permissions/logs/rollback como un sistema"
    descripcion: |
      Cada acción del agente se registra en run_ledger.json con:
      permission, target, diff_summary, before_sha, after_sha, rollback, verified.
      Si rollback no es posible → acción high-risk → aprobación humana.
      Sin ledger completo → NO hay entrega.

  capa_5_canary_fix:
    evidencia: "Google SRE Workbook - canary release aplicado a fixes"
    descripcion: |
      Cuando un task toca múltiples archivos:
      aplicar a 1 primero, verificar, luego expandir.
      Orden: models → repositories → services → routes → tests (Python)
             types → hooks → components → pages → tests (TS)

# ----------------------------------------------------------------------------
# Loop: 8 fases (SDD + producción hardening)
# ----------------------------------------------------------------------------
# SPECIFY → PLAN → TASKS → IMPLEMENT → VERIFY → CRITIQUE → FIX → FINAL_VERIFY

fases:

  1_SPECIFY:
    tipo: agent (LLM haiku)
    accion: |
      1. Recibe SPEC del usuario.
      2. Verifica data readiness (¿los datos necesarios existen?).
      3. Verifica scope (¿es 1 bug/feature atómica? NO scope creep).
      4. Verifica rollback possibility (¿se puede deshacer el cambio?).
      5. Normaliza a EARS notation (5 patrones testables).
      6. Crea run_ledger.json con run_id + spec.
      7. Output: spec.md + run_ledger entry inicial.
      8. Human checkpoint.
    llm_calls: 1
    human_checkpoint: true

  2_PLAN:
    tipo: agent (LLM sonnet)
    accion: |
      1. Lee spec.md.
      2. Detecta stack de cada target_file (Python/TS/ambos).
      3. Calcula blast_radius via project_index (importers).
      4. Si blast_radius > 20 → decompose en sub-tasks.
      5. Identifica archivos a crear/modificar.
      6. Output: plan.md con stack + blast_radius + dependencias.
      7. Human checkpoint.
    llm_calls: 1
    human_checkpoint: true

  3_TASKS:
    tipo: agent (LLM sonnet)
    accion: |
      1. Lee plan.md.
      2. Descompone en atomic tasks (max 3 archivos por task — canary).
      3. Para cada task:
         - Archivos afectados
         - Funciones publicas tocadas (AST-scan)
         - Tests existentes que deben seguir pasando
         - Rollback path explícito
         - Stack de cada archivo
      4. Output: tasks.json con DAG + run_ledger por task.
      5. Human checkpoint.
    llm_calls: 1
    human_checkpoint: true

  4_IMPLEMENT:
    tipo: agent (LLM sonnet) + workflow (contextual TDD + canary)
    accion: |
      Pre-IMPLEMENT (workflow):
        1. Detectar stack de cada target_file.
        2. AST-scan para identificar funciones publicas.
        3. Buscar test files existentes (bilingüe).
        4. Calcular blast_radius (importers).
        5. Inyectar en prompt:
           - Tests que existen y deben seguir pasando
           - Funciones publicas afectadas (contratos)
           - Archivos que importan los afectados

      IMPLEMENT (LLM) con canary application:
        1. Aplicar fix al PRIMER archivo (orden dependencias).
        2. Actualizar run_ledger con before_sha + after_sha + rollback.
        3. Si toca 2+ archivos → delegation trigger (un writer + review).
        4. Tras cada archivo, verificar gates sobre ese archivo solo.
        5. Si pasa → siguiente archivo. Si falla → rollback + HALT ese task.
    llm_calls: 1
    human_checkpoint: false

  5_VERIFY:
    tipo: workflow (codigo, sin LLM)
    accion: |
      Ejecuta 12 gates en paralelo (8 workers), cada una en sandbox.

      Para cada gate, detectar stack y usar herramienta correcta:
        Python (src/):
          tests_pass: pytest -x
          tests_deterministic: 3 runs pytest
          no_security_issues: AST scan (eval/exec/pickle/shell=True + SQL + secrets)
          no_broken_imports: import check
          no_circular_imports: AST DFS
          integration_smoke: python -c "import module"
          coverage_branch: pytest --cov --cov-branch
          lint_clean: ruff (incluye vulture dead code + TODO scan)
          types_clean: mypy --strict
          mutation_score: mutmut (weight=2)
          complexity_max: radon cc
          test_quality: ratio behavior-tests/src

        TypeScript (frontend/src/):
          tests_pass: vitest run
          tests_deterministic: 3 runs vitest
          no_security_issues: AST scan (eval/innerHTML/dangerouslySetInnerHTML + secrets)
          no_broken_imports: tsc --noEmit
          no_circular_imports: madge --circular
          integration_smoke: vite build
          coverage_branch: vitest --coverage --provider=v8
          lint_clean: eslint --max-warnings=0 (incluye dead code + TODO)
          types_clean: tsc --strict
          mutation_score: stryker run (weight=2)
          complexity_max: eslint complexity rule
          test_quality: ratio behavior-tests/src

      Si task toca Python Y TS → correr ambas en paralelo.
    llm_calls: 0
    parallel: true
    parallel_workers: 8
    sandboxed: true

  6_CRITIQUE:
    tipo: agent (LLM sonnet) - Reflexion verbal
    accion: |
      SOLO si VERIFY fallo. Recibe:
        - failures de VERIFY
        - diff aplicado
        - top-5 reflexiones pasadas de memory.json (Jaccard similarity)
        - run_ledger actualizado

      LLM produce reflexion verbal (Reflexion paper):
        1. ANALYZE: causa raiz en una oracion
        2. WHY DIDN'T IT WORK LAST TIME: si ocurrio antes, que se intento
        3. HYPOTHESIS: cambio especifico que lo arreglaria
        4. RISK: podria el fix introducir nuevo fallo?
        5. REFLEXION: que aprendi sobre este problema

      La reflexion se guarda en memory.json (cross-session).
    llm_calls: 1

  7_FIX:
    tipo: agent (LLM sonnet Architect) + workflow (Editor + canary + ledger)
    accion: |
      Architect/Editor pattern (Aider SOTA) + canary + run_ledger:

      ARQUITECTO LLM recibe:
        - failures de VERIFY
        - codigo afectado
        - reflexiones episodic
      Produce: diagnostico + plan de fix en lenguaje natural.

      EDITOR LLM recibe:
        - Plan del Arquitecto
        - Archivos afectados
      Produce: unified diff (NO archivo completo).

      Validator (codigo) con canary:
        1. git stash (snapshot global)
        2. git apply diff al PRIMER archivo (canary)
        3. Actualizar run_ledger: before_sha, after_sha, rollback
        4. Verificar gates sobre ese archivo solo
        5. Si pasa → aplicar al siguiente archivo
        6. Si falla → git stash pop (rollback) + volver a Editor
        7. Si todos pasan individualmente → verificación conjunta (VERIFY completo)

      Veto rules (hardcoded):
        - VETO si diff borra un test sin reemplazo
        - VETO si diff introduce *_API_KEY = literal
        - VETO si diff es vacio
        - VETO si rollback no es posible (high-risk)
    llm_calls: 2

  8_FINAL_VERIFY:
    tipo: workflow (codigo, sin LLM)
    accion: |
      Tras todas las tasks, ejecutar test suite COMPLETO del proyecto:
        Python: pytest --tb=short (sobre src/tests/)
        TypeScript: vitest run --reporter=verbose (sobre frontend/src/__tests__/)

      Si un solo test falla:
        1. Identificar task culpable via run_ledger (git blame + before/after sha).
        2. Re-ejecutar esa task sola.
        3. Si tras 2 re-ejecuciones sigue fallando → HALT.
        4. Actualizar run_ledger con final_status.

      OBLIGATORIA. Atrapa errores de integración que las 12 gates
      individuales no detectan.
    llm_calls: 0
    sandboxed: true
    timeout: 900

  9_HALT:
    trigger:
      - 2 PIVOTs consecutivos sin mejorar (max_pivots=2)
      - total_budget_tokens excedido (2M)
      - score < 5 tras 50% del presupuesto
      - 3 fallos repetidos consecutivos
      - fase 8 falla tras 2 re-ejecuciones
      - run_ledger se corrompe
      - rollback no posible en acción high-risk
    accion: |
      Declarar FALLO controlado. Entregar:
        - Mejor version + run_ledger completo
        - Reporte de blockers
        - Reflexiones episodic
        - Hipótesis de por qué falló
        - Recomendación para humano
    llm_calls: 0

# ----------------------------------------------------------------------------
# Guards (con producción hardening)
# ----------------------------------------------------------------------------
guards:
  - si iteraciones > 30: aborta
  - si total_tokens > 2_000_000: aborta
  - si cascading_creates > 20: aborta (runaway)
  - si misma secuencia de fallos 3 veces: PIVOT forzado
  - si 2 PIVOTs consecutivos no mejoran: HALT
  - si score < 5 tras 50% del presupuesto: PIVOT forzado
  - si fase 8 falla tras 2 re-ejecuciones: HALT
  - si run_ledger no tiene rollback para una acción: HALT (high-risk)
  - si canary fix falla en archivo N: rollback ese archivo, NO continuar
  - si project_root se modifica fuera de target_files: HALT inmediato

# ----------------------------------------------------------------------------
# Regla de oro (bilingüe + producción)
# ----------------------------------------------------------------------------
regla_de_oro:
  flujo: |
    TAREA ENTRANTE
        ↓
    [SDD] SPECIFY → PLAN → TASKS (con human checkpoints + data readiness)
        ↓
    [CONTEXTUAL TDD BILINGÜE] AST-scan identifica tests + funciones publicas
        ↓
    [CANARY FIX] Aplicar a 1 archivo, verificar, expandir
        ↓
    [RUN LEDGER] Cada acción registrada con rollback
        ↓
    [12 GATES BILINGÜES] stack-aware, en paralelo, sandboxed
        ↓
    [CRITIQUE] reflexion verbal + memory cross-session
        ↓
    [FIX] Architect/Editor + unified diffs + canary
        ↓
    [FINAL_VERIFY] test suite completo Python + TypeScript
        ↓
    ENTREGA (solo si 6/6 hard + 6/6 soft score >= 8 + fase 8 pass + run_ledger completo)

# ----------------------------------------------------------------------------
# Output final (con run_ledger obligatorio)
# ----------------------------------------------------------------------------
output_final:
  solo_si:
    - hard_gates ALL pass (6/6)
    - soft_score >= 8/10 (weighted_avg real)
    - fase_8_final_verify pass
    - reflexion documentada en memory.json
    - run_ledger.json completo (todas las acciones con rollback)
    - todos los canary fixes verificados individualmente

  formato:
    - spec.md (EARS notation)
    - plan.md (con stack + blast_radius)
    - tasks.json (DAG + run_ledger por task)
    - codigo final (en disco)
    - tests finales (en disco)
    - memory.json (reflexiones cross-session)
    - run_ledger.json (registro completo de acciones)
    - score final (12 gates detalladas)
    - log de iteraciones con reflexiones verbales
    - unified diff entre penultima y ultima iteracion
    - metricas:
        - tokens_usados (por fase)
        - tiempo_total_seg
        - num_iteraciones
        - num_pivots
        - score_history
        - sandbox_runs
        - tipos_de_tests_escritos: {unit: N, integration: N, e2e: N}
        - stack_detectado: {python: bool, typescript: bool}
        - delegation_triggers_disparados: N
        - reflexiones_episodic_count
        - canary_fixes_aplicados: N
        - rollbacks_ejecutados: N
        - run_ledger_completo: true | false

# ============================================================================
# FIN Code-Forge v1.0 — Zenic-Flujo Edition (Production-Hardened)
# ============================================================================
