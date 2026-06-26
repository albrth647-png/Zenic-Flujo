"""
API Connector package — Sprint 5.
"""

from src.hat.level5_tools.data.api_connector.pagination import PaginationCollector
from src.hat.level5_tools.data.api_connector.rate_limiter import RateLimiter
from src.hat.level5_tools.data.api_connector.response_cache import ResponseCache
from src.hat.level5_tools.data.api_connector.service import APIConnectorService
from src.hat.level5_tools.data.api_connector.webhooks import WebhookCallbackRegistry
from src.hat.level5_tools.data.api_connector.xml_processor import XMLProcessor

__all__ = [
    "APIConnectorService",
    "PaginationCollector",
    "RateLimiter",
    "ResponseCache",
    "WebhookCallbackRegistry",
    "XMLProcessor",
]
