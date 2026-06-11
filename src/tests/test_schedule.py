"""
Workflow Determinista — Tests del ScheduleWorker
Tests unitarios para el worker de cron: threading.Timer, parseo de expresiones cron.
"""

from datetime import datetime

import pytest


class TestScheduleWorker:
    """Tests para la clase ScheduleWorker."""

    def test_schedule_worker_starts_and_stops(self, db_manager):
        """Test: ScheduleWorker inicia y se detiene correctamente."""
        from src.events.bus import EventBus
        from src.events.schedule_worker import ScheduleWorker

        EventBus._instance = None
        worker = ScheduleWorker(interval=5)
        worker.start()
        assert worker.is_running() is True

        worker.stop()
        assert worker.is_running() is False
        EventBus._instance = None

    def test_uses_threading_timer(self):
        """Test: ScheduleWorker usa threading.Timer (spec: NO APScheduler)."""
        import inspect

        from src.events.schedule_worker import ScheduleWorker

        source = inspect.getsource(ScheduleWorker)
        assert "threading.Timer" in source
        # Exclude docstrings from APScheduler check to avoid false positives
        # (the docstring says "No usa APScheduler" which contains the word)
        lines = source.split("\n")
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            # Track triple-quoted docstrings
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            assert "APScheduler" not in line, f"Found 'APScheduler' in code: {line}"
            assert "apscheduler" not in line.lower(), f"Found 'apscheduler' in code: {line}"


class TestCronParser:
    """Tests para el parser de expresiones cron."""

    def test_parse_every_minute(self):
        """Test: * * * * * → cada minuto."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("* * * * *")
        assert 0 in result["minute"]
        assert 59 in result["minute"]
        assert 0 in result["hour"]
        assert 23 in result["hour"]

    def test_parse_specific_time(self):
        """Test: 30 9 * * * → a las 9:30 cada día."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("30 9 * * *")
        assert result["minute"] == [30]
        assert result["hour"] == [9]

    def test_parse_range(self):
        """Test: 0 9-17 * * * → cada hora de 9 a 17."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("0 9-17 * * *")
        assert result["hour"] == [9, 10, 11, 12, 13, 14, 15, 16, 17]

    def test_parse_step(self):
        """Test: */15 * * * * → cada 15 minutos."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("*/15 * * * *")
        assert 0 in result["minute"]
        assert 15 in result["minute"]
        assert 30 in result["minute"]
        assert 45 in result["minute"]

    def test_parse_comma_separated(self):
        """Test: 0 9,12,18 * * * → a las 9, 12 y 18."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("0 9,12,18 * * *")
        assert result["hour"] == [9, 12, 18]

    def test_parse_day_of_week(self):
        """Test: 0 9 * * 1 → cada lunes a las 9."""
        from src.utils.helpers import parse_cron_expression

        result = parse_cron_expression("0 9 * * 1")
        assert result["day_of_week"] == [1]

    def test_invalid_cron_raises(self):
        """Test: expresión cron inválida lanza ValueError."""
        from src.utils.helpers import parse_cron_expression

        with pytest.raises(ValueError):
            parse_cron_expression("invalid")

    def test_should_run_now_specific_time(self):
        """Test: should_run_now coincide con la hora actual."""
        from src.utils.helpers import parse_cron_expression, should_run_now

        now = datetime(2026, 6, 7, 9, 30, 0)  # 9:30 AM
        cron = parse_cron_expression("30 9 * * *")
        assert should_run_now(cron, now) is True

        cron_no_match = parse_cron_expression("45 10 * * *")
        assert should_run_now(cron_no_match, now) is False

    def test_should_run_now_every_minute(self):
        """Test: * * * * * siempre coincide."""
        from src.utils.helpers import parse_cron_expression, should_run_now

        now = datetime(2026, 6, 7, 14, 22, 0)
        cron = parse_cron_expression("* * * * *")
        assert should_run_now(cron, now) is True

    def test_schedule_interval_60_seconds(self):
        """Test: SCHEDULE_INTERVAL_SECONDS es 60 (spec requirement)."""
        from src.config import SCHEDULE_INTERVAL_SECONDS

        assert SCHEDULE_INTERVAL_SECONDS == 60
