"""
DDE v3 — Fragmentos de Workflow (unidad mínima reutilizable)

Cada fragmento es un bloque atómico que describe un paso de workflow.
El WorkflowCompiler (Etapa 9) ensambla N fragmentos para componer
workflows complejos, en vez de usar plantillas monolíticas.

Determinista. Sin IA.
"""

from __future__ import annotations

from src.nlu.entities.base import StepFragment

FRAGMENTS: tuple[StepFragment, ...] = (
    # ── TRIGGERS ────────────────────────────────────────
    StepFragment(
        kind="trigger",
        intent_tags=("registro_cliente", "lead_avanzar_etapa", "factura_vencida", "producto_agotado", "archivo_nuevo"),
        produces={
            "type": "event",
            "config": {"event": "$intent_event"},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="trigger",
        intent_tags=("alerta_stock_bajo", "factura_automatica", "backup_automatico", "email_cumpleanos"),
        produces={
            "type": "schedule",
            "config": {"cron": "$slot.frecuencia"},
        },
        requires_slots=("frecuencia",),
    ),
    StepFragment(
        kind="trigger",
        intent_tags=("webhook_ejecutar",),
        produces={
            "type": "webhook",
            "config": {},
        },
        requires_slots=("url_webhook",),
    ),
    # ── STEPS ───────────────────────────────────────────
    StepFragment(
        kind="step",
        intent_tags=("registro_cliente",),
        produces={
            "tool": "crm",
            "action": "create_lead",
            "params": {
                "name": "$slot.nombre",
                "email": "$slot.email_destino",
                "phone": "$slot.telefono",
            },
        },
        requires_slots=("nombre", "email_destino"),
    ),
    StepFragment(
        kind="step",
        intent_tags=("registro_cliente",),
        produces={
            "tool": "notification",
            "action": "send_email",
            "params": {
                "to": "$slot.email_destino",
                "subject": "¡Bienvenido!",
                "body": "Gracias por registrarte.",
            },
        },
        requires_slots=("email_destino",),
    ),
    StepFragment(
        kind="step",
        intent_tags=("alerta_stock_bajo",),
        produces={
            "tool": "inventory",
            "action": "get_low_stock_products",
            "params": {"threshold": "$slot.umbral_stock"},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=(
            "alerta_stock_bajo",
            "factura_automatica",
            "backup_automatico",
            "email_cumpleanos",
            "lead_avanzar_etapa",
            "producto_agotado",
        ),
        produces={
            "tool": "notification",
            "action": "send_email",
            "params": {
                "to": "$slot.email_admin",
                "subject": "$intent.label",
                "body": "$output.1",
            },
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("factura_automatica",),
        produces={
            "tool": "invoice",
            "action": "get_overdue_invoices",
            "params": {},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("backup_automatico",),
        produces={
            "tool": "system",
            "action": "backup_database",
            "params": {},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("email_cumpleanos",),
        produces={
            "tool": "notification",
            "action": "send_birthday_emails",
            "params": {},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("factura_vencida",),
        produces={
            "tool": "invoice",
            "action": "get_invoice",
            "params": {"invoice_id": "$input.invoice_id"},
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("factura_vencida",),
        produces={
            "tool": "notification",
            "action": "send_email",
            "params": {
                "to": "$slot.email_cliente",
                "subject": "Factura vencida",
                "body": "Tu factura está vencida.",
            },
        },
        requires_slots=("email_cliente",),
    ),
    StepFragment(
        kind="step",
        intent_tags=("webhook_ejecutar",),
        produces={
            "tool": "notification",
            "action": "send_notification",
            "params": {
                "channel": "log",
                "recipients": "admin",
                "message": "Webhook recibido: $input.body",
            },
        },
        requires_slots=(),
    ),
    StepFragment(
        kind="step",
        intent_tags=("archivo_nuevo",),
        produces={
            "tool": "notification",
            "action": "send_notification",
            "params": {
                "channel": "log",
                "recipients": "admin",
                "message": "Archivo nuevo: $input.filename",
            },
        },
        requires_slots=(),
    ),
)


def get_fragments_by_intent(intent_name: str) -> list[StepFragment]:
    """Retorna los fragmentos que aplican para una intención.

    Args:
        intent_name: Nombre de la intención

    Returns:
        Lista de fragmentos relevantes
    """
    return [f for f in FRAGMENTS if intent_name in f.intent_tags]


def get_fragments_by_kind(kind: str) -> list[StepFragment]:
    """Retorna fragmentos por tipo.

    Args:
        kind: 'trigger' | 'step' | 'condition' | 'loop'

    Returns:
        Lista de fragmentos del tipo solicitado
    """
    return [f for f in FRAGMENTS if f.kind == kind]
