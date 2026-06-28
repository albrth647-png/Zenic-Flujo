"""
Workflow Determinista — CRM Service
"""

from src.core.logging import setup_logging
from src.events.bus import EventBus
from src.hat.level5_tools.business.crm.models import STAGE_ORDER, STAGES
from src.hat.level5_tools.business.crm.repository import CRMRepository
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
        stage: str = "new",
    ) -> dict[str, Any]:
        lead = self._repo.create_lead(name, email, phone, company, source, notes, user_id, stage)
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

    # ── Foso 3: Clients ──────────────────────────────────────

    def create_client(
        self,
        name: str,
        fiscal_type: str = "",
        fiscal_id: str = "",
        email: str = "",
        phone: str = "",
        address: str = "",
        city: str = "",
        country_code: str = "MX",
        currency: str = "MXN",
        lead_id: int | None = None,
    ) -> dict[str, Any]:
        """Crea un cliente maestro. Si lead_id se provee, vincula al lead."""
        client = self._repo.create_client(
            name=name, fiscal_type=fiscal_type, fiscal_id=fiscal_id,
            email=email, phone=phone, address=address, city=city,
            country_code=country_code, currency=currency, lead_id=lead_id,
        )
        self._event_bus.publish("crm.client.created", dict(client) if client else {})
        logger.info(f"Cliente creado: {client.get('name')} (ID: {client.get('id')})")
        return client

    def get_client(self, client_id: int) -> dict[str, Any] | None:
        return self._repo.get_client(client_id)

    def get_client_by_fiscal_id(self, fiscal_id: str, country_code: str) -> dict[str, Any] | None:
        return self._repo.get_client_by_fiscal_id(fiscal_id, country_code)

    def list_clients(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._repo.list_clients(limit, offset)

    def update_client(self, client_id: int, **fields) -> dict[str, Any] | None:
        return self._repo.update_client(client_id, **fields)

    def convert_lead_to_deal(
        self,
        lead_id: int,
        title: str = "",
        amount: float = 0.0,
        currency: str = "MXN",
        items: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Convierte un Lead closed_won en Client + Deal.

        1. Obtiene el lead
        2. Crea un Client con los datos del lead
        3. Crea un Deal vinculado al lead y al client
        4. Publica evento crm.lead.converted
        """
        lead = self._repo.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} no encontrado")

        # Crear client desde lead
        client = self._repo.create_client(
            name=lead["name"],
            email=lead.get("email") or "",
            phone=lead.get("phone") or "",
            lead_id=lead_id,
        )

        # Crear deal vinculado
        deal_title = title or f"Deal - {lead['name']}"
        deal = self._repo.create_deal(
            lead_id=lead_id,
            title=deal_title,
            amount=amount,
            currency=currency,
            items=items,
            client_id=client.get("id"),
        )

        self._event_bus.publish("crm.lead.converted", {
            "lead_id": lead_id,
            "client_id": client.get("id"),
            "deal_id": deal.get("id"),
        })
        logger.info(f"Lead {lead_id} convertido → client={client.get('id')} deal={deal.get('id')}")
        return {"client": client, "deal": deal}
