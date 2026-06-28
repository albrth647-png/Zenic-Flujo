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
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, SpecialistResult, Subtask


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

    # Tabla de routing por tool (refactorizado de CC=47 a CC≈8, Forge Fase 1.4).
    # Formato: (matcher_func, [(action_keywords, action_name)], default_action, tool_name)
    _ROUTING_TABLE: tuple[tuple[
        tuple[str, ...],                                  # keywords que activan este tool
        list[tuple[tuple[str, ...], str]],                # (action_keywords, action_name)
        str,                                              # default action
        str,                                              # tool name
    ], ...] = (
        (
            ("stripe",),
            [
                (("suscripción", "subscription"), "create_subscription"),
                (("link de pago", "payment link", "link"), "create_payment_link"),
                (("listar cliente", "list customers"), "list_customers"),
                (("crear cliente", "nuevo cliente"), "create_customer"),
                (("consultar pago", "retrieve", "estado de pago"), "retrieve_payment_intent"),
                (("listar factura", "list invoice"), "list_invoices"),
            ],
            "create_payment_intent",
            "stripe",
        ),
        (
            ("mercadopago", "mp "),
            [
                (("webhook", "notificación", "notificacion"), "process_webhook"),
                (("buscar pago", "search"), "search_payments"),
                (("crear cliente", "nuevo cliente"), "create_customer"),
                (("consultar pago", "get payment", "estado de pago"), "get_payment"),
            ],
            "create_preference",
            "mercadopago",
        ),
        (
            ("tarjeta",),
            [],  # sin sub-actions: siempre create_payment_intent en stripe
            "create_payment_intent",
            "stripe",
        ),
        (
            ("factura", "invoice", "recibo", "cobrar"),
            [
                (("crear", "nueva", "nuevo", "alta", "emitir"), "create_invoice"),
                (("pagar", "paid", "pagada", "pagado", "marcar pagada"), "mark_paid"),
                (("vencidas", "adeudadas", "overdue invoices", "facturas vencidas"), "get_overdue_invoices"),
                (("vencida", "vencimiento", "overdue"), "mark_overdue"),
                (("cancelar", "anular", "cancel"), "cancel"),
                (("estadística", "stats", "resumen", "dashboard"), "get_stats"),
                (("obtener", "buscar", "get", "ver factura"), "get_invoice"),
            ],
            "list_invoices",
            "invoice",
        ),
    )

    def _match_action(self, desc: str, actions: list[tuple[tuple[str, ...], str]], default: str) -> str:
        """Devuelve la primera action cuyas keywords matcheen, sino default."""
        for keywords, action_name in actions:
            if any(kw in desc for kw in keywords):
                return action_name
        return default

    def _match_tool(self, desc: str) -> tuple[tuple[str, ...], list[tuple[tuple[str, ...], str]], str, str] | None:
        """Devuelve la entrada de la tabla de routing que aplica al description.

        Soporta matcher especial para `desc.endswith(' mp')` (caso MercadoPago).
        """
        for entry in self._ROUTING_TABLE:
            tool_keywords, _actions, _default_action, tool_name = entry
            if tool_name == "mercadopago" and desc.endswith(" mp"):
                return entry
            if any(kw in desc for kw in tool_keywords):
                return entry
        return None

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask.

        Implementación basada en tabla de routing (`_ROUTING_TABLE`) para
        mantener baja la complejidad ciclomática. Antes CC=47, ahora CC≈6.
        """
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        entry = self._match_tool(desc)
        if entry is None:
            # Default seguro: listar facturas
            return "invoice", "list_invoices", params

        _tool_keywords, actions, default_action, tool_name = entry
        action_name = self._match_action(desc, actions, default_action)
        return tool_name, action_name, params

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
