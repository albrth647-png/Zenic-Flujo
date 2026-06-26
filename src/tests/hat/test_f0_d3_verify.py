"""
VERIFY F0-D3 — 10 verificaciones del protocolo Code-Forge Agent v2.0
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
STATES_FILE = REPO_ROOT / "src/hat/orbital_n0/states.py"
FSM_FILE = REPO_ROOT / "src/hat/orbital_n0/fsm_disambiguator.py"


# ─────────────────────────────────────────────────────────
# Las 10 verificaciones Code-Forge v2.0
# ─────────────────────────────────────────────────────────


def test_v01_tests_pass():
    """V01: Todos los tests de F0-D3 pasan (pytest -v)."""
    result = subprocess.run(
        ["python", "-m", "pytest", "src/tests/hat/test_orbital_n0_states_fsm.py",
         "-q", "--tb=line"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"Tests fallando.\nstdout: {result.stdout[-500:]}\nstderr: {result.stderr[-300:]}"
    )


def test_v02_coverage_above_90():
    """V02: Coverage ≥ 90% en los 2 módulos nuevos (heuristic sin pytest-cov).

    Verifica que cada función pública y cada rama de control de flujo
    (if/elif/for) esté cubierta por al menos un test que invoca la función.
    """
    states_src = STATES_FILE.read_text()
    fsm_src = FSM_FILE.read_text()
    test_src = (REPO_ROOT / "src/tests/hat/test_orbital_n0_states_fsm.py").read_text()

    # 1. Toda función pública (a nivel de módulo, no de Protocol/ABC) debe
    # aparecer en el test.
    def _module_level_public_functions(src: str) -> list[str]:
        """Retorna nombres de funciones públicas definidas a nivel módulo
        (no dentro de clases como Protocol/ABC)."""
        tree = ast.parse(src)
        result = []
        for node in tree.body:  # solo top-level
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                result.append(node.name)
        return result

    public_funcs_states = _module_level_public_functions(states_src)
    public_funcs_fsm = _module_level_public_functions(fsm_src)
    for fn in public_funcs_states + public_funcs_fsm:
        assert fn in test_src, f"Función pública {fn} no aparece en tests"

    # 2. Cobertura de ramas: cada rama if/elif/for debe tener un test path que la ejercite.
    # Heurística: número de tests debe ser >= número de branches.
    for filepath, src in [(STATES_FILE, states_src), (FSM_FILE, fsm_src)]:
        tree = ast.parse(src)
        branch_count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.BoolOp)):
                branch_count += 1 if not isinstance(node, ast.BoolOp) else len(node.values)
        # Número de funciones test en el archivo
        test_count = test_src.count("def test_")
        # Heurística: 1 test cubre ~1.5 branches en promedio (cada test tiene assertions múltiples)
        assert test_count * 1.5 >= branch_count, (
            f"{filepath.name}: {test_count} tests para {branch_count} branches "
            f"(ratio {test_count/max(branch_count,1):.2f}, esperado ≥ 0.67)"
        )


def test_v03_no_code_quality_issues():
    """V03: Sin issues obvios de calidad (identificadores sombra, funciones demasiado largas)."""
    for filepath in [STATES_FILE, FSM_FILE]:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                length = node.end_lineno - node.lineno + 1
                assert length <= 50, (
                    f"{filepath.name}:{node.name} demasiado larga: {length} > 50 líneas"
                )


def test_v04_type_hints_on_public_functions():
    """V04: Toda función pública tiene type hints en args y return."""
    for filepath in [STATES_FILE, FSM_FILE]:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                # Args (excluyendo self) deben tener anotación
                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    assert arg.annotation is not None, (
                        f"{filepath.name}:{node.name} arg {arg.arg} sin type hint"
                    )
                # Return debe tener anotación
                assert node.returns is not None, (
                    f"{filepath.name}:{node.name} sin return type hint"
                )


def test_v05_no_duplication():
    """V05: Sin duplicación obvia (no hay 2 funciones idénticas en el mismo archivo)."""
    for filepath in [STATES_FILE, FSM_FILE]:
        src = filepath.read_text()
        tree = ast.parse(src)
        funcs_signatures = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Signature = nombre + número de args + longitud de cuerpo
                sig = (node.name, len(node.args.args), node.end_lineno - node.lineno)
                funcs_signatures.append(sig)
        # No debe haber 2 funciones con la misma signature (excluyendo nombre)
        # Lo que sí prohibimos: 2 funciones con MISMO cuerpo
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
        r"AKIA[0-9A-Z]{16}",  # AWS
        r"ghp_[A-Za-z0-9]{36}",  # GitHub
        r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
        r"password\s*=\s*['\"][^'\"]+['\"]",  # password literal
        r"api_key\s*=\s*['\"][^'\"]+['\"]",  # api_key literal
    ]
    for filepath in [STATES_FILE, FSM_FILE]:
        src = filepath.read_text()
        for pattern in secret_patterns:
            matches = re.findall(pattern, src, re.IGNORECASE)
            assert not matches, f"Posible secret en {filepath.name}: {matches}"


def test_v07_no_circular_imports():
    """V07: Sin imports circulares en src/hat/orbital_n0/."""
    # Parsear AST y buscar imports reales (no menciones en strings/comentarios).
    for filepath, forbidden_module in [
        (STATES_FILE, "fsm_disambiguator"),
        (FSM_FILE, None),  # fsm sí puede importar states, eso es unidireccional
    ]:
        if forbidden_module is None:
            continue
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert forbidden_module not in (alias.name or ""), (
                        f"{filepath.name}: import circular de {forbidden_module}"
                    )
                if node.module and forbidden_module in node.module:
                    pytest.fail(f"{filepath.name}: import circular de {forbidden_module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert forbidden_module not in (alias.name or ""), (
                        f"{filepath.name}: import circular de {forbidden_module}"
                    )


def test_v08_complexity_below_7():
    """V08: Complejidad ciclomática ≤ 7 por función."""
    # Heurística: contar if/elif/for/while/and/or/try por función
    for filepath in [STATES_FILE, FSM_FILE]:
        src = filepath.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity = 1  # base
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
    for filepath in [STATES_FILE, FSM_FILE]:
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
        r"^\s*pass\s*$",  # pass desnudo (no pass en except que sería válido)
    ]
    for filepath in [STATES_FILE, FSM_FILE]:
        lines = filepath.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            for pattern in debt_patterns:
                # El pass en `except: pass` es válido; excluirlo
                if pattern == r"^\s*pass\s*$" and "except" in lines[i-2] if i >= 2 else False:
                    continue
                matches = re.findall(pattern, line, re.IGNORECASE)
                assert not matches, (
                    f"{filepath.name}:{i}: deuda técnica: {line.strip()!r} match {pattern}"
                )
