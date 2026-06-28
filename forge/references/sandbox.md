# Sandbox Dual — Protocolo Completo

Sandbox dual para ejecución segura de código de agentes de IA. Proporciona aislamiento de filesystem, red y recursos.

**Basado en:** Anthropic CC Oct 2025, Codex pattern

---

## API

```python
from forge import ForgeSandbox

with ForgeSandbox("/ruta/del/proyecto", ram_gb=12) as sb:
    result = sb.run(["python3", "script.py"])
    print(result["stdout"])
```

### Constructor

```python
ForgeSandbox(project_root: str | Path, run_id: str | None = None, ram_gb: int = 12)
```

- `project_root`: Raíz del proyecto (read-only)
- `run_id`: Opcional. Genera: `forge-<YYYYMMDD_HHMMSS>`
- `ram_gb`: RAM en GB para rlimits (default: 12, optimizado para Xiaomi Redmi 12 Pro)

### Context Manager

```python
with ForgeSandbox(project_root) as sb:
    # start() se llama automáticamente al entrar
    ...
# cleanup() se llama automáticamente al salir
```

### Métodos principales

| Método | Descripción |
|--------|-------------|
| `run(cmd, cwd, timeout, env)` | Ejecuta un comando en el sandbox |
| `run_python(code, workdir_subdir, timeout)` | Ejecuta código Python inline |
| `copy_to_workdir(path)` | Copia archivo del project_root al workdir |
| `snapshot_project()` | Crea un git stash snapshot del workdir |
| `apply_diff(diff_content, target_file)` | Aplica un diff a un archivo en el workdir |
| `sanitized_env()` | Retorna entorno sanitizado (sin secrets) |
| `start()` | Inicia el sandbox |
| `stop()` | Detiene el sandbox (mata procesos) |
| `cleanup()` | Detiene y elimina el sandbox |
| `get_logs()` | Retorna logs del sandbox |

---

## Estructura de directorios

```
/tmp/forge-<run_id>/
├── workdir/           # Writable: aquí se ejecuta el código
│   ├── src/           # Código copiado
│   ├── tests/         # Tests copiados
│   └── logs/          # Logs de ejecución
├── data/              # WFD_DATA_DIR para SQLite
└── home/              # HOME sanitizado
```

---

## Filesystem Isolation

- **workdir:** `/tmp/forge_<run_id>/workdir/` — writable, aquí se ejecuta todo
- **project_root:** Read-only. Solo se puede leer, no modificar fuera de target_files
- **copy_to_workdir:** Copia archivos específicos del project_root al workdir
- **snapshot/restore:** Vía `git stash` en el workdir

---

## Network Allowlist

Solo estos dominios están permitidos:

| Dominio | Propósito |
|---------|-----------|
| `pypi.org` | pip install (Python deps) |
| `files.pythonhosted.org` | Python package downloads |
| `registry.npmjs.org` | npm install (TypeScript deps) |
| `github.com` | git fetch (solo lectura) |
| `raw.githubusercontent.com` | Raw content downloads |

Todo lo demás está bloqueado. Implementación vía proxy Unix domain socket.

---

## Resource Limits (rlimits)

| Recurso | Límite |
|---------|--------|
| CPU | 1800 segundos (30 min por gate) |
| RAM (AS) | 12 GB (configurable vía `ram_gb`) |
| Filesize | 500 MB |
| Procesos | 200 |
| File Descriptors | 1024 |
| Core dumps | 0 (deshabilitado) |
| Stack | 8 MB |

---

## Environment Sanitization

**Variables eliminadas** (patrones de secrets):
- `*_SECRET`, `*_TOKEN`, `*_API_KEY`, `*_PASSWORD`, `*_KEY`

**Variables inyectadas:**
| Variable | Valor |
|----------|-------|
| `NODE_ENV` | `test` |
| `PYTHONUNBUFFERED` | `1` |
| `WFD_DATA_DIR` | `/tmp/forge_<run_id>/data` |
| `FORGE_SANDBOX` | `1` |
| `FORGE_RUN_ID` | `<run_id>` |
| `HOME` | `/tmp/forge_<run_id>/home` |
| `TMPDIR` | `/tmp/forge_<run_id>` |

**Variables conservadas:** `PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`

---

## Resultado de ejecución

```python
result = sb.run(["python3", "script.py"])
# {
#   "stdout": "...",
#   "stderr": "...",
#   "returncode": 0,
#   "duration": 1.23,
#   "timed_out": False
# }
```

---

## Ejemplo completo

```python
from forge import ForgeSandbox

project_root = "/ruta/del/proyecto"

with ForgeSandbox(project_root, ram_gb=8) as sb:
    # 1. Copiar archivos necesarios
    sb.copy_to_workdir("src/tools/crm/service.py")
    sb.copy_to_workdir("src/tools/crm/models.py")
    
    # 2. Aplicar diff
    diff = """--- a/service.py
+++ b/service.py
@@ -10,3 +10,5 @@
 def list_leads():
-    return db.query(Lead).all()
+    leads = db.query(Lead).all()
+    if not leads:
+        return []
+    return leads"""
    
    ok, msg = sb.apply_diff(diff, "src/tools/crm/service.py")
    
    # 3. Ejecutar tests
    result = sb.run(["python3", "-m", "pytest", "tests/test_crm.py", "-x", "-q"])
    
    # 4. Verificar resultado
    if result["returncode"] == 0:
        print("✅ Tests passed")
    else:
        print(f"❌ Tests failed: {result['stderr'][:200]}")
```
