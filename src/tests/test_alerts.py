"""
Tests del AlertService (Sprint 11 — Monitoreo + Alertas).

Cubre:
- Evaluación de reglas (cada operador: gt, lt, gte, lte, eq).
- Cooldown: no re-dispara la misma alerta constantemente.
- Persistencia: list, count, resolve, stats.
- Registro de providers de métricas.
- Reglas por defecto (DEFAULT_RULES).
- Notificadores (con mocks para no enviar emails/slack reales).
"""
from __future__ import annotations

import pytest

from src.observability.alerts import (
    DEFAULT_RULES,
    AlertEvent,
    AlertRule,
    AlertService,
    EmailNotifier,
    Notifier,
    SlackNotifier,
    WebhookNotifier,
)


@pytest.fixture
def alert_service(db_manager) -> AlertService:
    """AlertService aislado por test."""
    service = AlertService(db=db_manager)
    # Limpiar alertas de tests anteriores si las hay
    db_manager.execute("DELETE FROM alert_events")
    db_manager.commit()
    return service


class TestAlertRuleEvaluation:
    """Tests de evaluación de reglas (operadores de comparación)."""

    @pytest.mark.parametrize(
        "comparison,threshold,value,expected",
        [
            ("gt", 10, 15, True),    # 15 > 10
            ("gt", 10, 5, False),    # 5 > 10
            ("gt", 10, 10, False),   # 10 > 10 (estricto)
            ("lt", 10, 5, True),     # 5 < 10
            ("lt", 10, 15, False),
            ("gte", 10, 10, True),   # 10 >= 10
            ("gte", 10, 9, False),
            ("lte", 10, 10, True),   # 10 <= 10
            ("lte", 10, 11, False),
            ("eq", 10, 10, True),
            ("eq", 10, 11, False),
        ],
    )
    def test_comparison_operators(self, comparison, threshold, value, expected):
        rule = AlertRule(
            name="test",
            metric_name="m",
            threshold=threshold,
            comparison=comparison,
        )
        assert rule.evaluate(value) is expected

    def test_unknown_comparison_defaults_to_false(self):
        rule = AlertRule(name="x", metric_name="m", threshold=0, comparison="invalid_op")
        assert rule.evaluate(999) is False


class TestAlertServiceEvaluation:
    """Tests de evaluación de reglas con providers registrados."""

    def test_evaluate_rule_no_provider_returns_none(
        self, alert_service: AlertService
    ):
        rule = AlertRule(name="x", metric_name="missing_metric", threshold=0)
        assert alert_service.evaluate_rule(rule) is None

    def test_evaluate_rule_provider_exception_returns_none(
        self, alert_service: AlertService
    ):
        def bad_provider() -> float:
            raise RuntimeError("boom")

        alert_service.register_metric_provider("bad_metric", bad_provider)
        rule = AlertRule(name="x", metric_name="bad_metric", threshold=0)
        assert alert_service.evaluate_rule(rule) is None

    def test_evaluate_rule_violated_creates_event(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high",
            metric_name="cpu",
            threshold=90.0,
            comparison="gt",
            channels=[],  # sin notificadores para no enviar nada real
        )

        event = alert_service.evaluate_rule(rule)
        assert event is not None
        assert event.rule_name == "cpu_high"
        assert event.metric_value == 95.0
        assert event.threshold == 90.0
        assert event.status == "active"
        assert event.id is not None

    def test_evaluate_rule_not_violated_returns_none(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 50.0)
        rule = AlertRule(
            name="cpu_high", metric_name="cpu", threshold=90.0, comparison="gt", channels=[],
        )
        assert alert_service.evaluate_rule(rule) is None

    def test_cooldown_prevents_redispatch(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high",
            metric_name="cpu",
            threshold=90.0,
            comparison="gt",
            cooldown_seconds=3600,  # 1h cooldown
            channels=[],
        )

        # Primera evaluación: dispara
        event1 = alert_service.evaluate_rule(rule)
        assert event1 is not None

        # Segunda evaluación inmediata: cooldown activo, no dispara
        event2 = alert_service.evaluate_rule(rule)
        assert event2 is None

    def test_evaluate_all_rules_returns_only_triggered(
        self, alert_service: AlertService
    ):
        # Provider para una sola de las 4 reglas por defecto
        alert_service.register_metric_provider("workflow_failure_rate_1h", lambda: 0.5)
        # Las demás reglas no tienen provider → se omiten

        triggered = alert_service.evaluate_all_rules()
        # Solo la regla workflow_failure_rate_high debe disparar
        assert len(triggered) == 1
        assert triggered[0].rule_name == "workflow_failure_rate_high"


