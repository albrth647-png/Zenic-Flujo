"""
Tests for ForgeSandbox — Code-Forge v1.0
Cobertura: run, isolation, cleanup, env sanitization, rlimits, lifecycle
"""

import os
import tempfile
from pathlib import Path

import pytest

from forge.sandbox import ForgeSandbox


class TestForgeSandboxCreation:
    """Tests de creación e inicialización."""

    def test_creates_sandbox_with_valid_project_root(self):
        """ForgeSandbox crea estructura de directorios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            sb = ForgeSandbox(project, run_id="test-sandbox-001")

            assert sb.sandbox_root.exists()
            assert sb.workdir.exists()
            assert sb.data_dir.exists()
            assert (sb.workdir / "src").exists()
            assert (sb.workdir / "tests").exists()
            sb.cleanup()

    def test_rejects_nonexistent_project_root(self):
        """ForgeSandbox rechaza project root inexistente."""
        with pytest.raises(FileNotFoundError):
            ForgeSandbox("/nonexistent/path")

    def test_auto_generates_run_id(self):
        """run_id auto-generado si no se provee."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            sb = ForgeSandbox(project)
            assert sb.run_id.startswith("forge-")
            sb.cleanup()


class TestForgeSandboxRun:
    """Tests de ejecución."""

    def test_run_simple_command(self):
        """run ejecuta comando simple y captura output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                result = sb.run(["echo", "hello world"])
                assert result["returncode"] == 0
                assert "hello world" in result["stdout"]

    def test_run_string_command(self):
        """run acepta comando como string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                result = sb.run("echo hello")
                assert result["returncode"] == 0
                assert "hello" in result["stdout"]

    def test_run_failing_command(self):
        """run captura comando que falla."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                result = sb.run(["sh", "-c", "exit 42"])
                assert result["returncode"] == 42

    def test_run_timeout(self):
        """run detecta timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                result = sb.run(["sleep", "10"], timeout=1)
                assert result["timed_out"] is True
                assert result["returncode"] != 0

    def test_run_python_code(self):
        """run_python ejecuta código Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                result = sb.run_python('print("hello from forge")')
                assert result["returncode"] == 0
                assert "hello from forge" in result["stdout"]

    def test_run_python_with_return_value(self):
        """run_python ejecuta código que retorna valores vía print."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with ForgeSandbox(project) as sb:
                code = """
import json
data = {"result": "success", "value": 42}
print(json.dumps(data))
"""
                result = sb.run_python(code)
                assert result["returncode"] == 0
                assert '"result": "success"' in result["stdout"]

    def test_run_stopped_sandbox_fails_gracefully(self):
        """run en sandbox detenido falla graceful."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            sb = ForgeSandbox(project)
            sb.start()
            sb.stop()
            result = sb.run(["echo", "test"])
            assert result["returncode"] == -1
            assert "Sandbox stopped" in result["stderr"]
            sb.cleanup()


class TestFileSystemIsolation:
    """Tests de aislamiento de filesystem."""

    def test_copy_to_workdir(self):
        """copy_to_workdir copia archivo al workdir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            test_file = project / "test.py"
            test_file.write_text("print('hello')")

            with ForgeSandbox(project) as sb:
                dest = sb.copy_to_workdir(Path("test.py"))
                assert dest.exists()
                assert dest.read_text() == "print('hello')"

    def test_copy_to_workdir_preserves_subdirs(self):
        """copy_to_workdir preserva subdirectorios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            subdir = project / "src" / "tools"
            subdir.mkdir(parents=True)
            test_file = subdir / "service.py"
            test_file.write_text("def run(): pass")

            with ForgeSandbox(project) as sb:
                dest = sb.copy_to_workdir(Path("src/tools/service.py"))
                assert dest.exists()
                assert dest.read_text() == "def run(): pass"

    def test_copy_to_workdir_rejects_outside_project(self):
        """copy_to_workdir rechaza archivos fuera del project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            outside_file = Path(tmpdir) / "outside.txt"
            outside_file.write_text("secret")

            with ForgeSandbox(project) as sb, pytest.raises(PermissionError):
                sb.copy_to_workdir(Path("../outside.txt"))


