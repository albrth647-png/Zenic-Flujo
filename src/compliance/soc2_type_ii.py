"""
SOC 2 Type II — Operating Effectiveness Over Time

Extends the base compliance framework with SOC 2 Type II requirements:
- Monitoring periods (typically 3-12 months)
- Point-in-time sampling and evidence over time
- Control test results with pass/fail over multiple test cycles
- System description and boundary documentation
- Trend analysis across test periods
- Bridge letter preparation for transitions between periods
- Sample sizing methodology per AICPA guidelines
- Subservice organization mapping (carve-out / inclusive)
- Complementary user entity controls (CUEC) documentation
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging("soc2_type_ii")


class MonitoringPeriodStatus(Enum):
    """Status of a SOC 2 Type II monitoring period."""
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SamplingMethodology(Enum):
    """Sampling methodology per AICPA SOC 2 guidance."""
    RANDOM = "random"
    STRATIFIED = "stratified"
    SYSTEMATIC = "systematic"
    BLOCK = "block"
    HAPHAZARD = "haphazard"
    JUDGMENTAL = "judgmental"


class TestResultStatus(Enum):
    """Result of an individual control test during Type II period."""
    PASS = "pass"
    FAIL = "fail"
    NOT_TESTED = "not_tested"
    REMEDIATED = "remediated"
    EXCEPTION = "exception"


class ControlFrequency(Enum):
    """How frequently a control operates (determines sample size)."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"
    CONTINUOUS = "continuous"
    PER_TRANSACTION = "per_transaction"


@dataclass
class MonitoringPeriod:
    """A SOC 2 Type II monitoring period.

    Type II requires evidence of operating effectiveness over a period
    of time, typically 6-12 months (3-month minimum).
    """
    period_id: str = ""
    name: str = ""
    description: str = ""
    start_date: float = 0.0
    end_date: float = 0.0
    status: MonitoringPeriodStatus = MonitoringPeriodStatus.PLANNED
    auditor_name: str = ""
    audit_firm: str = ""
    monitoring_days: int = 0
    controls_tested: int = 0
    controls_passed: int = 0
    system_description: str = ""
    boundary_description: str = ""
    report_type: str = "Type II"  # Type II or bridge letter
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.period_id:
            self.period_id = f"period-{uuid.uuid4().hex[:10]}"
        if self.start_date and self.end_date:
            self.monitoring_days = int((self.end_date - self.start_date) / 86400)


@dataclass
class ControlTestResult:
    """An individual test result for a control during a monitoring period.

    Type II requires multiple test results over time to demonstrate
    operating effectiveness, not just point-in-time design.
    """
    test_id: str = ""
    period_id: str = ""
    control_id: str = ""
    test_date: float = field(default_factory=time.time)
    tester: str = "system"
    result: TestResultStatus = TestResultStatus.NOT_TESTED
    sample_size: int = 0
    sample_selected: list[str] = field(default_factory=list)
    exceptions_found: int = 0
    exception_details: str = ""
    evidence_snapshot: str = ""  # Evidence collected at this test point
    methodology: SamplingMethodology = SamplingMethodology.RANDOM
    notes: str = ""
    remediated: bool = False
    remediation_date: float = 0.0
    remediation_evidence: str = ""

    def __post_init__(self) -> None:
        if not self.test_id:
            self.test_id = f"test-{uuid.uuid4().hex[:10]}"


@dataclass
class SubserviceOrganization:
    """A subservice organization relevant to SOC 2 reporting.

    Used for carve-out or inclusive method reporting.
    """
    subservice_id: str = ""
    name: str = ""
    description: str = ""
    services_provided: str = ""
    reporting_method: str = "carve_out"  # carve_out or inclusive
    has_soc_report: bool = False
    soc_report_date: str = ""
    relevant_controls: list[str] = field(default_factory=list)
    cuce_controls: list[str] = field(default_factory=list)  # Complementary User Entity Controls
    contact_info: str = ""

    def __post_init__(self) -> None:
        if not self.subservice_id:
            self.subservice_id = f"sub-{uuid.uuid4().hex[:8]}"


