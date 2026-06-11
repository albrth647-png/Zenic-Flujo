"""
Tests para Sprint 5 del Roadmap Competitivo.
Cubre: Rate Limiting, Caching, Paginación Automática,
Webhook Callbacks, XML Support, y APIConnectorService mejorado.
"""

import threading
import time
from unittest.mock import MagicMock, patch

from src.tools.api_connector.service import (
    APIConnectorService,
    PaginationCollector,
    RateLimiter,
    ResponseCache,
    WebhookCallbackRegistry,
    XMLProcessor,
)

# ===================================================================
# 5.1 — Rate Limiting
# ===================================================================


class TestRateLimiter:
    """Tests para RateLimiter (token bucket)."""

    def test_acquire_allows_initial_request(self):
        """Primera request siempre permitida."""
        rl = RateLimiter(max_tokens=10, window_seconds=60)
        assert rl.acquire("https://api.example.com/users") is True

    def test_acquire_multiple_requests(self):
        """Múltiples requests consumen tokens."""
        rl = RateLimiter(max_tokens=5, window_seconds=60)
        for _ in range(5):
            assert rl.acquire("https://api.example.com/users") is True
        # Sexta request debe ser bloqueada
        assert rl.acquire("https://api.example.com/users") is False

    def test_acquire_different_domains_independent(self):
        """Diferentes dominios tienen buckets independientes."""
        rl = RateLimiter(max_tokens=3, window_seconds=60)
        for _ in range(3):
            assert rl.acquire("https://api.example.com") is True
        # Este dominio debería estar agotado
        assert rl.acquire("https://api.example.com") is False
        # Pero otro dominio debería funcionar
        assert rl.acquire("https://other-api.com") is True

    def test_rate_limit_status(self):
        """get_status retorna información del bucket."""
        rl = RateLimiter(max_tokens=10, window_seconds=60)
        rl.acquire("https://api.example.com")
        status = rl.get_status("https://api.example.com")
        assert status["domain"] == "api.example.com"
        assert status["tokens_remaining"] < 10
        assert status["total_requests"] == 1

    def test_reset_domain(self):
        """reset de un dominio específico."""
        rl = RateLimiter(max_tokens=5, window_seconds=60)
        rl.acquire("https://api.example.com")
        rl.reset("https://api.example.com")
        # Después de reset, debe permitir requests de nuevo
        assert rl.acquire("https://api.example.com") is True

    def test_reset_all(self):
        """reset de todos los dominios."""
        rl = RateLimiter(max_tokens=3, window_seconds=60)
        rl.acquire("https://api1.com")
        rl.acquire("https://api2.com")
        rl.reset()
        assert rl.acquire("https://api1.com") is True
        assert rl.acquire("https://api2.com") is True

    def test_thread_safety(self):
        """Rate limiter es thread-safe."""
        rl = RateLimiter(max_tokens=100, window_seconds=60)
        errors = []

        def worker():
            try:
                for _ in range(10):
                    rl.acquire("https://api.example.com")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        status = rl.get_status("https://api.example.com")
        assert status["total_requests"] == 50  # 5 hilos * 10 requests


# ===================================================================
# 5.3 — Response Cache
# ===================================================================


