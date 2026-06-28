"""SOC 2 Type II — Tests for monitoring periods, control testing, and reporting."""

from __future__ import annotations

import time

import pytest

from src.compliance.soc2_type_ii import (
    ControlFrequency,
    MonitoringPeriod,
    MonitoringPeriodStatus,
    SamplingMethodology,
    SOC2TypeIIManager,
    SubserviceOrganization,
    TestResultStatus,
    recommend_sample_size,
)


@pytest.fixture
def type_ii_manager(tmp_path):
    """SOC2TypeIIManager with temp database."""
    db_path = tmp_path / "test_compliance.db"
    manager = SOC2TypeIIManager(str(db_path))
    yield manager
    SOC2TypeIIManager.reset_instance()


class TestMonitoringPeriod:
    """Tests for monitoring period lifecycle."""

    def test_create_period(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="SOC 2 Type II 2026",
            start_date=time.time(),
            end_date=time.time() + (180 * 86400),
            description="Annual Type II report",
            auditor_name="Ernst & Young",
            audit_firm="EY",
        )
        assert period.name == "SOC 2 Type II 2026"
        assert period.monitoring_days == 180
        assert period.status == MonitoringPeriodStatus.PLANNED
        assert period.auditor_name == "Ernst & Young"
        assert period.audit_firm == "EY"

    def test_activate_period(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        assert type_ii_manager.activate_period(period.period_id) is True
        p = type_ii_manager.get_period(period.period_id)
        assert p.status == MonitoringPeriodStatus.ACTIVE

    def test_activate_non_planned_fails(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)
        # Cannot activate again
        assert type_ii_manager.activate_period(period.period_id) is False

    def test_complete_period(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)
        assert type_ii_manager.complete_period(period.period_id) is True
        p = type_ii_manager.get_period(period.period_id)
        assert p.status == MonitoringPeriodStatus.COMPLETED
        assert p.completed_at > 0

    def test_list_periods(self, type_ii_manager):
        type_ii_manager.create_monitoring_period("P1", time.time(), time.time() + 86400)
        type_ii_manager.create_monitoring_period("P2", time.time(), time.time() + 86400)
        assert len(type_ii_manager.list_periods()) == 2

    def test_list_periods_filter_status(self, type_ii_manager):
        p1 = type_ii_manager.create_monitoring_period("P1", time.time(), time.time() + 86400)
        type_ii_manager.create_monitoring_period("P2", time.time(), time.time() + 86400)
        type_ii_manager.activate_period(p1.period_id)
        active = type_ii_manager.list_periods(status=MonitoringPeriodStatus.ACTIVE)
        assert len(active) == 1
        planned = type_ii_manager.list_periods(status=MonitoringPeriodStatus.PLANNED)
        assert len(planned) == 1

    def test_monitoring_days_auto_calculated(self):
        start = time.time()
        end = start + (90 * 86400)
        period = MonitoringPeriod(name="90 days", start_date=start, end_date=end)
        assert period.monitoring_days == 90


class TestControlTesting:
    """Tests for control test result recording and remediation."""

    def test_record_test_result(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)
        result = type_ii_manager.record_test_result(
            period_id=period.period_id,
            control_id="ctrl-test-record",
            result=TestResultStatus.PASS,
            sample_size=10,
        )
        assert result is not None
        assert result.control_id == "ctrl-test-record"
        assert result.result == TestResultStatus.PASS

    def test_record_test_result_flow(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)

        result = type_ii_manager.record_test_result(
            period_id=period.period_id,
            control_id="ctrl-access-control",
            result=TestResultStatus.PASS,
            tester="auditor@example.com",
            sample_size=25,
            methodology=SamplingMethodology.RANDOM,
        )
        assert result is not None
        assert result.control_id == "ctrl-access-control"
        assert result.result == TestResultStatus.PASS
        assert result.sample_size == 25

    def test_record_fail_and_remediate(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)

        test = type_ii_manager.record_test_result(
            period_id=period.period_id,
            control_id="ctrl-encryption",
            result=TestResultStatus.FAIL,
            exceptions_found=2,
            exception_details="Two users had weak passwords",
        )
        assert test is not None
        assert test.exceptions_found == 2

        remediated = type_ii_manager.remediate_exception(
            test_id=test.test_id,
            remediation_evidence="Password reset completed for both users on 2026-01-15",
        )
        assert remediated is True

        # Verify remediation
        tests = type_ii_manager.get_test_results(control_id="ctrl-encryption")
        assert len(tests) == 1
        assert tests[0].remediated is True
        assert tests[0].result == TestResultStatus.REMEDIATED

    def test_record_on_inactive_period_fails(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        # Period is PLANNED, not ACTIVE
        result = type_ii_manager.record_test_result(
            period_id=period.period_id, control_id="ctrl-test", result=TestResultStatus.PASS,
        )
        assert result is None

    def test_remediate_nonexistent_fails(self, type_ii_manager):
        assert type_ii_manager.remediate_exception("nonexistent", "evidence") is False

    def test_remediate_non_fail_fails(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)
        test = type_ii_manager.record_test_result(
            period_id=period.period_id, control_id="ctrl-test",
            result=TestResultStatus.PASS,
        )
        assert test is not None
        assert type_ii_manager.remediate_exception(test.test_id, "evidence") is False

    def test_get_test_results_filter(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)
        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.PASS)
        type_ii_manager.record_test_result(period.period_id, "ctrl-2", TestResultStatus.FAIL)

        all_tests = type_ii_manager.get_test_results(period_id=period.period_id)
        assert len(all_tests) == 2

        fails = type_ii_manager.get_test_results(result=TestResultStatus.FAIL)
        assert len(fails) == 1


class TestSampleSizing:
    """Tests for AICPA sample size recommendations."""

    def test_recommend_daily_low_risk(self):
        size = recommend_sample_size(ControlFrequency.DAILY, 1000, "low")
        assert size <= 1000
        assert size > 0

    def test_recommend_daily_high_risk(self):
        low = recommend_sample_size(ControlFrequency.DAILY, 1000, "low")
        high = recommend_sample_size(ControlFrequency.DAILY, 1000, "high")
        assert high >= low  # High risk should have larger sample

    def test_recommend_sample_weekly(self):
        size = recommend_sample_size(ControlFrequency.WEEKLY, 100, "medium")
        assert 5 <= size <= 100

    def test_recommend_sample_continuous(self):
        size = recommend_sample_size(ControlFrequency.CONTINUOUS, 10000, "critical")
        assert size == 1  # Continuous/automated controls need 1 sample

    def test_recommend_respects_population(self):
        size = recommend_sample_size(ControlFrequency.DAILY, 5, "critical")
        assert size <= 5  # Should not exceed population

    def test_recommend_per_transaction(self):
        size = recommend_sample_size(ControlFrequency.PER_TRANSACTION, 10000, "medium")
        assert 5 <= size <= 10000

    def test_recommend_annual(self):
        size = recommend_sample_size(ControlFrequency.ANNUALLY, 2, "high")
        assert size <= 2


class TestTrendAnalysis:
    """Tests for trend analysis across test results."""

    def test_analyze_no_data(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        trends = type_ii_manager.analyze_trends(period.period_id)
        assert "error" in trends

    def test_analyze_improving_trend(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)

        # First test fails
        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.FAIL)
        # After a pause, second test passes
        time.sleep(0.001)
        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.PASS)

        trends = type_ii_manager.analyze_trends(period.period_id)
        assert trends["total_controls_tested"] == 1
        assert trends["overall_pass_rate_pct"] == 50.0

    def test_analyze_multiple_controls(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="Test", start_date=time.time(), end_date=time.time() + 86400
        )
        type_ii_manager.activate_period(period.period_id)

        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.PASS)
        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.PASS)
        type_ii_manager.record_test_result(period.period_id, "ctrl-2", TestResultStatus.FAIL)

        trends = type_ii_manager.analyze_trends(period.period_id)
        assert trends["total_controls_tested"] == 2
        assert trends["total_tests"] == 3
        assert trends["total_fails"] == 1


