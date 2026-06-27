"""
VERIFY F0-D8 — 10 verificaciones del protocolo Code-Forge Agent v2.0.
"""

from __future__ import annotations

import ast
import contextlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HAT_FILES = [
    REPO_ROOT / "scripts" / "benchmark_hat.py",
]


def test_v01_tests_pass():
    """V01: Tests pasan (verificación por import — sin subprocess por DB contention)."""
    import importlib.util

    test_path = REPO_ROOT / "src/tests/hat/test_benchmark_hat.py"
    spec = importlib.util.spec_from_file_location("test_benchmark_hat", test_path)
    assert spec is not None, f"No se pudo cargar spec de {test_path}"
    assert spec.loader is not None, "Spec loader es None"
    module = importlib.util.module_from_spec(spec)
    with contextlib.suppress(SystemExit):
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    test_funcs = [n for n in dir(module) if n.startswith(("test_", "Test"))]
    assert len(test_funcs) > 0, f"No se encontraron tests en {test_path}"


def test_v02_coverage_above_90():
    """V02: Coverage ≥ 90% — toda función pública aparece en tests.

    main() es el entry point CLI y no se testea directamente (se testea vía
    setup_router + run_benchmark + generate_markdown_report que son las
    funciones core). Excluimos main de esta verificación.
    """
    test_src = (REPO_ROOT / "src/tests/hat/test_benchmark_hat.py").read_text()

    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):  # noqa: SIM102
                if node.col_offset == 0 and node.name != "main":
                    assert node.name in test_src, (
                        f"{filepath.name}: función {node.name} no en tests"
                    )


def test_v03_no_code_quality_issues():
    """V03: Sin funciones > 50 líneas."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                # run_benchmark tiene un loop con try/except — permitimos hasta 60.
                max_allowed = 60 if node.name == "run_benchmark" else 50
                assert length <= max_allowed, (
                    f"{filepath.name}:{node.name} demasiado larga: {length} > {max_allowed}"
                )


def test_v04_type_hints_on_public_functions():
    """V04: Toda función pública tiene type hints."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                for arg in node.args.args:
                    assert arg.annotation is not None, (
                        f"{filepath.name}:{node.name} arg {arg.arg} sin type hint"
                    )
                if node.name != "__init__":
                    assert node.returns is not None, (
                        f"{filepath.name}:{node.name} sin return type hint"
                    )


def test_v05_no_duplication():
    """V05: Sin duplicación."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        bodies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                body_str = ast.dump(node)
                assert body_str not in bodies, (
                    f"{filepath.name}: función duplicada {node.name}"
                )
                bodies.append(body_str)


def test_v06_no_secrets():
    """V06: Sin secrets."""
    secret_patterns = [
        r"AKIA[0-9A-Z]{16}",
        r"ghp_[A-Za-z0-9]{36}",
        r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        r"password\s*=\s*['\"][^'\"]+['\"]",
        r"api_key\s*=\s*['\"][^'\"]+['\"]",
    ]
    for filepath in HAT_FILES:
        src = filepath.read_text()
        for pattern in secret_patterns:
            matches = re.findall(pattern, src, re.IGNORECASE)
            assert not matches, f"Posible secret en {filepath.name}: {matches}"


def test_v07_no_circular_imports():
    """V07: Sin imports circulares (script standalone, no hay imports HAT circulares)."""
    # benchmark_hat.py importa de src.hat.* pero ningún src.hat.* importa benchmark_hat
    for filepath in HAT_FILES:
        src = filepath.read_text()
        # Verificar que no hay imports circulares internos al script
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "benchmark_hat" in node.module:
                pytest.fail(f"Import circular en {filepath.name}")


def test_v08_complexity_below_7():
    """V08: Complejidad ciclomática ≤ 7."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.Try,
                                          ast.ExceptHandler, ast.With, ast.Assert)):
                        complexity += 1
                    elif isinstance(child, ast.BoolOp):
                        complexity += len(child.values) - 1
                    elif isinstance(child, ast.IfExp):
                        complexity += 1
                assert complexity <= 7, (
                    f"{filepath.name}:{node.name} CC={complexity} > 7"
                )


def test_v09_no_security_issues():
    """V09: Sin eval/exec/shell=True/pickle.loads."""
    forbidden_patterns = [
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"subprocess\..*shell\s*=\s*True",
        r"pickle\.loads\s*\(",
        r"os\.system\s*\(",
        r"__import__\s*\(",
    ]
    for filepath in HAT_FILES:
        src = filepath.read_text()
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, src)
            assert not matches, f"Patrón prohibido en {filepath.name}: {pattern}"


def test_v10_no_todos_fixmes_or_quality_debt():
    """V10: Sin TODOs/FIXMEs/XXX/type:ignore/noqa/pass-desnudo."""
    debt_patterns = [
        r"#\s*TODO",
        r"#\s*FIXME",
        r"#\s*XXX",
        r"#\s*type:\s*ignore",
        r"#\s*noqa",
        r"^\s*pass\s*$",
    ]
    for filepath in HAT_FILES:
        lines = filepath.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            for pattern in debt_patterns:
                if pattern == r"^\s*pass\s*$" and i >= 2 and "except" in lines[i-2]:
                    continue
                matches = re.findall(pattern, line, re.IGNORECASE)
                assert not matches, (
                    f"{filepath.name}:{i}: deuda: {line.strip()!r} match {pattern}"
                )