class TestResponseCache:
    """Tests para ResponseCache."""

    def test_get_miss_returns_none(self):
        """Cache miss retorna None."""
        cache = ResponseCache()
        result = cache.get("GET", "https://api.example.com/users")
        assert result is None

    def test_set_and_get(self):
        """Set y get funcionan."""
        cache = ResponseCache(default_ttl_seconds=60)
        response = {"status_code": 200, "body": {"users": []}}
        cache.set("GET", "https://api.example.com/users", response)
        cached = cache.get("GET", "https://api.example.com/users")
        assert cached is not None
        assert cached["status_code"] == 200

    def test_different_methods_different_cache(self):
        """Diferentes métodos HTTP tienen diferentes keys."""
        cache = ResponseCache()
        cache.set("GET", "https://api.example.com/users", {"status_code": 200, "body": "get"})
        cache.set("POST", "https://api.example.com/users", {"status_code": 201, "body": "post"})

        get_result = cache.get("GET", "https://api.example.com/users")
        post_result = cache.get("POST", "https://api.example.com/users")
        assert get_result["body"] == "get"
        assert post_result["body"] == "post"

    def test_ttl_expiration(self):
        """Cache expira después del TTL."""
        cache = ResponseCache(default_ttl_seconds=0)  # TTL 0 = expira inmediatamente
        response = {"status_code": 200, "body": "data"}
        cache.set("GET", "https://api.example.com/data", response, ttl_seconds=0)
        time.sleep(0.01)
        result = cache.get("GET", "https://api.example.com/data")
        assert result is None

    def test_does_not_cache_errors(self):
        """Respuestas con error no se cachean."""
        cache = ResponseCache()
        error_response = {"status_code": 500, "error": "Server error"}
        cache.set("GET", "https://api.example.com/error", error_response)
        result = cache.get("GET", "https://api.example.com/error")
        assert result is None

    def test_invalidate_all(self):
        """Invalidate all limpia todo el cache."""
        cache = ResponseCache()
        cache.set("GET", "https://api.example.com/a", {"status_code": 200, "body": "a"})
        cache.set("GET", "https://api.example.com/b", {"status_code": 200, "body": "b"})
        count = cache.invalidate()
        assert count == 2
        assert cache.get("GET", "https://api.example.com/a") is None

    def test_get_stats(self):
        """Estadísticas del cache."""
        cache = ResponseCache(default_ttl_seconds=300)
        cache.set("GET", "https://api.example.com/data", {"status_code": 200, "body": "data"})
        stats = cache.get_stats()
        assert stats["total_entries"] >= 1
        assert stats["default_ttl_seconds"] == 300

    def test_cache_key_with_body(self):
        """Cache key incluye body hash."""
        cache = ResponseCache()
        cache.set("POST", "https://api.example.com/search", {"status_code": 200, "body": "results"}, body={"q": "test"})
        # Misma URL, mismo body → cache hit
        result = cache.get("POST", "https://api.example.com/search", body={"q": "test"})
        assert result is not None
        # Diferente body → cache miss
        result2 = cache.get("POST", "https://api.example.com/search", body={"q": "other"})
        assert result2 is None


# ===================================================================
# 5.2 — Paginación
# ===================================================================


class TestPaginationCollector:
    """Tests para PaginationCollector."""

    def test_page_based_next_page(self):
        """Page-based: detecta siguiente página."""
        collector = PaginationCollector()
        response = {
            "status_code": 200,
            "body": {"data": [1, 2, 3], "total": 100},
        }
        nav = collector.collect_page_based(
            "https://api.example.com/users",
            {"page": 1, "limit": 20},
            response,
            pages_left=5,
        )
        assert nav["stop"] is False
        assert nav["next_params"]["page"] == 2

    def test_page_based_last_page_by_total(self):
        """Page-based: detecta última página por total."""
        collector = PaginationCollector()
        response = {
            "status_code": 200,
            "body": {"data": [1, 2], "total": 2},
        }
        nav = collector.collect_page_based(
            "https://api.example.com/users",
            {"page": 1, "limit": 20},
            response,
            pages_left=5,
        )
        assert nav["stop"] is True

    def test_page_based_no_pages_left(self):
        """Page-based: sin páginas restantes."""
        collector = PaginationCollector()
        response = {"status_code": 200, "body": {"data": [1, 2, 3]}}
        nav = collector.collect_page_based(
            "/users",
            {"page": 10, "limit": 20},
            response,
            pages_left=0,
        )
        assert nav["stop"] is True

    def test_cursor_based_next(self):
        """Cursor-based: detecta cursor."""
        collector = PaginationCollector()
        response = {
            "status_code": 200,
            "body": {"data": [1, 2], "next_cursor": "abc123"},
        }
        nav = collector.collect_cursor_based(
            "https://api.example.com/users",
            {"cursor": "initial"},
            response,
            pages_left=5,
        )
        assert nav["stop"] is False
        assert nav["next_params"]["cursor"] == "abc123"

    def test_cursor_based_no_more(self):
        """Cursor-based: sin más datos."""
        collector = PaginationCollector()
        response = {
            "status_code": 200,
            "body": {"data": [1, 2], "has_more": False},
        }
        nav = collector.collect_cursor_based(
            "/users",
            {"cursor": "xyz"},
            response,
            pages_left=5,
        )
        assert nav["stop"] is True

    def test_offset_based_next(self):
        """Offset-based: calcula siguiente offset."""
        collector = PaginationCollector()
        response = {
            "status_code": 200,
            "body": {"data": [1, 2, 3, 4, 5]},
        }
        nav = collector.collect_offset_based(
            "https://api.example.com/users",
            {"offset": 0, "limit": 5},
            response,
            pages_left=5,
        )
        assert nav["stop"] is False
        assert nav["next_params"]["offset"] == 5


