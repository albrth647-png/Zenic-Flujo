"""HAT NIVEL 2 — ComunicacionesSupervisor (M8: routing real por keywords).

Sub-orquestador de comunicaciones. NO conoce a OperacionesSupervisor ni DatosAutoSupervisor.

Coordina specialists de comunicaciones (Nivel 3):
- NotificationSpecialist (email + WhatsApp)
- EmailSpecialist (Gmail)
- ChatSpecialist (Slack + Telegram)

Routing por keywords (case-insensitive):
- "email", "correo", "gmail", "smtp" → EmailSpecialist
- "whatsapp", "wa", "slack", "telegram", "chat" → ChatSpecialist
- "notificar", "notificacion", "notification", "cumpleanos" → NotificationSpecialist

Si ningún keyword matchea, usa el primer specialist disponible (fallback graceful).

Implementación completa en M8.
"""
from __future__ import annotations

from typing import ClassVar

from src.core.logging import get_logger
from src.hat.level2_supervisors.base_router import SpecialistRouter
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

logger = get_logger("hat.level2.comunicaciones")


class ComunicacionesSupervisor(SpecialistRouter):
    """Sub-orquestador de comunicaciones con routing real por keywords.

    Hereda de :class:`SpecialistRouter` que implementa el routing genérico.
    Esta clase solo define el ``_keyword_map`` específico del dominio.
    """

    domain = "comunicaciones"

    # Mapeo keyword → specialist_name.
    # Orden: keywords más específicas primero para evitar substrings.
    # NOTA: "notificar" se pone antes que "notificacion" porque es más corta
    # y podría ser substring de otras palabras.
    _KEYWORD_MAP: ClassVar[dict[str, str]] = {
        # === Email (Gmail) ===
        "gmail": "email",
        "smtp": "email",
        "email": "email",
        "correo": "email",
        # === Chat (Slack + Telegram) ===
        "whatsapp": "chat",
        "slack": "chat",
        "telegram": "chat",
        "chat": "chat",
        # === Notification (email + WhatsApp genérico) ===
        "notificar": "notification",
        "notificacion": "notification",
        "notification": "notification",
        "cumpleanos": "notification",
        "cumpleaños": "notification",
        "birthday": "notification",
    
        # === CONECTORES EXTERNOS (Phase 4) ===
        "mailgun": "email",
        "sendgrid": "email",
        "mailchimp": "email",
        "discord": "chat",
        "twilio": "chat",
        "freshdesk": "notification",
        "intercom": "chat",
        "zendesk": "notification",
        "typeform": "notification",
        "teams": "chat",
    }

    def __init__(
        self,
        specialists: dict | None = None,
        ledger: LedgerRepository | None = None,
    ) -> None:
        """Inicializa el supervisor de comunicaciones.

        Args:
            specialists: Dict con keys 'notification', 'email', 'chat' (o subset).
            ledger: LedgerRepository opcional (no usado en routing).
        """
        super().__init__(specialists=specialists, ledger=ledger)
        self._keyword_map = dict(self._KEYWORD_MAP)
        logger.info(
            "ComunicacionesSupervisor inicializado con %d specialists, %d keywords",
            len(self._specialists), len(self._keyword_map),
        )
