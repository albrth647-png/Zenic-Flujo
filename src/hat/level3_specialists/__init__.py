"""NIVEL 3 — 9 Specialists (LA MAGIA — 1 responsabilidad cada uno).

Distribución:
- operaciones/: CrmSpecialist, InvoiceSpecialist, InventorySpecialist
- comunicaciones/: NotificationSpecialist, EmailSpecialist, ChatSpecialist
- datos_auto/: DataSpecialist, ApiSpecialist, CodeSpecialist

Implementación completa en M6.
"""
from src.hat.level3_specialists.base import AgentCard, CardPublisherMixin, SpecialistAgent

__all__ = ["AgentCard", "CardPublisherMixin", "SpecialistAgent"]
