"""
Workflow Determinista — CRM Service
"""

from src.events.bus import EventBus
from src.tools.crm.models import STAGE_ORDER, STAGES
from src.tools.crm.repository import CRMRepository
from src.utils.logger import setup_logging
from typing import Any

logger = setup_logging(__name__)


class CRMService:
    """Servicio de CRM con lógica de negocio y emisión de eventos."""

    def __init__(self, event_bus: EventBus | None = None):
        self._repo = CRMRepository()
        self._event_bus = event_bus or EventBus()

    def create_lead(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        source: str = "manual",
        notes: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        lead = self._repo.create_lead(name, email, phone, company, source, notes, user_id)
        self._event_bus.publish("crm.lead.created", dict(lead))
        logger.info(f"Lead creado: {lead.get('name')} (ID: {lead.get('id')})")
        return lead

    def update_lead(self, lead_id: int, **fields) -> dict[str, Any] | None:
        old = self._repo.get_lead(lead_id)
        lead = self._repo.update_lead(lead_id, **fields)
        if lead and old and "stage" in fields and old["stage"] != lead["stage"]:
            self._event_bus.publish(
                "crm.lead.stage_changed",
                {
                    "lead_id": lead_id,
                    "from_stage": old["stage"],
                    "to_stage": lead["stage"],
                },
            )
        return lead

    def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        return self._repo.get_lead(lead_id)

    def list_leads(
        self, stage: str | None = None, limit: int = 50, offset: int = 0, user_id: int | None = None
    ) -> list[dict]:
        return self._repo.list_leads(stage, limit, offset, user_id)

    def delete_lead(self, lead_id: int) -> bool:
        return self._repo.delete_lead(lead_id)

    def advance_stage(self, lead_id: int) -> dict[str, Any] | None:
        lead = self._repo.get_lead(lead_id)
        if not lead:
            return None
        current = lead["stage"]
        idx = STAGE_ORDER.get(current, 0)
        if idx < len(STAGES) - 2:  # No avanzar desde closed
            next_stage = STAGES[idx + 1]
            return self.update_lead(lead_id, stage=next_stage)
        return lead

    def close_won(self, lead_id: int) -> dict[str, Any] | None:
        return self.update_lead(lead_id, stage="closed_won")

    def close_lost(self, lead_id: int, reason: str | None = None) -> dict[str, Any] | None:
        return self.update_lead(lead_id, stage="closed_lost", notes=reason)

    def get_stats(self) -> dict[str, Any]:
        return self._repo.get_stats()
