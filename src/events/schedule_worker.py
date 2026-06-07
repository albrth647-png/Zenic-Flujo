"""
Workflow Determinista — ScheduleWorker
Worker que revisa cada 60s si hay workflows programados para ejecutarse.
Usa threading.Timer recursivo. Sin APScheduler. Zero dependencias externas.
"""
import threading
import time
from datetime import datetime
from typing import Any

from src.events.bus import EventBus
from src.workflow.repository import WorkflowRepository
from src.utils.helpers import parse_cron_expression, should_run_now
from src.utils.logger import setup_logging
from src.config import SCHEDULE_INTERVAL_SECONDS

logger = setup_logging(__name__)


class ScheduleWorker:
    """
    Worker que revisa periódicamente si hay workflows programados para ejecutar.
    
    No usa APScheduler. Usa threading.Timer recursivo.
    """

    def __init__(self, interval: int = SCHEDULE_INTERVAL_SECONDS):
        self._interval = interval
        self._timer: threading.Timer | None = None
        self._running = False
        self._repository = WorkflowRepository()
        self._event_bus = EventBus()

    def start(self) -> None:
        """Inicia el worker."""
        self._running = True
        self._schedule_next()
        logger.info(f"ScheduleWorker iniciado (intervalo: {self._interval}s)")

    def stop(self) -> None:
        """Detiene el worker."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("ScheduleWorker detenido")

    def is_running(self) -> bool:
        return self._running

    def _schedule_next(self) -> None:
        """Programa la siguiente ejecución del tick."""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """Revisa y ejecuta workflows programados para este minuto."""
        try:
            now = datetime.now()
            workflows = self._repository.get_active_scheduled()

            executed = 0
            for wf in workflows:
                try:
                    cron_expr = wf.trigger_config.get("cron", "")
                    if not cron_expr:
                        continue

                    cron_fields = parse_cron_expression(cron_expr)

                    if should_run_now(cron_fields, now):
                        logger.info(f"Ejecutando workflow programado: {wf.name} (ID: {wf.id})")
                        self._event_bus.publish("schedule.triggered", {
                            "workflow_id": wf.id,
                            "scheduled_time": now.isoformat(),
                        })
                        executed += 1

                except Exception as wf_error:
                    logger.error(f"Error procesando workflow programado {wf.id}: {wf_error}")

            if executed > 0:
                logger.info(f"ScheduleWorker: {executed} workflow(s) ejecutado(s)")

        except Exception as e:
            logger.error(f"Error en ScheduleWorker tick: {e}")

        finally:
            self._schedule_next()
