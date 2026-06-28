"""Shared domain keywords — used by both orbital_router and fsm/disambiguator.

Imported by fsm/disambiguator.py to avoid duplication.
"""
# These will be populated in M8 when we refactor tick_router and fsm.
DOMAIN_KEYWORDS = {
    "operaciones": ("cliente", "lead", "venta", "factura", "invoice", "producto", "stock", "inventario", "pago"),
    "comunicaciones": ("email", "correo", "whatsapp", "slack", "telegram", "notificar", "mensaje", "gmail"),
    "datos_auto": ("código", "python", "regla", "plantilla", "openai", "ollama", "api", "http", "sql", "sheets"),
}
