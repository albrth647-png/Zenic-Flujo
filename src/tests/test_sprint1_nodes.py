"""
Tests para Sprint 1 del Roadmap Competitivo.
Cubre: Wait node, WaitUntil node, Schedule interval, APIConnector registration.
"""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from src.workflow.step_executor import StepExecutor


class TestWaitNode:
    """Tests para el nodo Wait (delay fijo)."""

    def test_wait_basic(self):
        """Wait con segundos básicos."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait",
            "params": {"seconds": 0.1},
        }
        t0 = time.time()
        result = executor.execute(step, {})
        elapsed = time.time() - t0
        assert result.status == "completed"
        assert result.output_data.get("waited_seconds") == 0  # int(0.1) = 0
        assert elapsed >= 0.09

    def test_wait_zero_seconds(self):
        """Wait con 0 segundos retorna inmediatamente."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait",
            "params": {"seconds": 0},
        }
        t0 = time.time()
        result = executor.execute(step, {})
        elapsed = time.time() - t0
        assert result.status == "completed"
        assert elapsed < 0.5  # Debe ser casi instantáneo

    def test_wait_caps_at_24h(self):
        """Wait no acepta más de 86400 segundos (24h) — verifica que no crashea."""
        with patch('time.sleep'):  # No hacer sleep real
            executor = StepExecutor()
            step = {
                "id": 1,
                "tool": "system",
                "action": "wait",
                "params": {"seconds": 999999},
            }
            result = executor.execute(step, {})
            assert result.status == "completed"
            assert result.output_data.get("waited_seconds") == 86400

    def test_wait_float_seconds(self):
        """Wait acepta float."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait",
            "params": {"seconds": 0.5},
        }
        t0 = time.time()
        result = executor.execute(step, {})
        elapsed = time.time() - t0
        assert result.status == "completed"
        assert 0.4 <= elapsed <= 2.0


class TestWaitUntilNode:
    """Tests para el nodo WaitUntil (fecha absoluta)."""

    def test_wait_until_already_passed(self):
        """WaitUntil con datetime ya pasado retorna inmediatamente."""
        executor = StepExecutor()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait_until",
            "params": {"datetime": past},
        }
        t0 = time.time()
        result = executor.execute(step, {})
        elapsed = time.time() - t0
        assert result.status == "completed"
        assert result.output_data.get("reason") == "already_passed"
        assert elapsed < 0.5

    def test_wait_until_with_z_suffix(self):
        """WaitUntil acepta formato ISO 8601 con sufijo Z."""
        executor = StepExecutor()
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait_until",
            "params": {"datetime": past},
        }
        result = executor.execute(step, {})
        assert result.status == "completed"

    def test_wait_until_no_datetime(self):
        """WaitUntil sin datetime retorna skip en output."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait_until",
            "params": {},
        }
        result = executor.execute(step, {})
        assert result.status == "completed"  # System actions sin error son completed
        assert result.output_data.get("reason") == "no_datetime"

    def test_wait_until_invalid_format(self):
        """WaitUntil con formato inválido retorna failed (el error se captura en el thread)."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "wait_until",
            "params": {"datetime": "not-a-date"},
        }
        result = executor.execute(step, {})
        assert result.status == "failed"
        assert "Formato datetime inválido" in (result.error_message or "")


class TestScheduleIntervalNode:
    """Tests para el nodo Schedule interval."""

    def test_schedule_interval_requires_workflow_id(self):
        """Schedule sin workflow_id falla."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "schedule_interval",
            "params": {"interval_minutes": 60},
        }
        result = executor.execute(step, {})
        assert result.status == "completed"
        assert result.output_data.get("reason") == "workflow_id required"

    def test_schedule_interval_with_workflow_id(self):
        """Schedule con workflow_id crea la configuración."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "schedule_interval",
            "params": {"interval_minutes": 30, "workflow_id": 42},
        }
        result = executor.execute(step, {})
        assert result.status == "completed"
        assert result.output_data.get("interval_minutes") == 30
        assert result.output_data.get("workflow_id") == 42
        assert result.output_data.get("status") == "scheduled"


class TestAPIConnectorRegistration:
    """Tests para verificar que APIConnectorService está registrado."""

    def test_api_connector_tool_definition(self):
        """APIConnectorService tiene definición de tool."""
        from src.tools.api_connector.service import APIConnectorService
        api = APIConnectorService()
        definition = api.get_tool_definition()
        assert definition["tool"] == "api_connector"
        assert "request" in definition["actions"]
        assert definition["actions"]["request"]["params"][0]["name"] == "method"

    def test_api_connector_validate_url(self):
        """Validación de URLs funciona."""
        from src.tools.api_connector.service import APIConnectorService
        assert APIConnectorService.validate_url("https://api.example.com") is True
        assert APIConnectorService.validate_url("http://localhost:8080/api") is True
        assert APIConnectorService.validate_url("") is False
        assert APIConnectorService.validate_url("file:///etc/passwd") is False
        assert APIConnectorService.validate_url("javascript:alert(1)") is False

    def test_api_connector_allowed_methods(self):
        """Solo métodos HTTP válidos."""
        from src.tools.api_connector.service import APIConnectorService
        api = APIConnectorService()
        for method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
            assert method in api.ALLOWED_METHODS
        assert "OPTIONS" not in api.ALLOWED_METHODS
        assert "HEAD" not in api.ALLOWED_METHODS
