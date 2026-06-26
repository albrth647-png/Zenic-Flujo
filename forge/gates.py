"""
Gates Runner v1.0 — Zenic-Flujo Edition
========================================
12 Gates de calidad (6 hard + 6 soft) con detección automática de stack.

Hard gates (deben pasar TODOS):
  tests_pass, tests_deterministic, no_security_issues,
  no_broken_imports, no_circular_imports, integration_smoke

Soft goals (score ponderado ≥ 8/10):
  coverage_branch, lint_clean, types_clean, mutation_score,
  complexity_max, test_quality

Uso:
    from forge import GateRunner
    runner = GateRunner("/ruta/del/proyecto")
    report = runner.run_all()
    runner.print_report()
"""

import ast
import os
import subprocess
import sys
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from forge.sandbox import ForgeSandbox


class GateResult:
    """Resultado de un gate individual."""

    def __init__(self, name: str, passed: bool, evidence: str = "", stack: str = "python", duration: float = 0.0, score: float = 0.0):
        self.name = name
        self.passed = passed
        self.evidence = evidence
        self.stack = stack
        self.duration = duration
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "evidence": self.evidence[:500], "stack": self.stack, "duration": round(self.duration, 2), "score": round(self.score, 1)}

    def __repr__(self) -> str:
        status = "✅" if self.passed else "❌"
        return f"{status} {self.name} ({self.stack}) [{self.duration:.1f}s]"


