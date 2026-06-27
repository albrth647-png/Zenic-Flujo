"""
Sprint 11 — AlertService: monitorea métricas y dispara alertas.

Diseño:
- Reglas declarativas (AlertRule) que evalúan métricas periódicamente.
- Canales de notificación plugables (email, slack, webhook).
- Estado persistente en SQLite para no re-disparar alertas ya activas.
- Thread daemon opcional que evalúa reglas cada N segundos.

Cobertura inicial:
- Workflow failure rate (job_failure_rate > 0.3 en ventana 1h)
- Dead letter queue depth (queue_depth > 50)
- Worker pool health (workers_alive < 2)
- Throughput degradado (workflows_per_minute < 5 sostenido 5 min)

Las reglas son configurables vía DB (tabla alert_rules) para que los admin
puedan activar/desactivar sin redeploy.
"""
from __future__ import annotations

import json
import smtplib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.utils import now_iso

logger = setup_logging(__name__)


# ─── Constantes ──────────────────────────────────────────────────────────

DEFAULT_EVAL_INTERVAL_SECONDS = 60
"""Intervalo por defecto entre evaluaciones de reglas (1 minuto)."""

DEFAULT_ALERT_COOLDOWN_SECONDS = 300
"""Cooldown para no re-disparar la misma alerta constantemente (5 min)."""


# ─── Excepciones ─────────────────────────────────────────────────────────


class AlertError(Exception):
    """Error base del módulo de alertas."""


# ─── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class AlertRule:
    """
    Definición declarativa de una regla de alerta.

    Atributos:
        name: identificador único de la regla.
        description: descripción legible para UI.
        metric_name: nombre de la métrica a evaluar.
        threshold: valor umbral.
        comparison: operador de comparación ('gt', 'lt', 'gte', 'lte', 'eq').
        window_seconds: ventana de tiempo para aggregar (0 = instante).
        cooldown_seconds: tiempo mínimo entre disparos de la misma alerta.
        severity: 'info', 'warning', 'critical'.
        enabled: si la regla está activa.
        channels: lista de canales a notificar ('email', 'slack', 'webhook').
    """

    name: str
    description: str = ""
    metric_name: str = ""
    threshold: float = 0.0
    comparison: str = "gt"  # gt, lt, gte, lte, eq
    window_seconds: int = 0
    cooldown_seconds: int = DEFAULT_ALERT_COOLDOWN_SECONDS
    severity: str = "warning"
    enabled: bool = True
    channels: list[str] = field(default_factory=lambda: ["email"])

    def evaluate(self, current_value: float) -> bool:
        """Retorna True si el valor actual viola el umbral."""
        ops = {
            "gt": current_value > self.threshold,
            "lt": current_value < self.threshold,
            "gte": current_value >= self.threshold,
            "lte": current_value <= self.threshold,
            "eq": current_value == self.threshold,
        }
        return ops.get(self.comparison, False)


@dataclass
class AlertEvent:
    """Registro de una alerta disparada."""

    id: int | None = None
    rule_name: str = ""
    severity: str = "warning"
    metric_value: float = 0.0
    threshold: float = 0.0
    message: str = ""
    channels_notified: list[str] = field(default_factory=list[Any])
    created_at: str = ""
    resolved_at: str | None = None
    status: str = "active"  # active, resolved, suppressed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "message": self.message,
            "channels_notified": self.channels_notified,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "status": self.status,
        }


# ─── Reglas por defecto (Sprint 11) ──────────────────────────────────────

DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="workflow_failure_rate_high",
        description="Tasa de fallo de workflows > 30% en la última hora",
        metric_name="workflow_failure_rate_1h",
        threshold=0.3,
        comparison="gt",
        window_seconds=3600,
        cooldown_seconds=900,  # 15 min
        severity="critical",
        channels=["email", "slack"],
    ),
    AlertRule(
        name="dead_letter_queue_depth_high",
        description="Dead letter queue con más de 50 entradas pendientes",
        metric_name="dead_letter_queue_depth",
        threshold=50,
        comparison="gt",
        window_seconds=0,
        cooldown_seconds=300,
        severity="warning",
        channels=["email"],
    ),
    AlertRule(
        name="worker_pool_depleted",
        description="Menos de 2 workers vivos en el pool",
        metric_name="workers_alive",
        threshold=2,
        comparison="lt",
        window_seconds=0,
        cooldown_seconds=60,
        severity="critical",
        channels=["email", "slack"],
    ),
    AlertRule(
        name="queue_depth_high",
        description="Cola de workflows pendientes > 1000",
        metric_name="work_queue_depth",
        threshold=1000,
        comparison="gt",
        window_seconds=0,
        cooldown_seconds=300,
        severity="warning",
        channels=["slack", "webhook"],
    ),
]


# ─── Notificadores ───────────────────────────────────────────────────────


