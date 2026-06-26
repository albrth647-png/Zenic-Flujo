"""
Workflow Determinista — Plantillas de Intención
Templates para convertir lenguaje natural en definiciones de workflow.

Migrado de src/nlp/templates.py → src/nlu/templates.py
"""

from __future__ import annotations

TEMPLATES: list[dict] = [
    {
        "name": "registro_cliente",
        "label": "Registro de cliente con bienvenida",
        "description_es": "Cuando un nuevo cliente se registra, guardarlo en CRM y enviar email de bienvenida",
        "description_en": "When a new customer registers, save them to CRM and send a welcome email",
        "keywords_es": ["registr", "nuev", "client", "guard", "cre", "agreg", "lead", "contact"],
        "keywords_en": ["regist", "new", "client", "custom", "save", "creat", "add", "lead", "contact", "welcom", "sign", "join", "subscrib"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "crm",
                "action": "create_lead",
                "params": {"name": "$input.nombre", "email": "$input.email", "phone": "$input.telefono"},
            },
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$input.email",
                    "subject": "¡Bienvenido!",
                    "body": "Hola $input.nombre, gracias por registrarte.",
                },
            },
        ],
    },
    {
        "name": "alerta_stock_bajo",
        "label": "Alerta de stock bajo",
        "description_es": "Revisar inventario diariamente y alertar cuando productos tengan stock bajo",
        "description_en": "Check inventory daily and alert when products are low on stock",
        "keywords_es": ["inventari", "stock", "baj", "alert", "compr", "product", "reorden"],
        "keywords_en": ["invent", "stock", "low", "alert", "purchas", "product", "reorder", "shortage", "supply", "warehous", "restock"],
        "trigger": {"type": "schedule", "config": {"cron": "0 9 * * *"}},
        "steps": [
            {"id": 1, "tool": "inventory", "action": "get_low_stock_products"},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$settings.admin_email",
                    "subject": "Alerta: Productos con stock bajo",
                    "body": "$output.1",
                },
            },
        ],
    },
    {
        "name": "factura_automatica",
        "label": "Generar facturas semanales",
        "description_es": "Generar facturas pendientes cada lunes",
        "description_en": "Generate pending invoices every Monday",
        "keywords_es": ["factur", "invoice", "cobr", "pago", "venc", "semanal"],
        "keywords_en": ["invoic", "bill", "charg", "payment", "due", "weekly", "monday", "pend", "outstand", "recur"],
        "trigger": {"type": "schedule", "config": {"cron": "0 9 * * 1"}},
        "steps": [
            {"id": 1, "tool": "invoice", "action": "get_overdue_invoices"},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {"to": "$settings.admin_email", "subject": "Facturas de la semana", "body": "$output.1"},
            },
        ],
    },
    {
        "name": "backup_automatico",
        "label": "Backup automático de base de datos",
        "description_es": "Hacer respaldo automático de la base de datos cada noche",
        "description_en": "Automatic database backup every night",
        "keywords_es": ["backup", "respaldo", "copi", "seguridad", "base", "datos", "noche"],
        "keywords_en": ["backup", "sav", "copi", "secur", "databas", "night", "daili", "restor", "snapshot", "protect"],
        "trigger": {"type": "schedule", "config": {"cron": "0 23 * * *"}},
        "steps": [
            {"id": 1, "tool": "system", "action": "backup_database"},
        ],
    },
    {
        "name": "email_cumpleanos",
        "label": "Email de cumpleaños",
        "description_es": "Enviar emails de felicitación a clientes en su cumpleaños",
        "description_en": "Send birthday greeting emails to customers",
        "keywords_es": ["cumpleañ", "cumple", "felic", "navidad", "aniversari", "salud"],
        "keywords_en": ["birthday", "happy", "anniversari", "christma", "greet", "congrat", "celeb", "wish", "occasion"],
        "trigger": {"type": "schedule", "config": {"cron": "0 8 * * *"}},
        "steps": [
            {"id": 1, "tool": "notification", "action": "send_birthday_emails"},
        ],
    },
    {
        "name": "lead_avanzar_etapa",
        "label": "Avanzar lead de etapa",
        "description_es": "Cuando un lead cambia de etapa, notificar al equipo",
        "description_en": "When a lead changes stage, notify the team",
        "keywords_es": ["lead", "etap", "avanz", "oportunidad", "vent", "pipeline", "negoci"],
        "keywords_en": ["lead", "stage", "advanc", "opportun", "sale", "pipeline", "deal", "progres", "move", "funnel", "qualif"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.stage_changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$settings.admin_email",
                    "subject": "Lead avanzó: $input.to_stage",
                    "body": "Lead $input.lead_id cambió de $input.from_stage a $input.to_stage",
                },
            },
        ],
    },
    {
        "name": "factura_vencida",
        "label": "Alerta de factura vencida",
        "description_es": "Cuando una factura vence, notificar al cliente",
        "description_en": "When an invoice becomes overdue, notify the customer",
        "keywords_es": ["factur", "venc", "moros", "pago", "pendient", "cobranz"],
        "keywords_en": ["invoic", "overdu", "due", "payment", "pending", "collect", "late", "remind", "follow", "debt"],
        "trigger": {"type": "event", "config": {"event": "invoice.overdue"}},
        "steps": [
            {"id": 1, "tool": "invoice", "action": "get_invoice", "params": {"invoice_id": "$input.invoice_id"}},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$output.1.client_email",
                    "subject": "Factura vencida",
                    "body": "Tu factura está vencida.",
                },
            },
        ],
    },
    {
        "name": "producto_agotado",
        "label": "Alerta de producto agotado",
        "description_es": "Cuando un producto se agota, notificar al administrador",
        "description_en": "When a product runs out of stock, notify the admin",
        "keywords_es": ["product", "agot", "sin", "stock", "cero", "faltant"],
        "keywords_en": ["product", "out", "stock", "zero", "miss", "unavail", "empti", "sold", "exhaust", "deplet"],
        "trigger": {"type": "event", "config": {"event": "inventory.stock_out"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$settings.admin_email",
                    "subject": "Producto agotado: $input.name",
                    "body": "El producto $input.name (ID: $input.id) está agotado.",
                },
            },
        ],
    },
    {
        "name": "webhook_ejecutar",
        "label": "Ejecutar workflow por webhook",
        "description_es": "Ejecutar acciones cuando se recibe un webhook externo",
        "description_en": "Run actions when an external webhook is received",
        "keywords_es": ["webhook", "extern", "api", "http", "post", "recib"],
        "keywords_en": ["webhook", "extern", "api", "http", "post", "receiv", "calback", "payload", "trigger", "incom"],
        "trigger": {"type": "webhook", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_notification",
                "params": {"channel": "log", "recipients": "admin", "message": "Webhook recibido: $input.body"},
            },
        ],
    },
    {
        "name": "archivo_nuevo",
        "label": "Procesar archivo nuevo",
        "description_es": "Cuando se crea un archivo nuevo en una carpeta, procesarlo",
        "description_en": "When a new file is created in a folder, process it",
        "keywords_es": ["archiv", "nuev", "carpet", "directori", "csv", "excel", "sub"],
        "keywords_en": ["file", "new", "folder", "directori", "csv", "excel", "upload", "creat", "document", "attacht", "import"],
        "trigger": {"type": "event", "config": {"event": "file.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_notification",
                "params": {"channel": "log", "recipients": "admin", "message": "Archivo nuevo: $input.filename"},
            },
        ],
    },
    # ── Templates nuevos (v2.0 — producción) ─────────────────────────
    {
        "name": "email_lead_nuevo",
        "label": "Notificar lead nuevo por email",
        "description_es": "Cuando llega un lead nuevo, enviar email al equipo de ventas",
        "description_en": "When a new lead arrives, send email to sales team",
        "keywords_es": ["lead", "nuev", "email", "notific", "avis", "vent", "lleg", "recib", "contact"],
        "keywords_en": ["lead", "new", "email", "notif", "alert", "sale", "arriv", "receiv", "contact"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Nuevo lead recibido",
                    "body": "Se ha registrado un nuevo lead en el sistema.",
                },
            },
        ],
    },
    {
        "name": "whatsapp_lead_nuevo",
        "label": "Notificar lead nuevo por WhatsApp",
        "description_es": "Cuando llega un lead nuevo, enviar WhatsApp al equipo",
        "description_en": "When a new lead arrives, send WhatsApp to team",
        "keywords_es": ["whatsapp", "lead", "nuev", "notific", "avis", "mensaj", "lleg"],
        "keywords_en": ["whatsapp", "lead", "new", "notif", "alert", "messag", "arriv"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "whatsapp",
                "action": "send_message",
                "params": {
                    "to": "$slot.phone_admin",
                    "message": "Nuevo lead recibido en el sistema",
                },
            },
        ],
    },
    {
        "name": "telegram_mensaje_grupo",
        "label": "Enviar mensaje a grupo de Telegram",
        "description_es": "Enviar mensaje a un grupo o canal de Telegram",
        "description_en": "Send message to a Telegram group or channel",
        "keywords_es": ["telegram", "mensaj", "grup", "canal", "envi", "notific", "bot"],
        "keywords_en": ["telegram", "messag", "group", "channel", "send", "notif", "bot"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "telegram",
                "action": "send_message",
                "params": {
                    "chat_id": "$slot.chat_id",
                    "text": "$slot.mensaje",
                },
            },
        ],
    },
    {
        "name": "stripe_crear_cliente",
        "label": "Crear cliente en Stripe",
        "description_es": "Crear un nuevo cliente en Stripe",
        "description_en": "Create a new customer in Stripe",
        "keywords_es": ["stripe", "client", "cre", "pag", "suscrip", "tarjet"],
        "keywords_en": ["stripe", "custom", "creat", "pay", "subscrib", "card"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "stripe",
                "action": "create_customer",
                "params": {
                    "name": "$slot.nombre",
                    "email": "$slot.email_destino",
                },
            },
        ],
    },
    {
        "name": "stripe_crear_pago",
        "label": "Crear pago en Stripe",
        "description_es": "Crear un payment intent en Stripe",
        "description_en": "Create a payment intent in Stripe",
        "keywords_es": ["stripe", "pag", "cobr", "payment", "intent", "tarjet", "checkout"],
        "keywords_en": ["stripe", "pay", "charg", "payment", "intent", "card", "checkout"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "stripe",
                "action": "create_payment_intent",
                "params": {
                    "amount": "$slot.monto",
                    "currency": "usd",
                    "description": "$slot.descripcion",
                },
            },
        ],
    },
    {
        "name": "mercadopago_preferencia",
        "label": "Crear preferencia de pago en MercadoPago",
        "description_es": "Crear una preferencia de pago en MercadoPago",
        "description_en": "Create a payment preference in MercadoPago",
        "keywords_es": ["mercadopago", "preferenc", "pag", "checkout", "cobr", "link"],
        "keywords_en": ["mercadopago", "preferenc", "pay", "checkout", "charg", "link"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "mercadopago",
                "action": "create_preference",
                "params": {
                    "items": [{"title": "$slot.descripcion", "quantity": 1, "unit_price": "$slot.monto"}],
                    "payer": {"email": "$slot.email_destino"},
                },
            },
        ],
    },
    {
        "name": "openai_chat",
        "label": "Chat con OpenAI",
        "description_es": "Enviar un prompt a OpenAI y obtener respuesta",
        "description_en": "Send a prompt to OpenAI and get response",
        "keywords_es": ["openai", "chat", "gpt", "ia", "prompt", "inteligencia", "artific"],
        "keywords_en": ["openai", "chat", "gpt", "ai", "prompt", "intellig", "artific"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "openai",
                "action": "chat_completion",
                "params": {
                    "messages": [{"role": "user", "content": "$slot.prompt"}],
                },
            },
        ],
    },
    {
        "name": "reporte_diario_crm",
        "label": "Reporte diario del CRM",
        "description_es": "Enviar reporte diario de actividad del CRM por email",
        "description_en": "Send daily CRM activity report by email",
        "keywords_es": ["report", "diari", "crm", "resumen", "email", "envi", "diari"],
        "keywords_en": ["report", "daili", "crm", "summari", "email", "send"],
        "trigger": {"type": "schedule", "config": {"cron": "0 9 * * *"}},
        "steps": [
            {"id": 1, "tool": "crm", "action": "list_leads", "params": {"limit": 100}},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Reporte diario del CRM",
                    "body": "$output.1",
                },
            },
        ],
    },
    {
        "name": "sync_inventario_shopify",
        "label": "Sincronizar inventario con Shopify",
        "description_es": "Sincronizar stock de productos con Shopify",
        "description_en": "Sync product stock with Shopify",
        "keywords_es": ["sync", "sincron", "inventari", "shopifi", "product", "stock", "tiend"],
        "keywords_en": ["sync", "invent", "shopifi", "product", "stock", "store"],
        "trigger": {"type": "schedule", "config": {"cron": "0 */6 * * *"}},
        "steps": [
            {"id": 1, "tool": "inventory", "action": "list_products", "params": {}},
            {
                "id": 2,
                "tool": "api_connector",
                "action": "post",
                "params": {
                    "url": "$slot.shopify_url",
                    "body": "$output.1",
                },
            },
        ],
    },
    {
        "name": "email_pago_recibido",
        "label": "Email cuando se recibe un pago",
        "description_es": "Enviar email cuando se confirma un pago",
        "description_en": "Send email when a payment is confirmed",
        "keywords_es": ["email", "pag", "recib", "confirm", "cobr", "notific"],
        "keywords_en": ["email", "pay", "receiv", "confirm", "charg", "notif"],
        "trigger": {"type": "event", "config": {"event": "payment.received"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_cliente",
                    "subject": "Pago confirmado",
                    "body": "Hemos recibido tu pago. Gracias.",
                },
            },
        ],
    },
    {
        "name": "lead_cualificado_ventas",
        "label": "Notificar lead cualificado a ventas",
        "description_es": "Cuando un lead pasa a cualificado, notificar a ventas",
        "description_en": "When a lead becomes qualified, notify sales",
        "keywords_es": ["lead", "cualific", "qualif", "vent", "notific", "etap", "avanz"],
        "keywords_en": ["lead", "qualif", "sale", "notif", "stage", "advanc"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.stage_changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Lead cualificado",
                    "body": "Un lead ha pasado a etapa cualificada.",
                },
            },
        ],
    },
    {
        "name": "factura_pagada_thankyou",
        "label": "Email de agradecimiento por factura pagada",
        "description_es": "Enviar email de agradecimiento cuando se paga una factura",
        "description_en": "Send thank you email when an invoice is paid",
        "keywords_es": ["factur", "pag", "agradec", "graci", "thank", "email"],
        "keywords_en": ["invoic", "paid", "thank", "email", "gratitud"],
        "trigger": {"type": "event", "config": {"event": "invoice.paid"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_cliente",
                    "subject": "Gracias por tu pago",
                    "body": "Hemos registrado el pago de tu factura. ¡Gracias por tu confianza!",
                },
            },
        ],
    },
    {
        "name": "stock_reposicion_automatica",
        "label": "Reposición automática de stock",
        "description_es": "Crear orden de reposición cuando stock está bajo",
        "description_en": "Create restock order when stock is low",
        "keywords_es": ["stock", "repos", "reord", "compr", "orden", "autmat", "bajo"],
        "keywords_en": ["stock", "restock", "reorder", "purchas", "order", "autmat", "low"],
        "trigger": {"type": "schedule", "config": {"cron": "0 8 * * *"}},
        "steps": [
            {"id": 1, "tool": "inventory", "action": "get_low_stock_products", "params": {}},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Órdenes de reposición sugeridas",
                    "body": "$output.1",
                },
            },
        ],
    },
    {
        "name": "notificacion_slack",
        "label": "Enviar notificación a Slack",
        "description_es": "Enviar un mensaje a un canal de Slack",
        "description_en": "Send a message to a Slack channel",
        "keywords_es": ["slack", "mensaj", "canal", "notific", "envi", "avis"],
        "keywords_en": ["slack", "messag", "channel", "notif", "send"],
        "trigger": {"type": "manual", "config": {}},
        "steps": [
            {
                "id": 1,
                "tool": "slack",
                "action": "send_message",
                "params": {
                    "channel": "$slot.canal",
                    "text": "$slot.mensaje",
                },
            },
        ],
    },
    {
        "name": "lead_perdido_analisis",
        "label": "Análisis de lead perdido",
        "description_es": "Cuando un lead se marca como perdido, registrar y notificar",
        "description_en": "When a lead is marked lost, log and notify",
        "keywords_es": ["lead", "perd", "lost", "analisis", "notific", "etap"],
        "keywords_en": ["lead", "lost", "analysi", "notif", "stage"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.stage_changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Lead perdido - análisis",
                    "body": "Un lead ha sido marcado como perdido. Revisar causas.",
                },
            },
        ],
    },
    {
        "name": "sync_drive_backup",
        "label": "Backup a Google Drive",
        "description_es": "Subir backup de la base de datos a Google Drive",
        "description_en": "Upload database backup to Google Drive",
        "keywords_es": ["backup", "drive", "googl", "sub", "nub", "respald"],
        "keywords_en": ["backup", "drive", "googl", "upload", "cloud", "snapshot"],
        "trigger": {"type": "schedule", "config": {"cron": "0 2 * * *"}},
        "steps": [
            {"id": 1, "tool": "system", "action": "backup_database", "params": {}},
            {
                "id": 2,
                "tool": "drive",
                "action": "upload_file",
                "params": {
                    "file": "$output.1",
                    "folder": "backups",
                },
            },
        ],
    },
    {
        "name": "encuesta_satisfaccion",
        "label": "Encuesta de satisfacción post-venta",
        "description_es": "Enviar encuesta de satisfacción después de una venta",
        "description_en": "Send satisfaction survey after a sale",
        "keywords_es": ["encuest", "satisfacc", "post", "vent", "email", "feedback", "calific"],
        "keywords_en": ["survey", "satisfact", "post", "sale", "email", "feedback"],
        "trigger": {"type": "event", "config": {"event": "crm.lead.stage_changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_cliente",
                    "subject": "¿Cómo fue tu experiencia?",
                    "body": "Nos gustaría conocer tu opinión. Responde esta encuesta: [link]",
                },
            },
        ],
    },
    {
        "name": "newsletter_semanal",
        "label": "Newsletter semanal a clientes",
        "description_es": "Enviar newsletter semanal a todos los clientes",
        "description_en": "Send weekly newsletter to all customers",
        "keywords_es": ["newsletter", "boletin", "semanal", "client", "email", "envi"],
        "keywords_en": ["newsletter", "weekli", "custom", "email", "send"],
        "trigger": {"type": "schedule", "config": {"cron": "0 10 * * 1"}},
        "steps": [
            {"id": 1, "tool": "crm", "action": "list_leads", "params": {"limit": 1000}},
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$output.1",
                    "subject": "Newsletter semanal",
                    "body": "$slot.mensaje",
                },
            },
        ],
    },
    {
        "name": "alerta_precio_cambio",
        "label": "Alerta de cambio de precio",
        "description_es": "Cuando cambia el precio de un producto, notificar",
        "description_en": "When a product price changes, notify",
        "keywords_es": ["preci", "cambi", "alert", "product", "notific", "actualiz"],
        "keywords_en": ["price", "chang", "alert", "product", "notif", "updat"],
        "trigger": {"type": "event", "config": {"event": "inventory.price_changed"}},
        "steps": [
            {
                "id": 1,
                "tool": "notification",
                "action": "send_email",
                "params": {
                    "to": "$slot.email_admin",
                    "subject": "Cambio de precio detectado",
                    "body": "Un producto ha cambiado de precio.",
                },
            },
        ],
    },
    {
        "name": "confirmacion_pedido",
        "label": "Confirmación de pedido por WhatsApp",
        "description_es": "Enviar confirmación de pedido por WhatsApp al cliente",
        "description_en": "Send order confirmation via WhatsApp to customer",
        "keywords_es": ["confirm", "ped", "whatsapp", "client", "envi", "notific"],
        "keywords_en": ["confirm", "order", "whatsapp", "custom", "send", "notif"],
        "trigger": {"type": "event", "config": {"event": "order.created"}},
        "steps": [
            {
                "id": 1,
                "tool": "whatsapp",
                "action": "send_text_message",
                "params": {
                    "to": "$slot.phone_cliente",
                    "text": "Hemos recibido tu pedido. Lo procesaremos pronto.",
                },
            },
        ],
    },
    # ── Bug 5 fix: NLU intents para WhatsApp ENTRANTE ───────────────────
    # Antes el NLU no parseaba texto de WhatsApp entrante. Estos intents
    # permiten que un mensaje WhatsApp sea clasificado y dispare un workflow.
    {
        "name": "whatsapp_lead_capture",
        "label": "Capturar lead desde WhatsApp entrante",
        "description_es": "Cuando llega un WhatsApp de un número nuevo, crear un lead en CRM",
        "description_en": "When a WhatsApp arrives from a new number, create a CRM lead",
        "keywords_es": ["whatsapp", "lead", "captur", "entr", "nuevo", "crm", "contact", "interes"],
        "keywords_en": ["whatsapp", "lead", "captur", "inbound", "new", "crm", "contact", "interest"],
        "trigger": {"type": "event", "config": {"event": "whatsapp.message.received"}},
        "steps": [
            {
                "id": 1,
                "tool": "crm",
                "action": "create_lead",
                "params": {
                    "name": "$slot.sender_name",
                    "phone": "$slot.sender_phone",
                    "source": "whatsapp",
                    "notes": "Lead capturado desde WhatsApp: $slot.message_text",
                },
            },
            {
                "id": 2,
                "tool": "whatsapp",
                "action": "send_text_message",
                "params": {
                    "to": "$slot.sender_phone",
                    "text": "¡Hola! Gracias por contactarnos. Te responderemos pronto.",
                },
            },
        ],
    },
    {
        "name": "whatsapp_auto_reply",
        "label": "Auto-respuesta de WhatsApp",
        "description_es": "Responder automáticamente WhatsApps recibidos fuera de horario",
        "description_en": "Auto-reply to WhatsApp messages received outside business hours",
        "keywords_es": ["whatsapp", "auto", "respuest", "fuera", "horario", "automatic", "bot", "contest"],
        "keywords_en": ["whatsapp", "auto", "reply", "outside", "hours", "automatic", "bot", "answer"],
        "trigger": {"type": "event", "config": {"event": "whatsapp.message.received"}},
        "steps": [
            {
                "id": 1,
                "tool": "whatsapp",
                "action": "send_text_message",
                "params": {
                    "to": "$slot.sender_phone",
                    "text": "Gracias por tu mensaje. Nuestro horario es Lun-Vie 9-18h.",
                },
            },
        ],
    },
    {
        "name": "whatsapp_notify_admin",
        "label": "Notificar al admin por WhatsApp entrante",
        "description_es": "Cuando llega un WhatsApp, reenviarlo al admin",
        "description_en": "When a WhatsApp arrives, forward it to admin",
        "keywords_es": ["whatsapp", "admin", "notific", "avis", "reenv", "entr", "alert"],
        "keywords_en": ["whatsapp", "admin", "notif", "alert", "forward", "inbound"],
        "trigger": {"type": "event", "config": {"event": "whatsapp.message.received"}},
        "steps": [
            {
                "id": 1,
                "tool": "whatsapp",
                "action": "send_text_message",
                "params": {
                    "to": "$slot.phone_admin",
                    "text": "📩 WhatsApp entrante de $slot.sender_phone: $slot.message_text",
                },
            },
        ],
    },
]