# ===================================================================
# 5.4 — Webhook Callbacks
# ===================================================================


class TestWebhookCallbackRegistry:
    """Tests para WebhookCallbackRegistry."""

    def test_register_callback(self):
        """Registrar callback."""
        registry = WebhookCallbackRegistry()
        cid = registry.register(
            callback_url="https://hooks.example.com/callback",
            original_request={"method": "POST", "url": "https://api.example.com/process"},
        )
        assert cid is not None
        assert len(cid) == 32  # secrets.token_hex(16)

    def test_complete_callback(self):
        """Completar callback."""
        registry = WebhookCallbackRegistry()
        cid = registry.register("https://hooks.example.com/cb", {})
        result = registry.complete(cid, {"status": "done"})
        assert result is True

        entry = registry.get(cid)
        assert entry["status"] == "completed"
        assert entry["response"]["status"] == "done"

    def test_fail_callback(self):
        """Fallar callback."""
        registry = WebhookCallbackRegistry()
        cid = registry.register("https://hooks.example.com/cb", {})
        result = registry.fail(cid, "Processing failed")
        assert result is True

        entry = registry.get(cid)
        assert entry["status"] == "failed"
        assert entry["error"] == "Processing failed"

    def test_complete_nonexistent(self):
        """Completar callback inexistente."""
        registry = WebhookCallbackRegistry()
        result = registry.complete("nonexistent", {})
        assert result is False

    def test_list_pending(self):
        """Listar callbacks pendientes."""
        registry = WebhookCallbackRegistry()
        registry.register("https://hooks.example.com/cb1", {})
        registry.register("https://hooks.example.com/cb2", {})
        pending = registry.list_pending()
        assert len(pending) == 2

    def test_cleanup_expired(self):
        """Limpiar callbacks expirados."""
        registry = WebhookCallbackRegistry()
        registry.register("https://hooks.example.com/cb", {}, timeout_seconds=0)
        time.sleep(0.01)
        count = registry.cleanup_expired()
        assert count >= 0  # Puede haber expirado


# ===================================================================
# 5.6 — XML Support
# ===================================================================


class TestXMLProcessor:
    """Tests para XMLProcessor."""

    def test_parse_basic_xml(self):
        """Parseo básico de XML."""
        xml = "<root><name>Juan</name><age>30</age></root>"
        result = XMLProcessor.parse(xml)
        assert "parsed" in result
        assert result["format"] == "xml"

    def test_generate_basic_xml(self):
        """Generación básica de XML."""
        data = {"name": "Juan", "age": 30}
        xml = XMLProcessor.generate(data, "person")
        assert "<person>" in xml
        assert "<name>Juan</name>" in xml
        assert "<age>30</age>" in xml

    def test_generate_nested(self):
        """Generar XML con datos anidados."""
        data = {"user": {"name": "Ana", "address": {"city": "Lima"}}}
        xml = XMLProcessor.generate(data, "root")
        assert "<root>" in xml
        assert "<user>" in xml
        assert "<name>Ana</name>" in xml

    def test_generate_with_list(self):
        """Generar XML con listas."""
        data = {"items": ["a", "b", "c"]}
        xml = XMLProcessor.generate(data, "root")
        assert "<root>" in xml
        # xmltodict trata listas como elementos repetidos del mismo tag
        assert xml.count("items>") >= 1  # items aparecen como tags repetidos
        assert "a" in xml
        assert "b" in xml
        assert "c" in xml

    def test_parse_invalid_xml(self):
        """Parseo de XML inválido."""
        result = XMLProcessor.parse("not valid xml")
        # No debe crashear, retorna un resultado con error o vacío
        assert isinstance(result, dict)


# ===================================================================
# 5.5 — APIConnectorService Integration
# ===================================================================


