"""
Tests for RunLedger — Code-Forge v1.0
Cobertura: creación, append action, rollback, integrity check, corrupted ledger detection
"""

import json
import tempfile

import pytest

from forge.run_ledger import RunLedger


class TestRunLedgerCreation:
    """Tests de creación e inicialización del ledger."""

    def test_creates_new_ledger_with_run_id(self):
        """RunLedger crea un nuevo ledger con run_id único."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            assert ledger.ledger_path.exists()
            assert ledger.data["run_id"].startswith("zenic-fix-")
            assert ledger.data["final_status"] == "running"
            assert ledger.data["actions"] == []
            assert ledger.data["approvals"] == []
            assert ledger.data["proof"] == []

    def test_creates_ledger_with_custom_run_id(self):
        """RunLedger acepta run_id personalizado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir, run_id="test-run-001")
            assert ledger.data["run_id"] == "test-run-001"

    def test_loads_existing_ledger(self):
        """RunLedger carga ledger existente si existe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger1 = RunLedger(tmpdir, run_id="existing-001")
            ledger1.set_spec("Spec original")
            ledger1.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")

            # Nueva instancia debe cargar el existente
            ledger2 = RunLedger(tmpdir)
            assert ledger2.data["run_id"] == "existing-001"
            assert ledger2.data["spec"] == "Spec original"
            assert len(ledger2.data["actions"]) == 1

    def test_rejects_corrupted_ledger(self):
        """RunLedger lanza error si el ledger existente está corrupto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir, run_id="test-corrupt")
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")

            # Corromper el archivo JSON manualmente
            with open(ledger.ledger_path, "w") as f:
                f.write("{ invalid json }")

            with pytest.raises(RuntimeError, match="RUN LEDGER CORRUPTED"):
                RunLedger(tmpdir)


class TestRunLedgerSpec:
    """Tests de registro de SPEC."""

    def test_set_spec_stores_spec(self):
        """set_spec guarda la SPEC en el ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.set_spec("Implementar feature X")
            assert ledger.data["spec"] == "Implementar feature X"

    def test_set_spec_overwrites(self):
        """set_spec sobrescribe SPEC anterior."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.set_spec("Spec v1")
            ledger.set_spec("Spec v2")
            assert ledger.data["spec"] == "Spec v2"


class TestRunLedgerActions:
    """Tests de registro de acciones."""

    def test_add_action_basic(self):
        """add_action registra acción básica."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            action = ledger.add_action(
                "edit_file", "src/main.py", rollback="git checkout src/main.py"
            )
            assert len(ledger.data["actions"]) == 1
            assert action["action_type"] == "edit_file"
            assert action["target"] == "src/main.py"
            assert action["rollback"] == "git checkout src/main.py"
            assert action["verified"] is False

    def test_add_action_increments_files_changed(self):
        """edit_file incrementa contador de archivos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("edit_file", "src/a.py", rollback="git checkout src/a.py")
            ledger.add_action("edit_file", "src/b.py", rollback="git checkout src/b.py")
            assert ledger.data["metadata"]["total_files_changed"] == 2

    def test_add_action_rejects_missing_rollback_for_edit_file(self):
        """add_action rechaza edit_file sin rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            with pytest.raises(ValueError, match="rollback no definido"):
                ledger.add_action("edit_file", "src/test.py")

    def test_add_action_rejects_missing_rollback_for_git_commit(self):
        """add_action rechaza git_commit sin rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            with pytest.raises(ValueError, match="rollback no definido"):
                ledger.add_action("git_commit", "commit message")

    def test_add_action_allows_other_types_without_rollback(self):
        """add_action permite run_test sin rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            action = ledger.add_action("run_test", "pytest src/tests/")
            assert action["action_type"] == "run_test"
            assert action["rollback"] == ""

    def test_mark_verified(self):
        """mark_verified marca acción como verificada."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")
            ledger.mark_verified(0)
            assert ledger.data["actions"][0]["verified"] is True

    def test_record_rollback(self):
        """record_rollback registra rollback ejecutado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")
            ledger.record_rollback(0, "Test falló")
            action = ledger.data["actions"][0]
            assert action["verified"] is False
            assert action["rolled_back"] is True
            assert action["rollback_reason"] == "Test falló"
            assert ledger.data["metadata"]["rollbacks_executed"] == 1

    def test_record_canary_fix(self):
        """record_canary_fix incrementa contador canary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.record_canary_fix("src/test.py")
            assert ledger.data["metadata"]["canary_fixes_applied"] == 1


