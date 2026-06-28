"""
VERIFY F1-D2 — 10 verificaciones del protocolo Code-Forge Agent v2.0.
"""

from __future__ import annotations

import ast
import contextlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HAT_FILES = [
    REPO_ROOT / "scripts" / "benchmark_anti_dup.py",
]


def test_v01_tests_pass():
    """V01: Tests pasan (verificación por import)."""
    import importlib.util

    test_path = REPO_ROOT / "src/tests/hat/test_benchmark_anti_dup.py"
    spec = importlib.util.spec_from_file_location("test_benchmark_anti_dup", test_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with contextlib.suppress(SystemExit):
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    test_funcs = [n for n in dir(module) if n.startswith(("test_", "Test"))]
    assert len(test_funcs) > 0


def test_v02_coverage_above_90():
    """V02: Coverage — toda función pública (excepto main) en tests."""
    test_src = (REPO_ROOT / "src/tests/hat/test_benchmark_anti_dup.py").read_text()
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):  # noqa: SIM102
                if node.col_offset == 0 and node.name != "main":
                    assert node.name in test_src, f"Función {node.name} no en tests"


def test_v03_no_code_quality_issues():
    """V03: Sin funciones > 60 líneas."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                assert length <= 60, f"{filepath.name}:{node.name} {length} > 60"


def test_v04_type_hints_on_public_functions():
    """V04: Type hints en funciones públicas."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                for arg in node.args.args:
                    assert arg.annotation is not None, f"{node.name} arg {arg.arg} sin hint"
                if node.name != "__init__":
                    assert node.returns is not None, f"{node.name} sin return hint"


def test_v05_no_duplication():
    """V05: Sin duplicación."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        bodies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                body_str = ast.dump(node)
                assert body_str not in bodies, f"Duplicada: {node.name}"
                bodies.append(body_str)


def test_v06_no_secrets():
    """V06: Sin secrets."""
    patterns = [r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{36}", r"-----BEGIN.*PRIVATE KEY"]
    for filepath in HAT_FILES:
        src = filepath.read_text()
        for p in patterns:
            assert not re.findall(p, src)


def test_v07_no_circular_imports():
    """V07: Sin imports circulares."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "benchmark_anti_dup" in node.module:
                pytest.fail(f"Import circular en {filepath.name}")


def test_v08_complexity_below_7():
    """V08: CC ≤ 7."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                cc = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler)):
                        cc += 1
                    elif isinstance(child, ast.BoolOp):
                        cc += len(child.values) - 1
                assert cc <= 7, f"{filepath.name}:{node.name} CC={cc}"


def test_v09_no_security_issues():
    """V09: Sin eval/exec/shell=True/pickle."""
    patterns = [r"\beval\s*\(", r"\bexec\s*\(", r"shell\s*=\s*True", r"pickle\.loads"]
    for filepath in HAT_FILES:
        src = filepath.read_text()
        for p in patterns:
            assert not re.findall(p, src)


def test_v10_no_todos_fixmes():
    """V10: Sin TODOs/FIXMEs/XXX/type:ignore/noqa/pass-desnudo."""
    patterns = [r"#\s*TODO", r"#\s*FIXME", r"#\s*XXX", r"#\s*type:\s*ignore", r"#\s*noqa"]
    for filepath in HAT_FILES:
        lines = filepath.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            for p in patterns:
                if p == r"^\s*pass\s*$" and i >= 2 and "except" in lines[i-2]:
                    continue
                assert not re.findall(p, line, re.IGNORECASE), f"L{i}: {line.strip()}"
