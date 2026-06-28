"""
Workflow Templates — Marketplace Connector Integrations
========================================================

Plantillas de workflow pre-construidas que integran conectores
del marketplace en casos de uso reales.
Cada template es una definición de workflow completa que puede
instalarse desde el marketplace y personalizarse.

Formato compatible con WorkflowDefinition (src/workflow/repository.py)
y con la UI de editor visual.
"""

from __future__ import annotations

from typing import Any

# ── Estructura de un Template ─────────────────────────────────
#
# MARKETPLACE_TEMPLATES: list[dict[str, Any]]
#
# Cada template tiene:
#   name:           str   — ID único del template
#   label:          str   — Nombre visible
#   description_es: str   — Descripción en español
#   category:       str   — Categoría marketplace
#   connectors:     list  — Conectores requeridos
#   difficulty:     str   — beginner | intermediate | advanced
#   trigger:        dict  — {type, config}  type: event|schedule|webhook|manual
#   steps:          list  — [{id, tool, action, params}]
#   tags:           list  — Etiquetas de búsqueda


MARKETPLACE_TEMPLATES: list[dict[str, Any]] = [
    # ── 1. Shopify → Xero: Contabilidad automatizada ──────────
    {
        "name": "shopify_to_xero_invoice",
        "label": "Facturación Xero desde Shopify",
        "description_es": (
            "Cuando se crea una orden pagada en Shopify, "
            "genera automáticamente la factura correspondiente en Xero "
            "y envía un resumen al equipo de finanzas."
        ),
        "category": "finance",
        "connectors": ["shopify", "xero"],
        "difficulty": "intermediate",
        "tags": ["ecommerce", "accounting", "invoice", "automatizacion"],
        "trigger": {"type": "webhook", "config": {"path": "/shopify/order-paid"}},
        "steps": [
            {
                "id": 1,
                "tool": "shopify",
                "action": "get_order",
                "params": {"order_id": "$input.order_id"},
            },
            {
                "id": 2,
                "tool": "xero",
                "action": "create_invoice",
                "params": {
                    "contact_name": "$output.1.customer.email",
                    "line_items": "$output.1.line_items",
                    "due_date": "$input.due_date",
                    "reference": "Shopify Order #$input.order_id",
                },
            },
            {
                "id": 3,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$settings.admin_email",
                    "subject": "Factura creada: Shopify Order #$input.order_id",
                    "body": "Factura creada en Xero para la orden de Shopify #$input.order_id",
                },
            },
        ],
    },
    # ── 2. Mailchimp → SendGrid: Bienvenida por email ─────────
    {
        "name": "mailchimp_welcome_email",
        "label": "Email de bienvenida para nuevos suscriptores",
        "description_es": (
            "Cuando un nuevo suscriptor se agrega a una lista de Mailchimp, "
            "enviar un email de bienvenida personalizado vía SendGrid "
            "y registrar la actividad en CRM."
        ),
        "category": "communication",
        "connectors": ["mailchimp", "sendgrid"],
        "difficulty": "beginner",
        "tags": ["email", "marketing", "welcome", "onboarding"],
        "trigger": {"type": "event", "config": {"event": "mailchimp.subscriber.added"}},
        "steps": [
            {
                "id": 1,
                "tool": "sendgrid",
                "action": "send_template_email",
                "params": {
                    "to": "$input.email",
                    "from": "welcome@corp.com",
                    "template_id": "$settings.welcome_template_id",
                    "dynamic_data": {
                        "name": "$input.name",
                        "company": "Zenic-Flijo",
                    },
                },
            },
            {
                "id": 2,
                "tool": "crm",
                "action": "create_lead",
                "params": {"name": "$input.name", "email": "$input.email", "source": "mailchimp"},
            },
        ],
    },
    # ── 3. Okta → Slack: Notificación de nuevo usuario ────────
    {
        "name": "okta_user_onboarding_slack",
        "label": "Notificar nuevo usuario en Okta vía Slack",
        "description_es": (
            "Cuando se crea un nuevo usuario en Okta, "
            "enviar una notificación al canal de IT en Slack "
            "con los detalles del usuario y su estado."
        ),
        "category": "iam",
        "connectors": ["okta", "slack"],
        "difficulty": "beginner",
        "tags": ["identity", "notificacion", "it", "slack"],
        "trigger": {"type": "event", "config": {"event": "okta.user.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "okta",
                "action": "get_user",
                "params": {"user_id": "$input.user_id"},
            },
            {
                "id": 2,
                "tool": "slack",
                "action": "send_message",
                "params": {
                    "channel": "#it-notifications",
                    "text": (
                        "🆕 Nuevo usuario creado en Okta:\n"
                        "• Nombre: $output.1.profile.firstName $output.1.profile.lastName\n"
                        "• Email: $output.1.profile.email\n"
                        "• Estado: $output.1.status"
                    ),
                },
            },
        ],
    },
    # ── 4. Zendesk → Monday.com: Ticket escalado a tarea ─────
    {
        "name": "zendesk_ticket_to_monday_task",
        "label": "Convertir ticket Zendesk escalado en tarea Monday",
        "description_es": (
            "Cuando un ticket de Zendesk es escalado (prioridad alta), "
            "crear automáticamente una tarea en Monday.com "
            "y asignarla al equipo responsable."
        ),
        "category": "productivity",
        "connectors": ["zendesk", "monday"],
        "difficulty": "intermediate",
        "tags": ["support", "ticketing", "task", "escalation"],
        "trigger": {"type": "event", "config": {"event": "zendesk.ticket.escalated"}},
        "steps": [
            {
                "id": 1,
                "tool": "zendesk",
                "action": "get_ticket",
                "params": {"ticket_id": "$input.ticket_id"},
            },
            {
                "id": 2,
                "tool": "monday",
                "action": "create_item",
                "params": {
                    "board_id": "$settings.monday_board_id",
                    "name": "Soporte: $output.1.ticket.subject",
                    "column_values": {
                        "description": "$output.1.ticket.description",
                        "priority": "Alta",
                        "status": "Por hacer",
                    },
                },
            },
            {
                "id": 3,
                "tool": "zendesk",
                "action": "update_ticket",
                "params": {
                    "ticket_id": "$input.ticket_id",
                    "comment": "✅ Ticket escalado. Tarea creada en Monday.com para seguimiento.",
                    "status": "pending",
                },
            },
        ],
    },
    # ── 5. Grafana → Splunk: Alerta a logging ─────────────────
    {
        "name": "grafana_alert_to_splunk",
        "label": "Registrar alertas de Grafana en Splunk",
        "description_es": (
            "Cuando Grafana dispara una alerta, "
            "registrar el evento en Splunk para trazabilidad "
            "y crear una anotación en Grafana con el resultado."
        ),
        "category": "monitoring",
        "connectors": ["grafana", "splunk"],
        "difficulty": "advanced",
        "tags": ["monitoring", "alerting", "logging", "observability"],
        "trigger": {"type": "webhook", "config": {"path": "/grafana/alert"}},
        "steps": [
            {
                "id": 1,
                "tool": "splunk",
                "action": "submit_event",
                "params": {
                    "index": "$settings.splunk_index",
                    "source": "grafana",
                    "sourcetype": "_json",
                    "event": {
                        "alert_name": "$input.alert_name",
                        "dashboard": "$input.dashboard_uid",
                        "message": "$input.message",
                        "severity": "$input.severity",
                        "timestamp": "$input.timestamp",
                    },
                },
            },
            {
                "id": 2,
                "tool": "grafana",
                "action": "create_annotation",
                "params": {
                    "text": "Alerta $input.alert_name registrada en Splunk",
                    "tags": ["splunk", "alert", "$input.severity"],
                    "time": "$input.timestamp",
                },
            },
        ],
    },
    # ── 6. Shopify → Mailchimp: Cliente nuevo a newsletter ────
    {
        "name": "shopify_customer_to_mailchimp",
        "label": "Sincronizar clientes Shopify a Mailchimp",
        "description_es": (
            "Cuando un nuevo cliente completa su primera compra en Shopify, "
            "agregarlo automáticamente a una lista de Mailchimp "
            "para campañas de follow-up y marketing."
        ),
        "category": "communication",
        "connectors": ["shopify", "mailchimp"],
        "difficulty": "beginner",
        "tags": ["ecommerce", "marketing", "crm", "customer"],
        "trigger": {"type": "event", "config": {"event": "shopify.order.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "shopify",
                "action": "get_customer",
                "params": {"customer_id": "$input.customer_id"},
            },
            {
                "id": 2,
                "tool": "mailchimp",
                "action": "add_member",
                "params": {
                    "list_id": "$settings.mailchimp_list_id",
                    "email": "$output.1.customer.email",
                    "first_name": "$output.1.customer.first_name",
                    "last_name": "$output.1.customer.last_name",
                    "tags": ["shopify", "nuevo-cliente", "compra-unica"],
                    "status": "subscribed",
                },
            },
        ],
    },
    # ── 7. AFIP → WhatsApp: Notificación de factura ───────────
    {
        "name": "afip_invoice_whatsapp",
        "label": "Notificar factura AFIP vía WhatsApp",
        "description_es": (
            "Cuando se emite una factura electrónica en AFIP, "
            "enviar un mensaje de WhatsApp al cliente "
            "con el detalle de la factura y el enlace de pago."
        ),
        "category": "finance",
        "connectors": ["afip_argentina", "twilio"],
        "difficulty": "advanced",
        "tags": ["latam", "argentina", "factura-electronica", "whatsapp"],
        "trigger": {"type": "event", "config": {"event": "afip.invoice.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "afip_argentina",
                "action": "get_invoice",
                "params": {"cuit": "$input.cuit", "punto_venta": "$input.punto_venta", "numero": "$input.numero"},
            },
            {
                "id": 2,
                "tool": "notification",
                "action": "send_whatsapp_template",
                "params": {
                    "to": "$input.client_phone",
                    "template_name": "factura_electronica",
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": "$output.1.monto"}], "language": "es"}
                    ],
                },
            },
        ],
    },
    # ── 8. DTE Chile → Mail: Envío de factura a cliente ──────
    {
        "name": "dte_send_invoice_email",
        "label": "Enviar DTE por email al cliente",
        "description_es": (
            "Cuando se timbra un DTE en el SII de Chile, "
            "enviar automáticamente el PDF del documento "
            "al correo del cliente con copia a contabilidad."
        ),
        "category": "finance",
        "connectors": ["dte_chile", "sendgrid"],
        "difficulty": "advanced",
        "tags": ["latam", "chile", "dte", "sii", "factura-electronica"],
        "trigger": {"type": "event", "config": {"event": "dte.timbrado"}},
        "steps": [
            {
                "id": 1,
                "tool": "dte_chile",
                "action": "get_dte",
                "params": {"rut_emisor": "$input.rut_emisor", "folio": "$input.folio", "tipo_dte": "$input.tipo_dte"},
            },
            {
                "id": 2,
                "tool": "sendgrid",
                "action": "send_email",
                "params": {
                    "to": "$input.cliente_email",
                    "cc": "$settings.admin_email",
                    "from": "facturacion@corp.com",
                    "subject": "DTE $input.tipo_dte - Folio $input.folio",
                    "body": "Adjuntamos el DTE correspondiente a su compra.",
                },
            },
        ],
    },
    # ── 9. Monday.com → Slack: Tarea movida → notificar ──────
    {
        "name": "monday_task_moved_slack",
        "label": "Notificar cambio de estado en Monday.com a Slack",
        "description_es": (
            "Cuando una tarea en Monday.com cambia de estado "
            "(ej: 'En progreso' → 'Completada'), "
            "enviar una notificación al canal de Slack correspondiente."
        ),
        "category": "productivity",
        "connectors": ["monday", "slack"],
        "difficulty": "beginner",
        "tags": ["task", "notification", "status", "collaboration"],
        "trigger": {"type": "webhook", "config": {"path": "/monday/column-changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "monday",
                "action": "get_item",
                "params": {"item_id": "$input.item_id"},
            },
            {
                "id": 2,
                "tool": "slack",
                "action": "send_message",
                "params": {
                    "channel": "#proyectos",
                    "text": (
                        "📋 *Tarea actualizada en Monday.com*\n"
                        "• Tarea: $output.1.item.name\n"
                        "• Nuevo estado: $input.column_value\n"
                        "• Board: $output.1.item.board.name"
                    ),
                },
            },
        ],
    },
    # ── 10. Okta → Zendesk: Baja de usuario ───────────────────
    {
        "name": "okta_user_offboarding_zendesk",
        "label": "Ticket de offboarding cuando se desactiva usuario Okta",
        "description_es": (
            "Cuando un usuario es desactivado en Okta, "
            "crear automáticamente un ticket en Zendesk "
            "para que el equipo de IT complete el proceso "
            "de offboarding (revocar accesos, recuperar equipo, etc.)."
        ),
        "category": "iam",
        "connectors": ["okta", "zendesk"],
        "difficulty": "intermediate",
        "tags": ["identity", "it", "offboarding", "security", "ticketing"],
        "trigger": {"type": "event", "config": {"event": "okta.user.deactivated"}},
        "steps": [
            {
                "id": 1,
                "tool": "okta",
                "action": "get_user",
                "params": {"user_id": "$input.user_id"},
            },
            {
                "id": 2,
                "tool": "zendesk",
                "action": "create_ticket",
                "params": {
                    "subject": "Offboarding: $output.1.profile.email",
                    "description": (
                        "Usuario desactivado en Okta. Completar proceso de offboarding:\n"
                        "1. Revocar accesos a sistemas (Slack, Notion, GitHub)\n"
                        "2. Recuperar equipo corporativo\n"
                        "3. Transferir documentos pendientes\n"
                        "4. Eliminar cuenta de email"
                    ),
                    "priority": "high",
                    "tags": ["offboarding", "it", "automatico"],
                    "type": "task",
                },
            },
            {
                "id": 3,
                "tool": "slack",
                "action": "send_message",
                "params": {
                    "channel": "#it-operations",
                    "text": (
                        "🔄 *Offboarding iniciado*\n"
                        "Usuario: $output.1.profile.firstName $output.1.profile.lastName\n"
                        "Email: $output.1.profile.email\n"
                        "Ticket Zendesk creado para seguimiento."
                    ),
                },
            },
        ],
    },
]