class Notifier:
    """Interfaz base para notificadores."""

    def send(self, alert: AlertEvent, rule: AlertRule) -> bool:
        raise NotImplementedError


class EmailNotifier(Notifier):
    """Envía alertas por email vía SMTP (configurado en settings)."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    def send(self, alert: AlertEvent, rule: AlertRule) -> bool:
        try:
            from src.core.repositories.settings_repository import SettingsRepository

            settings = SettingsRepository(self._db)
            smtp_host = settings.get_setting("smtp_host", "")
            smtp_port = settings.get_setting("smtp_port", 587)
            smtp_user = settings.get_setting("smtp_user", "")
            smtp_pass = settings.get_setting("smtp_password", "")
            from_email = settings.get_setting("smtp_from", smtp_user)
            admin_email = settings.get_setting("admin_email", "")

            if not smtp_host or not admin_email:
                logger.warning("EmailNotifier: SMTP no configurado, omitiendo alerta")
                return False

            subject = f"[Zenic-Flijo Alert][{alert.severity.upper()}] {rule.name}"
            body = (
                f"Alerta: {rule.description}\n\n"
                f"Regla: {rule.name}\n"
                f"Severidad: {alert.severity}\n"
                f"Métrica: {rule.metric_name} = {alert.metric_value}\n"
                f"Umbral: {rule.comparison} {alert.threshold}\n\n"
                f"Mensaje: {alert.message}\n"
                f"Timestamp: {alert.created_at}\n"
            )

            msg = (
                f"From: {from_email}\r\n"
                f"To: {admin_email}\r\n"
                f"Subject: {subject}\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\n"
                f"\r\n"
                f"{body}"
            )

            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                if int(smtp_port) == 587:
                    server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [admin_email], msg)

            logger.info(f"EmailNotifier: alerta {rule.name} enviada a {admin_email}")
            return True
        except Exception as exc:
            logger.error(f"EmailNotifier falló: {exc}")
            return False


class SlackNotifier(Notifier):
    """Envía alertas a Slack vía webhook URL configurada en settings."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    def send(self, alert: AlertEvent, rule: AlertRule) -> bool:
        try:
            from src.core.repositories.settings_repository import SettingsRepository

            settings = SettingsRepository(self._db)
            webhook_url = settings.get_setting("slack_webhook_url", "")
            if not webhook_url:
                logger.warning("SlackNotifier: webhook no configurado, omitiendo")
                return False

            severity_emoji = {
                "info": "ℹ️",  # noqa: RUF001
                "warning": "⚠️",
                "critical": "🚨",
            }.get(alert.severity, "⚠️")

            payload = {
                "text": f"{severity_emoji} *Alerta Zenic-Flijo*",
                "attachments": [
                    {
                        "color": {"info": "#36a64f", "warning": "#warning", "critical": "#ff0000"}.get(
                            alert.severity, "#cccccc"
                        ),
                        "fields": [
                            {"title": "Regla", "value": rule.name, "short": True},
                            {"title": "Severidad", "value": alert.severity, "short": True},
                            {
                                "title": "Métrica",
                                "value": f"{rule.metric_name} = {alert.metric_value}",
                                "short": True,
                            },
                            {
                                "title": "Umbral",
                                "value": f"{rule.comparison} {alert.threshold}",
                                "short": True,
                            },
                            {"title": "Mensaje", "value": alert.message, "short": False},
                        ],
                        "ts": int(time.time()),
                    }
                ],
            }

            req = Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    logger.error(f"SlackNotifier: HTTP {resp.status}")
                    return False

            logger.info(f"SlackNotifier: alerta {rule.name} enviada a Slack")
            return True
        except URLError as exc:
            logger.error(f"SlackNotifier URL error: {exc}")
            return False
        except Exception as exc:
            logger.error(f"SlackNotifier falló: {exc}")
            return False