class TestAlertPersistence:
    """Tests de persistencia de alertas."""

    def test_list_alerts_returns_most_recent_first(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high", metric_name="cpu", threshold=90.0,
            comparison="gt", cooldown_seconds=0, channels=[],
        )

        # Disparar 3 veces (cooldown=0 permite redisparo)
        for _ in range(3):
            alert_service.evaluate_rule(rule)

        alerts = alert_service.list_alerts()
        assert len(alerts) == 3
        # Ordenadas por created_at DESC, id DESC
        assert alerts[0].id is not None
        assert alerts[0].id > alerts[-1].id  # más reciente primero

    def test_list_alerts_filter_by_status(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high", metric_name="cpu", threshold=90.0,
            comparison="gt", cooldown_seconds=0, channels=[],
        )

        # Disparar 2
        e1 = alert_service.evaluate_rule(rule)
        e2 = alert_service.evaluate_rule(rule)

        # Resolver la primera
        alert_service.resolve_alert(e1.id)  # type: ignore[arg-type]

        active = alert_service.list_alerts(status="active")
        resolved = alert_service.list_alerts(status="resolved")
        assert len(active) == 1
        assert len(resolved) == 1
        assert active[0].id == e2.id
        assert resolved[0].id == e1.id

    def test_resolve_alert_returns_false_if_not_found(
        self, alert_service: AlertService
    ):
        assert alert_service.resolve_alert(99999) is False

    def test_resolve_already_resolved_returns_false(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high", metric_name="cpu", threshold=90.0,
            comparison="gt", cooldown_seconds=0, channels=[],
        )
        event = alert_service.evaluate_rule(rule)
        assert event is not None

        assert alert_service.resolve_alert(event.id) is True
        # Segunda resolución debe fallar
        assert alert_service.resolve_alert(event.id) is False

    def test_count_alerts_total_and_by_status(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        rule = AlertRule(
            name="cpu_high", metric_name="cpu", threshold=90.0,
            comparison="gt", cooldown_seconds=0, channels=[],
        )

        e1 = alert_service.evaluate_rule(rule)
        alert_service.evaluate_rule(rule)
        alert_service.resolve_alert(e1.id)  # type: ignore[arg-type]

        assert alert_service.count_alerts() == 2
        assert alert_service.count_alerts(status="active") == 1
        assert alert_service.count_alerts(status="resolved") == 1

    def test_get_alert_stats_aggregates_by_severity(
        self, alert_service: AlertService
    ):
        alert_service.register_metric_provider("cpu", lambda: 95.0)
        alert_service.register_metric_provider("mem", lambda: 5.0)

        rules = [
            AlertRule(
                name="cpu_high", metric_name="cpu", threshold=90.0,
                comparison="gt", cooldown_seconds=0, severity="critical", channels=[],
            ),
            AlertRule(
                name="mem_low", metric_name="mem", threshold=10.0,
                comparison="lt", cooldown_seconds=0, severity="warning", channels=[],
            ),
        ]

        for rule in rules:
            alert_service.evaluate_rule(rule)

        stats = alert_service.get_alert_stats()
        assert stats["total_active"] == 2
        assert stats["total_resolved"] == 0
        assert stats["rules_count"] == len(DEFAULT_RULES)  # DEFAULT_RULES siempre se cuentan
        assert "critical" in stats["by_severity"]
        assert "warning" in stats["by_severity"]
        assert stats["by_severity"]["critical"]["active"] == 1
        assert stats["by_severity"]["warning"]["active"] == 1


class TestDefaultRules:
    """Tests de las reglas por defecto del Sprint 11."""

    def test_default_rules_count(self):
        assert len(DEFAULT_RULES) == 4

    def test_default_rules_have_unique_names(self):
        names = [r.name for r in DEFAULT_RULES]
        assert len(names) == len(set(names))

    def test_default_rules_have_valid_channels(self):
        valid_channels = {"email", "slack", "webhook"}
        for rule in DEFAULT_RULES:
            assert len(rule.channels) > 0
            for ch in rule.channels:
                assert ch in valid_channels, f"Invalid channel: {ch}"

    def test_default_rules_have_valid_severity(self):
        valid_severities = {"info", "warning", "critical"}
        for rule in DEFAULT_RULES:
            assert rule.severity in valid_severities

    def test_get_active_rules_returns_enabled_only(self, alert_service: AlertService):
        rules = alert_service.get_active_rules()
        for r in rules:
            assert r.enabled is True

    def test_workflow_failure_rate_rule_definition(self):
        rule = next(r for r in DEFAULT_RULES if r.name == "workflow_failure_rate_high")
        assert rule.metric_name == "workflow_failure_rate_1h"
        assert rule.threshold == 0.3
        assert rule.comparison == "gt"
        assert rule.severity == "critical"

    def test_dead_letter_queue_rule_definition(self):
        rule = next(r for r in DEFAULT_RULES if r.name == "dead_letter_queue_depth_high")
        assert rule.threshold == 50
        assert rule.severity == "warning"

    def test_worker_pool_rule_definition(self):
        rule = next(r for r in DEFAULT_RULES if r.name == "worker_pool_depleted")
        assert rule.threshold == 2
        assert rule.comparison == "lt"
        assert rule.severity == "critical"


class TestNotifiers:
    """Tests de los notificadores (con verificación de configuración)."""

    def test_email_notifier_returns_false_if_not_configured(
        self, db_manager
    ):
        notifier = EmailNotifier(db_manager)
        # Sin SMTP configurado, debe retornar False y no levantar excepción
        event = AlertEvent(rule_name="test", message="test")
        rule = AlertRule(name="test", channels=["email"])
        result = notifier.send(event, rule)
        assert result is False

    def test_slack_notifier_returns_false_if_not_configured(
        self, db_manager
    ):
        notifier = SlackNotifier(db_manager)
        event = AlertEvent(rule_name="test", message="test")
        rule = AlertRule(name="test", channels=["slack"])
        result = notifier.send(event, rule)
        assert result is False

    def test_webhook_notifier_returns_false_if_not_configured(
        self, db_manager
    ):
        notifier = WebhookNotifier(db_manager)
        event = AlertEvent(rule_name="test", message="test")
        rule = AlertRule(name="test", channels=["webhook"])
        result = notifier.send(event, rule)
        assert result is False

    def test_notifier_interface_raises_not_implemented(self):
        notifier = Notifier()
        event = AlertEvent(rule_name="x", message="y")
        rule = AlertRule(name="x")
        with pytest.raises(NotImplementedError):
            notifier.send(event, rule)


class TestAlertEventSerialization:
    """Tests de serialización de AlertEvent."""

    def test_to_dict_roundtrip(self):
        event = AlertEvent(
            id=42,
            rule_name="cpu_high",
            severity="critical",
            metric_value=95.0,
            threshold=90.0,
            message="CPU is high",
            channels_notified=["email", "slack"],
            created_at="2026-06-17T10:00:00",
            status="active",
        )
        d = event.to_dict()
        assert d["id"] == 42
        assert d["rule_name"] == "cpu_high"
        assert d["severity"] == "critical"
        assert d["metric_value"] == 95.0
        assert d["channels_notified"] == ["email", "slack"]
        assert d["status"] == "active"
        assert d["resolved_at"] is None