class TestEnvSanitization:
    """Tests de sanitización de entorno."""

    def test_sanitized_env_contains_required_vars(self):
        """sanitized_env incluye vars requeridas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            sb = ForgeSandbox(project)
            env = sb.sanitized_env()

            assert env["NODE_ENV"] == "test"
            assert env["PYTHONUNBUFFERED"] == "1"
            assert env["FORGE_SANDBOX"] == "1"
            assert env["FORGE_RUN_ID"] == sb.run_id
            sb.cleanup()

    def test_sanitized_env_removes_secrets(self):
        """sanitized_env elimina variables con palabras sensibles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            os.environ["MY_SECRET_KEY"] = "super-secret-123"
            os.environ["API_TOKEN"] = "token-abc"

            sb = ForgeSandbox(project)
            env = sb.sanitized_env()

            assert "MY_SECRET_KEY" not in env
            assert "API_TOKEN" not in env

            # Limpiar
            del os.environ["MY_SECRET_KEY"]
            del os.environ["API_TOKEN"]
            sb.cleanup()

    def test_sanitized_env_keeps_path(self):
        """sanitized_env mantiene PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            sb = ForgeSandbox(project)
            env = sb.sanitized_env()
            assert "PATH" in env
            sb.cleanup()


class TestLifecycle:
    """Tests de ciclo de vida."""

    def test_context_manager(self):
        """Context manager inicia y limpia correctamente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            sandbox_root = None
            with ForgeSandbox(project) as sb:
                assert sb._started_at is not None
                assert sb._stopped is False
                sandbox_root = sb.sandbox_root

            # Después del context, debe limpiarse
            assert not sandbox_root.exists()

    def test_start_and_stop(self):
        """start y stop funcionan sin context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            sb = ForgeSandbox(project)
            sb.start()
            assert sb._started_at is not None
            assert sb._stopped is False

            stats = sb.stop()
            assert sb._stopped is True
            assert stats["run_id"] == sb.run_id
            assert stats["processes_spawned"] >= 0
            sb.cleanup()

    def test_cleanup_removes_sandbox_root(self):
        """cleanup elimina sandbox_root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            sb = ForgeSandbox(project)
            sb.start()
            root = sb.sandbox_root
            assert root.exists()

            sb.cleanup()
            assert not root.exists()


class TestLogging:
    """Tests de logging interno."""

    def test_get_logs(self):
        """get_logs retorna eventos registrados."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            with ForgeSandbox(project) as sb:
                sb.run(["echo", "hello"])
                logs = sb.get_logs()

                assert len(logs) >= 2  # al menos process_start + process_end
                assert logs[0]["event"] == "sandbox_start"
                assert any(log["event"] == "process_end" for log in logs)

    def test_empty_logs_before_any_action(self):
        """get_logs retorna lista vacía si no hay logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            sb = ForgeSandbox(project)
            assert sb.get_logs() == []
            sb.cleanup()


class TestSnapshotAndDiff:
    """Tests de snapshot y diff."""

    def test_snapshot_project(self):
        """snapshot_project crea stash en git."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            with ForgeSandbox(project) as sb:
                # Crear archivo en workdir
                test_file = sb.workdir / "test.txt"
                test_file.write_text("version 1")

                # Snapshot
                result = sb.snapshot_project()
                assert result is not None

    def test_apply_diff(self):
        """apply_diff aplica diff generado por git diff correctamente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            with ForgeSandbox(project) as sb:
                import subprocess
                test_file = sb.workdir / "test.txt"
                test_file.write_text("original content\n")

                sb._init_git_workdir()
                subprocess.run(["git", "config", "user.email", "test@test.com"],
                               cwd=sb.workdir, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Test"],
                               cwd=sb.workdir, capture_output=True)
                subprocess.run(["git", "add", "test.txt"], cwd=sb.workdir, capture_output=True)
                subprocess.run(["git", "commit", "-m", "initial"], cwd=sb.workdir, capture_output=True)

                # Modify file and capture git diff
                test_file.write_text("modified content\n")
                diff = subprocess.run(
                    ["git", "diff", "test.txt"],
                    cwd=sb.workdir, capture_output=True, text=True,
                ).stdout

                # Revert so apply has work to do
                test_file.write_text("original content\n")

                ok, msg = sb.apply_diff(diff, "test.txt")
                assert ok is True, f"Diff failed: {msg}"
                assert test_file.read_text() == "modified content\n"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