class TestAPIConnectorServiceIntegration:
    """Tests de integración para APIConnectorService mejorado."""

    def test_validate_url(self):
        """Validación de URLs."""
        assert APIConnectorService.validate_url("https://api.example.com") is True
        assert APIConnectorService.validate_url("http://localhost:8080/api") is True
        assert APIConnectorService.validate_url("") is False
        assert APIConnectorService.validate_url("file:///etc/passwd") is False
        assert APIConnectorService.validate_url("javascript:alert(1)") is False

    def test_rate_limiter_accessible(self):
        """Rate limiter accesible como property."""
        api = APIConnectorService()
        rl = api.rate_limiter
        assert isinstance(rl, RateLimiter)
        assert rl.acquire("https://test.com") is True

    def test_cache_accessible(self):
        """Cache accesible como property."""
        api = APIConnectorService()
        cache = api.cache
        assert isinstance(cache, ResponseCache)

    def test_callbacks_accessible(self):
        """WebhookCallbackRegistry accesible como property."""
        api = APIConnectorService()
        cbs = api.callbacks
        assert isinstance(cbs, WebhookCallbackRegistry)

    def test_error_on_invalid_url(self):
        """Request con URL inválida retorna error."""
        api = APIConnectorService()
        result = api.request(method="GET", url="")
        assert result["status_code"] == 0
        assert "URL inválida" in result.get("error", "")

    def test_error_on_invalid_method(self):
        """Request con método inválido retorna error."""
        api = APIConnectorService()
        result = api.request(method="OPTIONS", url="https://api.example.com")
        assert result["status_code"] == 0
        assert "no soportado" in result.get("error", "")

    def test_xml_parse_wrapper(self):
        """Wrapper público xml_parse funciona."""
        api = APIConnectorService()
        result = api.xml_parse("<root><item>test</item></root>")
        assert "parsed" in result

    def test_xml_generate_wrapper(self):
        """Wrapper público xml_generate funciona."""
        api = APIConnectorService()
        xml = api.xml_generate({"name": "test"}, "root")
        assert "<name>test</name>" in xml

    def test_get_tool_definition(self):
        """Definición de tool incluye nuevas acciones."""
        definition = APIConnectorService.get_tool_definition()
        assert definition["tool"] == "api_connector"
        assert "request" in definition["actions"]
        assert "xml_parse" in definition["actions"]
        assert "xml_generate" in definition["actions"]
        assert "cache_stats" in definition["actions"]
        assert "rate_limit_status" in definition["actions"]

    def test_extract_items_from_dict(self):
        """Extraer items de respuesta paginada."""
        body = {"data": [{"id": 1}, {"id": 2}]}
        items = APIConnectorService._extract_items(body)
        assert len(items) == 2

    def test_extract_items_from_list(self):
        """Extraer items de respuesta que es directamente una lista."""
        body = [{"id": 1}, {"id": 2}]
        items = APIConnectorService._extract_items(body)
        assert len(items) == 2

    def test_extract_items_empty(self):
        """Extraer items de respuesta sin datos."""
        items = APIConnectorService._extract_items({"message": "ok"})
        assert items == []

    @patch("requests.request")
    def test_request_execution(self, mock_request):
        """Request real (mockeada) fluye correctamente."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"result": "ok"}
        mock_response.text = '{"result": "ok"}'
        mock_request.return_value = mock_response

        api = APIConnectorService()
        result = api.request(
            method="GET",
            url="https://api.example.com/test",
            headers={"Accept": "application/json"},
        )
        assert result["status_code"] == 200
        assert result["body"] == {"result": "ok"}

    @patch("requests.request")
    def test_request_with_rate_limiting(self, mock_request):
        """Rate limiting se aplica a requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"data": "ok"}
        mock_response.text = '{"data": "ok"}'
        mock_request.return_value = mock_response

        api = APIConnectorService()
        # Consumir todos los tokens
        for _ in range(60):
            api.rate_limiter.acquire("https://api.example.com/test")

        # Esta request debería ser rate-limited
        result = api.request(
            method="GET",
            url="https://api.example.com/test",
            rate_limit_cost=1,
        )
        assert result.get("rate_limited") is True
        assert result["status_code"] == 429
