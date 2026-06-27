"""
Tests for forge/ledger_cli.py — Subcomando `forge ledger`
Cobertura: init, verify, show, list, integrity checks
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.ledger_cli import (
    _check_integrity,
    init_ledger,
    list_ledgers,
    show_ledger,
    verify_ledger,
)


class TestInitLedger:
    """Tests de init_ledger."""

    def test_init_creates_ledger_in_empty_dir(self, tmp_path: Path):
        """init_ledger crea run_ledger.json en directorio vacío."""
        target = tmp_path / "phase5"
        ledger_path = init_ledger(target)
        assert ledger_path.exists()
        assert ledger_path.name == "run_ledger.json"
        # Verificar que el JSON es válido
        with open(ledger_path) as f:
            data = json.load(f)
        assert data["final_status"] == "running"
        assert "run_id" in data

    def test_init_with_custom_run_id(self, tmp_path: Path):
        """init_ledger respeta run_id personalizado."""
        target = tmp_path / "phase5"
        init_ledger(target, run_id="custom-run-id-123")
        with open(target / "run_ledger.json") as f:
            data = json.load(f)
        assert data["run_id"] == "custom-run-id-123"

    def test_init_rejects_existing_ledger(self, tmp_path: Path):
        """init_ledger rechaza si ya existe un ledger."""
        target = tmp_path / "phase5"
        init_ledger(target)
        with pytest.raises(FileExistsError):
            init_ledger(target)

    def test_init_creates_parent_dirs(self, tmp_path: Path):
        """init_ledger crea directorios padre si no existen."""
        target = tmp_path / "nested" / "deep" / "phase5"
        ledger_path = init_ledger(target)
        assert ledger_path.exists()


class TestCheckIntegrity:
    """Tests de _check_integrity (función interna)."""

    def test_valid_ledger_passes(self):
        """Ledger válido pasa integridad."""
        data = {
            "run_id": "test",
            "spec": "test spec",
            "actions": [],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, error = _check_integrity(data)
        assert valid is True
        assert error == ""

    def test_missing_required_key_fails(self):
        """Falta una key requerida → inválido."""
        data = {
            "run_id": "test",
            # missing spec
            "actions": [],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, error = _check_integrity(data)
        assert valid is False
        assert "spec" in error

    def test_edit_file_without_rollback_fails(self):
        """edit_file sin rollback → inválido."""
        data = {
            "run_id": "test",
            "spec": "test",
            "actions": [
                {"action_type": "edit_file", "target": "src/main.py", "rollback": ""},
            ],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, error = _check_integrity(data)
        assert valid is False
        assert "rollback" in error

    def test_edit_file_with_rollback_passes(self):
        """edit_file con rollback → válido."""
        data = {
            "run_id": "test",
            "spec": "test",
            "actions": [
                {"action_type": "edit_file", "target": "src/main.py", "rollback": "git checkout src/main.py"},
            ],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, _ = _check_integrity(data)
        assert valid is True

    def test_git_commit_without_rollback_fails(self):
        """git_commit sin rollback → inválido."""
        data = {
            "run_id": "test",
            "spec": "test",
            "actions": [
                {"action_type": "git_commit", "target": "git commit", "rollback": ""},
            ],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, _error = _check_integrity(data)
        assert valid is False

    def test_run_test_without_rollback_passes(self):
        """run_test no requiere rollback."""
        data = {
            "run_id": "test",
            "spec": "test",
            "actions": [
                {"action_type": "run_test", "target": "pytest", "rollback": ""},
            ],
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, _ = _check_integrity(data)
        assert valid is True

    def test_actions_not_list_fails(self):
        """actions no es lista → inválido."""
        data = {
            "run_id": "test",
            "spec": "test",
            "actions": "not a list",
            "approvals": [],
            "proof": [],
            "final_status": "running",
        }
        valid, error_msg = _check_integrity(data)
        assert valid is False
        assert "list" in error_msg


class TestVerifyLedger:
    """Tests de verify_ledger."""

    def test_verify_valid_ledger(self, tmp_path: Path):
        """verify_ledger confirma ledger válido."""
        target = tmp_path / "phase5"
        init_ledger(target, run_id="verify-test")
        result = verify_ledger(target / "run_ledger.json")
        assert result["valid"] is True
        assert result["error"] == ""
        assert result["actions_count"] == 0
        assert result["final_status"] == "running"

    def test_verify_nonexistent_file(self, tmp_path: Path):
        """verify_ledger reporta file not found."""
        result = verify_ledger(tmp_path / "nonexistent.json")
        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    def test_verify_corrupted_json(self, tmp_path: Path):
        """verify_ledger detecta JSON corrupto."""
        ledger_path = tmp_path / "corrupt.json"
        ledger_path.write_text("{ invalid json }")
        result = verify_ledger(ledger_path)
        assert result["valid"] is False
        assert "JSON decode error" in result["error"]
        assert result["final_status"] == "corrupted"

    def test_verify_ledger_with_actions_and_metadata(self, tmp_path: Path):
        """verify_ledger lee actions_count y metadata correctamente."""
        target = tmp_path / "phase5"
        init_ledger(target, run_id="verify-test")
        ledger_path = target / "run_ledger.json"
        with open(ledger_path) as f:
            data = json.load(f)
        data["actions"] = [
            {"action_type": "edit_file", "target": "src/main.py", "rollback": "git checkout src/main.py"},
            {"action_type": "run_test", "target": "pytest", "rollback": ""},
        ]
        data["metadata"]["hard_gates_passed"] = 5
        data["metadata"]["soft_score"] = 8.5
        data["final_status"] = "pass"
        with open(ledger_path, "w") as f:
            json.dump(data, f)

        result = verify_ledger(ledger_path)
        assert result["valid"] is True
        assert result["actions_count"] == 2
        assert result["hard_gates_passed"] == 5
        assert result["soft_score"] == 8.5
        assert result["final_status"] == "pass"


class TestShowLedger:
    """Tests de show_ledger."""

    def test_show_returns_summary(self, tmp_path: Path):
        """show_ledger devuelve LedgerSummary."""
        target = tmp_path / "phase5"
        init_ledger(target, run_id="show-test")
        summary = show_ledger(target / "run_ledger.json")
        assert summary is not None
        assert summary["run_id"] == "show-test"
        assert summary["final_status"] == "running"
        assert summary["is_complete"] is False

    def test_show_nonexistent_returns_none(self, tmp_path: Path):
        """show_ledger devuelve None si no existe."""
        assert show_ledger(tmp_path / "nonexistent.json") is None

    def test_show_corrupted_returns_none(self, tmp_path: Path):
        """show_ledger devuelve None si está corrupto."""
        ledger_path = tmp_path / "corrupt.json"
        ledger_path.write_text("{ invalid }")
        assert show_ledger(ledger_path) is None


class TestListLedgers:
    """Tests de list_ledgers."""

    def test_list_finds_ledgers_in_forge_dir(self, tmp_path: Path):
        """list_ledgers encuentra ledgers en .forge/*/."""
        # Crear 3 ledgers
        for phase in ["phase1", "phase2", "phase3"]:
            init_ledger(tmp_path / ".forge" / phase, run_id=f"run-{phase}")

        entries = list_ledgers(tmp_path)
        assert len(entries) == 3
        paths = [e["path"] for e in entries]
        assert ".forge/phase1/run_ledger.json" in paths
        assert ".forge/phase2/run_ledger.json" in paths
        assert ".forge/phase3/run_ledger.json" in paths

    def test_list_empty_when_no_forge_dir(self, tmp_path: Path):
        """list_ledgers devuelve [] si no hay .forge/."""
        entries = list_ledgers(tmp_path)
        assert entries == []

    def test_list_skips_invalid_ledgers(self, tmp_path: Path):
        """list_ledgers salta ledgers inválidos."""
        # Ledger válido
        init_ledger(tmp_path / ".forge" / "phase1", run_id="valid")
        # Ledger inválido (corrupto)
        invalid_dir = tmp_path / ".forge" / "phase2"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "run_ledger.json").write_text("{ invalid }")

        entries = list_ledgers(tmp_path)
        assert len(entries) == 1
        assert entries[0]["run_id"] == "valid"

    def test_list_entries_have_required_fields(self, tmp_path: Path):
        """Cada entry tiene todos los campos de LedgerListEntry."""
        init_ledger(tmp_path / ".forge" / "phase1", run_id="test")
        entries = list_ledgers(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert "path" in e
        assert "run_id" in e
        assert "final_status" in e
        assert "actions_count" in e
        assert "hard_gates_passed" in e
        assert "soft_score" in e


class TestIntegrationWithRealPhaseLedgers:
    """Tests de integración con ledgers reales de Fases 1-4."""

    def test_verify_phase1_ledger(self):
        """verify_ledger funciona sobre el ledger real de Fase 1."""
        ledger_path = Path(".forge/phase1/run_ledger.json")
        if not ledger_path.exists():
            pytest.skip("Phase 1 ledger not found")
        result = verify_ledger(ledger_path)
        assert result["valid"] is True
        assert result["actions_count"] >= 0

    def test_verify_phase3_ledger(self):
        """verify_ledger funciona sobre el ledger real de Fase 3."""
        ledger_path = Path(".forge/phase3/run_ledger.json")
        if not ledger_path.exists():
            pytest.skip("Phase 3 ledger not found")
        result = verify_ledger(ledger_path)
        assert result["valid"] is True

    def test_list_finds_all_phase_ledgers(self):
        """list_ledgers encuentra todos los ledgers de fase."""
        project_root = Path(".")
        entries = list_ledgers(project_root)
        # Debería encontrar al menos phase1, phase3, phase4
        phase_paths = [e["path"] for e in entries]
        assert any("phase1" in p for p in phase_paths)
        assert any("phase3" in p for p in phase_paths)
        assert any("phase4" in p for p in phase_paths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
