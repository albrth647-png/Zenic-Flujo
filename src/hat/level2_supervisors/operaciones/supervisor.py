"""HAT NIVEL 2 — OperacionesSupervisor (M8: routing real por keywords).

Sub-orquestador de operaciones. NO conoce a ComunicacionesSupervisor ni DatosAutoSupervisor.

Coordina specialists de operaciones (Nivel 3):
- CrmSpecialist (gestión de clientes/leads)
- InvoiceSpecialist (facturación)
- InventorySpecialist (inventario/stock)

Routing por keywords (case-insensitive):
- "cliente", "lead", "venta", "crm", "oportunidad", "contacto" → CrmSpecialist
- "factura", "invoice", "cobro", "pago", "stripe", "mercadopago" → InvoiceSpecialist
- "producto", "stock", "inventario", "inventory" → InventorySpecialist

Si ningún keyword matchea, usa el primer specialist disponible (fallback graceful).

Implementación completa en M8.
"""
from __future__ import annotations

from typing import ClassVar

from src.core.logging import get_logger
from src.hat.level2_supervisors.base_router import SpecialistRouter
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

logger = get_logger("hat.level2.operaciones")


class OperacionesSupervisor(SpecialistRouter):
    """Sub-orquestador de operaciones con routing real por keywords.

    Aislamiento: NO importa nada de level2_supervisors/comunicaciones/ ni
    level2_supervisors/datos_auto/. Solo conoce sus specialists (N3).

    Hereda de :class:`SpecialistRouter` que implementa el routing genérico.
    Esta clase solo define el ``_keyword_map`` específico del dominio.
    """

    domain = "operaciones"

    # Mapeo keyword → specialist_name.
    # El orden importa: si un mensaje contiene múltiples keywords, gana el
    # primer match en orden de inserción. Por eso ponemos keywords más
    # específicas primero y evitamos substrings ambiguos.
    # NOTA: "venta" se omite porque es substring de "inventario" (in-venta-rio)
    # y causa falsos positivos. Usar "oportunidad" o "negocio" en su lugar.
    _KEYWORD_MAP: ClassVar[dict[str, str]] = {
        # === Inventory (inventario) — PRIMERO para evitar substrings ===
        "producto": "inventory",
        "stock": "inventory",
        "inventario": "inventory",
        "inventory": "inventory",
        # === Invoice (facturación) ===
        "factura": "invoice",
        "invoice": "invoice",
        "cobro": "invoice",
        "pago": "invoice",
        "stripe": "invoice",
        "mercadopago": "invoice",
        # === CRM (clientes/leads) ===
        "cliente": "crm",
        "lead": "crm",
        "crm": "crm",
        "oportunidad": "crm",
        "contacto": "crm",
        "negocio": "crm",
    
        # === CONECTORES EXTERNOS (Phase 4) ===
        # CRM connectors → crm specialist
        "salesforce": "crm",
        "hubspot": "crm",
        "pipedrive": "crm",
        "zoho": "crm",
        "marketo": "crm",
        # E-commerce → inventory specialist
        "shopify": "inventory",
        "woocommerce": "inventory",
        "mercadolibre": "inventory",
        # Payments → invoice specialist
        "paypal": "invoice",
        "wise": "invoice",
        "square": "invoice",
        "quickbooks": "invoice",
        "xero": "invoice",
        # Fiscal → invoice specialist
        "afip": "invoice",
        "dte": "invoice",
        "nfe": "invoice",
        "sat": "invoice",
        "totvs": "invoice",
    }

    def __init__(
        self,
        specialists: dict | None = None,
        ledger: LedgerRepository | None = None,
    ) -> None:
        """Inicializa el supervisor de operaciones.

        Args:
            specialists: Dict con keys 'crm', 'invoice', 'inventory' (o subset).
                Si falta alguno, el routing a ese specialist fallará graceful.
            ledger: LedgerRepository opcional (no usado en routing).
        """
        super().__init__(specialists=specialists, ledger=ledger)
        self._keyword_map = dict(self._KEYWORD_MAP)
        logger.info(
            "OperacionesSupervisor inicializado con %d specialists, %d keywords",
            len(self._specialists), len(self._keyword_map),
        )