def list_templates(
    category: str | None = None,
    connector: str | None = None,
    difficulty: str | None = None,
) -> list[dict[str, Any]]:
    """Lista los templates de workflow del marketplace.

    Args:
        category: Filtrar por categoría (finance, communication, iam, etc.)
        connector: Filtrar por conector requerido (shopify, xero, okta, etc.)
        difficulty: Filtrar por dificultad (beginner, intermediate, advanced)

    Returns:
        Lista de templates filtrados (sin los steps para vista previa)
    """
    result = []
    for t in MARKETPLACE_TEMPLATES:
        if category and t["category"] != category:
            continue
        if connector and connector not in t["connectors"]:
            continue
        if difficulty and t["difficulty"] != difficulty:
            continue
        # Vista previa: incluir metadata pero no steps completos
        preview = {
            "name": t["name"],
            "label": t["label"],
            "description_es": t["description_es"],
            "category": t["category"],
            "connectors": t["connectors"],
            "difficulty": t["difficulty"],
            "tags": t["tags"],
            "trigger": t["trigger"],
            "step_count": len(t["steps"]),
        }
        result.append(preview)
    return result


def get_template(name: str) -> dict[str, Any] | None:
    """Obtiene un template completo por su nombre.

    Args:
        name: Nombre único del template

    Returns:
        Template completo con steps, o None si no existe
    """
    for t in MARKETPLACE_TEMPLATES:
        if t["name"] == name:
            return dict(t)
    return None


def list_categories() -> list[dict[str, Any]]:
    """Lista las categorías disponibles con conteo de templates."""
    counts: dict[str, int] = {}
    for t in MARKETPLACE_TEMPLATES:
        cat = t["category"]
        counts[cat] = counts.get(cat, 0) + 1
    return [{"name": name, "count": count} for name, count in sorted(counts.items())]


def get_templates_by_connector(connector_name: str) -> list[dict[str, Any]]:
    """Obtiene todos los templates que usan un conector específico."""
    return [t for t in MARKETPLACE_TEMPLATES if connector_name in t["connectors"]]


def template_to_workflow_definition(name: str) -> dict[str, Any] | None:
    """Convierte un template en una definición de workflow lista para crear.

    Args:
        name: Nombre del template

    Returns:
        Dict compatible con WorkflowDefinition.create() o None si no existe
    """
    template = get_template(name)
    if not template:
        return None
    return {
        "name": template["label"],
        "description": template["description_es"],
        "trigger_type": template["trigger"]["type"],
        "trigger_config": template["trigger"]["config"],
        "steps": template["steps"],
    }