class TestReporting:
    """Tests for Type II report generation."""

    def test_generate_report_nonexistent(self, type_ii_manager):
        report = type_ii_manager.generate_type_ii_report("nonexistent")
        assert "error" in report

    def test_generate_report(self, type_ii_manager):
        period = type_ii_manager.create_monitoring_period(
            name="SOC 2 Type II 2026", start_date=time.time(), end_date=time.time() + 86400,
            system_description="Cloud workflow automation platform",
            boundary_description="All production systems in us-east-1",
        )
        type_ii_manager.activate_period(period.period_id)

        type_ii_manager.record_test_result(period.period_id, "ctrl-1", TestResultStatus.PASS)
        type_ii_manager.record_test_result(period.period_id, "ctrl-2", TestResultStatus.PASS)
        type_ii_manager.record_test_result(period.period_id, "ctrl-3", TestResultStatus.FAIL)

        report = type_ii_manager.generate_type_ii_report(period.period_id)
        assert report["report_title"] == "SOC 2 Type II Report — SOC 2 Type II 2026"
        assert report["period"]["name"] == "SOC 2 Type II 2026"
        assert len(report["exceptions"]) == 1
        assert report["summary"]["total_controls_tested"] == 3
        assert "trend_analysis" in report

    def test_generate_bridge_letter(self, type_ii_manager):
        p1 = type_ii_manager.create_monitoring_period(
            "Period 1", time.time() - 86400, time.time(),
        )
        p2 = type_ii_manager.create_monitoring_period(
            "Period 2", time.time() + 100, time.time() + 90000,
        )
        type_ii_manager.activate_period(p1.period_id)
        type_ii_manager.record_test_result(p1.period_id, "ctrl-1", TestResultStatus.PASS)

        bridge = type_ii_manager.generate_bridge_letter(p1.period_id, p2.period_id)
        assert "Bridge Letter" in bridge["report_title"]
        assert bridge["controls_in_scope"] == 1

    def test_bridge_letter_missing_period(self, type_ii_manager):
        p1 = type_ii_manager.create_monitoring_period(
            "P1", time.time(), time.time() + 86400,
        )
        bridge = type_ii_manager.generate_bridge_letter(p1.period_id, "nonexistent")
        assert "error" in bridge


