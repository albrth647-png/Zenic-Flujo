"""
Workflow Determinista — ScheduleWorker
Worker que revisa cada 60s si hay workflows programados para ejecutarse.
Usa threading.Timer recursivo. Sin APScheduler. Zero dependencias externas.

Soporta:
- CRON expressions (5-field: minuto hora día-del-mes mes día-de-la-semana)
- Intervalos (cada X minutos configurado vía system steps)
- Timezone-aware (UTC por defecto, configurable)
"""
import sqlite3
import threading
from datetime import datetime
from src.data.database_manager import DatabaseManager
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
    Soporta CRON 5-field e intervalos por workflow.
    """

    def __init__(self, interval: int = SCHEDULE_INTERVAL_SECONDS):
        self._interval = interval
        self._timer: threading.Timer | None = None
        self._running = False
        self._repository = WorkflowRepository()
        self._event_bus = EventBus()
        self._db = DatabaseManager()
        self._lock = threading.RLock()
        # _interval_cache: workflow_id -> (last_run, interval_minutes)
        self._interval_cache: dict[int, tuple[datetime, int]] = {}

    def start(self) -> None:
        """Inicia el worker."""
        self._running = True
        self._load_intervals()
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

    def _load_intervals(self) -> None:
        """Carga los intervalos configurados desde la DB."""
        rows = self._db.fetchall(
            "SELECT key, value FROM settings WHERE key LIKE 'interval_%'"
        )
        for row in rows:
            try:
                wf_id = int(row["key"].replace("interval_", ""))
                minutes = int(row["value"])
                with self._lock:
                    self._interval_cache[wf_id] = (datetime.utcnow(), minutes)
                logger.info(f"Intervalo cargado: workflow {wf_id} cada {minutes}min")
            except (ValueError, KeyError):
                pass

    def _schedule_next(self) -> None:
        """Programa la siguiente ejecución del tick."""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _get_interval_minutes(self, workflow_id: int) -> int | None:
        """Obtiene los minutos de intervalo para un workflow."""
        val = self._db.get_setting(f"interval_{workflow_id}")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    def _tick(self) -> None:
        """Revisa y ejecuta workflows programados para este minuto.
        
        Soporta:
        - CRON expressions (5-field)
        - Intervalos configurables (cada X minutos desde settings)
        - Timezone UTC
        
        Refresca la caché de intervalos desde DB en cada tick para
        recoger nuevos intervalos creados por steps de workflow.
        """
        try:
            now = datetime.utcnow()

            # Refrescar caché de intervalos desde DB (recoge nuevos del step executor)
            self._load_intervals()

            # ── 1. CRON workflows ─────────────────────────────────
            workflows = self._repository.get_active_scheduled()
            executed = 0
            for wf in workflows:
                try:
                    cron_expr = wf.trigger_config.get("cron", "")
                    if not cron_expr:
                        continue

                    cron_fields = parse_cron_expression(cron_expr)

                    if should_run_now(cron_fields, now):
                        logger.info(f"[CRON] Ejecutando: {wf.name} (ID: {wf.id})")
                        self._event_bus.publish("schedule.triggered", {
                            "workflow_id": wf.id,
                            "scheduled_time": now.isoformat(),
                            "cron": cron_expr,
                        })
                        executed += 1

                except (ValueError, KeyError, TypeError) as wf_error:
                    logger.error(f"Error procesando workflow CRON {wf.id}: {wf_error}")

            # ── 2. Interval workflows ─────────────────────────────
            with self._lock:
                cache_snapshot = list(self._interval_cache.items())
            for wf_id, (last_run, interval_minutes) in cache_snapshot:
                elapsed = (now - last_run).total_seconds() / 60
                if elapsed >= interval_minutes:
                    wf = self._repository.get(wf_id)
                    if wf and wf.status == "active":
                        logger.info(f"[INTERVAL] Ejecutando: {wf.name} (ID: {wf.id}) cada {interval_minutes}min")
                        self._event_bus.publish("schedule.triggered", {
                            "workflow_id": wf_id,
                            "scheduled_time": now.isoformat(),
                            "interval_minutes": interval_minutes,
                        })
                        with self._lock:
                            self._interval_cache[wf_id] = (now, interval_minutes)
                        executed += 1

            if executed > 0:
                logger.info(f"ScheduleWorker: {executed} workflow(s) ejecutado(s)")

        except (OSError, ValueError, sqlite3.Error) as e:
            logger.error(f"Error en ScheduleWorker tick: {e}")

        finally:
            self._schedule_next()

    # ── API pública ────────────────────────────────────────────

    def register_interval(self, workflow_id: int, interval_minutes: int) -> None:
        """Registra un intervalo de ejecución para un workflow."""
        with self._lock:
            self._db.set_setting(f"interval_{workflow_id}", str(interval_minutes))
            self._interval_cache[workflow_id] = (datetime.utcnow(), interval_minutes)
            logger.info(f"Intervalo registrado: workflow {workflow_id} cada {interval_minutes}min")

    def unregister_interval(self, workflow_id: int) -> None:
        """Elimina el intervalo de un workflow."""
        with self._lock:
            self._db.set_setting(f"interval_{workflow_id}", "")
            self._interval_cache.pop(workflow_id, None)
            logger.info(f"Intervalo eliminado: workflow {workflow_id}")

    def _get_interval_minutes(self, workflow_id: int) -> int | None:
        """Obtiene los minutos de intervalo desde la caché."""
        with self._lock:
            entry = self._interval_cache.get(workflow_id)
            if entry:
                return entry[1]
        return None
