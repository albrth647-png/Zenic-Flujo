"""Workflow Determinista — CRM Models"""

from dataclasses import dataclass, field

STAGES = ["new", "contacted", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]

STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}


@dataclass
class Client:
    """Cliente maestro (no confundir con Lead). Puede provenir de conversión de Lead."""
    name: str
    fiscal_type: str = ""        # person | company
    fiscal_id: str = ""          # CUIT/RUT/CPF/RFC/CURP
    email: str = ""
    phone: str = ""              # WhatsApp E.164 (+521...)
    address: str = ""
    city: str = ""
    country_code: str = "MX"     # ISO 3166-1 alpha-2
    currency: str = "MXN"        # ISO 4217
    lead_id: int | None = None   # si viene de conversión
    user_id: int = 1
    id: int | None = None


@dataclass
class Deal:
    """Oportunidad de venta con monto asociado a un Lead/Client."""
    lead_id: int
    title: str
    amount: float
    currency: str = "MXN"
    probability: float = 0.5
    expected_close_date: str = ""
    stage: str = "proposal"
    items: list = field(default_factory=list)
    notes: str = ""
    client_id: int | None = None
    id: int | None = None