class TestRunLedgerApprovals:
    """Tests de aprobaciones de fase."""

    def test_add_approval(self):
        """add_approval registra aprobación."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_approval("specify", "human", "Aprobado por revisión")
            assert len(ledger.data["approvals"]) == 1
            assert ledger.data["approvals"][0]["phase"] == "specify"
            assert ledger.data["approvals"][0]["approved_by"] == "human"
            assert ledger.data["approvals"][0]["notes"] == "Aprobado por revisión"


class TestRunLedgerGates:
    """Tests de registro de resultados de gates."""

    def test_add_gate_result_pass(self):
        """add_gate_result registra gate que pasa."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_gate_result("tests_pass", True, "2088 passed", "python")
            assert len(ledger.data["proof"]) == 1
            assert ledger.data["proof"][0]["gate_name"] == "tests_pass"
            assert ledger.data["proof"][0]["passed"] is True
            assert ledger.data["proof"][0]["stack"] == "python"

    def test_add_gate_result_fail(self):
        """add_gate_result registra gate que falla."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_gate_result("lint_clean", False, "E501 line too long", "python")
            assert ledger.data["proof"][0]["passed"] is False

    def test_add_gate_result_updates_hard_gates_count(self):
        """Hard gates que pasan incrementan contador."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            # 3 hard gates que pasan
            ledger.add_gate_result("tests_pass", True, "OK", "python")
            ledger.add_gate_result("no_security_issues", True, "OK", "python")
            ledger.add_gate_result("no_broken_imports", True, "OK", "python")
            # 1 soft gate que falla (no cuenta)
            ledger.add_gate_result("lint_clean", False, "E501", "python")

            assert ledger.data["metadata"]["hard_gates_passed"] == 3

    def test_set_soft_score(self):
        """set_soft_score registra score ponderado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.set_soft_score(8.5)
            assert ledger.data["metadata"]["soft_score"] == 8.5


class TestRunLedgerHighRisk:
    """Tests de detección de alto riesgo."""

    def test_is_high_risk_without_rollback(self):
        """Acción sin rollback es high-risk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("run_test", "pytest")  # sin rollback
            assert ledger.is_high_risk(0) is True

    def test_is_high_risk_with_rollback(self):
        """Acción con rollback NO es high-risk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")
            assert ledger.is_high_risk(0) is False


class TestRunLedgerCompletion:
    """Tests de finalización."""

    def test_complete_sets_status(self):
        """complete marca ledger como completo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            summary = ledger.complete("pass")
            assert ledger.data["final_status"] == "pass"
            assert "completed_at" in ledger.data
            assert summary["final_status"] == "pass"

    def test_summary_returns_correct_data(self):
        """summary devuelve resumen correcto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir, run_id="test-summary")
            ledger.set_spec("Mi spec")
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")
            ledger.add_gate_result("tests_pass", True, "OK", "python")
            ledger.complete("pass")

            summary = ledger.summary()
            assert summary["run_id"] == "test-summary"
            assert summary["spec"] == "Mi spec"
            assert summary["final_status"] == "pass"
            assert summary["total_actions"] == 1
            assert summary["verified_actions"] == 0
            assert summary["hard_gates_passed"] == 1
            assert summary["is_complete"] is True


class TestRunLedgerIntegrity:
    """Tests de verificación de integridad."""

    def test_verify_integrity_valid_ledger(self):
        """verify_integrity retorna True para ledger válido."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            ledger.add_action("edit_file", "src/test.py", rollback="git checkout src/test.py")
            assert ledger.verify_integrity() is True

    def test_verify_integrity_missing_required_keys(self):
        """verify_integrity detecta claves faltantes — constructor falla."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RunLedger(tmpdir)
            # Corromper manualmente eliminando clave requerida
            del ledger.data["actions"]
            with open(ledger.ledger_path, "w") as f:
                json.dump(ledger.data, f)

            # Constructor debe fallar al cargar ledger corrupto
            with pytest.raises(RuntimeError, match="RUN LEDGER CORRUPTED"):
                RunLedger(tmpdir)

    def test_verify_integrity_missing_rollback_on_edit_file(self):
        """verify_integrity detecta edit_file sin rollback — constructor falla."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crear ledger corrupto manualmente
            ledger = RunLedger(tmpdir)
            ledger.data["actions"].append({
                "action_type": "edit_file",
                "target": "src/test.py",
                "rollback": "",  # Sin rollback
            })
            ledger._save()

            # Constructor debe fallar al cargar ledger corrupto
            with pytest.raises(RuntimeError, match="RUN LEDGER CORRUPTED"):
                RunLedger(tmpdir)


class TestRunLedgerPersistence:
    """Tests de persistencia entre instancias."""

    def test_persists_across_instances(self):
        """Datos persisten entre instancias."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger1 = RunLedger(tmpdir, run_id="persist-test")
            ledger1.set_spec("Spec persistente")
            ledger1.add_action("edit_file", "src/a.py", rollback="git checkout src/a.py")
            ledger1.add_gate_result("tests_pass", True, "OK", "python")
            ledger1.complete("pass")

            # Nueva instancia
            ledger2 = RunLedger(tmpdir)
            assert ledger2.data["run_id"] == "persist-test"
            assert ledger2.data["spec"] == "Spec persistente"
            assert len(ledger2.data["actions"]) == 1
            assert len(ledger2.data["proof"]) == 1
            assert ledger2.data["final_status"] == "pass"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
