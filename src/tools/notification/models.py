"""
Workflow Determinista — Notification Models
Modelos y constantes para el sistema de notificaciones.
"""

# Canales de notificación soportados
NOTIFICATION_CHANNELS = ["email", "log", "slack", "sms"]

# Estados de una notificación
NOTIFICATION_STATUSES = ["pending", "sent", "failed", "queued"]

# Plantillas de email predefinidas
EMAIL_TEMPLATES = {
    "welcome": {
        "subject": "¡Bienvenido!",
        "body": "Hola {nombre}, gracias por registrarte en nuestro servicio.",
    },
    "invoice_created": {
        "subject": "Nueva factura #{numero}",
        "body": "Estimado/a {cliente}, se ha generado la factura #{numero} por un total de ${total}.",
    },
    "invoice_overdue": {
        "subject": "Factura vencida #{numero}",
        "body": "Estimado/a {cliente}, la factura #{numero} por ${total} está vencida. Por favor, realice el pago a la brevedad.",
    },
    "stock_low": {
        "subject": "Alerta: Stock bajo — {producto}",
        "body": "El producto '{producto}' tiene un stock de {stock} unidades, por debajo del mínimo de {min_stock}.",
    },
    "birthday": {
        "subject": "¡Feliz cumpleaños, {nombre}!",
        "body": "Querido/a {nombre}, te deseamos un muy feliz cumpleaños. ¡Que tengas un día maravilloso!",
    },
}
