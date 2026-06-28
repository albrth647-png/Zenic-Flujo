#!/usr/bin/env python3
"""Tests para el pre-commit hook `pre_commit_any_ratchet.py`.

Cubre los casos clave:
- Bloquea un `Any` injustificado en archivo nuevo (exit 1).
- Permite un `Any` justificado con `# legítimo:` (exit 0).
- Bypass vía `ANY_RATCHET_ALLOW=1` (exit 0 con warning).
- Archivos fuera de scope (`src/core/`, `src/tests/`) se ignoran.
- `Any` en línea preexistente (no modificada) no se reporta.
- Colecciones bare (`dict` sin parametrizar) se detectan.
- `Any` ya presente en HEAD no se reporta como nuevo (ratchet).

Los tests crean un repo git temporal real para que `git show HEAD:<file>`
y `git show :<file>` funcionen de forma realista.

Uso:
    pytest scripts/hooks/tests/test_pre_commit_any_ratchet.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

HOOK_PATH = Path(__file__).resolve().parent.parent / "pre_commit_any_ratchet.py"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Ejecuta git en cwd y retorna el CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def temp_repo(tmp_path: Path) -> Path:
    """Crea un repo git temporal con un commit inicial vacío.

    El repo tiene la estructura mínima para que el hook funcione:
    - `.git/` inicializado
    - `src/` creado
    - usuario git configurado (para que commit funcione)
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # git init + config
    assert _run_git(["init", "-q"], repo).returncode == 0
    # Intentar cambiar rama default a main (git 2.28+)
    _run_git(["symbolic-ref", "HEAD", "refs/heads/main"], repo)
    assert _run_git(["config", "user.email", "test@example.com"], repo).returncode == 0
    assert _run_git(["config", "user.name", "Test"], repo).returncode == 0
    # Commit inicial vacío para que HEAD exista
    assert _run_git(["commit", "--allow-empty", "-m", "init"], repo).returncode == 0
    # Estructura src/
    (repo / "src").mkdir()
    return repo


def _write_and_stage(repo: Path, rel_path: str, content: str) -> None:
    """Escribe un archivo y lo stagea con git add."""
    file_path = repo / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    assert _run_git(["add", rel_path], repo).returncode == 0


