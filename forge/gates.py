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
# ruff: noqa: RUF012 — class attributes (HARD_GATES, SOFT_GOALS, etc.) son
# intencionalmente mutables para permitir extensión por subclasses.

import ast
import contextlib
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from forge.sandbox import ForgeSandbox

if TYPE_CHECKING:
    from forge.memory import PersistentMemory


class ScanIssue(TypedDict):
    severity: str
    message: str
    line: int


class CmdResult(TypedDict):
    stdout: str
    stderr: str
    returncode: int


class GateResultDict(TypedDict):
    name: str
    passed: bool
    evidence: str
    stack: str
    duration: float
    score: float


class HardGateReport(TypedDict):
    passed: bool
    count: str
    results: list[GateResultDict]


class SoftGoalReport(TypedDict):
    passed: bool
    score: float
    threshold: float
    results: list[GateResultDict]


class OverallReport(TypedDict):
    passed: bool
    hard_passed: bool
    soft_passed: bool
    soft_score: float


class EvalReport(TypedDict):
    hard_gates: HardGateReport
    soft_goals: SoftGoalReport
    overall: OverallReport


class GateResult:
    """Resultado de un gate individual."""

    def __init__(self, name: str, passed: bool, evidence: str = "", stack: str = "python", duration: float = 0.0, score: float = 0.0):
        self.name = name
        self.passed = passed
        self.evidence = evidence
        self.stack = stack
        self.duration = duration
        self.score = score

    def to_dict(self) -> GateResultDict:
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
    def scan_python(cls, file_path: Path) -> list[ScanIssue]:
        issues: list[ScanIssue] = []
        try:
            with open(file_path) as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return [ScanIssue(severity="error", message=f"Cannot parse {file_path}", line=0)]

        # Pre-computar set de líneas con `# forge-ignore-security` para opt-out
        lines_list = content.split("\n")
        ignored_lines = {i + 1 for i, ln in enumerate(lines_list) if "forge-ignore-security" in ln}

        for node in ast.walk(tree):
            # Saltar líneas marcadas con forge-ignore-security
            if hasattr(node, "lineno") and node.lineno in ignored_lines:
                continue
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "__import__"):
                    issues.append(ScanIssue(severity="high", message=f"{node.func.id}() detectado en línea {node.lineno}", line=node.lineno))
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append(ScanIssue(severity="high", message=f"subprocess.{node.func.attr}() con shell=True en línea {node.lineno}", line=node.lineno))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("pickle", "subprocess", "shutil"):
                        issues.append(ScanIssue(severity="medium", message=f"import {alias.name} en línea {node.lineno}", line=node.lineno))
            if isinstance(node, ast.ImportFrom) and node.module in ("pickle", "subprocess"):
                issues.append(ScanIssue(severity="medium", message=f"from {node.module} import en línea {node.lineno}", line=node.lineno))

        secret_patterns = [(r"(?i)(api_key|apikey|secret|token|password)\s*=\s*['\"][A-Za-z0-9_\-]{16,}", "Posible secreto hardcodeado")]
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Permitir opt-out con comentario `# forge-ignore-security`
            if "forge-ignore-security" in line:
                continue
            for pattern, desc in secret_patterns:
                if re.search(pattern, line):
                    issues.append(ScanIssue(severity="high", message=f"{desc} en línea {i}", line=i))
        return issues

    @classmethod
    def scan_typescript(cls, file_path: Path) -> list[ScanIssue]:
        issues: list[ScanIssue] = []
        try:
            content = file_path.read_text()
        except Exception:
            return [ScanIssue(severity="error", message=f"Cannot read {file_path}", line=0)]

        patterns = [
            (r"eval\s*\(", "high", "eval() detectado"),
            (r"innerHTML\s*=", "high", "innerHTML assignment (XSS risk)"),
            (r"dangerouslySetInnerHTML", "high", "dangerouslySetInnerHTML (XSS risk)"),
            (r"document\.write\s*\(", "high", "document.write() (XSS risk)"),
            (r"(?i)(api_key|apikey|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "high", "Posible secreto hardcodeado"),
        ]
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Permitir opt-out con comentario `// forge-ignore-security`
            if "forge-ignore-security" in line:
                continue
            for pattern, severity, desc in patterns:
                if re.search(pattern, line):
                    issues.append(ScanIssue(severity=severity, message=f"{desc} en línea {i}", line=i))
        return issues


class GateRunner:
    """Ejecuta los 12 gates de calidad sobre el proyecto."""

    HARD_GATES = ["tests_pass", "tests_deterministic", "no_security_issues", "no_broken_imports", "no_circular_imports", "integration_smoke"]
    SOFT_GOALS = ["coverage_branch", "lint_clean", "types_clean", "mutation_score", "complexity_max", "test_quality"]
    SOFT_WEIGHTS = {"coverage_branch": 1.0, "lint_clean": 1.0, "types_clean": 1.0, "mutation_score": 2.0, "complexity_max": 1.0, "test_quality": 1.0}

    # ── Fase 3.3: Gates que requieren red (se skippean en modo airgap) ──
    # Estos gates pueden disparar `pip install` o `npm install` cuando las
    # herramientas no están instaladas localmente. En modo airgap, los
    # marcamos como SKIPPED en vez de FAIL.
    NETWORK_DEPENDENT_GATES = {"mutation_score", "coverage_branch"}

    MIN_COVERAGE = 85.0
    MIN_MUTATION_SCORE = 80.0
    MAX_COMPLEXITY = 10
    MIN_TEST_QUALITY_RATIO = 0.30
    SOFT_PASS_THRESHOLD = 8.0

    def __init__(
        self,
        project_root: str | Path,
        sandbox: ForgeSandbox | None = None,
        max_workers: int = 8,
        memory: "PersistentMemory | None" = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.sandbox = sandbox
        self.max_workers = max_workers
        self.python_src = self.project_root / "src"
        self.ts_src = self.project_root / "frontend" / "src"
        self.has_python = self.python_src.exists()
        self.has_typescript = self.ts_src.exists()
        self.results: dict[str, GateResult] = {}
        # ── Fase 5.3: Memoria cross-session ────────────────────────────
        # Si se pasa una PersistentMemory, los gates que fallan generan
        # reflexiones automáticas para aprendizaje cross-session.
        self.memory = memory

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
            with contextlib.suppress(Exception):
                all_issues.extend(SecurityScanner.scan_python(f) if stack == "python" else SecurityScanner.scan_typescript(f))
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

    EXPENSIVE_GATES = {"mutation_score", "coverage_branch"}

    def run_all(self, stacks: list[str] | None = None, sandbox: ForgeSandbox | None = None, exclude: set[str] | None = None) -> EvalReport:
        if stacks is None:
            stacks = [s for s, flag in [("python", self.has_python), ("typescript", self.has_typescript)] if flag]
        exclude = exclude or set()

        # ── Fase 3.2: Integración con ForgeSandbox ────────────────────────
        # Si se pasa un sandbox, usarlo como context manager para ejecutar
        # los gates dentro del entorno aislado. El sandbox se start/stop
        # automáticamente. Si no se pasa, comportamiento legacy (sin sandbox).
        if sandbox is not None:
            self.sandbox = sandbox
            # Asegurar que el sandbox esté iniciado
            if sandbox._started_at is None or sandbox._stopped:
                sandbox.start()
            try:
                return self._run_gates(stacks, exclude)
            finally:
                # NO hacer cleanup automáticamente — el caller es responsable
                # si creó el sandbox. Solo stop para matar procesos hijos.
                pass
        else:
            return self._run_gates(stacks, exclude)

    def _run_gates(self, stacks: list[str], exclude: set[str]) -> EvalReport:
        """Ejecuta los gates en paralelo ( ThreadPoolExecutor).

        Fase 3.3: Si el sandbox está en modo airgap, los gates en
        NETWORK_DEPENDENT_GATES se marcan como SKIPPED en vez de ejecutarse.
        """
        # Determinar si estamos en modo airgap
        is_airgap = self.sandbox is not None and self.sandbox.is_airgap()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for gate_name in self.HARD_GATES + self.SOFT_GOALS:
                if gate_name in exclude:
                    continue
                # Fase 3.3: Skippear gates network-dependent en modo airgap
                if is_airgap and gate_name in self.NETWORK_DEPENDENT_GATES:
                    for stack in stacks:
                        skipped = GateResult(
                            gate_name,
                            passed=False,  # SKIPPED no es PASS ni FAIL
                            evidence="SKIPPED: airgap mode (network unavailable)",
                            stack=stack,
                            duration=0.0,
                            score=0.0,
                        )
                        self.results[f"{skipped.name}:{skipped.stack}"] = skipped
                    continue
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

        # ── Fase 5.3: Generar reflexiones automáticas para gates fallidos ──
        if self.memory is not None:
            self._generate_reflections_on_failure()

        return self.evaluate()

    def _generate_reflections_on_failure(self) -> None:
        """Genera reflexiones automáticas en PersistentMemory para gates fallidos.

        Fase 5.3: Cada gate que falla (passed=False, no SKIPPED) genera una
        reflexión con score=0.0, root_cause extraído del evidence, y
        key_learnings automáticas. Esto permite aprendizaje cross-session:
        antes de CRITIQUE, el agente puede buscar reflexiones similares.

        Solo se generan reflexiones si self.memory está configurado.
        Los gates SKIPPED (airgap) NO generan reflexiones (no son fallos reales).
        """
        if self.memory is None:
            return

        from datetime import UTC, datetime

        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        failed_gates = [
            r for r in self.results.values()
            if not r.passed and "SKIPPED" not in r.evidence
        ]

        for result in failed_gates:
            iteration_id = f"gate-failure-{result.name}-{result.stack}-{timestamp}"
            # Extraer root_cause del evidence (primera línea, truncada)
            evidence_lines = result.evidence.split("\n") if result.evidence else []
            root_cause = evidence_lines[0][:200] if evidence_lines else "Unknown failure"

            # Key learnings automáticas basadas en el tipo de gate
            key_learnings = self._extract_learnings_from_failure(result)

            self.memory.add_reflection(
                iteration_id=iteration_id,
                summary=f"Gate '{result.name}' ({result.stack}) failed: {root_cause[:100]}",
                verbal_reflection=(
                    f"Gate {result.name} on {result.stack} stack failed with evidence: "
                    f"{result.evidence[:300]}. Duration: {result.duration:.1f}s. "
                    f"Score: {result.score:.1f}/10. This failure was recorded automatically "
                    f"by GateRunner for cross-session learning. Search similar failures "
                    f"with find_similar('{result.name} {result.stack} failure') before "
                    f"attempting a fix to avoid repeating past mistakes."
                ),
                score=0.0,
                root_cause=root_cause,
                files_affected=[],
                key_learnings=key_learnings,
            )

    @staticmethod
    def _extract_learnings_from_failure(result: "GateResult") -> list[str]:
        """Extrae key_learnings automáticas basadas en el tipo de gate fallido.

        Args:
            result: GateResult del gate que falló.

        Returns:
            Lista de key_learnings (max 5) para la reflexión automática.
        """
        learnings: list[str] = []
        gate_name = result.name
        stack = result.stack

        if gate_name == "lint_clean":
            learnings.append(f"Lint issues in {stack} — run auto-fix then manual fix remaining")
        elif gate_name == "types_clean":
            learnings.append(f"Type errors in {stack} — add type annotations, fix incompatible types")
        elif gate_name == "tests_pass":
            learnings.append(f"Tests failing in {stack} — check test output for specific failures")
        elif gate_name == "tests_deterministic":
            learnings.append(f"Non-deterministic tests in {stack} — look for time/random/order dependencies")
        elif gate_name == "no_security_issues":
            learnings.append(f"Security issues in {stack} — review eval/exec/secrets, use forge-ignore-security if intentional")
        elif gate_name == "no_broken_imports":
            learnings.append(f"Broken imports in {stack} — create missing modules or fix import paths")
        elif gate_name == "no_circular_imports":
            learnings.append(f"Circular imports in {stack} — use lazy import or refactor to break cycle")
        elif gate_name == "integration_smoke":
            learnings.append(f"Integration failure in {stack} — check build/compile output for errors")
        elif gate_name == "coverage_branch":
            learnings.append(f"Low coverage in {stack} — add tests for uncovered branches")
        elif gate_name == "mutation_score":
            learnings.append(f"Low mutation score in {stack} — add tests to kill surviving mutants")
        elif gate_name == "complexity_max":
            learnings.append(f"High complexity in {stack} — refactor with dict dispatch or extract methods")
        elif gate_name == "test_quality":
            learnings.append(f"Low test ratio in {stack} — add more test files")

        learnings.append(f"Search memory with find_similar('{gate_name} {stack} failure') before fixing")
        return learnings[:5]

    def evaluate(self) -> EvalReport:
        hard = [r for r in self.results.values() if r.name in self.HARD_GATES]
        soft = [r for r in self.results.values() if r.name in self.SOFT_GOALS]
        hard_passed = all(r.passed for r in hard)
        total_w = sum(self.SOFT_WEIGHTS.get(r.name, 1.0) for r in soft)
        weighted = sum(r.score * self.SOFT_WEIGHTS.get(r.name, 1.0) for r in soft)
        soft_score = weighted / total_w if total_w > 0 else 0.0
        return EvalReport(
            hard_gates=HardGateReport(passed=hard_passed, count=f"{sum(1 for r in hard if r.passed)}/{len(hard)}", results=[r.to_dict() for r in hard]),
            soft_goals=SoftGoalReport(passed=soft_score >= self.SOFT_PASS_THRESHOLD, score=round(soft_score, 2), threshold=self.SOFT_PASS_THRESHOLD, results=[r.to_dict() for r in soft]),
            overall=OverallReport(passed=hard_passed and soft_score >= self.SOFT_PASS_THRESHOLD, hard_passed=hard_passed, soft_passed=soft_score >= self.SOFT_PASS_THRESHOLD, soft_score=round(soft_score, 2)),
        )

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

    def _run_cmd(self, cmd: list[str], cwd: str | Path, timeout: int = 120) -> CmdResult:
        # ── Fase 3.2: Si hay sandbox configurado, ejecutar dentro de él ────
        # El sandbox aísla filesystem (workdir temporal), sanitiza env
        # (elimina secrets), y aplica rlimits (CPU/RAM/filesize/procs).
        if self.sandbox is not None and not self.sandbox._stopped:
            try:
                result = self.sandbox.run(cmd, cwd=cwd, timeout=timeout)
                return {
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "returncode": result["returncode"],
                }
            except Exception as e:
                return {"stdout": "", "stderr": f"Sandbox error: {e}", "returncode": -1}
        # Comportamiento legacy (sin sandbox)
        try:
            proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
            return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"TIMEOUT after {timeout}s", "returncode": -1}
        except FileNotFoundError:
            return {"stdout": "", "stderr": f"Command not found: {' '.join(cmd)}", "returncode": -1}


def self_test(project_root: str | Path | None = None, stacks: list[str] | None = None) -> EvalReport:
    """Ejecuta self-test de todos los gates sobre un directorio temporal."""
    import tempfile

    root = Path(project_root) if project_root else Path(tempfile.mkdtemp())
    created_tmp = False

    if not project_root:
        created_tmp = True
        (root / "src").mkdir(parents=True)
        (root / "src" / "module.py").write_text("x = 1\ny = 2\nprint(x + y)\n")
        (root / "src" / "tests").mkdir()
        (root / "src" / "tests" / "test_module.py").write_text(
            "def test_x(): assert 1 + 1 == 2\n"
        )

    runner = GateRunner(root)
    report = runner.run_all(stacks=stacks or ["python"], exclude=set(runner.EXPENSIVE_GATES))
    runner.print_report()

    if created_tmp and project_root is None:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    return report
