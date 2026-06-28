"""Push Notification Service — Firebase Cloud Messaging integration.

Sends push notifications to Android/iOS devices for:
- Workflow completion/failure
- Agent decisions requiring human input
- Budget alerts
- Compliance alerts
- Connector errors
- Daily summaries

Android Integration:
- FCM (Firebase Cloud Messaging) for push delivery
- Notification channels for categorization (Android 8+)
- BigTextStyle for workflow details
- Action buttons for quick responses (approve/reject)
- Deep links to specific screens

No root required — FCM uses Google Play Services which is
available on all certified Android devices.
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

from src.core.logging import get_logger

logger = get_logger("mobile.push")


class NotificationPriority(Enum):
    """FCM message priority levels."""

    NORMAL = "normal"
    HIGH = "high"


class NotificationCategory(Enum):
    """Android notification channel categories."""

    WORKFLOW = "workflow"
    AGENT = "agent"
    BUDGET = "budget"
    COMPLIANCE = "compliance"
    CONNECTOR = "connector"
    SYSTEM = "system"


@dataclass
class PushNotification:
    """A push notification to send to a mobile device."""

    notification_id: str = ""
    device_id: str = ""
    fcm_token: str = ""
    title: str = ""
    body: str = ""
    category: NotificationCategory = NotificationCategory.SYSTEM
    priority: NotificationPriority = NotificationPriority.NORMAL
    data: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, str]] = field(default_factory=list)
    deep_link: str = ""
    sound: str = "default"
    badge_count: int = 0
    created_at: float = field(default_factory=time.time)
    sent_at: float = 0.0
    delivered: bool = False

    def __post_init__(self) -> None:
        if not self.notification_id:
            self.notification_id = f"notif-{uuid.uuid4().hex[:8]}"


# ── Android Notification Channel Definitions ────────────────

NOTIFICATION_CHANNELS: dict[str, dict[str, Any]] = {
    "workflow": {
        "id": "zenic_workflow",
        "name": "Workflows",
        "description": "Notificaciones de ejecución de workflows",
        "importance": "HIGH",
        "sound": True,
        "vibration": True,
        "lights": True,
        "light_color": "#4CAF50",
    },
    "agent": {
        "id": "zenic_agent",
        "name": "Agentes IA",
        "description": "Decisiones y resultados de agentes",
        "importance": "HIGH",
        "sound": True,
        "vibration": True,
        "lights": True,
        "light_color": "#2196F3",
    },
    "budget": {
        "id": "zenic_budget",
        "name": "Presupuesto IA",
        "description": "Alertas de gasto y presupuesto",
        "importance": "URGENT",
        "sound": True,
        "vibration": True,
        "lights": True,
        "light_color": "#FF9800",
    },
    "compliance": {
        "id": "zenic_compliance",
        "name": "Cumplimiento",
        "description": "Alertas SOC 2 y auditoría",
        "importance": "URGENT",
        "sound": True,
        "vibration": True,
        "lights": True,
        "light_color": "#F44336",
    },
    "connector": {
        "id": "zenic_connector",
        "name": "Conectores",
        "description": "Errores y estado de conectores",
        "importance": "DEFAULT",
        "sound": True,
        "vibration": False,
        "lights": False,
        "light_color": "#9C27B0",
    },
    "system": {
        "id": "zenic_system",
        "name": "Sistema",
        "description": "Notificaciones generales del sistema",
        "importance": "LOW",
        "sound": False,
        "vibration": False,
        "lights": False,
        "light_color": "#607D8B",
    },
}


class PushNotificationService:
    """Send push notifications to mobile devices via FCM.

    Handles:
    - Device token management
    - Notification queuing and delivery
    - Android notification channel configuration
    - Batch sending for efficiency
    - Delivery tracking and analytics

    FCM Architecture (no root needed):
    - App registers with Firebase → gets FCM token
    - Token sent to our server → stored in device registrations
    - Server sends message to FCM → FCM delivers to device
    - Google Play Services handles wake-up and display

    Usage:
        service = PushNotificationService.get_instance()
        service.send_workflow_completed(device_id, workflow_name, success=True)
        service.send_budget_alert(device_id, tenant_id, threshold_pct=90)
    """

    _instance: PushNotificationService | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from src.core.config import PUSH_NOTIFICATIONS_DB_PATH
            db_path = str(PUSH_NOTIFICATIONS_DB_PATH)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._pending: list[PushNotification] = []
        self._lock_local = threading.Lock()
        self._init_db()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> PushNotificationService:
        """Get or create the singleton service."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    def _init_db(self) -> None:
        """Initialize notification database."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS push_notifications (
                notification_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                data TEXT DEFAULT '{}',
                deep_link TEXT DEFAULT '',
                created_at REAL NOT NULL,
                sent_at REAL,
                delivered INTEGER DEFAULT 0
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notif_device ON push_notifications(device_id)"
        )
        self._conn.commit()

    # ── High-Level Notification Methods ─────────────────────

    def send_workflow_completed(
        self,
        device_id: str,
        workflow_name: str,
        execution_id: str = "",
        success: bool = True,
    ) -> PushNotification:
        """Send a workflow completion notification."""
        title = "Workflow Completado" if success else "Workflow Falló"
        body = f"'{workflow_name}' {'se ejecutó exitosamente' if success else 'falló durante la ejecución'}"
        return self.send(
            device_id=device_id,
            title=title,
            body=body,
            category=NotificationCategory.WORKFLOW,
            priority=NotificationPriority.HIGH if not success else NotificationPriority.NORMAL,
            data={
                "type": "workflow_completed",
                "workflow_name": workflow_name,
                "execution_id": execution_id,
                "success": success,
            },
            deep_link=f"zenic://workflows/{execution_id}",
            actions=[
                {"title": "Ver Detalles", "action": "view"},
                {"title": "Re-ejecutar", "action": "retry"},
            ] if not success else [
                {"title": "Ver Resultado", "action": "view"},
            ],
        )

    def send_agent_decision(
        self,
        device_id: str,
        agent_name: str,
        decision_summary: str,
        agent_id: str = "",
    ) -> PushNotification:
        """Send an agent decision notification requiring human input."""
        return self.send(
            device_id=device_id,
            title="Agente: Decisión Requerida",
            body=f"{agent_name}: {decision_summary[:100]}",
            category=NotificationCategory.AGENT,
            priority=NotificationPriority.HIGH,
            data={
                "type": "agent_decision",
                "agent_id": agent_id,
                "agent_name": agent_name,
            },
            deep_link=f"zenic://agents/{agent_id}",
            actions=[
                {"title": "Aprobar", "action": "approve"},
                {"title": "Rechazar", "action": "reject"},
                {"title": "Ver Detalles", "action": "view"},
            ],
        )

    def send_budget_alert(
        self,
        device_id: str,
        tenant_id: str,
        threshold_pct: float,
        current_spend: float,
        budget_limit: float,
        budget_type: str = "monthly",
    ) -> PushNotification:
        """Send a budget alert notification."""
        return self.send(
            device_id=device_id,
            title=f"⚠️ Alerta de Presupuesto {budget_type.title()}",
            body=f"Has usado {threshold_pct:.0f}% del presupuesto: ${current_spend:.2f} / ${budget_limit:.2f}",
            category=NotificationCategory.BUDGET,
            priority=NotificationPriority.HIGH,
            data={
                "type": "budget_alert",
                "tenant_id": tenant_id,
                "threshold_pct": threshold_pct,
                "current_spend": current_spend,
                "budget_limit": budget_limit,
                "budget_type": budget_type,
            },
            deep_link="zenic://billing",
        )

    def send_compliance_alert(
        self,
        device_id: str,
        control_name: str,
        ref_code: str = "",
        risk_level: str = "high",
    ) -> PushNotification:
        """Send a compliance alert notification."""
        return self.send(
            device_id=device_id,
            title="🛡️ Alerta de Cumplimiento",
            body=f"{control_name} ({ref_code}) requiere atención. Riesgo: {risk_level}",
            category=NotificationCategory.COMPLIANCE,
            priority=NotificationPriority.HIGH,
            data={
                "type": "compliance_alert",
                "control_name": control_name,
                "ref_code": ref_code,
                "risk_level": risk_level,
            },
            deep_link="zenic://compliance",
        )

    # ── Core Send Method ────────────────────────────────────

    def send(
        self,
        device_id: str,
        title: str,
        body: str,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        data: dict[str, Any] | None = None,
        actions: list[dict[str, str]] | None = None,
        deep_link: str = "",
    ) -> PushNotification:
        """Send a push notification to a device.

        In production, this calls the FCM HTTP v1 API.
        Currently stores locally for development/testing.
        """
        notification = PushNotification(
            device_id=device_id,
            title=title,
            body=body,
            category=category,
            priority=priority,
            data=data or {},
            actions=actions or [],
            deep_link=deep_link,
        )

        with self._lock_local:
            self._pending.append(notification)
            self._persist_notification(notification)

        # In production: send to FCM
        self._send_to_fcm(notification)

        logger.info(
            "Push notification sent: %s → %s (%s)",
            notification.notification_id,
            device_id,
            category.value,
        )

        return notification

    def _send_to_fcm(self, notification: PushNotification) -> bool:
        """Send notification to Firebase Cloud Messaging.

        Production implementation would use:
        - google-auth library for service account authentication
        - FCM HTTP v1 API: POST https://fcm.googleapis.com/v1/projects/{project}/messages:send
        - Batch sending for multiple devices
        """
        # Build FCM message payload
        fcm_message = {
            "message": {
                "token": notification.fcm_token,
                "notification": {
                    "title": notification.title,
                    "body": notification.body,
                },
                "android": {
                    "priority": notification.priority.value,
                    "notification": {
                        "channel_id": NOTIFICATION_CHANNELS.get(
                            notification.category.value, {}
                        ).get("id", "zenic_system"),
                        "sound": notification.sound,
                        "click_action": notification.deep_link,
                        "notification_count": notification.badge_count,
                    },
                },
                "data": {k: str(v) for k, v in notification.data.items()},
            }
        }

        # Production: HTTP POST to FCM
        # For now, just log it
        logger.debug("FCM message prepared: %s", json.dumps(fcm_message, indent=2))
        notification.sent_at = time.time()
        return True

    def _persist_notification(self, notification: PushNotification) -> None:
        """Persist notification for audit trail."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO push_notifications
                   (notification_id, device_id, title, body, category, priority,
                    data, deep_link, created_at, sent_at, delivered)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    notification.notification_id,
                    notification.device_id,
                    notification.title,
                    notification.body,
                    notification.category.value,
                    notification.priority.value,
                    json.dumps(notification.data),
                    notification.deep_link,
                    notification.created_at,
                    notification.sent_at,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist notification: %s", exc)

    # ── Batch Operations ────────────────────────────────────

    def send_batch(self, notifications: list[PushNotification]) -> int:
        """Send multiple notifications efficiently."""
        sent = 0
        for notif in notifications:
            try:
                self._send_to_fcm(notif)
                sent += 1
            except Exception as exc:
                logger.error("Batch send failed for %s: %s", notif.notification_id, exc)
        return sent

    def get_notification_history(
        self,
        device_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get notification history for a device."""
        if self._conn is None:
            return []
        try:
            cursor = self._conn.execute(
                """SELECT notification_id, title, body, category, priority,
                          data, deep_link, created_at, delivered
                   FROM push_notifications
                   WHERE device_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (device_id, limit),
            )
            return [
                {
                    "notification_id": r[0],
                    "title": r[1],
                    "body": r[2],
                    "category": r[3],
                    "priority": r[4],
                    "data": json.loads(r[5]) if r[5] else {},
                    "deep_link": r[6],
                    "created_at": r[7],
                    "delivered": bool(r[8]),
                }
                for r in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    def get_preferences(self, device_id: str) -> dict[str, Any] | None:
        """Get push notification preferences for a device.

        Fix Sprint 2 bug #16: API pública para el endpoint mobile
        /notifications/preferences. Lee de la tabla push_preferences
        (creada en _init_db). Retorna None si no hay preferencias guardadas.

        Args:
            device_id: ID del dispositivo.

        Returns:
            Dict con preferences + quiet_hours, o None si no hay config previa.
        """
        if self._conn is None:
            return None
        try:
            # Crear tabla si no existe (idempotente)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS push_preferences (
                    device_id TEXT PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    quiet_hours TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self._conn.commit()

            cursor = self._conn.execute(
                "SELECT preferences, quiet_hours FROM push_preferences WHERE device_id = ?",
                (device_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "preferences": json.loads(row[0]) if row[0] else {},
                "quiet_hours": json.loads(row[1]) if row[1] else {},
            }
        except sqlite3.Error as e:
            logger.error("Failed to get preferences for %s: %s", device_id, e)
            return None

    def set_preferences(
        self,
        device_id: str,
        preferences: dict[str, Any],
        quiet_hours: dict[str, Any] | None = None,
    ) -> bool:
        """Save push notification preferences for a device.

        Args:
            device_id: ID del dispositivo.
            preferences: Dict con flags de preferencias por categoría.
            quiet_hours: Dict con config de horas tranquilas (opcional).

        Returns:
            True si se guardó, False si falló.
        """
        if self._conn is None:
            return False
        try:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS push_preferences (
                    device_id TEXT PRIMARY KEY,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    quiet_hours TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self._conn.execute(
                """INSERT OR REPLACE INTO push_preferences
                   (device_id, preferences, quiet_hours, updated_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (
                    device_id,
                    json.dumps(preferences),
                    json.dumps(quiet_hours or {}),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set preferences for %s: %s", device_id, e)
            return False

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
