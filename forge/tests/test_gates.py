"""
Tests for GateRunner — Code-Forge v1.0

Cobertura: GateResult, SecurityScanner (Python + TypeScript),
GateRunner init/detect_stack/_run_cmd, 12 individual gates,
run_all/evaluate aggregation, print_report.
"""

import os
from unittest.mock import patch

import pytest

from forge.gates import GateResult, GateRunner, SecurityScanner

# ──────────────────────────────────────────────
# GateResult
# ──────────────────────────────────────────────

class TestGateResult:
    def test_creates_with_defaults(self):
        r = GateResult("test", True)
        assert r.name == "test"
        assert r.passed is True
        assert r.evidence == ""
        assert r.stack == "python"
        assert r.duration == 0.0
        assert r.score == 0.0

    def test_creates_with_all_fields(self):
        r = GateResult("cov", False, "low", "typescript", 1.5, 7.0)
        assert r.name == "cov"
        assert r.passed is False
        assert r.evidence == "low"
        assert r.stack == "typescript"
        assert r.duration == 1.5
        assert r.score == 7.0

    def test_to_dict_rounds_values(self):
        r = GateResult("test", True, evidence="x" * 600, duration=3.14159, score=9.8765)
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["passed"] is True
        assert len(d["evidence"]) == 500
        assert d["duration"] == 3.14
        assert d["score"] == 9.9

    def test_repr_passed(self):
        r = GateResult("lint", True, duration=2.0)
        text = repr(r)
        assert r.name in text
        assert r.stack in text
        assert "2.0" in text

    def test_repr_failed(self):
        r = GateResult("lint", False, duration=0.5)
        text = repr(r)
        assert r.name in text


# ──────────────────────────────────────────────
# SecurityScanner — Python
# ──────────────────────────────────────────────

