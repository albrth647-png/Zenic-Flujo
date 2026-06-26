"""
APIConnectorService — Fachada pública del conector de APIs
=============================================================

API pública única. Delega en:
• :mod:`._connector_service` — APIConnectorService (orquestación)
• :mod:`._connector_helpers` — Helpers HTTP (request, parse, transform)

Retrocompatible: importaciones existentes no requieren cambios.

Evolución: 2 archivos (service.py + http_client.py) → 3 archivos
(service.py facade + _connector_service.py + _connector_helpers.py)
"""

# Re-exportar desde submódulos internos
from src.hat.level5_tools.data.api_connector._connector_service import (
    APIConnectorService,
)
from src.hat.level5_tools.data.api_connector._connector_helpers import (
    _elapsed,
    _error,
    execute_request,
    extract_items,
    transform_response,
    validate_url,
)
from src.hat.level5_tools.data.api_connector.pagination import PaginationCollector
from src.hat.level5_tools.data.api_connector.rate_limiter import RateLimiter
from src.hat.level5_tools.data.api_connector.response_cache import ResponseCache
from src.hat.level5_tools.data.api_connector.webhooks import WebhookCallbackRegistry
from src.hat.level5_tools.data.api_connector.xml_processor import XMLProcessor

# ── Re-exportar clases de submódulos para compatibilidad ─────
__all__ = [
    "APIConnectorService",
    "PaginationCollector",
    "RateLimiter",
    "ResponseCache",
    "WebhookCallbackRegistry",
    "XMLProcessor",
]