class TestSubserviceOrganizations:
    """Tests for subservice organization management."""

    def test_add_subservice(self, type_ii_manager):
        sub = SubserviceOrganization(
            name="AWS",
            description="AWS cloud infrastructure (us-east-1)",
            services_provided="Compute, storage, networking",
            reporting_method="carve_out",
            has_soc_report=True,
            soc_report_date="2025-12-31",
            contact_info="audit@aws.com",
        )
        sub_id = type_ii_manager.add_subservice(sub)
        assert sub_id is not None

    def test_list_subservices(self, type_ii_manager):
        sub1 = SubserviceOrganization(name="AWS", services_provided="Cloud")
        sub2 = SubserviceOrganization(name="Azure", services_provided="Cloud")

        type_ii_manager.add_subservice(sub1)
        type_ii_manager.add_subservice(sub2)

        subs = type_ii_manager.list_subservices()
        assert len(subs) == 2
        assert subs[0].name in ("AWS", "Azure")


class TestSingleton:
    """Tests for SOC2TypeIIManager singleton pattern."""

    def test_singleton(self):
        m1 = SOC2TypeIIManager.get_instance()
        m2 = SOC2TypeIIManager.get_instance()
        assert m1 is m2
        SOC2TypeIIManager.reset_instance()

    def test_reset(self):
        SOC2TypeIIManager.reset_instance()
        m1 = SOC2TypeIIManager.get_instance()
        SOC2TypeIIManager.reset_instance()
        m2 = SOC2TypeIIManager.get_instance()
        assert m1 is not m2
