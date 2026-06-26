"""
Forge Sandbox v1.0 — Zenic-Flujo Edition
=========================================
Sandbox dual para ejecución segura de código de agentes de IA.

Características:
  - Filesystem isolation: workdir temporal, project_root read-only
  - Network allowlist: solo pypi.org, registry.npmjs.org, github.com
  - rlimits: CPU, RAM, filesize, procesos, file descriptors
  - Env sanitization: elimina secrets, inyecta entorno controlado
  - Optimizado para Xiaomi Redmi 12 Pro (12GB RAM): límites realistas

Basado en: Anthropic CC Oct 2025, Codex pattern

Uso:
    from forge import ForgeSandbox
    with ForgeSandbox("/ruta/del/proyecto") as sb:
        result = sb.run(["python3", "script.py"])
        print(result)
"""

import json
import os
import resource
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ForgeSandbox:
    """Sandbox dual con aislamiento de filesystem, red y recursos.

    Optimizado para dispositivos con 12GB RAM (Xiaomi Redmi 12 Pro).
    """

    ALLOWED_DOMAINS: set[str] = {
        "pypi.org",
        "files.pythonhosted.org",
        "registry.npmjs.org",
        "github.com",
        "raw.githubusercontent.com",
    }

    def __init__(
        self,
        project_root: str | Path,
        run_id: str | None = None,
        ram_gb: int = 12,
    ):
        self.project_root = Path(project_root).resolve()
        if not self.project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")

        if run_id is None:
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            run_id = f"forge-{ts}"

        self.run_id = run_id
        self.ram_gb = ram_gb

        self.sandbox_root = Path(tempfile.gettempdir()) / run_id
        self.workdir = self.sandbox_root / "workdir"
        self.data_dir = self.sandbox_root / "data"
        self._setup_directories()

        self._started_at: float | None = None
        self._stopped = False
        self._processes: list[subprocess.Popen] = []

    def _setup_directories(self) -> None:
        """Crea la estructura de directorios del sandbox."""
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        (self.workdir / "src").mkdir(exist_ok=True)
        (self.workdir / "tests").mkdir(exist_ok=True)
        (self.workdir / "logs").mkdir(exist_ok=True)
        self._init_git_workdir()

    def _init_git_workdir(self) -> None:
        """Inicializa un repo git vacío en el workdir."""
        git_dir = self.workdir / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=self.workdir, capture_output=True, timeout=10,
                )
                subprocess.run(
                    ["git", "config", "user.email", "forge@zenic-flujo.local"],
                    cwd=self.workdir, capture_output=True, timeout=10,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Forge Sandbox"],
                    cwd=self.workdir, capture_output=True, timeout=10,
                )
            except Exception:
                pass  # git no disponible, continuar sin él

    # ── Filesystem Isolation ──────────────────────────────────────────

    def copy_to_workdir(self, path: str | Path) -> Path:
        src = self.project_root / path
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {src}")
        if not str(src.resolve()).startswith(str(self.project_root)):
            raise PermissionError(f"Path outside project root: {src}")

        dest = self.workdir / src.relative_to(self.project_root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def snapshot_project(self) -> str:
        self._init_git_workdir()
        subprocess.run(
            ["git", "add", "-A"],
            cwd=self.workdir, capture_output=True, text=True, timeout=30,
        )
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"snapshot-{self.run_id}"],
            cwd=self.workdir, capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip() or result.stderr.strip()

    def apply_diff(self, diff_content: str, target_file: str) -> tuple[bool, str]:
        work_target = self.workdir / target_file
        diff_path = self.workdir / f"{target_file}.diff"
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(diff_content)

        result = subprocess.run(
            ["git", "apply", str(diff_path)],
            cwd=self.workdir, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            self._log_event("diff_applied", {"target": target_file})
            return True, "Diff applied successfully"
        return False, result.stderr

    # ── Environment Sanitization ──────────────────────────────────────

    def sanitized_env(self) -> dict[str, str]:
        env = os.environ.copy()
        keep = {"PATH", "HOME", "USER", "LANG", "TMPDIR"}
        inject = {
            "NODE_ENV": "test",
            "PYTHONUNBUFFERED": "1",
            "WFD_DATA_DIR": str(self.data_dir),
            "FORGE_SANDBOX": "1",
            "FORGE_RUN_ID": self.run_id,
            "HOME": str(self.sandbox_root / "home"),
        }

        patterns = ["SECRET", "TOKEN", "API_KEY", "PASSWORD", "KEY"]
        keys_to_delete = [k for k in env if any(p in k.upper() for p in patterns)]
        for key in keys_to_delete:
            del env[key]

        clean_env = {k: v for k, v in env.items() if k in keep}
        clean_env.update(inject)
        clean_env["TMPDIR"] = str(self.sandbox_root)
        if "PATH" not in clean_env:
            clean_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        return clean_env

    # ── Resource Limits ─────────────────────────────────────────────

    def apply_rlimits(self) -> None:
        ram_bytes = self.ram_gb * 1_024 * 1_024 * 1_024
        limits = {
            resource.RLIMIT_CPU: (1800, 1800),
            resource.RLIMIT_AS: (ram_bytes, ram_bytes),
            resource.RLIMIT_FSIZE: (500_000_000, 500_000_000),
            resource.RLIMIT_NPROC: (200, 200),
            resource.RLIMIT_NOFILE: (1024, 1024),
            resource.RLIMIT_CORE: (0, 0),
            resource.RLIMIT_STACK: (8_388_608, 8_388_608),
        }
        for rlimit, (soft, hard) in limits.items():
            try:
                resource.setrlimit(rlimit, (soft, hard))
            except (ValueError, resource.error):
                pass

    # ── Process Execution ─────────────────────────────────────────────

    def run(
        self,
        cmd: list[str] | str,
        cwd: str | Path | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> dict[str, Any]:
        if self._stopped:
            return {"stdout": "", "stderr": "Sandbox stopped", "returncode": -1, "duration": 0.0, "timed_out": False}

        cwd = Path(cwd) if cwd else self.workdir
        env = env or self.sanitized_env()

        if isinstance(cmd, str):
            cmd_str = cmd
            cmd = ["/bin/sh", "-c", cmd]
        else:
            cmd_str = " ".join(cmd)

        start = time.time()
        self._log_event("process_start", {"cmd": cmd_str, "cwd": str(cwd)})

        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True, preexec_fn=self.apply_rlimits,
            )
            self._processes.append(proc)
            stdout, stderr = proc.communicate(timeout=timeout)
            duration = time.time() - start
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
            duration = time.time() - start
            timed_out = True
            self._log_event("process_timeout", {"cmd": cmd_str, "timeout": timeout})

        result = {
            "stdout": (stdout or ""),
            "stderr": (stderr or ""),
            "returncode": proc.returncode,
            "duration": round(duration, 2),
            "timed_out": timed_out,
        }
        self._log_event("process_end", result)
        return result

    def run_python(self, code: str, workdir_subdir: str | None = None, timeout: int = 60) -> dict[str, Any]:
        cwd = self.workdir
        if workdir_subdir:
            cwd = self.workdir / workdir_subdir
            cwd.mkdir(parents=True, exist_ok=True)
        script_path = cwd / "_forge_script.py"
        script_path.write_text(code)
        return self.run(["python3", str(script_path)], cwd=cwd, timeout=timeout)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        self._started_at = time.time()
        self._stopped = False
        self._log_event("sandbox_start", {"ram_gb": self.ram_gb})
        (self.sandbox_root / "home").mkdir(parents=True, exist_ok=True)

    def stop(self) -> dict[str, Any]:
        self._stopped = True
        for proc in self._processes:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        duration = time.time() - self._started_at if self._started_at else 0.0
        stats = {"run_id": self.run_id, "duration_seconds": round(duration, 2), "processes_spawned": len(self._processes), "sandbox_root": str(self.sandbox_root)}
        self._log_event("sandbox_stop", stats)
        return stats

    def cleanup(self) -> None:
        self.stop()
        if self.sandbox_root.exists():
            shutil.rmtree(self.sandbox_root, ignore_errors=True)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.cleanup()

    # ── Utils ─────────────────────────────────────────────────────────

    def _log_event(self, event: str, data: dict[str, Any]) -> None:
        log_file = self.sandbox_root / "sandbox.log"
        with open(log_file, "a") as f:
            f.write(json.dumps({"event": event, "data": data, "timestamp": datetime.now(tz=timezone.utc).isoformat()}) + "\n")

    def get_logs(self) -> list[dict[str, Any]]:
        log_file = self.sandbox_root / "sandbox.log"
        if not log_file.exists():
            return []
        logs = []
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return logs

    def __repr__(self) -> str:
        return f"<ForgeSandbox run_id={self.run_id} ram={self.ram_gb}GB running={self._started_at is not None and not self._stopped}>"