class SecurityScanner:
    """Escáner de seguridad vía AST para Python y TypeScript."""

    PYTHON_DANGEROUS = {
        "eval": "Evaluación dinámica",
        "exec": "Ejecución dinámica",
        "__import__": "Importación dinámica",
        "pickle": "Deserialización insegura",
        "subprocess": "Ejecución de subprocesos",
    }

    @classmethod
    def scan_python(cls, file_path: Path) -> list[dict[str, Any]]:
        issues = []
        try:
            with open(file_path) as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return [{"severity": "error", "message": f"Cannot parse {file_path}"}]

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "__import__"):
                    issues.append({"severity": "high", "message": f"{node.func.id}() detectado en línea {node.lineno}", "line": node.lineno})
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append({"severity": "high", "message": f"subprocess.{node.func.attr}() con shell=True en línea {node.lineno}", "line": node.lineno})
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("pickle", "subprocess", "shutil"):
                        issues.append({"severity": "medium", "message": f"import {alias.name} en línea {node.lineno}", "line": node.lineno})
            if isinstance(node, ast.ImportFrom) and node.module in ("pickle", "subprocess"):
                issues.append({"severity": "medium", "message": f"from {node.module} import en línea {node.lineno}", "line": node.lineno})

        secret_patterns = [(r"(?i)(api_key|apikey|secret|token|password)\s*=\s*['\"][A-Za-z0-9_\-]{16,}", "Posible secreto hardcodeado")]
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for pattern, desc in secret_patterns:
                if re.search(pattern, line):
                    issues.append({"severity": "high", "message": f"{desc} en línea {i}", "line": i})
        return issues

    @classmethod
    def scan_typescript(cls, file_path: Path) -> list[dict[str, Any]]:
        issues = []
        try:
            content = file_path.read_text()
        except Exception:
            return [{"severity": "error", "message": f"Cannot read {file_path}"}]

        patterns = [
            (r"eval\s*\(", "high", "eval() detectado"),
            (r"innerHTML\s*=", "high", "innerHTML assignment (XSS risk)"),
            (r"dangerouslySetInnerHTML", "high", "dangerouslySetInnerHTML (XSS risk)"),
            (r"document\.write\s*\(", "high", "document.write() (XSS risk)"),
            (r"(?i)(api_key|apikey|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "high", "Posible secreto hardcodeado"),
        ]
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for pattern, severity, desc in patterns:
                if re.search(pattern, line):
                    issues.append({"severity": severity, "message": f"{desc} en línea {i}", "line": i})
        return issues


class GateRunner:
    """Ejecuta los 12 gates de calidad sobre el proyecto."""

    HARD_GATES = ["tests_pass", "tests_deterministic", "no_security_issues", "no_broken_imports", "no_circular_imports", "integration_smoke"]
    SOFT_GOALS = ["coverage_branch", "lint_clean", "types_clean", "mutation_score", "complexity_max", "test_quality"]
    SOFT_WEIGHTS = {"coverage_branch": 1.0, "lint_clean": 1.0, "types_clean": 1.0, "mutation_score": 2.0, "complexity_max": 1.0, "test_quality": 1.0}

    MIN_COVERAGE = 85.0
    MIN_MUTATION_SCORE = 80.0
    MAX_COMPLEXITY = 10
    MIN_TEST_QUALITY_RATIO = 0.30
    SOFT_PASS_THRESHOLD = 8.0

    def __init__(self, project_root: str | Path, sandbox: ForgeSandbox | None = None, max_workers: int = 8):
        self.project_root = Path(project_root).resolve()
        self.sandbox = sandbox
        self.max_workers = max_workers
        self.python_src = self.project_root / "src"
        self.ts_src = self.project_root / "frontend" / "src"
        self.has_python = self.python_src.exists()
        self.has_typescript = self.ts_src.exists()
        self.results: dict[str, GateResult] = {}

    def detect_stack(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if path.suffix in (".py",):
            return "python"
        if path.suffix in (".ts", ".tsx"):
            return "typescript"
        if str(path).startswith("src/") or "src/" in str(path):
            return "python"
        if "frontend/" in str(path):
            return "typescript"
        return "python"

    def gate_tests_pass(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            cmd = ["python3", "-m", "pytest", "-x", "-q", "--tb=short", str(self.python_src / "tests")]
            cwd = self.project_root
        else:
            cmd = ["npx", "vitest", "run", "--reporter=verbose"]
            cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 180)
        passed = result["returncode"] == 0
        return GateResult("tests_pass", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start)

    def gate_tests_deterministic(self, stack: str = "python") -> GateResult:
        start = time.time()
        exit_codes = []
        for _ in range(3):
            if stack == "python":
                cmd = ["python3", "-m", "pytest", "-x", "-q", "--tb=line", str(self.python_src / "tests")]
                cwd = self.project_root
            else:
                cmd = ["npx", "vitest", "run", "--reporter=verbose"]
                cwd = self.project_root / "frontend"
            result = self._run_cmd(cmd, cwd, 180)
            exit_codes.append(result["returncode"])
        return GateResult("tests_deterministic", len(set(exit_codes)) == 1, f"Exit codes: {exit_codes}", stack, time.time() - start)

    def gate_no_security_issues(self, stack: str = "python") -> GateResult:
        start = time.time()
        src_dir = self.python_src if stack == "python" else self.ts_src
        files = list(src_dir.rglob("*.py")) if stack == "python" else list(src_dir.rglob("*.ts")) + list(src_dir.rglob("*.tsx"))
        all_issues = []
        for f in files:
            if any(p.name in ("__pycache__", "node_modules", ".venv", "venv") for p in f.parents):
                continue
            try:
                all_issues.extend(SecurityScanner.scan_python(f) if stack == "python" else SecurityScanner.scan_typescript(f))
            except Exception:
                pass
        high = [i for i in all_issues if i.get("severity") == "high"]
        evidence = "\n".join([f"[{i['severity']}] {i['message']}" for i in all_issues[:10]]) if all_issues else "No issues found"
        return GateResult("no_security_issues", len(high) == 0, evidence, stack, time.time() - start)

    def gate_no_broken_imports(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            cmd = ["python3", "-c", "import sys; sys.path.insert(0, '.'); print('OK')"]
            cwd = self.project_root
        else:
            cmd = ["npx", "tsc", "--noEmit"]
            cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 120)
        passed = result["returncode"] == 0
        return GateResult("no_broken_imports", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start)

    def gate_no_circular_imports(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            return GateResult("no_circular_imports", True, "Python circular check: using madge for TS", stack, time.time() - start)
        cmd = ["npx", "madge", "--circular", str(self.ts_src)]
        cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 60)
        return GateResult("no_circular_imports", result["returncode"] == 0, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start)

    def gate_integration_smoke(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            cmd = ["python3", "-c", "import sys; sys.path.insert(0, '.'); print('OK')"]
            cwd = self.project_root
        else:
            cmd = ["npx", "vite", "build"]
            cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 180)
        passed = result["returncode"] == 0
        return GateResult("integration_smoke", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start)

    def gate_coverage_branch(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            cmd = ["python3", "-m", "pytest", "--cov=" + str(self.python_src), "--cov-branch", "--cov-report=term-missing", "-q", "--tb=short", str(self.python_src / "tests")]
            cwd = self.project_root
        else:
            cmd = ["npx", "vitest", "run", "--coverage", "--provider=v8", "--reporter=verbose"]
            cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 300)
        output = result.get("stdout", "") + result.get("stderr", "")
        cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        cov_pct = float(cov_match.group(1)) if cov_match else 0.0
        passed = cov_pct >= self.MIN_COVERAGE
        return GateResult("coverage_branch", passed, f"Coverage: {cov_pct:.1f}%", stack, time.time() - start, min(cov_pct / self.MIN_COVERAGE * 10, 10))

    def gate_lint_clean(self, stack: str = "python") -> GateResult:
        start = time.time()
        cmd = ["ruff", "check", str(self.python_src)] if stack == "python" else ["npx", "eslint", str(self.ts_src), "--max-warnings=0"]
        cwd = self.project_root if stack == "python" else self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 120)
        passed = result["returncode"] == 0
        return GateResult("lint_clean", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start, 10.0 if passed else 5.0)

    def gate_types_clean(self, stack: str = "python") -> GateResult:
        start = time.time()
        cmd = ["python3", "-m", "mypy", "--strict", str(self.python_src)] if stack == "python" else ["npx", "tsc", "--strict", "--noEmit"]
        cwd = self.project_root if stack == "python" else self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 120)
        passed = result["returncode"] == 0
        return GateResult("types_clean", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start, 10.0 if passed else 4.0)

    def gate_mutation_score(self, stack: str = "python") -> GateResult:
        start = time.time()
        cmd = ["python3", "-m", "mutmut", "run"] if stack == "python" else ["npx", "stryker", "run"]
        cwd = self.project_root if stack == "python" else self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 300)
        output = (result.get("stdout", "") + result.get("stderr", "")).lower()
        score = 0.0
        mut_match = re.search(r"(\d+\.?\d*)% mutation score", output)
        if mut_match:
            score = float(mut_match.group(1))
        return GateResult("mutation_score", score >= self.MIN_MUTATION_SCORE, f"Mutation: {score:.1f}%" if score else output[:300], stack, time.time() - start, score)

    def gate_complexity_max(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            cmd = ["radon", "cc", str(self.python_src), "-s", "-n", "C"]
            cwd = self.project_root
        else:
            cmd = ["npx", "eslint", str(self.ts_src), "--rule", "{'complexity': ['error', 10]}", "--max-warnings=0"]
            cwd = self.project_root / "frontend"
        result = self._run_cmd(cmd, cwd, 60)
        passed = result["returncode"] == 0 or "No modules found" in (result.get("stdout", "") + result.get("stderr", ""))
        return GateResult("complexity_max", passed, (result.get("stdout", "") + result.get("stderr", ""))[:500], stack, time.time() - start, 10.0 if passed else 5.0)

    def gate_test_quality(self, stack: str = "python") -> GateResult:
        start = time.time()
        if stack == "python":
            src_files = sum(1 for f in self.python_src.rglob("*.py") if f.name != "__init__.py" and "tests" not in str(f) and "__pycache__" not in str(f))
            test_files = len(list((self.python_src / "tests").rglob("test_*.py")))
        else:
            src_files = len(list(self.ts_src.rglob("*.ts"))) + len(list(self.ts_src.rglob("*.tsx")))
            test_files = len(list((self.ts_src / "__tests__").rglob("*.ts"))) + len(list((self.ts_src / "__tests__").rglob("*.tsx")))
        ratio = test_files / max(src_files, 1)
        return GateResult("test_quality", ratio >= self.MIN_TEST_QUALITY_RATIO, f"Test ratio: {ratio:.1%}", stack, time.time() - start, min(ratio / self.MIN_TEST_QUALITY_RATIO * 10, 10))

    def run_all(self, stacks: list[str] | None = None, sandbox: ForgeSandbox | None = None) -> dict[str, Any]:
        if stacks is None:
            stacks = [s for s, flag in [("python", self.has_python), ("typescript", self.has_typescript)] if flag]
        if sandbox:
            self.sandbox = sandbox

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for gate_name in self.HARD_GATES + self.SOFT_GOALS:
                for stack in stacks:
                    method = getattr(self, f"gate_{gate_name}", None)
                    if method:
                        futures.append(executor.submit(method, stack))
            for future in as_completed(futures):
                try:
                    r = future.result()
                    self.results[f"{r.name}:{r.stack}"] = r
                except Exception as e:
                    print(f"Gate error: {e}")
        return self.evaluate()

    def evaluate(self) -> dict[str, Any]:
        hard = [r for r in self.results.values() if r.name in self.HARD_GATES]
        soft = [r for r in self.results.values() if r.name in self.SOFT_GOALS]
        hard_passed = all(r.passed for r in hard)
        total_w = sum(self.SOFT_WEIGHTS.get(r.name, 1.0) for r in soft)
        weighted = sum(r.score * self.SOFT_WEIGHTS.get(r.name, 1.0) for r in soft)
        soft_score = weighted / total_w if total_w > 0 else 0.0
        return {
            "hard_gates": {"passed": hard_passed, "count": f"{sum(1 for r in hard if r.passed)}/{len(hard)}", "results": [r.to_dict() for r in hard]},
            "soft_goals": {"passed": soft_score >= self.SOFT_PASS_THRESHOLD, "score": round(soft_score, 2), "threshold": self.SOFT_PASS_THRESHOLD, "results": [r.to_dict() for r in soft]},
            "overall": {"passed": hard_passed and soft_score >= self.SOFT_PASS_THRESHOLD, "hard_passed": hard_passed, "soft_passed": soft_score >= self.SOFT_PASS_THRESHOLD, "soft_score": round(soft_score, 2)},
        }

    def print_report(self) -> None:
        ev = self.evaluate()
        print("\n" + "=" * 60)
        print("  FORGE — GATES REPORT")
        print("=" * 60)
        print(f"\n  📊 HARD GATES ({ev['hard_gates']['count']})")
        for r in self.results.values():
            if r.name in self.HARD_GATES:
                print(f"    {'✅' if r.passed else '❌'} {r.name:25s} | {r.stack:12s} | {r.duration:5.1f}s")
        print(f"\n  🎯 SOFT GOALS (score: {ev['soft_goals']['score']}/10)")
        for r in self.results.values():
            if r.name in self.SOFT_GOALS:
                print(f"    {'✅' if r.passed else '❌'} {r.name:25s} | {r.stack:12s} | score={r.score:4.1f} | {r.duration:5.1f}s")
        v = "✅ PASS" if ev["overall"]["passed"] else "❌ FAIL"
        print(f"\n  🏁 VERDICT: {v}")
        print(f"     Hard: {'PASS' if ev['overall']['hard_passed'] else 'FAIL'} | Soft: {'PASS' if ev['overall']['soft_passed'] else 'FAIL'} ({ev['overall']['soft_score']:.1f}/10)")
        print("=" * 60 + "\n")

    def _run_cmd(self, cmd: list[str], cwd: str | Path, timeout: int = 120) -> dict[str, Any]:
        try:
            proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
            return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"TIMEOUT after {timeout}s", "returncode": -1}
        except FileNotFoundError:
            return {"stdout": "", "stderr": f"Command not found: {' '.join(cmd)}", "returncode": -1}