def recommend_sample_size(
    control_frequency: ControlFrequency,
    population_size: int,
    risk_level: str = "medium",
) -> int:
    """Recommend sample size based on control frequency and risk level.

    Based on AICPA SOC 2 sampling guidance:
    - Daily: 25-60 samples
    - Weekly: 8-15 samples
    - Monthly: 3-8 samples
    - Quarterly: 2-4 samples
    - Annually: 1-2 samples
    - Continuous/automated: 1 sample + config review
    - Per-transaction: based on population (statistical sampling)
    """
    base_samples: dict[ControlFrequency, tuple[int, int, int]] = {
        ControlFrequency.DAILY: (25, 40, 60),
        ControlFrequency.WEEKLY: (8, 10, 15),
        ControlFrequency.MONTHLY: (3, 5, 8),
        ControlFrequency.QUARTERLY: (2, 3, 4),
        ControlFrequency.ANNUALLY: (1, 1, 2),
        ControlFrequency.CONTINUOUS: (1, 1, 1),
        ControlFrequency.PER_TRANSACTION: (10, 25, 50),
    }

    risk_multipliers: dict[str, float] = {
        "low": 0.8,
        "medium": 1.0,
        "high": 1.3,
        "critical": 1.5,
    }

    low, medium, high = base_samples.get(control_frequency, (5, 10, 20))
    base = {"low": low, "medium": medium, "high": high}

    risk_level_key = risk_level if risk_level in base else "medium"
    samples = int(base[risk_level_key] * risk_multipliers.get(risk_level, 1.0))

    return min(samples, population_size)