class TestSecurityScannerPython:
    def test_clean_file_returns_empty(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("x = 1\ny = x + 2\nprint(y)\n")
        assert SecurityScanner.scan_python(f) == []

    def test_detects_eval(self, tmp_path):
        f = tmp_path / "eval_test.py"
        f.write_text("result = eval(user_input)\n")
        issues = SecurityScanner.scan_python(f)
        assert any("eval" in i["message"] and i["severity"] == "high" for i in issues)

    def test_detects_exec(self, tmp_path):
        f = tmp_path / "exec_test.py"
        f.write_text('exec("dangerous")\n')
        issues = SecurityScanner.scan_python(f)
        assert any("exec" in i["message"] for i in issues)

    def test_detects_import_pickle(self, tmp_path):
        f = tmp_path / "pickle_test.py"
        f.write_text("import pickle\n")
        issues = SecurityScanner.scan_python(f)
        assert any("pickle" in i["message"] for i in issues)

    def test_detects_from_pickle_import(self, tmp_path):
        f = tmp_path / "from_pickle.py"
        f.write_text("from pickle import loads\n")
        issues = SecurityScanner.scan_python(f)
        assert any("pickle" in i["message"] for i in issues)

    def test_detects_subprocess_shell_true(self, tmp_path):
        f = tmp_path / "subprocess_test.py"
        f.write_text("import subprocess\nsubprocess.run('ls', shell=True)\n")
        issues = SecurityScanner.scan_python(f)
        assert any("shell=True" in i["message"] for i in issues)

    def test_subprocess_without_shell_is_clean(self, tmp_path):
        f = tmp_path / "safe_subprocess.py"
        f.write_text("import subprocess\nsubprocess.run(['ls'], shell=False)\n")
        issues = SecurityScanner.scan_python(f)
        assert not any("shell=True" in i["message"] for i in issues)

    def test_detects_hardcoded_secret(self, tmp_path):
        f = tmp_path / "secret.py"
        f.write_text('API_KEY = "sk-12345678901234567890"\n')
        issues = SecurityScanner.scan_python(f)
        assert any("Posible secreto" in i["message"] for i in issues)

    def test_short_string_not_secret(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text('name = "abc"\n')
        assert SecurityScanner.scan_python(f) == []

    def test_syntax_error_returns_error_issue(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("this is not valid python {{{{\n")
        issues = SecurityScanner.scan_python(f)
        assert any(i["severity"] == "error" and "Cannot parse" in i["message"] for i in issues)

    def test_detects_shutil_import(self, tmp_path):
        f = tmp_path / "shutil_test.py"
        f.write_text("import shutil\n")
        issues = SecurityScanner.scan_python(f)
        assert any("shutil" in i["message"] for i in issues)

    def test_detects_import_subprocess(self, tmp_path):
        f = tmp_path / "import_subprocess.py"
        f.write_text("import subprocess\n")
        issues = SecurityScanner.scan_python(f)
        assert any("import subprocess" in i["message"] for i in issues)

    def test_secret_pattern_case_insensitive(self, tmp_path):
        f = tmp_path / "case_secret.py"
        f.write_text('Api_Key = "abcdefghijklmnopqrstuvwxyz"\n')
        issues = SecurityScanner.scan_python(f)
        assert any(i["severity"] == "high" for i in issues)

    def test_multiple_issues_in_one_file(self, tmp_path):
        f = tmp_path / "multi.py"
        f.write_text("import pickle\neval(x)\n")
        issues = SecurityScanner.scan_python(f)
        assert len(issues) >= 2


# ──────────────────────────────────────────────
# SecurityScanner — TypeScript
# ──────────────────────────────────────────────

class TestSecurityScannerTypeScript:
    def test_clean_file_returns_empty(self, tmp_path):
        f = tmp_path / "clean.ts"
        f.write_text("const x = 1;\nconsole.log(x);\n")
        assert SecurityScanner.scan_typescript(f) == []

    def test_detects_eval(self, tmp_path):
        f = tmp_path / "eval.ts"
        f.write_text("const result = eval(input);\n")
        issues = SecurityScanner.scan_typescript(f)
        assert any("eval" in i["message"] for i in issues)

    def test_detects_inner_html(self, tmp_path):
        f = tmp_path / "xss.ts"
        f.write_text("el.innerHTML = '<b>bold</b>';\n")
        issues = SecurityScanner.scan_typescript(f)
        assert any("innerHTML" in i["message"] for i in issues)

    def test_detects_dangerously_set_inner_html(self, tmp_path):
        f = tmp_path / "dangerous.tsx"
        f.write_text('<div dangerouslySetInnerHTML={{ __html: content }} />\n')
        issues = SecurityScanner.scan_typescript(f)
        assert any("dangerouslySetInnerHTML" in i["message"] for i in issues)

    def test_detects_document_write(self, tmp_path):
        f = tmp_path / "doc_write.ts"
        f.write_text("document.write('<script>alert(1)</script>');\n")
        issues = SecurityScanner.scan_typescript(f)
        assert any("document.write" in i["message"] for i in issues)

    def test_detects_hardcoded_token(self, tmp_path):
        f = tmp_path / "token.ts"
        f.write_text('const token = "ghp_123456789012345678901234567890123456";\n')
        issues = SecurityScanner.scan_typescript(f)
        assert any("Posible secreto" in i["message"] for i in issues)

    def test_unreadable_file_returns_error(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("Cannot test unreadable files as root")
        f = tmp_path / "no_access.ts"
        f.write_text("ok")
        try:
            f.chmod(0o000)
            issues = SecurityScanner.scan_typescript(f)
            assert any("Cannot read" in i["message"] for i in issues)
        finally:
            f.chmod(0o644)


# ──────────────────────────────────────────────
# GateRunner — init / detect_stack / _run_cmd
# ──────────────────────────────────────────────

class TestGateRunnerInit:
    def test_creates_with_valid_project_root(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(str(tmp_path))
        assert gr.project_root == tmp_path.resolve()
        assert gr.has_python is True
        assert gr.has_typescript is False
        assert gr.results == {}

    def test_detects_both_stacks(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        assert gr.has_python is True
        assert gr.has_typescript is True

    def test_detect_stack_by_extension(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        assert gr.detect_stack("file.py") == "python"
        assert gr.detect_stack("file.ts") == "typescript"
        assert gr.detect_stack("file.tsx") == "typescript"

    def test_detect_stack_by_path(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        assert gr.detect_stack("src/tools/util.py") == "python"
        assert gr.detect_stack("frontend/components/Button.tsx") == "typescript"

    def test_detect_stack_defaults_to_python(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        assert gr.detect_stack("unknown.txt") == "python"


class TestGateRunnerRunCmd:
    def test_run_cmd_success(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        result = gr._run_cmd(["echo", "hello"], tmp_path)
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_run_cmd_failure(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        result = gr._run_cmd(["sh", "-c", "exit 1"], tmp_path)
        assert result["returncode"] == 1

    def test_run_cmd_not_found(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        result = gr._run_cmd(["nonexistent_cmd_xyz"], tmp_path)
        assert result["returncode"] == -1

    def test_run_cmd_timeout(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        result = gr._run_cmd(["sleep", "10"], tmp_path, timeout=1)
        assert result["returncode"] == -1
        assert "TIMEOUT" in result["stderr"]


# ──────────────────────────────────────────────
# GateRunner — 12 gate methods (mocked _run_cmd)
# ──────────────────────────────────────────────

@pytest.fixture
def gr_with_src(tmp_path):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    return GateRunner(tmp_path)


class MockCmd:
    """Helper to make GateRunner gates return predictable results."""

    @staticmethod
    def ok(stdout="", stderr=""):
        return {"stdout": stdout, "stderr": stderr, "returncode": 0}

    @staticmethod
    def fail(stdout="", stderr=""):
        return {"stdout": stdout, "stderr": stderr, "returncode": 1}


class TestHardGates:
    def test_gate_tests_pass_python_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_tests_pass("python")
            assert r.passed is True
            assert r.name == "tests_pass"
            assert r.stack == "python"

    def test_gate_tests_pass_python_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("FAIL")):
            r = gr_with_src.gate_tests_pass("python")
            assert r.passed is False

    def test_gate_tests_pass_ts_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_tests_pass("typescript")
            assert r.passed is True

    def test_gate_tests_deterministic_all_same(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_tests_deterministic("python")
            assert r.passed is True

    def test_gate_tests_deterministic_different(self, gr_with_src):
        values = [MockCmd.ok(), MockCmd.ok(), MockCmd.fail()]
        with patch.object(gr_with_src, "_run_cmd", side_effect=values):
            r = gr_with_src.gate_tests_deterministic("python")
            assert r.passed is False

    def test_gate_no_security_issues_clean(self, gr_with_src):
        (gr_with_src.python_src / "clean.py").write_text("x = 1\n")
        r = gr_with_src.gate_no_security_issues("python")
        assert r.passed is True

    def test_gate_no_security_issues_with_issues(self, gr_with_src):
        (gr_with_src.python_src / "danger.py").write_text("import pickle\neval(x)\n")
        r = gr_with_src.gate_no_security_issues("python")
        assert r.passed is False

    def test_gate_no_broken_imports_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_no_broken_imports("python")
            assert r.passed is True

    def test_gate_no_broken_imports_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("ERR")):
            r = gr_with_src.gate_no_broken_imports("python")
            assert r.passed is False

    def test_gate_no_circular_imports_python(self, gr_with_src):
        r = gr_with_src.gate_no_circular_imports("python")
        assert r.passed is True

    def test_gate_no_circular_imports_ts_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_no_circular_imports("typescript")
            assert r.passed is True

    def test_gate_no_circular_imports_ts_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("CIRCULAR")):
            r = gr_with_src.gate_no_circular_imports("typescript")
            assert r.passed is False

    def test_gate_integration_smoke_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_integration_smoke("python")
            assert r.passed is True

    def test_gate_integration_smoke_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("FAIL")):
            r = gr_with_src.gate_integration_smoke("python")
            assert r.passed is False


class TestSoftGoals:
    def test_gate_coverage_above_threshold(self, gr_with_src):
        stdout = "TOTAL    100  50  90%"
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok(stdout)):
            r = gr_with_src.gate_coverage_branch("python")
            assert r.passed is True
            assert r.score > 0

    def test_gate_coverage_below_threshold(self, gr_with_src):
        stdout = "TOTAL    100  50  30%"
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok(stdout)):
            r = gr_with_src.gate_coverage_branch("python")
            assert r.passed is False

    def test_gate_coverage_no_match(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("No coverage data")):
            r = gr_with_src.gate_coverage_branch("python")
            assert r.passed is False
            assert r.score == 0.0

    def test_gate_lint_clean_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_lint_clean("python")
            assert r.passed is True
            assert r.score == 10.0

    def test_gate_lint_clean_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("lint err")):
            r = gr_with_src.gate_lint_clean("python")
            assert r.passed is False
            assert r.score == 5.0

    def test_gate_types_clean_ok(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("OK")):
            r = gr_with_src.gate_types_clean("python")
            assert r.passed is True
            assert r.score == 10.0

    def test_gate_types_clean_fail(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.fail("type err")):
            r = gr_with_src.gate_types_clean("python")
            assert r.passed is False
            assert r.score == 4.0

    def test_gate_mutation_score_above_threshold(self, gr_with_src):
        stdout = "85.0% mutation score"
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok(stdout)):
            r = gr_with_src.gate_mutation_score("python")
            assert r.passed is True
            assert r.score >= 80.0

    def test_gate_mutation_score_below_threshold(self, gr_with_src):
        stdout = "50.0% mutation score"
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok(stdout)):
            r = gr_with_src.gate_mutation_score("python")
            assert r.passed is False
            assert r.score == 50.0

    def test_gate_mutation_score_no_match(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("No data")):
            r = gr_with_src.gate_mutation_score("python")
            assert r.passed is False
            assert r.score == 0.0

    def test_gate_complexity_clean(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok("")):
            r = gr_with_src.gate_complexity_max("python")
            assert r.passed is True
            assert r.score == 10.0

    def test_gate_complexity_no_modules(self, gr_with_src):
        with patch.object(gr_with_src, "_run_cmd",
                          return_value=MockCmd.fail("No modules found")):
            r = gr_with_src.gate_complexity_max("python")
            assert r.passed is True

    def test_gate_test_quality_above_ratio(self, gr_with_src):
        (gr_with_src.python_src / "module.py").write_text("x=1")
        (gr_with_src.python_src / "tests").mkdir(exist_ok=True)
        (gr_with_src.python_src / "tests" / "test_module.py").write_text("def test_x(): pass")
        r = gr_with_src.gate_test_quality("python")
        assert r.passed is True

    def test_gate_test_quality_below_ratio(self, gr_with_src):
        for i in range(10):
            (gr_with_src.python_src / f"mod{i}.py").write_text("x=1")
        (gr_with_src.python_src / "tests").mkdir(exist_ok=True)
        (gr_with_src.python_src / "tests" / "test_one.py").write_text("def test_x(): pass")
        r = gr_with_src.gate_test_quality("python")
        assert r.passed is False

    def test_gate_test_quality_zero_src(self, gr_with_src):
        r = gr_with_src.gate_test_quality("python")
        assert r.passed is False


# ──────────────────────────────────────────────
# GateRunner — run_all / evaluate / print_report
# ──────────────────────────────────────────────

class TestRunAllAndEvaluate:
    def test_run_all_with_no_stacks(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        with patch.object(gr, "_run_cmd", return_value=MockCmd.ok("OK")):
            report = gr.run_all(stacks=["python"])
        assert "hard_gates" in report
        assert "soft_goals" in report
        assert "overall" in report

    def test_run_all_success(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "src" / "module.py").write_text("x = 1\ny = 2\n")
        (tmp_path / "src" / "tests").mkdir()
        (tmp_path / "src" / "tests" / "test_module.py").write_text("def test_x(): pass\ndef test_y(): pass\n")

        def mock_run(cmd, cwd, timeout=120):
            cmd_str = " ".join(cmd)
            if "coverage" in cmd_str or "cov" in cmd_str:
                return MockCmd.ok("TOTAL    100  50  90%\n")
            if "mutmut" in cmd_str or "mutation" in cmd_str:
                return MockCmd.ok("85.0% mutation score\n")
            return MockCmd.ok("OK\n")

        gr = GateRunner(tmp_path)
        with patch.object(gr, "_run_cmd", side_effect=mock_run):
            report = gr.run_all(stacks=["python"])
        assert report["overall"]["passed"] is True, f"report={report}"

    def test_evaluate_empty_results(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        ev = gr.evaluate()
        assert ev["hard_gates"]["passed"] is True
        assert ev["soft_goals"]["score"] == 0.0
        assert ev["overall"]["passed"] is False

    def test_evaluate_with_mixed_results(self, gr_with_src):
        for gate in GateRunner.HARD_GATES:
            key = f"{gate}:python"
            gr_with_src.results[key] = GateResult(gate, True, stack="python", score=10.0)
        gr_with_src.results["tests_pass:python"] = GateResult("tests_pass", False, stack="python", score=0.0)
        ev = gr_with_src.evaluate()
        assert ev["hard_gates"]["passed"] is False

    def test_evaluate_soft_score_weighted(self, gr_with_src):
        for gate in GateRunner.SOFT_GOALS:
            key = f"{gate}:python"
            gr_with_src.results[key] = GateResult(gate, True, stack="python", score=10.0)
        ev = gr_with_src.evaluate()
        assert ev["soft_goals"]["score"] == 10.0

    def test_evaluate_soft_score_failing(self, gr_with_src):
        for gate in GateRunner.SOFT_GOALS:
            key = f"{gate}:python"
            gr_with_src.results[key] = GateResult(gate, False, stack="python", score=1.0)
        ev = gr_with_src.evaluate()
        assert ev["soft_goals"]["score"] < 8.0
        assert ev["soft_goals"]["passed"] is False

    def test_print_report_does_not_raise(self, gr_with_src):
        for gate in GateRunner.HARD_GATES + GateRunner.SOFT_GOALS:
            key = f"{gate}:python"
            gr_with_src.results[key] = GateResult(gate, True, stack="python", score=10.0)
        gr_with_src.print_report()

    def test_run_all_with_security_issue(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "danger.py").write_text("import pickle\neval(x)\n")
        gr = GateRunner(tmp_path)
        with patch.object(gr, "_run_cmd", return_value=MockCmd.ok("OK")):
            report = gr.run_all(stacks=["python"])
        assert report["overall"]["passed"] is False

    def test_run_all_includes_both_stacks(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        gr = GateRunner(tmp_path)
        with patch.object(gr, "_run_cmd", return_value=MockCmd.ok("OK")):
            gr.run_all()
        result_keys = list(gr.results.keys())
        py_keys = [k for k in result_keys if ":python" in k]
        ts_keys = [k for k in result_keys if ":typescript" in k]
        assert len(py_keys) == len(GateRunner.HARD_GATES + GateRunner.SOFT_GOALS)
        assert len(ts_keys) == len(GateRunner.HARD_GATES + GateRunner.SOFT_GOALS)


# ──────────────────────────────────────────────
# GateRunner — stack-specific test quality
# ──────────────────────────────────────────────

class TestTestQualityStack:
    def test_test_quality_python_uses_src_tests(self, tmp_path):
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "mod.py").write_text("x=1")
        (tmp_path / "src" / "tests").mkdir()
        (tmp_path / "src" / "tests" / "test_mod.py").write_text("def test_x(): pass")
        gr = GateRunner(tmp_path)
        r = gr.gate_test_quality("python")
        assert r.passed is True

    def test_test_quality_ts_uses_src_tests(self, tmp_path):
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "component.ts").write_text("export const x = 1;")
        (tmp_path / "frontend" / "src" / "__tests__").mkdir()
        (tmp_path / "frontend" / "src" / "__tests__" / "test_component.ts").write_text("test('x', () => {})")
        gr = GateRunner(tmp_path)
        r = gr.gate_test_quality("typescript")
        assert r.passed is True


def test_gate_coverage_score_bounded(gr_with_src):
    stdout = "TOTAL    100  50  200%"
    with patch.object(gr_with_src, "_run_cmd", return_value=MockCmd.ok(stdout)):
        r = gr_with_src.gate_coverage_branch("python")
        assert r.score <= 10.0


def test_gate_result_evidence_truncated():
    r = GateResult("test", True, evidence="x" * 1000)
    assert len(r.to_dict()["evidence"]) == 500
