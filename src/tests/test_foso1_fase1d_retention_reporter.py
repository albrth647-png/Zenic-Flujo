"""Tests Fase 1D — Foso 1: Retention policy LATAM + ReproducibilityReporter.

Cubre:
- get_retention_days: 5-10 años por país (LATAM)
- should_purge: retención cumplida vs pendiente
- get_regulator_name: SBS, CNBV, BACEN, SFC, CMF
- list_retention_policies: lista completa
- ReproducibilityReporter.generate_report: PDF generado con verificaciones
- ReproducibilityReporter: detecta tampering (hash mismatch)
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="foso1_1d_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / ".workflow_determinista"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "workflow_determinista.db"
    monkeypatch.setenv("WFD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    from src.core.db import sqlite_manager as sm_mod
    monkeypatch.setattr(sm_mod, "DB_PATH", db_path)
    sm_mod.DatabaseManager._reset()
    from src.core.security.encryption import EncryptionService
    EncryptionService._instance = None  # type: ignore[attr-defined]
    EncryptionService._initialized = False  # type: ignore[attr-defined]
    from src.orbital.context import OrbitalContext
    OrbitalContext._reset()
    yield
    with contextlib.suppress(Exception):
        sm_mod.DatabaseManager._reset()


# ── Retention policy ───────────────────────────────────────────────────


class TestRetentionPolicy:
    """Políticas de retención LATAM (5-10 años por país)."""

    @pytest.mark.parametrize("country,expected_years", [
        ("MX", 10),  # CNBV
        ("BR", 10),  # BACEN
        ("AR", 10),  # BCRA
        ("CO", 5),   # SFC
        ("CL", 5),   # CMF
        ("PE", 10),  # SBS
        ("EC", 7),   # SBS Ecuador
        ("UY", 10),  # BCU
        ("PY", 5),   # BCP
        ("BO", 10),  # ASFI
    ])
    def test_banking_retention_by_country(self, country, expected_years):
        from src.compliance.retention_policy import get_retention_days

        days = get_retention_days(country, "banking")
        years = days / 365
        assert years == expected_years, (
            f"Banking retention for {country} should be {expected_years} years, "
            f"got {years}"
        )

    def test_unknown_country_falls_back_to_5_years(self):
        from src.compliance.retention_policy import DEFAULT_RETENTION_DAYS, get_retention_days

        assert get_retention_days("US", "banking") == DEFAULT_RETENTION_DAYS
        assert get_retention_days("XX", "banking") == DEFAULT_RETENTION_DAYS
        assert DEFAULT_RETENTION_DAYS == 365 * 5

    def test_data_type_affects_retention(self):
        """Healthcare y PII pueden tener diferente retención que banking."""
        from src.compliance.retention_policy import get_retention_days

        # Colombia: banking 5 años, healthcare 10 años
        assert get_retention_days("CO", "banking") == 365 * 5
        assert get_retention_days("CO", "healthcare") == 365 * 10
        assert get_retention_days("CO", "pii") == 365 * 5

    def test_should_purge_old_entry(self):
        """Entry con antiguedad > retention_days → True (purgable)."""
        import time

        from src.compliance.retention_policy import should_purge

        # Entry de hace 6 años (supera los 5 años de CO banking)
        old_ts = time.time() - (365 * 6 * 86400)
        assert should_purge(old_ts, country_code="CO", data_type="banking") is True

    def test_should_not_purge_recent_entry(self):
        """Entry reciente → False (debe conservarse)."""
        import time

        from src.compliance.retention_policy import should_purge

        recent_ts = time.time() - 86400  # 1 día
        assert should_purge(recent_ts, country_code="MX", data_type="banking") is False

    def test_get_regulator_name(self):
        from src.compliance.retention_policy import get_regulator_name

        assert get_regulator_name("MX") == "CNBV"
        assert get_regulator_name("BR") == "BACEN"
        assert get_regulator_name("AR") == "BCRA"
        assert get_regulator_name("CO") == "SFC"
        assert get_regulator_name("CL") == "CMF"
        assert get_regulator_name("PE") == "SBS"
        assert get_regulator_name("XX") == "Desconocido"

    def test_list_retention_policies_returns_all(self):
        from src.compliance.retention_policy import list_retention_policies

        policies = list_retention_policies()
        # 10 países * 4 tipos de dato = 40 políticas mínimo
        assert len(policies) >= 40
        # Cada policy debe tener los campos esperados
        p = policies[0]
        assert "country" in p
        assert "regulator" in p
        assert "data_type" in p
        assert "retention_days" in p
        assert "retention_years" in p


# ── ReproducibilityReporter ───────────────────────────────────────────


class TestReproducibilityReporter:
    """Genera reportes de reproducibilidad para reguladores."""

    def _setup_orbital_execution(self, workflow_exec_id: int = 1):
        """Helper: crea un OrbitalResult y lo persiste para un workflow_execution."""
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result = engine.run_tick()

        persistence = OrbitalPersistence()
        persistence.save_orbital_result(
            result=result, workflow_execution_id=workflow_exec_id, previous_hash="",
        )
        return result

    def test_generate_report_creates_pdf(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        self._setup_orbital_execution(workflow_exec_id=1)
        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=1,
            country_code="MX",
        )

        assert "pdf_path" in report
        assert os.path.exists(report["pdf_path"])
        assert report["pdf_path"].endswith(".pdf")
        # PDF debe ser no vacío
        assert os.path.getsize(report["pdf_path"]) > 1000

    def test_report_contains_all_verifications(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        self._setup_orbital_execution(workflow_exec_id=2)
        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=2,
            country_code="PE",
        )

        # Todos los campos esperados
        assert "reproducible" in report
        assert "input_verified" in report
        assert "output_verified" in report
        assert "signatures_verified" in report
        assert "chain_verified" in report
        assert "cod_proof" in report
        assert "country_code" in report
        assert "regulator" in report
        assert "retention_days" in report

    def test_report_regulator_by_country(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        self._setup_orbital_execution(workflow_exec_id=3)
        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=3,
            country_code="BR",
        )
        assert report["regulator"] == "BACEN"
        assert report["country_code"] == "BR"
        # Brasil: 10 años banking
        assert report["retention_days"] == 365 * 10

    def test_report_input_verified_when_fingerprint_present(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        self._setup_orbital_execution(workflow_exec_id=4)
        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=4,
            country_code="MX",
        )
        # input_fingerprint debe estar poblado por run_tick
        assert report["input_verified"] is True
        assert report["input_fingerprint"]
        assert len(report["input_fingerprint"]) == 64

    def test_report_output_hash_matches(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        self._setup_orbital_execution(workflow_exec_id=5)
        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=5,
            country_code="MX",
        )
        # Sin tampering, output_verified debe ser True
        assert report["output_verified"] is True

    def test_report_detects_tampering(self):
        """Si modificamos final_state, output_verified debe ser False."""
        from src.compliance.reproducibility_reporter import ReproducibilityReporter
        from src.core.db.sqlite_manager import DatabaseManager

        self._setup_orbital_execution(workflow_exec_id=6)
        # Tamper
        db = DatabaseManager()
        db.execute(
            "UPDATE orbital_executions SET final_state = 'tampered' "
            "WHERE workflow_execution_id = 6"
        )
        db.commit()

        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=6,
            country_code="MX",
        )
        assert report["output_verified"] is False
        assert report["reproducible"] is False

    def test_report_for_nonexistent_execution_returns_error(self):
        from src.compliance.reproducibility_reporter import ReproducibilityReporter

        reporter = ReproducibilityReporter()
        report = reporter.generate_report(
            workflow_execution_id=99999,
            country_code="MX",
        )
        assert "error" in report
