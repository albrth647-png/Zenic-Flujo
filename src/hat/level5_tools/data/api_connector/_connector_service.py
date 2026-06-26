"""
APIConnectorService Core — Orquestador de peticiones HTTP
===========================================================

Extraído de service.py. Responsabilidad única: orquestar peticiones HTTP
componiendo: RateLimiter, ResponseCache, PaginationCollector,
WebhookCallbackRegistry, XMLProcessor y helpers HTTP.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar, TypedDict
from urllib.parse import urlparse

from src.hat.level5_tools.data.api_connector._connector_helpers import (
    ApiResult,
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
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class PaginationConfig(TypedDict, total=False):
    """Configuración de paginación automática."""
    start_page: int
    limit: int
    start_offset: int
    cursor_param: str
    start_cursor: str


class APIConnectorService:
    """
    Conecta con APIs externas vía HTTP — Versión Mejorada (Sprint 5).

    Compone RateLimiter, ResponseCache, PaginationCollector,
    WebhookCallbackRegistry y XMLProcessor desde submódulos.
    La ejecución HTTP está en _connector_helpers.py.
    """

    ALLOWED_METHODS: ClassVar[list[str]] = ["GET", "POST", "PUT", "DELETE", "PATCH"]

    def __init__(self):
        self._rate_limiter = RateLimiter(max_tokens=60, window_seconds=60)
        self._cache = ResponseCache(default_ttl_seconds=300)
        self._paginator = PaginationCollector(max_pages=10)
        self._callbacks = WebhookCallbackRegistry()
        self._xml = XMLProcessor()

    # ── Propiedades para acceso directo ─────────────────────

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    @property
    def callbacks(self) -> WebhookCallbackRegistry:
        return self._callbacks

    # ── Request principal ───────────────────────────────────

    def request(
        self,
        method: str = "GET",
        url: str = "",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        auth_type: str = "none",
        auth_credentials: dict[str, Any] | None = None,
        timeout: int = 30,
        cache_ttl: int | None = None,
        use_cache: bool = True,
        pagination: str | None = None,
        max_pages: int = 5,
        pagination_params: PaginationConfig | None = None,
        response_format: str = "auto",
        async_callback_url: str | None = None,
        rate_limit_cost: int = 1,
    ) -> ApiResult:
        """Realiza una petición HTTP con rate limiting, caching, paginación y callbacks."""
        start_time = time.time()

        if not validate_url(url):
            return _error(f"URL inválida: {url}", start_time)

        method = method.upper()
        if method not in self.ALLOWED_METHODS:
            return _error(f"Método no soportado: {method}", start_time)

        # Rate limiting
        if rate_limit_cost > 0 and not self._rate_limiter.acquire(url, rate_limit_cost):
            return {
                "status_code": 429,
                "error": f"Rate limit excedido para {urlparse(url).netloc}",
                "duration_ms": _elapsed(start_time),
                "rate_limited": True,
            }

        # Cache check (solo GET sin paginación)
        if use_cache and method == "GET" and not pagination:
            cached = self._cache.get(method, url, body)
            if cached:
                cached["from_cache"] = True
                cached["duration_ms"] = _elapsed(start_time)
                return cached

        # Callback async
        callback_id = None
        if async_callback_url:
            callback_id = self._callbacks.register(
                callback_url=async_callback_url,
                original_request={"method": method, "url": url, "headers": headers, "body": body, "params": params},
            )

        # Ejecutar con o sin paginación
        if pagination and method == "GET":
            result = self._request_with_pagination(
                method=method, url=url, headers=headers, params=params,
                auth_type=auth_type, auth_credentials=auth_credentials, timeout=timeout,
                pagination=pagination, max_pages=max_pages, pagination_params=pagination_params,
                start_time=start_time,
            )
        else:
            result = execute_request(
                method=method, url=url, headers=headers, body=body, params=params,
                auth_type=auth_type, auth_credentials=auth_credentials, timeout=timeout,
                start_time=start_time,
            )

        # Transformar respuesta
        if result.get("status_code", 0) < 400:
            result = transform_response(result, response_format)

        # Cachear resultado exitoso
        if use_cache and method == "GET" and result.get("status_code", 0) < 400 and not pagination:
            self._cache.set(method, url, result, body, cache_ttl)

        if async_callback_url:
            result["async"] = True
            result["callback_id"] = callback_id
            result["callback_url"] = async_callback_url

        return result

    # ── Request con paginación ─────────────────────────────

    def _request_with_pagination(
        self,
        method: str, url: str, headers: dict[str, str] | None,
        params: dict[str, str] | None,
        auth_type: str, auth_credentials: dict[str, Any] | None, timeout: int,
        pagination: str, max_pages: int, pagination_params: PaginationConfig | None,
        start_time: float,
    ) -> ApiResult:
        """Recolecta múltiples páginas de un endpoint paginado."""
        all_items = []
        current_params = dict(params or {})
        current_url = url
        pages = 0
        errors = []

        pparams = dict(pagination_params or {})
        if pagination == "page":
            current_params["page"] = pparams.get("start_page", 1)
            current_params["limit"] = pparams.get("limit", 20)
        elif pagination == "offset":
            current_params["offset"] = pparams.get("start_offset", 0)
            current_params["limit"] = pparams.get("limit", 20)
        elif pagination == "cursor":
            cursor_param = pparams.get("cursor_param", "cursor")
            if "start_cursor" in pparams:
                current_params[cursor_param] = pparams["start_cursor"]

        while pages < max_pages:
            try:
                response = execute_request(
                    method=method, url=current_url, headers=headers, body=None,
                    params=current_params, auth_type=auth_type,
                    auth_credentials=auth_credentials, timeout=timeout,
                    start_time=time.time(),
                )
            except Exception as e:
                errors.append(str(e))
                break

            if response.get("status_code", 0) >= 400:
                errors.append(f"HTTP {response['status_code']}: {response.get('body', response.get('error', ''))}")
                if response.get("body"):
                    all_items.append(response["body"])
                break

            body = response.get("body", {})
            items = extract_items(body)
            if items:
                all_items.extend(items)

            pages += 1

            if pagination == "page":
                nav = self._paginator.collect_page_based(current_url, current_params, response, max_pages - pages)
            elif pagination == "cursor":
                nav = self._paginator.collect_cursor_based(current_url, current_params, response, max_pages - pages)
            elif pagination == "offset":
                nav = self._paginator.collect_offset_based(current_url, current_params, response, max_pages - pages)
            else:
                nav = {"next_url": None, "next_params": None, "stop": True}

            if nav.get("stop"):
                break
            current_url = nav["next_url"] or current_url
            current_params = nav["next_params"] or current_params

        final_status = 200 if all_items else 500
        result = {
            "status_code": final_status,
            "body": all_items,
            "pagination": {"strategy": pagination, "pages_collected": pages, "total_items": len(all_items), "max_pages": max_pages},
            "duration_ms": _elapsed(start_time),
        }
        if errors:
            result["pagination_errors"] = errors
        return result

    # ── XML público ───────────────────────────────────────

    def xml_parse(self, xml_string: str) -> dict:
        return self._xml.parse(xml_string)

    def xml_generate(self, data: dict, root_name: str = "root") -> str:
        return self._xml.generate(data, root_name)

    # ── Validación de URL ────────────────────────────────

    @staticmethod
    def validate_url(url: str) -> bool:
        return validate_url(url)

    @staticmethod
    def _extract_items(body: Any) -> list:
        """Extrae items de un body paginado. Backward compat."""
        return extract_items(body)

    # ── Tool definition ────────────────────────────────────

    @staticmethod
    def get_tool_definition() -> dict:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "api_connector",
            "name": "API Connector Plus",
            "description": "Conecta con APIs externas vía HTTP con rate limiting, paginación y caching",
            "actions": {
                "request": {
                    "name": "Petición HTTP",
                    "description": "Realiza una petición HTTP con soporte avanzado",
                    "params": [
                        {"name": "method", "type": "select", "options": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                         "required": True, "default": "GET", "label": "Método HTTP"},
                        {"name": "url", "type": "string", "required": True, "label": "URL",
                         "placeholder": "https://api.example.com/endpoint"},
                        {"name": "headers", "type": "dict", "required": False, "default": {}, "label": "Headers"},
                        {"name": "body", "type": "dict", "required": False, "default": {}, "label": "Body (JSON)"},
                        {"name": "params", "type": "dict", "required": False, "default": {}, "label": "Query Params"},
                        {"name": "auth_type", "type": "select",
                         "options": ["none", "bearer", "basic", "api-key"],
                         "required": False, "default": "none", "label": "Autenticación"},
                        {"name": "auth_credentials", "type": "dict", "required": False, "default": {}, "label": "Credenciales"},
                        {"name": "timeout", "type": "number", "required": False, "default": 30, "label": "Timeout (segundos)"},
                        {"name": "pagination", "type": "select",
                         "options": [None, "page", "cursor", "offset"],
                         "required": False, "default": None, "label": "Paginación automática"},
                        {"name": "max_pages", "type": "number", "required": False, "default": 5, "label": "Máx. páginas"},
                        {"name": "use_cache", "type": "boolean", "required": False, "default": True, "label": "Usar cache"},
                        {"name": "cache_ttl", "type": "number", "required": False, "default": 300, "label": "TTL cache (seg)"},
                        {"name": "response_format", "type": "select",
                         "options": ["auto", "json", "xml", "text"],
                         "required": False, "default": "auto", "label": "Formato respuesta"},
                        {"name": "async_callback_url", "type": "string", "required": False, "default": "", "label": "URL callback"},
                    ],
                },
                "xml_parse": {
                    "name": "Parsear XML", "description": "Convierte XML a dict",
                    "params": [{"name": "xml_string", "type": "string", "required": True, "label": "String XML"}],
                },
                "xml_generate": {
                    "name": "Generar XML", "description": "Convierte dict a XML",
                    "params": [
                        {"name": "data", "type": "dict", "required": True, "label": "Datos"},
                        {"name": "root_name", "type": "string", "required": False, "default": "root", "label": "Elemento raíz"},
                    ],
                },
                "cache_stats": {
                    "name": "Estadísticas de cache", "description": "Muestra estado del cache",
                    "params": [],
                },
                "rate_limit_status": {
                    "name": "Estado de rate limiting", "description": "Muestra estado de los buckets",
                    "params": [],
                },
            },
        }