def _run_hook(
    repo: Path,
    files: list[str],
    env_override: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Ejecuta el hook contra `files` con cwd=repo.

    Pasa los archivos vía argv (como hace pre-commit con pass_filenames: true).
    """
    env = os.environ.copy()
    # Asegurar que el hook no hereda un ANY_RATCHET_ALLOW del entorno del runner.
    env.pop("ANY_RATCHET_ALLOW", None)
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH), *files, "--project-root", str(repo)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_blocks_unjustified_any_in_new_file(temp_repo: Path) -> None:
    """Un `Any` injustificado en un archivo nuevo debe bloquear (exit 1)."""
    _write_and_stage(
        temp_repo,
        "src/connectors/foo.py",
        "from typing import Any\n\n\ndef parse(payload: Any) -> Any:\n    return payload\n",
    )
    result = _run_hook(temp_repo, ["src/connectors/foo.py"])
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    # El mensaje debe mencionar el archivo y la violación
    combined = result.stdout + result.stderr
    assert "src/connectors/foo.py" in combined
    assert "Any Ratchet" in combined or "any-ratchet" in combined.lower()
    # Debe sugerir un reemplazo
    assert "legítimo" in combined or "Protocol" in combined or "object" in combined or "TypeVar" in combined


def test_allows_justified_any(temp_repo: Path) -> None:
    """Un `Any` con `# legítimo:` debe pasar (exit 0).

    Nota: el hook detecta tanto el uso (`param_annotation`) como el import
    (`import_any`) como ocurrencias separadas — ambos deben justificarse.
    Esto es consistente con any_audit.py (el baseline cuenta import_any).
    Alternativa: usar `typing.Any` cualificado para evitar `from ... import Any`.
    """
    _write_and_stage(
        temp_repo,
        "src/connectors/foo.py",
        (
            "from typing import Any  # legítimo: boundary de API externa\n\n\n"
            "def parse(payload: Any) -> str:  # legítimo: payload de API externa sin schema\n"
            "    return str(payload)\n"
        ),
    )
    result = _run_hook(temp_repo, ["src/connectors/foo.py"])
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"


def test_allows_justified_any_with_todo_marker(temp_repo: Path) -> None:
    """El marker `# TODO: tipar` también justifica (en uso e import)."""
    _write_and_stage(
        temp_repo,
        "src/tools/bar.py",
        (
            "from typing import Any  # TODO: tipar\n\n\n"
            "def handler(data: Any) -> None:  # TODO: tipar\n"
            "    pass\n"
        ),
    )
    result = _run_hook(temp_repo, ["src/tools/bar.py"])
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


def test_allows_qualified_typing_any_without_import(temp_repo: Path) -> None:
    """Usar `typing.Any` cualificado evita el antipatrón import_any.

    Solo se reporta el uso (param_annotation), que se justifica con un marker.
    """
    _write_and_stage(
        temp_repo,
        "src/connectors/baz.py",
        (
            "import typing\n\n\n"
            "def parse(payload: typing.Any) -> str:  # legítimo: payload de API externa\n"
            "    return str(payload)\n"
        ),
    )
    result = _run_hook(temp_repo, ["src/connectors/baz.py"])
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


def test_bypass_env_var(temp_repo: Path) -> None:
    """`ANY_RATCHET_ALLOW=1` permite el commit con warning."""
    _write_and_stage(
        temp_repo,
        "src/foo.py",
        "from typing import Any\n\ndef f(x: Any) -> Any:\n    return x\n",
    )
    result = _run_hook(
        temp_repo,
        ["src/foo.py"],
        env_override={"ANY_RATCHET_ALLOW": "1"},
    )
    assert result.returncode == 0, f"Expected exit 0 with bypass, got {result.returncode}"
    assert "bypass" in result.stderr.lower() or "ANY_RATCHET_ALLOW" in result.stderr


def test_out_of_scope_files_ignored(temp_repo: Path) -> None:
    """Archivos en src/core/ y src/tests/ se ignoran (exit 0)."""
    _write_and_stage(
        temp_repo,
        "src/core/db.py",
        "from typing import Any\n\ndef f(x: Any) -> Any:\n    return x\n",
    )
    _write_and_stage(
        temp_repo,
        "src/tests/test_foo.py",
        "from typing import Any\n\ndef test_f(x: Any) -> Any:\n    return x\n",
    )
    result = _run_hook(temp_repo, ["src/core/db.py", "src/tests/test_foo.py"])
    assert result.returncode == 0, f"Expected exit 0 for out-of-scope, got {result.returncode}\nstderr: {result.stderr}"


def test_non_python_files_ignored(temp_repo: Path) -> None:
    """Archivos .md / .json / sin extensión .py se ignoran."""
    _write_and_stage(temp_repo, "src/readme.md", "# Some doc with Any mention\n")
    _write_and_stage(temp_repo, "src/config.json", '{"a": "Any"}\n')
    result = _run_hook(temp_repo, ["src/readme.md", "src/config.json"])
    assert result.returncode == 0


def test_existing_any_in_head_not_flagged(temp_repo: Path) -> None:
    """Un `Any` ya presente en HEAD no se reporta al modificar otra línea.

    Esto verifica la semántica del ratchet: la deuda existente no bloquea,
    solo los Any NUEVOS.
    """
    # Commit 1: archivo con Any preexistente en HEAD
    _write_and_stage(
        temp_repo,
        "src/svc.py",
        (
            "from typing import Any\n\n\n"
            "def old_fn(x: Any) -> Any:\n    return x\n"
        ),
    )
    assert _run_git(["commit", "-m", "add old_fn with Any"], temp_repo).returncode == 0

    # Commit 2: modificar una línea DISTINTA (añadir una función sin Any)
    _write_and_stage(
        temp_repo,
        "src/svc.py",
        (
            "from typing import Any\n\n\n"
            "def old_fn(x: Any) -> Any:\n    return x\n\n\n"
            "def new_fn(y: int) -> int:\n    return y + 1\n"
        ),
    )
    result = _run_hook(temp_repo, ["src/svc.py"])
    assert result.returncode == 0, (
        f"Expected exit 0 (old Any in HEAD, new line has no Any), got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )


def test_new_any_in_modified_file_blocked(temp_repo: Path) -> None:
    """Añadir un `Any` nuevo a un archivo existente debe bloquear."""
    # Commit 1: archivo limpio en HEAD
    _write_and_stage(
        temp_repo,
        "src/svc.py",
        "def old_fn(x: int) -> int:\n    return x\n",
    )
    assert _run_git(["commit", "-m", "clean file"], temp_repo).returncode == 0

    # Commit 2: añadir función con Any injustificado
    _write_and_stage(
        temp_repo,
        "src/svc.py",
        (
            "def old_fn(x: int) -> int:\n    return x\n\n\n"
            "from typing import Any\n\n\ndef new_fn(y: Any) -> Any:\n    return y\n"
        ),
    )
    result = _run_hook(temp_repo, ["src/svc.py"])
    assert result.returncode == 1, (
        f"Expected exit 1 (new unjustified Any), got {result.returncode}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "new_fn" in combined or "src/svc.py" in combined


def test_bare_dict_detected(temp_repo: Path) -> None:
    """Una colección bare `dict` sin parametrizar se detecta como antipatrón."""
    _write_and_stage(
        temp_repo,
        "src/data.py",
        "def get_config() -> dict:\n    return {}\n",
    )
    result = _run_hook(temp_repo, ["src/data.py"])
    assert result.returncode == 1, (
        f"Expected exit 1 for bare dict, got {result.returncode}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "bare_dict" in combined or "dict[" in combined or "Parametriza" in combined


def test_imports_and_module_run(temp_repo: Path) -> None:
    """Smoke test: el hook se importa sin errores y --help funciona."""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"--help failed: {result.stderr}"
    assert "any-ratchet" in result.stdout.lower() or "any" in result.stdout.lower()


def test_no_files_returns_zero(temp_repo: Path) -> None:
    """Sin archivos (argv vacío y stdin cerrado), retorna 0 (no-op)."""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH), "--project-root", str(temp_repo)],
        cwd=str(temp_repo),
        capture_output=True,
        text=True,
        env={**os.environ},
        # stdin cerrado (no tty, no input) → _read_stdin_files lee ""
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0, f"Expected exit 0 with no files, got {result.returncode}\nstderr: {result.stderr}"