class SOC2TypeIIManager:
    """Manages SOC 2 Type II monitoring periods and control testing.

    Extends the base ComplianceManager with Type II-specific features:
    - Monitoring period lifecycle (plan → active → complete)
    - Control test scheduling and execution over time
    - Sample sizing methodology
    - Trend analysis across test cycles
    - System description / boundary documentation
    - Subservice organization mapping
    - Complementary user entity controls (CUEC)
    - Bridge letter generation

    Usage:
        manager = SOC2TypeIIManager.get_instance()
        period = manager.create_monitoring_period(
            name="SOC 2 Type II Jan-Dec 2026",
            start_date=...
        )
        result = manager.record_test_result(
            period_id=period.period_id,
            control_id="ctrl-abc123",
            result=TestResultStatus.PASS,
        )
        report = manager.generate_type_ii_report(period_id)
    """

    _instance: SOC2TypeIIManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = None) -> None:
        if db_path is None:
            from src.core.config import COMPLIANCE_DB_PATH
            db_path = str(COMPLIANCE_DB_PATH)
        self._db_path = db_path
        self._periods: dict[str, MonitoringPeriod] = {}
        self._test_results: dict[str, ControlTestResult] = {}
        self._subservices: dict[str, SubserviceOrganization] = {}
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @classmethod
    def get_instance(cls, **kwargs: Any) -> SOC2TypeIIManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        # Fix NEW-BUG-6: PRAGMA WAL + busy_timeout (mismo fix que compliance/__init__.py bug #40)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS soc2_typeii_periods (
                period_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                start_date REAL NOT NULL,
                end_date REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned',
                auditor_name TEXT,
                audit_firm TEXT,
                monitoring_days INTEGER DEFAULT 0,
                controls_tested INTEGER DEFAULT 0,
                controls_passed INTEGER DEFAULT 0,
                system_description TEXT,
                boundary_description TEXT,
                report_type TEXT DEFAULT 'Type II',
                created_at REAL,
                completed_at REAL
            );
            CREATE TABLE IF NOT EXISTS soc2_typeii_test_results (
                test_id TEXT PRIMARY KEY,
                period_id TEXT NOT NULL,
                control_id TEXT NOT NULL,
                test_date REAL NOT NULL,
                tester TEXT DEFAULT 'system',
                result TEXT NOT NULL DEFAULT 'not_tested',
                sample_size INTEGER DEFAULT 0,
                sample_selected TEXT DEFAULT '[]',
                exceptions_found INTEGER DEFAULT 0,
                exception_details TEXT DEFAULT '',
                evidence_snapshot TEXT DEFAULT '',
                methodology TEXT DEFAULT 'random',
                notes TEXT DEFAULT '',
                remediated INTEGER DEFAULT 0,
                remediation_date REAL DEFAULT 0,
                remediation_evidence TEXT DEFAULT '',
                FOREIGN KEY (period_id) REFERENCES soc2_typeii_periods(period_id)
            );
            CREATE TABLE IF NOT EXISTS soc2_typeii_subservices (
                subservice_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                services_provided TEXT,
                reporting_method TEXT DEFAULT 'carve_out',
                has_soc_report INTEGER DEFAULT 0,
                soc_report_date TEXT,
                relevant_controls TEXT DEFAULT '[]',
                cuce_controls TEXT DEFAULT '[]',
                contact_info TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_typeii_period_status ON soc2_typeii_periods(status);
            CREATE INDEX IF NOT EXISTS idx_typeii_tests_period ON soc2_typeii_test_results(period_id);
            CREATE INDEX IF NOT EXISTS idx_typeii_tests_control ON soc2_typeii_test_results(control_id);
        """)
        self._conn.commit()
        logger.info("SOC2TypeIIManager: Database initialized")

    # ── Monitoring Period Lifecycle ─────────────────────────

    def create_monitoring_period(
        self,
        name: str,
        start_date: float,
        end_date: float,
        description: str = "",
        system_description: str = "",
        boundary_description: str = "",
        auditor_name: str = "",
        audit_firm: str = "",
    ) -> MonitoringPeriod:
        """Create a new SOC 2 Type II monitoring period."""
        period = MonitoringPeriod(
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            status=MonitoringPeriodStatus.PLANNED,
            system_description=system_description,
            boundary_description=boundary_description,
            auditor_name=auditor_name,
            audit_firm=audit_firm,
        )
        self._periods[period.period_id] = period
        self._persist_period(period)
        logger.info(f"SOC2 Type II: Period '{name}' created ({period.period_id})")
        return period

    def activate_period(self, period_id: str) -> bool:
        """Activate a monitoring period (start collecting evidence)."""
        period = self._periods.get(period_id)
        if not period or period.status != MonitoringPeriodStatus.PLANNED:
            return False
        period.status = MonitoringPeriodStatus.ACTIVE
        self._persist_period(period)
        logger.info(f"SOC2 Type II: Period '{period_id}' activated")
        return True

    def complete_period(self, period_id: str) -> bool:
        """Mark a monitoring period as completed."""
        period = self._periods.get(period_id)
        if not period or period.status != MonitoringPeriodStatus.ACTIVE:
            return False
        period.status = MonitoringPeriodStatus.COMPLETED
        period.completed_at = time.time()

        # Calculate stats
        tests = [t for t in self._test_results.values() if t.period_id == period_id]
        period.controls_tested = len({t.control_id for t in tests})
        period.controls_passed = len({
            t.control_id for t in tests if t.result == TestResultStatus.PASS
        })
        self._persist_period(period)
        logger.info(f"SOC2 Type II: Period '{period_id}' completed")
        return True

    def get_period(self, period_id: str) -> MonitoringPeriod | None:
        return self._periods.get(period_id)

    def list_periods(self, status: MonitoringPeriodStatus | None = None) -> list[MonitoringPeriod]:
        periods = list(self._periods.values())
        if status:
            periods = [p for p in periods if p.status == status]
        return sorted(periods, key=lambda p: p.start_date, reverse=True)

    # ── Control Test Results ────────────────────────────────

    def record_test_result(
        self,
        period_id: str,
        control_id: str,
        result: TestResultStatus,
        tester: str = "system",
        sample_size: int = 1,
        exceptions_found: int = 0,
        exception_details: str = "",
        evidence_snapshot: str = "",
        methodology: SamplingMethodology = SamplingMethodology.RANDOM,
        notes: str = "",
    ) -> ControlTestResult | None:
        """Record a control test result during a monitoring period."""
        period = self._periods.get(period_id)
        if not period or period.status != MonitoringPeriodStatus.ACTIVE:
            logger.warning(f"SOC2 Type II: Period '{period_id}' not active")
            return None

        test = ControlTestResult(
            period_id=period_id,
            control_id=control_id,
            test_date=time.time(),
            tester=tester,
            result=result,
            sample_size=sample_size,
            exceptions_found=exceptions_found,
            exception_details=exception_details,
            evidence_snapshot=evidence_snapshot,
            methodology=methodology,
            notes=notes,
        )
        self._test_results[test.test_id] = test
        self._persist_test_result(test)
        return test

    def remediate_exception(
        self,
        test_id: str,
        remediation_evidence: str,
        tester: str = "system",
    ) -> bool:
        """Mark a failed test as remediated with evidence."""
        test = self._test_results.get(test_id)
        if not test or test.result not in (TestResultStatus.FAIL, TestResultStatus.EXCEPTION):
            return False
        test.remediated = True
        test.remediation_date = time.time()
        test.remediation_evidence = remediation_evidence
        test.result = TestResultStatus.REMEDIATED
        self._persist_test_result(test)
        logger.info(f"SOC2 Type II: Exception '{test_id}' remediated")
        return True

    def get_test_results(
        self,
        period_id: str | None = None,
        control_id: str | None = None,
        result: TestResultStatus | None = None,
    ) -> list[ControlTestResult]:
        tests = list(self._test_results.values())
        if period_id:
            tests = [t for t in tests if t.period_id == period_id]
        if control_id:
            tests = [t for t in tests if t.control_id == control_id]
        if result:
            tests = [t for t in tests if t.result == result]
        return sorted(tests, key=lambda t: t.test_date)

    def recommend_sample_size_for_control(
        self,
        control_frequency: ControlFrequency,
        population_size: int,
        risk_level: str = "medium",
    ) -> int:
        """Get AICPA-recommended sample size for a control."""
        return recommend_sample_size(control_frequency, population_size, risk_level)

    # ── Trend Analysis ──────────────────────────────────────

    def analyze_trends(self, period_id: str) -> dict[str, Any]:
        """Analyze control test result trends over the monitoring period."""
        tests = [t for t in self._test_results.values() if t.period_id == period_id]
        if not tests:
            return {"error": "No test results found for this period"}

        # Group by control
        by_control: dict[str, list[ControlTestResult]] = {}
        for t in tests:
            by_control.setdefault(t.control_id, []).append(t)

        trends: dict[str, Any] = {}
        total_passes = 0
        total_fails = 0
        total_remediated = 0

        for control_id, control_tests in by_control.items():
            sorted_tests = sorted(control_tests, key=lambda t: t.test_date)
            passes = sum(1 for t in sorted_tests if t.result == TestResultStatus.PASS)
            fails = sum(1 for t in sorted_tests if t.result in (TestResultStatus.FAIL, TestResultStatus.EXCEPTION))
            remediated = sum(1 for t in sorted_tests if t.remediated)

            # Determine trend direction
            if len(sorted_tests) >= 2:
                first_result = sorted_tests[0].result
                last_result = sorted_tests[-1].result
                if first_result == TestResultStatus.FAIL and last_result == TestResultStatus.PASS:
                    direction = "improving"
                elif first_result == TestResultStatus.PASS and last_result == TestResultStatus.FAIL:
                    direction = "degrading"
                else:
                    direction = "stable"
            else:
                direction = "insufficient_data"

            trends[control_id] = {
                "total_tests": len(sorted_tests),
                "passes": passes,
                "fails": fails,
                "remediated": remediated,
                "pass_rate_pct": round((passes / len(sorted_tests)) * 100, 1),
                "trend_direction": direction,
                "first_test_date": sorted_tests[0].test_date,
                "last_test_date": sorted_tests[-1].test_date,
            }
            total_passes += passes
            total_fails += fails
            total_remediated += remediated

        return {
            "period_id": period_id,
            "total_controls_tested": len(by_control),
            "total_tests": len(tests),
            "overall_pass_rate_pct": round((total_passes / len(tests)) * 100, 1) if tests else 0.0,
            "total_fails": total_fails,
            "total_remediated": total_remediated,
            "trends": trends,
            "analysis_date": time.time(),
        }

    # ── Subservice Organizations ────────────────────────────

    def add_subservice(self, subservice: SubserviceOrganization) -> str:
        """Add a subservice organization for carve-out/inclusive reporting."""
        self._subservices[subservice.subservice_id] = subservice
        self._persist_subservice(subservice)
        return subservice.subservice_id

    def list_subservices(self) -> list[SubserviceOrganization]:
        return list(self._subservices.values())

    # ── Reporting ───────────────────────────────────────────

    def generate_type_ii_report(self, period_id: str) -> dict[str, Any]:
        """Generate a comprehensive SOC 2 Type II report."""
        period = self._periods.get(period_id)
        if not period:
            return {"error": f"Period '{period_id}' not found"}

        trends = self.analyze_trends(period_id)
        tests = self.get_test_results(period_id=period_id)
        subservices = self.list_subservices()

        # Identify exceptions
        exceptions = [t for t in tests if t.result in (TestResultStatus.FAIL, TestResultStatus.EXCEPTION)]
        remediated = [t for t in tests if t.remediated]

        return {
            "report_title": f"SOC 2 {period.report_type} Report — {period.name}",
            "report_type": period.report_type,
            "period": {
                "period_id": period.period_id,
                "name": period.name,
                "start_date": period.start_date,
                "end_date": period.end_date,
                "monitoring_days": period.monitoring_days,
                "status": period.status.value,
            },
            "system_description": period.system_description,
            "boundary_description": period.boundary_description,
            "auditor": {
                "name": period.auditor_name,
                "firm": period.audit_firm,
            },
            "trend_analysis": trends,
            "exceptions": [
                {
                    "test_id": e.test_id,
                    "control_id": e.control_id,
                    "test_date": e.test_date,
                    "exceptions_found": e.exceptions_found,
                    "exception_details": e.exception_details,
                    "remediated": e.remediated,
                }
                for e in exceptions
            ],
            "remediated_exceptions": [
                {
                    "test_id": r.test_id,
                    "control_id": r.control_id,
                    "remediation_date": r.remediation_date,
                }
                for r in remediated
            ],
            "subservice_organizations": [
                {
                    "name": s.name,
                    "services_provided": s.services_provided,
                    "reporting_method": s.reporting_method,
                    "has_soc_report": s.has_soc_report,
                }
                for s in subservices
            ],
            "summary": {
                "total_controls_tested": trends.get("total_controls_tested", 0),
                "overall_pass_rate_pct": trends.get("overall_pass_rate_pct", 0.0),
                "total_exceptions": len(exceptions),
                "remediated_exceptions": len(remediated),
                "subservices_count": len(subservices),
            },
            "generated_at": time.time(),
        }

    def generate_bridge_letter(self, from_period_id: str, to_period_id: str) -> dict[str, Any]:
        """Generate a bridge letter between two monitoring periods.

        Bridge letters cover the gap between the end of one Type II
        period and the issuance of the next report.
        """
        from_period = self._periods.get(from_period_id)
        to_period = self._periods.get(to_period_id)
        if not from_period or not to_period:
            return {"error": "One or both periods not found"}

        gap_days = int((to_period.start_date - from_period.end_date) / 86400)

        # Get relevant test results from the from-period
        from_results = self.get_test_results(period_id=from_period_id)

        return {
            "report_title": f"SOC 2 Bridge Letter — {from_period.name} → {to_period.name}",
            "from_period": {
                "name": from_period.name,
                "end_date": from_period.end_date,
            },
            "to_period": {
                "name": to_period.name,
                "start_date": to_period.start_date,
            },
            "bridge_period_days": gap_days,
            "controls_in_scope": len({r.control_id for r in from_results}),
            "material_changes_during_bridge": [],
            "opinion": "No events occurred during the bridge period that would materially affect the opinion.",
            "generated_at": time.time(),
        }

    # ── Persistence ────────────────────────────────────────

    def _persist_period(self, period: MonitoringPeriod) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT OR REPLACE INTO soc2_typeii_periods
               (period_id, name, description, start_date, end_date, status,
                auditor_name, audit_firm, monitoring_days, controls_tested,
                controls_passed, system_description, boundary_description,
                report_type, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (period.period_id, period.name, period.description,
             period.start_date, period.end_date, period.status.value,
             period.auditor_name, period.audit_firm, period.monitoring_days,
             period.controls_tested, period.controls_passed,
             period.system_description, period.boundary_description,
             period.report_type, period.created_at, period.completed_at),
        )
        self._conn.commit()

    def _persist_test_result(self, test: ControlTestResult) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT OR REPLACE INTO soc2_typeii_test_results
               (test_id, period_id, control_id, test_date, tester, result,
                sample_size, sample_selected, exceptions_found, exception_details,
                evidence_snapshot, methodology, notes, remediated,
                remediation_date, remediation_evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (test.test_id, test.period_id, test.control_id, test.test_date,
             test.tester, test.result.value, test.sample_size,
             json.dumps(test.sample_selected), test.exceptions_found,
             test.exception_details, test.evidence_snapshot,
             test.methodology.value, test.notes, int(test.remediated),
             test.remediation_date, test.remediation_evidence),
        )
        self._conn.commit()

    def _persist_subservice(self, sub: SubserviceOrganization) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT OR REPLACE INTO soc2_typeii_subservices
               (subservice_id, name, description, services_provided,
                reporting_method, has_soc_report, soc_report_date,
                relevant_controls, cuce_controls, contact_info)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sub.subservice_id, sub.name, sub.description,
             sub.services_provided, sub.reporting_method,
             int(sub.has_soc_report), sub.soc_report_date,
             json.dumps(sub.relevant_controls),
             json.dumps(sub.cuce_controls), sub.contact_info),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None
