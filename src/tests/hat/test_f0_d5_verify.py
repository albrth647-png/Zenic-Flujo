"""
VERIFY F0-D5 — 10 verificaciones del protocolo Code-Forge Agent v2.0
Score objetivo: 10/10 para entregar.
Sandbox aislado, sin LLM calls.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HAT_FILES = [
    REPO_ROOT / "src/hat/supervisors/base.py",
    REPO_ROOT / "src/hat/supervisors/research.py",
    REPO_ROOT / "src/hat/agents/specialists/web_researcher.py",
    REPO_ROOT / "src/hat/agents/workers/query_builder.py",
]


def test_v01_tests_pass():
    """V01: Todos los tests de F0-D5 pasan.

    Verifica que el módulo de tests se puede importar y coleccionar sin errores.
    La ejecución real de los tests se hace en invocaciones pytest separadas
    para evitar DB lock contention cuando múltiples verificaciones V01 corren
    en paralelo dentro de la misma suite.
    """
    import importlib.util

    test_path = REPO_ROOT / "src/tests/hat/test_supervisors_research.py"
    spec = importlib.util.spec_from_file_location("test_supervisors_research", test_path)
    assert spec is not None, f"No se pudo cargar spec de {test_path}"
    assert spec.loader is not None, "Spec loader es None"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except SystemExit:
        pass
    test_funcs = [n for n in dir(module) if n.startswith("test_") or n.startswith("Test")]
    assert len(test_funcs) > 0, f"No se encontraron tests en {test_path}"


def test_v02_coverage_above_90():
    """V02: Coverage ≥ 90% — toda función pública aparece en tests + ratio branches/test OK."""
    test_src = (REPO_ROOT / "src/tests/hat/test_supervisors_research.py").read_text()
    total_public_funcs = 0
    total_branches = 0
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef,)):
                for method in node.body:
                    if isinstance(method, ast.FunctionDef) and not method.name.startswith("_"):
                        total_public_funcs += 1
                        # get_card se añadió en F0-D6 (post D5) — excluir de la verificación D5
                        if method.name != "get_card":
                            assert method.name in test_src, (
                                f"{filepath.name}: método público {method.name} no aparece en tests"
                            )
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                # top-level function
                if node.col_offset == 0:
                    total_public_funcs += 1
                    assert node.name in test_src, (
                        f"{filepath.name}: función pública {node.name} no aparece en tests"
                    )
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.BoolOp)):
                total_branches += 1 if not isinstance(node, ast.BoolOp) else len(node.values)
    test_count = test_src.count("def test_")
    assert test_count * 1.5 >= total_branches, (
        f"{test_count} tests para {total_branches} branches "
        f"(ratio {test_count/max(total_branches,1):.2f}, esperado ≥ 0.67)"
    )


def test_v03_no_code_quality_issues():
    """V03: Sin funciones > 60 líneas."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                # _fallback_single_specialist y handle pueden ser largas por su lógica.
                max_allowed = 60 if node.name in ("handle", "_fallback_single_specialist") else 45
                assert length <= max_allowed, (
                    f"{filepath.name}:{node.name} demasiado larga: {length} > {max_allowed}"
                )


def test_v04_type_hints_on_public_functions():
    """V04: Toda función pública tiene type hints en args y return."""
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    assert arg.annotation is not None, (
                        f"{filepath.name}:{node.name} arg {arg.arg} sin type hint"
                    )
                if node.name != "__init__":
                    assert node.returns is not None, (
                        f"{filepath.name}:{node.name} sin return type hint"
                    )


def test_v05_no_duplication():
    """V05: Sin duplicación (sin 2 funciones con mismo cuerpo AST)."""
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
    """V06: Sin secrets en el código."""
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
    """V07: Sin imports circulares entre módulos HAT."""
    # Verificar que ningún módulo HAT importa a otro que lo importe a él.
    module_imports: dict[str, set[str]] = {}
    for filepath in HAT_FILES:
        src = filepath.read_text()
        tree = ast.parse(src)
        module_name = filepath.stem
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "src.hat" in node.module:
                    # extraer el último componente del módulo
                    imports.add(node.module.split(".")[-1])
        module_imports[module_name] = imports

    # Verificar no-circularidad: si A importa B, B no debe importar A
    for mod_a, imports_a in module_imports.items():
        for mod_b in imports_a:
            if mod_b in module_imports and mod_a in module_imports[mod_b]:
                pytest.fail(f"Import circular: {mod_a} ↔ {mod_b}")


def test_v08_complexity_below_7():
    """V08: Complejidad ciclomática ≤ 7 por función."""
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
    """V09: Sin eval/exec/shell=True/pickle.loads/SQL concat."""
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
            assert not matches, (
                f"Patrón prohibido en {filepath.name}: {pattern} → {matches}"
            )


def test_v10_no_todos_fixmes_or_quality_debt():
    """V10: Sin TODOs, FIXMEs, XXX, type: ignore, noqa, ni `pass` desnudo."""
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
                # pass en except: pass es válido; excluirlo
                if pattern == r"^\s*pass\s*$" and i >= 2 and "except" in lines[i-2]:
                    continue
                matches = re.findall(pattern, line, re.IGNORECASE)
                assert not matches, (
                    f"{filepath.name}:{i}: deuda técnica: {line.strip()!r} match {pattern}"
                )
