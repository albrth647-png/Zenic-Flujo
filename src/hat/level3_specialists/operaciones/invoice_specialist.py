"""
HAT NIVEL 3 — InvoiceSpecialist
================================

UNA SOLA RESPONSABILIDAD: Facturación.

Coordina los workers del Nivel 4 para las tools (Nivel 5):
- invoice (InvoiceService): create_invoice, mark_paid, mark_overdue, cancel,
  get_invoice, list_invoices, get_overdue_invoices, get_stats
- stripe (StripeService): create_payment_intent, retrieve_payment_intent,
  create_customer, list_customers, create_subscription, list_invoices,
  create_payment_link
- mercadopago (MercadoPagoService): create_preference, get_payment,
  search_payments, create_customer, process_webhook

Routing por keywords:
- "factura", "invoice", "recibo", "cobrar" → invoice actions
- "stripe", "tarjeta" → stripe actions
- "mercadopago", "mp" → mercadopago actions
- Default: list_invoices
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class InvoiceSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: facturación."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="invoice",
            responsibility="facturacion",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="invoice",
            agent_name="Invoice",
            domain="operaciones",
            tier="specialist",
            capabilities=[
                # invoice
                "create_invoice", "mark_paid", "mark_overdue", "cancel",
                "get_invoice", "list_invoices", "get_overdue_invoices", "get_stats",
                # stripe
                "stripe_create_payment_intent", "stripe_create_customer",
                "stripe_list_customers", "stripe_create_subscription",
                "stripe_create_payment_link", "stripe_retrieve_payment_intent",
                "stripe_list_invoices",
                # mercadopago
                "mp_create_preference", "mp_get_payment", "mp_search_payments",
                "mp_create_customer", "mp_process_webhook",
            ],
            cost_per_call=0.0,
            avg_latency_ms=80,
            orbital_keywords=[
                "factura", "invoice", "recibo", "cobrar", "pago", "stripe",
                "tarjeta", "mercadopago", "mp", "suscripción", "cobro",
            ],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # --- Stripe routing ---
        if any(kw in desc for kw in ["stripe"]):
            if any(kw in desc for kw in ["suscripción", "subscription"]):
                return "stripe", "create_subscription", params
            if any(kw in desc for kw in ["link de pago", "payment link", "link"]):
                return "stripe", "create_payment_link", params
            if any(kw in desc for kw in ["listar cliente", "list customers"]):
                return "stripe", "list_customers", params
            if any(kw in desc for kw in ["crear cliente", "nuevo cliente"]):
                return "stripe", "create_customer", params
            if any(kw in desc for kw in ["consultar pago", "retrieve", "estado de pago"]):
                return "stripe", "retrieve_payment_intent", params
            if any(kw in desc for kw in ["listar factura", "list invoice"]):
                return "stripe", "list_invoices", params
            # Default stripe: payment intent
            return "stripe", "create_payment_intent", params

        # --- MercadoPago routing ---
        if any(kw in desc for kw in ["mercadopago", "mp "]) or desc.endswith(" mp"):
            if any(kw in desc for kw in ["webhook", "notificación", "notificacion"]):
                return "mercadopago", "process_webhook", params
            if any(kw in desc for kw in ["buscar pago", "search"]):
                return "mercadopago", "search_payments", params
            if any(kw in desc for kw in ["crear cliente", "nuevo cliente"]):
                return "mercadopago", "create_customer", params
            if any(kw in desc for kw in ["consultar pago", "get payment", "estado de pago"]):
                return "mercadopago", "get_payment", params
            # Default mp: create preference
            return "mercadopago", "create_preference", params

        # --- Tarjeta genérica → stripe ---
        if any(kw in desc for kw in ["tarjeta"]):
            return "stripe", "create_payment_intent", params

        # --- Invoice routing ---
        if any(kw in desc for kw in ["factura", "invoice", "recibo", "cobrar"]):
            if any(kw in desc for kw in ["crear", "nueva", "nuevo", "alta", "emitir"]):
                return "invoice", "create_invoice", params
            if any(kw in desc for kw in ["pagar", "paid", "pagada", "pagado", "marcar pagada"]):
                return "invoice", "mark_paid", params
            if any(kw in desc for kw in ["vencidas", "adeudadas", "overdue invoices", "facturas vencidas"]):
                return "invoice", "get_overdue_invoices", params
            if any(kw in desc for kw in ["vencida", "vencimiento", "overdue"]):
                return "invoice", "mark_overdue", params
            if any(kw in desc for kw in ["cancelar", "anular", "cancel"]):
                return "invoice", "cancel", params
            if any(kw in desc for kw in ["estadística", "stats", "resumen", "dashboard"]):
                return "invoice", "get_stats", params
            if any(kw in desc for kw in ["obtener", "buscar", "get", "ver factura"]):
                return "invoice", "get_invoice", params
            # Default invoice: listar
            return "invoice", "list_invoices", params

        # --- Default seguro: listar facturas ---
        return "invoice", "list_invoices", params

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Ejecuta el specialist: route → invoke tool → return result."""
        import time
        start = time.monotonic()

        tool_name, action_name, params = self.route_action(subtask)
        tool = self._tools.get(tool_name)

        if tool is None:
            return SpecialistResult(
                status="failed",
                error=f"tool '{tool_name}' not available",
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            method = getattr(tool, action_name)
            result = method(**params) if params else method()
            return SpecialistResult(
                status="completed",
                action=action_name,
                result=result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return SpecialistResult(
                status="failed",
                error=str(exc),
                action=action_name,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
