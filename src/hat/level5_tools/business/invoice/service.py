"""
Workflow Determinista — Invoice Service
"""

from datetime import datetime, timedelta

from src.core.logging import setup_logging
from src.core.utils import generate_id
from src.events.bus import EventBus
from src.hat.level5_tools.business.invoice.repository import InvoiceRepository
from typing import Any

logger = setup_logging(__name__)


class InvoiceService:
    def __init__(self, event_bus: EventBus | None = None):
        self._repo = InvoiceRepository()
        self._event_bus = event_bus or EventBus()

    def create_invoice(
        self,
        client_name: str,
        client_email: str | None = None,
        items: list[Any] | None = None,
        tax_rate: float = 0.16,
        discount: float = 0.0,
        due_days: int = 30,
        notes: str | None = None,
        user_id: int | None = None,
        # Foso 3: nuevos campos
        lead_id: int | None = None,
        client_id: int | None = None,
        currency: str = "MXN",
        client_phone: str | None = None,
    ) -> dict[str, Any]:
        items = items or []
        # Asegurar tipos numéricos para evitar errores si llegan como string
        safe_items = []
        for item in items:
            safe_item = dict(item)
            try:
                q = safe_item.get("quantity", 1)
                safe_item["quantity"] = int(q) if not isinstance(q, int) else q
            except (ValueError, TypeError):
                safe_item["quantity"] = 1
            try:
                p = safe_item.get("unit_price", 0)
                safe_item["unit_price"] = float(p) if not isinstance(p, (int, float)) else p
            except (ValueError, TypeError):
                safe_item["unit_price"] = 0
            safe_items.append(safe_item)
        items = safe_items
        subtotal = sum(item.get("quantity", 1) * item.get("unit_price", 0) for item in items)
        tax_amount = subtotal * tax_rate
        total = subtotal + tax_amount - discount
        number = f"FAC-{datetime.now().year}-{generate_id().upper()}"
        due_date = (datetime.now() + timedelta(days=due_days)).strftime("%Y-%m-%d")

        invoice = self._repo.create(
            number=number,
            client_name=client_name,
            client_email=client_email,
            items=items,
            subtotal=subtotal,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            discount=discount,
            total=total,
            due_date=due_date,
            notes=notes,
            user_id=user_id,
            # Foso 3: nuevos campos
            lead_id=lead_id,
            client_id=client_id,
            currency=currency,
        )
        self._event_bus.publish("invoice.created", dict(invoice) if invoice else {})
        logger.info(f"Factura creada: {number} - ${total:.2f}")
        return invoice

    def mark_paid(self, invoice_id: int, amount: float | None = None) -> dict[str, Any] | None:
        invoice = self._repo.mark_paid(invoice_id)
        if invoice:
            self._event_bus.publish(
                "invoice.paid",
                {
                    "invoice_id": invoice_id,
                    "amount": amount or invoice.get("total", 0),
                },
            )
        return invoice

    def mark_overdue(self, invoice_id: int) -> dict[str, Any] | None:
        from datetime import datetime as dt_mod

        invoice = self._repo.get(invoice_id)
        if invoice and invoice["status"] == "pending":
            invoice = self._repo.update_status(invoice_id, "overdue")
            self._event_bus.publish(
                "invoice.overdue",
                {
                    "invoice_id": invoice_id,
                    "client": invoice.get("client_name"),
                    "days_overdue": (dt_mod.now() - datetime.strptime(invoice["due_date"], "%Y-%m-%d")).days,
                },
            )
        return invoice

    def cancel(self, invoice_id: int) -> dict[str, Any] | None:
        return self._repo.update_status(invoice_id, "cancelled")

    def get_invoice(self, invoice_id: int) -> dict[str, Any] | None:
        return self._repo.get(invoice_id)

    def list_invoices(self, status: str | None = None, limit: int = 50, user_id: int | None = None) -> list[dict]:
        return self._repo.list_invoices(status, limit, user_id)

    def get_overdue_invoices(self) -> list[dict]:
        return self._repo.get_overdue()

    def get_stats(self) -> dict[str, Any]:
        return self._repo.get_stats()