class WebhookNotifier(Notifier):
    """Envía alertas a un webhook saliente configurable (JSON POST)."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    def send(self, alert: AlertEvent, rule: AlertRule) -> bool:
        try:
            from src.core.repositories.settings_repository import SettingsRepository

            settings = SettingsRepository(self._db)
            webhook_url = settings.get_setting("alert_webhook_url", "")
            if not webhook_url:
                logger.warning("WebhookNotifier: webhook no configurado, omitiendo")
                return False

            payload = {
                "alert": alert.to_dict(),
                "rule": {
                    "name": rule.name,
                    "description": rule.description,
                    "metric_name": rule.metric_name,
                    "threshold": rule.threshold,
                    "comparison": rule.comparison,
                    "severity": rule.severity,
                },
                "source": "zenic-flijo",
                "timestamp": now_iso(),
            }

            req = Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    logger.error(f"WebhookNotifier: HTTP {resp.status}")
                    return False

            logger.info(f"WebhookNotifier: alerta {rule.name} enviada a webhook")
            return True
        except Exception as exc:
            logger.error(f"WebhookNotifier falló: {exc}")
            return False


# ─── AlertService ────────────────────────────────────────────────────────


class AlertService:
    """
    Orquestador de alertas: evalúa reglas, dispara notificaciones, persiste estado.

    Uso:
        service = AlertService()
        service.start()  # arranca thread daemon que evalúa cada 60s
        # ... o manualmente:
        service.evaluate_all_rules()
    """

    def __init__(self, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager()
        self._notifiers: dict[str, Notifier] = {
            "email": EmailNotifier(self._db),
            "slack": SlackNotifier(self._db),
            "webhook": WebhookNotifier(self._db),
        }
        self._metric_providers: dict[str, Callable[[], float]] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._eval_interval = DEFAULT_EVAL_INTERVAL_SECONDS
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Crea la tabla alert_events si no existe (idempotente)."""
        # DatabaseManager.execute solo permite 1 statement por llamada.
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS alert_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name       TEXT NOT NULL,
                severity        TEXT NOT NULL,
                metric_value    REAL NOT NULL,
                threshold       REAL NOT NULL,
                message         TEXT DEFAULT '',
                channels_notified TEXT DEFAULT '[]',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at     TIMESTAMP,
                status          TEXT NOT NULL DEFAULT 'active'
            )"""
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_rule ON alert_events(rule_name)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_created ON alert_events(created_at)"
        )
        self._db.commit()

    # ── Registro de proveedores de métricas ────────────────────

    def register_metric_provider(self, metric_name: str, provider: Callable[[], float]) -> None:
        """
        Registra una función que retorna el valor actual de una métrica.
        El AlertService la invoca al evaluar reglas que usen esa métrica.
        """
        self._metric_providers[metric_name] = provider
        logger.debug(f"Métrica registrada: {metric_name}")

    # ── Reglas ─────────────────────────────────────────────────

    def get_default_rules(self) -> list[AlertRule]:
        """Retorna las reglas por defecto del Sprint 11."""
        return list[Any](DEFAULT_RULES)

    def get_active_rules(self) -> list[AlertRule]:
        """Retorna las reglas activas. Por ahora usa DEFAULT_RULES filtradas por enabled."""
        return [r for r in DEFAULT_RULES if r.enabled]

    # ── Evaluación ─────────────────────────────────────────────

    def evaluate_rule(self, rule: AlertRule) -> AlertEvent | None:
        """
        Evalúa una regla. Si se viola y no hay alerta activa en cooldown,
        dispara la alerta (crea registro + notifica).
        Retorna el AlertEvent creado, o None si no se disparó.
        """
        provider = self._metric_providers.get(rule.metric_name)
        if provider is None:
            logger.debug(f"Sin provider para métrica {rule.metric_name}, regla {rule.name} omitida")
            return None

        try:
            current_value = float(provider())
        except Exception as exc:
            logger.error(f"Provider de métrica {rule.metric_name} falló: {exc}")
            return None

        if not rule.evaluate(current_value):
            return None  # Regla no violada

        # Verificar cooldown: ¿hay una alerta activa reciente para esta regla?
        if self._has_recent_alert(rule.name, rule.cooldown_seconds):
            logger.debug(f"Alerta {rule.name} en cooldown, omitiendo")
            return None

        # Crear evento de alerta
        message = (
            f"Regla '{rule.name}' violada: "
            f"{rule.metric_name}={current_value} {rule.comparison} {rule.threshold}"
        )
        event = AlertEvent(
            rule_name=rule.name,
            severity=rule.severity,
            metric_value=current_value,
            threshold=rule.threshold,
            message=message,
            channels_notified=[],
            created_at=now_iso(),
            status="active",
        )

        # Notificar por los canales configurados
        notified_channels: list[str] = []
        for channel_name in rule.channels:
            notifier = self._notifiers.get(channel_name)
            if notifier is None:
                logger.warning(f"Canal desconocido: {channel_name}")
                continue
            try:
                if notifier.send(event, rule):
                    notified_channels.append(channel_name)
            except Exception as exc:
                logger.error(f"Notificador {channel_name} falló: {exc}")

        event.channels_notified = notified_channels

        # Persistir
        event.id = self._persist_alert(event)
        logger.info(
            f"Alerta disparada: {rule.name} (severity={rule.severity}, "
            f"value={current_value}, channels={notified_channels})"
        )
        return event

    def evaluate_all_rules(self) -> list[AlertEvent]:
        """Evalúa todas las reglas activas. Retorna la lista de alertas disparadas."""
        triggered: list[AlertEvent] = []
        for rule in self.get_active_rules():
            event = self.evaluate_rule(rule)
            if event is not None:
                triggered.append(event)
        return triggered

    # ── Persistencia ───────────────────────────────────────────

    def _persist_alert(self, event: AlertEvent) -> int:
        cursor = self._db.execute(
            """INSERT INTO alert_events
               (rule_name, severity, metric_value, threshold, message,
                channels_notified, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event.rule_name,
                event.severity,
                event.metric_value,
                event.threshold,
                event.message,
                json.dumps(event.channels_notified),
                event.status,
            ),
        )
        self._db.commit()
        return cursor.lastrowid or 0

    def _has_recent_alert(self, rule_name: str, cooldown_seconds: int) -> bool:
        """
        True si hay una alerta activa de esta regla dentro del cooldown.
        cooldown_seconds=0 significa sin cooldown (siempre permite redisparo).
        """
        if cooldown_seconds <= 0:
            return False  # sin cooldown

        row = self._db.fetchone(
            """SELECT COUNT(*) AS c FROM alert_events
               WHERE rule_name = ?
                 AND status = 'active'
                 AND datetime(created_at) >= datetime('now', ?)""",
            (rule_name, f"-{cooldown_seconds} seconds"),
        )
        return bool(row and row["c"] > 0)

    def list_alerts(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEvent]:
        """Lista alertas, opcionalmente filtradas por status."""
        if status:
            rows = self._db.fetchall(
                """SELECT * FROM alert_events
                   WHERE status = ?
                   ORDER BY created_at DESC, id DESC
                   LIMIT ? OFFSET ?""",
                (status, limit, offset),
            )
        else:
            rows = self._db.fetchall(
                """SELECT * FROM alert_events
                   ORDER BY created_at DESC, id DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        return [self._row_to_event(r) for r in rows]

    def resolve_alert(self, alert_id: int) -> bool:
        """Marca una alerta como resuelta."""
        cursor = self._db.execute(
            """UPDATE alert_events
               SET status = 'resolved', resolved_at = ?
               WHERE id = ? AND status = 'active'""",
            (now_iso(), alert_id),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def count_alerts(self, status: str | None = None) -> int:
        """Cuenta alertas, opcionalmente filtradas por status."""
        if status:
            row = self._db.fetchone(
                "SELECT COUNT(*) AS c FROM alert_events WHERE status = ?",
                (status,),
            )
        else:
            row = self._db.fetchone("SELECT COUNT(*) AS c FROM alert_events")
        return row["c"] if row else 0

    def get_alert_stats(self) -> dict[str, Any]:
        """Resumen agregado para dashboard."""
        rows = self._db.fetchall(
            """SELECT severity, status, COUNT(*) AS count
               FROM alert_events
               GROUP BY severity, status"""
        )
        stats: dict[str, dict[str, int]] = {}
        for r in rows:
            sev = r["severity"]
            if sev not in stats:
                stats[sev] = {"active": 0, "resolved": 0, "suppressed": 0}
            stats[sev][r["status"]] = r["count"]

        total_active = sum(s.get("active", 0) for s in stats.values())
        total_resolved = sum(s.get("resolved", 0) for s in stats.values())

        return {
            "by_severity": stats,
            "total_active": total_active,
            "total_resolved": total_resolved,
            "rules_count": len(self.get_active_rules()),
        }

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> AlertEvent:
        channels = row.get("channels_notified") or "[]"
        try:
            channels_list = json.loads(channels) if isinstance(channels, str) else channels
        except (json.JSONDecodeError, TypeError):
            channels_list = []
        return AlertEvent(
            id=row["id"],
            rule_name=row["rule_name"],
            severity=row["severity"],
            metric_value=row["metric_value"],
            threshold=row["threshold"],
            message=row.get("message") or "",
            channels_notified=channels_list if isinstance(channels_list, list[Any]) else [],
            created_at=row.get("created_at") or "",
            resolved_at=row.get("resolved_at"),
            status=row["status"],
        )

    # ── Thread daemon ──────────────────────────────────────────

    def start(self, eval_interval: int = DEFAULT_EVAL_INTERVAL_SECONDS) -> None:
        """Arranca un thread daemon que evalúa reglas periódicamente."""
        if self._thread and self._thread.is_alive():
            logger.warning("AlertService ya está corriendo")
            return

        self._eval_interval = max(10, eval_interval)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="AlertService", daemon=True
        )
        self._thread.start()
        logger.info(f"AlertService iniciado (evalúa cada {self._eval_interval}s)")

    def stop(self) -> None:
        """Detiene el thread daemon."""
        self._stop_event.set[Any]()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AlertService detenido")

    def _run_loop(self) -> None:
        """Loop principal del thread daemon."""
        while not self._stop_event.is_set():
            try:
                self.evaluate_all_rules()
            except Exception as exc:
                logger.error(f"AlertService loop error: {exc}")
            # Esperar interrumpiblemente
            self._stop_event.wait(self._eval_interval)
