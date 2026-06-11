"""
Workflow Determinista — APIConnectorService Mejorado
=======================================================

Sprint 5 del Roadmap Competitivo.
Mejoras sobre el APIConnectorService original:

5.1. Rate limiting por dominio (token bucket)
5.2. Paginación automática (page, cursor, offset)
5.3. Caching de respuestas con TTL
5.4. Webhook receiver para callbacks asíncronos
5.5. Transform JSON → dict automática
5.6. XML support (parse + generate con xmltodict)
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, ClassVar
from urllib.parse import urlparse

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


# ===================================================================
# 5.1 — Rate Limiting (Token Bucket por dominio)
# ===================================================================


class RateLimiter:
    """
    Rate limiter usando token bucket algorithm.

    Cada dominio tiene su propio bucket con:
    - max_tokens: máximo de requests permitidos en la ventana
    - window_seconds: duración de la ventana en segundos
    - tokens: tokens disponibles actualmente
    - last_refill: timestamp del último rellenado

    Thread-safe mediante RLock.
    """

    def __init__(self, max_tokens: int = 60, window_seconds: int = 60):
        self._max_tokens = max_tokens
        self._window_seconds = window_seconds
        self._buckets: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _get_domain(self, url: str) -> str:
        """Extrae el dominio de una URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"

    def _get_bucket(self, domain: str) -> dict:
        """Obtiene o crea un bucket para un dominio."""
        if domain not in self._buckets:
            self._buckets[domain] = {
                "tokens": self._max_tokens,
                "last_refill": time.time(),
                "max_tokens": self._max_tokens,
                "total_requests": 0,
                "blocked_requests": 0,
            }
        return self._buckets[domain]

    def _refill(self, bucket: dict) -> None:
        """Rellena tokens según el tiempo transcurrido."""
        now = time.time()
        elapsed = now - bucket["last_refill"]
        tokens_to_add = (elapsed / self._window_seconds) * bucket["max_tokens"]
        bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now

    def acquire(self, url: str, cost: int = 1) -> bool:
        """
        Intenta adquirir tokens para una request.

        Args:
            url: URL completa de la request
            cost: Costo en tokens (default 1)

        Returns:
            True si la request está permitida, False si está rate-limited
        """
        domain = self._get_domain(url)
        with self._lock:
            bucket = self._get_bucket(domain)
            self._refill(bucket)

            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                bucket["total_requests"] += 1
                return True
            else:
                bucket["blocked_requests"] += 1
                logger.warning(
                    f"Rate limit excedido para {domain}: {bucket['tokens']:.1f}/{bucket['max_tokens']} tokens"
                )
                return False

    def get_status(self, url: str | None = None) -> dict:
        """
        Retorna estado del rate limiter.

        Args:
            url: Si se provee, retorna solo el estado de ese dominio

        Returns:
            dict con estado de buckets
        """
        with self._lock:
            if url:
                domain = self._get_domain(url)
                bucket = self._get_bucket(domain)
                self._refill(bucket)
                return {
                    "domain": domain,
                    "tokens_remaining": round(bucket["tokens"], 1),
                    "max_tokens": bucket["max_tokens"],
                    "total_requests": bucket["total_requests"],
                    "blocked_requests": bucket["blocked_requests"],
                }

            return {
                domain: {
                    "tokens_remaining": round(b["tokens"], 1),
                    "max_tokens": b["max_tokens"],
                    "total_requests": b["total_requests"],
                    "blocked_requests": b["blocked_requests"],
                }
                for domain, b in self._buckets.items()
            }

    def reset(self, url: str | None = None) -> None:
        """Resetea buckets."""
        with self._lock:
            if url:
                domain = self._get_domain(url)
                self._buckets.pop(domain, None)
            else:
                self._buckets.clear()


# ===================================================================
# 5.3 — Response Cache
# ===================================================================


class ResponseCache:
    """
    Cache de respuestas HTTP en memoria.

    Almacena respuestas por URL + método + body hash.
    TTL configurable por dominio o global.
    Thread-safe mediante RLock.
    Límite máximo de entradas para evitar memory leak.
    """

    MAX_ENTRIES = 1000

    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl = default_ttl_seconds
        self._cache: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _make_key(self, method: str, url: str, body: dict | None = None) -> str:
        """Genera una key única para cache."""
        raw = f"{method.upper()}:{url}"
        if body:
            raw += f":{hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, method: str, url: str, body: dict | None = None) -> dict | None:
        """
        Obtiene una respuesta del cache si no ha expirado.

        Args:
            method: Método HTTP
            url: URL de la request
            body: Body de la request (opcional)

        Returns:
            Respuesta cacheada o None
        """
        key = self._make_key(method, url, body)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Verificar TTL
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None

            entry["hits"] = entry.get("hits", 0) + 1
            logger.debug(f"Cache HIT: {method} {url}")
            return entry["response"]

    def set(
        self, method: str, url: str, response: dict, body: dict | None = None, ttl_seconds: int | None = None
    ) -> None:
        """
        Almacena una respuesta en cache.

        Args:
            method: Método HTTP
            url: URL de la request
            response: Respuesta a cachear
            body: Body de la request (opcional)
            ttl_seconds: TTL personalizado (usa default si None)
        """
        if response.get("status_code", 0) >= 400:
            return  # No cachear errores

        key = self._make_key(method, url, body)
        ttl = ttl_seconds or self._default_ttl

        with self._lock:
            # Limpiar cache si está lleno
            if len(self._cache) >= self.MAX_ENTRIES:
                self._evict()

            self._cache[key] = {
                "response": response,
                "expires_at": time.time() + ttl,
                "created_at": time.time(),
                "ttl": ttl,
                "hits": 0,
            }
            logger.debug(f"Cache SET: {method} {url} (TTL: {ttl}s)")

    def invalidate(self, url_pattern: str | None = None) -> int:
        """
        Invalida entradas del cache.

        Args:
            url_pattern: Si se provee, invalida URLs que contengan el patrón

        Returns:
            Número de entradas invalidadas
        """
        with self._lock:
            if url_pattern is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            keys_to_delete = [
                k for k, v in self._cache.items() if url_pattern.lower() in str(v.get("response", {})).lower()
            ]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    def _evict(self) -> None:
        """Elimina las entradas más viejas cuando el cache está lleno."""
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1]["created_at"],
        )
        # Eliminar 10% de las entradas más viejas
        to_remove = max(1, len(sorted_entries) // 10)
        for key, _ in sorted_entries[:to_remove]:
            del self._cache[key]

    def get_stats(self) -> dict:
        """Estadísticas del cache."""
        with self._lock:
            total = len(self._cache)
            active = sum(1 for e in self._cache.values() if time.time() <= e["expires_at"])
            total_hits = sum(e.get("hits", 0) for e in self._cache.values())
            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": total - active,
                "total_hits": total_hits,
                "max_entries": self.MAX_ENTRIES,
                "default_ttl_seconds": self._default_ttl,
            }


# ===================================================================
# 5.2 — Paginación Automática
# ===================================================================


class PaginationCollector:
    """
    Recolecta datos paginados automáticamente.

    Estrategias:
    - page: paginación clásica (?page=1&limit=10)
    - cursor: paginación por cursor (?cursor=abc123)
    - offset: paginación por offset (?offset=0&limit=10)

    Detecta automáticamente next_page/cursor/offset de la respuesta
    y continúa recolectando hasta max_pages o condición de parada.
    """

    # Patrones comunes para detectar paginación en respuestas JSON
    NEXT_PAGE_KEYS: ClassVar[set[str]] = {"next_page", "nextPage", "next", "next_url", "nextUrl"}
    CURSOR_KEYS: ClassVar[set[str]] = {"cursor", "next_cursor", "nextCursor", "after", "page_token", "pageToken"}
    HAS_MORE_KEYS: ClassVar[set[str]] = {"has_more", "hasMore", "more"}
    TOTAL_KEYS: ClassVar[set[str]] = {"total", "total_count", "totalCount", "count", "total_items", "totalItems"}

    def __init__(self, max_pages: int = 10, max_total_items: int = 1000):
        self.max_pages = max_pages
        self.max_total_items = max_total_items

    def collect_page_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        """
        Navega paginación page-based.

        Detecta el número de página actual y la siguiente,
        construye la URL para la siguiente página.

        Args:
            url: URL base
            params: Parámetros actuales (deben incluir page)
            response: Respuesta de la página actual
            pages_left: Páginas restantes

        Returns:
            dict con: next_url, next_params, stop (bool)
        """
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}

        current_page = int(params.get("page", 1))
        next_page = current_page + 1

        # Verificar si hay más páginas por la respuesta
        body = response.get("body", {})
        if isinstance(body, dict):
            # Buscar has_more flag
            for key in self.HAS_MORE_KEYS:
                if key in body and not body[key]:
                    return {"next_url": None, "next_params": None, "stop": True}

            # Buscar total para calcular última página
            limit = int(params.get("limit", params.get("per_page", 20)))
            for key in self.TOTAL_KEYS:
                total = body.get(key)
                if total is not None:
                    last_page = (int(total) + limit - 1) // limit
                    if current_page >= last_page:
                        return {"next_url": None, "next_params": None, "stop": True}
                    break

            # Buscar next_page explícito
            for key in self.NEXT_PAGE_KEYS:
                np = body.get(key)
                if np is not None:
                    if np == current_page or np is False or np == "":
                        return {"next_url": None, "next_params": None, "stop": True}
                    break

        new_params = dict(params)
        new_params["page"] = next_page
        return {"next_url": url, "next_params": new_params, "stop": False}

    def collect_cursor_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        """
        Navega paginación cursor-based.

        Args:
            url: URL base
            params: Parámetros actuales
            response: Respuesta de la página actual
            pages_left: Páginas restantes

        Returns:
            dict con: next_url, next_params, stop (bool)
        """
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}

        body = response.get("body", {})
        if not isinstance(body, dict):
            return {"next_url": None, "next_params": None, "stop": True}

        # Buscar cursor en la respuesta
        next_cursor = None
        for key in self.CURSOR_KEYS:
            cursor = body.get(key)
            if cursor is not None and cursor != "":
                next_cursor = cursor
                break

        if not next_cursor:
            # Verificar has_more
            for key in self.HAS_MORE_KEYS:
                if key in body and not body[key]:
                    return {"next_url": None, "next_params": None, "stop": True}
            return {"next_url": None, "next_params": None, "stop": True}

        new_params = dict(params)
        # Reemplazar el parámetro cursor/after/page_token
        cursor_param = None
        for p in params:
            if p.lower() in {"cursor", "after", "page_token", "starting_after"}:
                cursor_param = p
                break
        if cursor_param:
            new_params[cursor_param] = next_cursor
        else:
            new_params["cursor"] = next_cursor

        return {"next_url": url, "next_params": new_params, "stop": False}

    def collect_offset_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        """
        Navega paginación offset-based.

        Args:
            url: URL base
            params: Parámetros actuales
            response: Respuesta de la página actual
            pages_left: Páginas restantes

        Returns:
            dict con: next_url, next_params, stop (bool)
        """
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}

        current_offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 20))

        body = response.get("body", {})

        # Si la respuesta tiene menos items que el límite, es la última página
        items = None
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            # Buscar la lista de items en la respuesta
            for key in ["data", "items", "results", "records", "results_list"]:
                val = body.get(key)
                if isinstance(val, list):
                    items = val
                    break

        if items is not None and len(items) < limit:
            return {"next_url": None, "next_params": None, "stop": True}

        # Buscar total para saber si hay más
        if isinstance(body, dict):
            for key in self.TOTAL_KEYS:
                total = body.get(key)
                if total is not None:
                    if current_offset + limit >= int(total):
                        return {"next_url": None, "next_params": None, "stop": True}
                    break

        new_params = dict(params)
        new_params["offset"] = current_offset + limit
        return {"next_url": url, "next_params": new_params, "stop": False}


# ===================================================================
# 5.4 — Webhook Callback Receiver
# ===================================================================


class WebhookCallbackRegistry:
    """
    Registro de callbacks asíncronos para webhooks.

    Permite registrar una URL de callback que será llamada cuando
    una respuesta asíncrona esté disponible. Almacena el estado
    de los callbacks (pending, completed, failed) en memoria.

    Uso típico:
    1. Se hace una request con async_callback_url
    2. La API externa procesa y llama al webhook del sistema
    3. El webhook_handler recibe la respuesta y completa el callback
    """

    def __init__(self):
        self._callbacks: dict[str, dict] = {}
        self._lock = threading.RLock()

    def register(self, callback_url: str, original_request: dict, timeout_seconds: int = 3600) -> str:
        """
        Registra un callback webhook.

        Args:
            callback_url: URL que recibirá la respuesta asíncrona
            original_request: Datos de la request original
            timeout_seconds: Tiempo máximo de espera (default 1h)

        Returns:
            ID único del callback
        """
        import secrets

        callback_id = secrets.token_hex(16)

        with self._lock:
            self._callbacks[callback_id] = {
                "id": callback_id,
                "callback_url": callback_url,
                "original_request": original_request,
                "status": "pending",
                "response": None,
                "created_at": time.time(),
                "expires_at": time.time() + timeout_seconds,
                "error": None,
            }

        logger.info(f"WebhookCallback registrado: {callback_id} → {callback_url}")
        return callback_id

    def complete(self, callback_id: str, response: dict) -> bool:
        """
        Marca un callback como completado.

        Args:
            callback_id: ID del callback
            response: Respuesta recibida

        Returns:
            True si se completó, False si no existe
        """
        with self._lock:
            if callback_id not in self._callbacks:
                return False
            self._callbacks[callback_id].update(
                {
                    "status": "completed",
                    "response": response,
                    "completed_at": time.time(),
                }
            )
        logger.info(f"WebhookCallback completado: {callback_id}")
        return True

    def fail(self, callback_id: str, error: str) -> bool:
        """
        Marca un callback como fallido.

        Args:
            callback_id: ID del callback
            error: Mensaje de error

        Returns:
            True si se marcó, False si no existe
        """
        with self._lock:
            if callback_id not in self._callbacks:
                return False
            self._callbacks[callback_id].update(
                {
                    "status": "failed",
                    "error": error,
                    "completed_at": time.time(),
                }
            )
        logger.warning(f"WebhookCallback fallido: {callback_id}: {error}")
        return True

    def get(self, callback_id: str) -> dict | None:
        """Obtiene el estado de un callback."""
        with self._lock:
            entry = self._callbacks.get(callback_id)
            if entry and time.time() > entry["expires_at"]:
                entry["status"] = "expired"
            return dict(entry) if entry else None

    def list_pending(self) -> list[dict]:
        """Lista callbacks pendientes."""
        with self._lock:
            now = time.time()
            return [dict(c) for c in self._callbacks.values() if c["status"] == "pending" and now <= c["expires_at"]]

    def cleanup_expired(self) -> int:
        """Limpia callbacks expirados."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._callbacks.items() if now > v["expires_at"]]
            for k in expired:
                del self._callbacks[k]
            return len(expired)


# ===================================================================
# 5.6 — XML Support
# ===================================================================


class XMLProcessor:
    """
    Procesa XML: parsea a dict y genera XML desde dict.

    Usa xmltodict si está disponible, fallback a parseo manual básico.
    """

    @staticmethod
    def parse(xml_string: str) -> dict:
        """
        Parsea XML a dict.

        Args:
            xml_string: String XML

        Returns:
            dict con el contenido parseado
        """
        try:
            import xmltodict

            result = xmltodict.parse(xml_string)
            return {"parsed": result, "format": "xml", "parser": "xmltodict"}
        except ImportError:
            logger.warning("xmltodict no instalado, usando parseo básico")
            return XMLProcessor._basic_parse(xml_string)
        except Exception as e:
            return {"error": f"Error parseando XML: {e}", "format": "xml"}

    @staticmethod
    def generate(data: dict, root_name: str = "root") -> str:
        """
        Genera XML desde un dict.

        Args:
            data: Dict a convertir a XML
            root_name: Nombre del elemento raíz

        Returns:
            String XML
        """
        try:
            import xmltodict

            result = xmltodict.unparse({root_name: data}, pretty=True)
            return result
        except ImportError:
            logger.warning("xmltodict no instalado, usando generación básica")
            return XMLProcessor._basic_generate(data, root_name)
        except Exception as e:
            return f"<!-- Error generando XML: {e} -->"

    @staticmethod
    def _basic_parse(xml_string: str) -> dict:
        """
        Parseo XML básico sin xmltodict.
        Extrae tags y contenido de forma simple.
        """
        import re

        result = {}
        # Extraer tags con contenido
        pattern = r"<(\w+)>([^<]+)</\1>"
        for match in re.finditer(pattern, xml_string):
            tag = match.group(1)
            content = match.group(2).strip()
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(content)
            else:
                result[tag] = content
        return {"parsed": result, "format": "xml", "parser": "basic"}

    @staticmethod
    def _basic_generate(data: dict, root_name: str = "root", indent: int = 0) -> str:
        """Generación XML básica sin xmltodict."""
        indent_str = "  " * indent
        lines = [f"{indent_str}<{root_name}>"]
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(XMLProcessor._basic_generate(value, key, indent + 1))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        lines.append(XMLProcessor._basic_generate(item, key, indent + 1))
                    else:
                        lines.append(f"{indent_str}  <{key}>{item}</{key}>")
            else:
                lines.append(f"{indent_str}  <{key}>{value}</{key}>")
        lines.append(f"{indent_str}</{root_name}>")
        return "\n".join(lines)


# ===================================================================
# APIConnectorService Mejorado
# ===================================================================


class APIConnectorService:
    """
    Conecta con APIs externas vía HTTP — Versión Mejorada (Sprint 5).

    Mejoras sobre la versión original:
    - Rate limiting por dominio (token bucket)
    - Paginación automática (page, cursor, offset)
    - Caching de respuestas con TTL
    - Webhook callbacks asíncronos
    - XML support (parse + generate)
    - Auto-detección de formato de respuesta
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
        headers: dict | None = None,
        body: dict | None = None,
        params: dict | None = None,
        auth_type: str = "none",
        auth_credentials: dict | None = None,
        timeout: int = 30,
        # Sprint 5: Nuevos parámetros
        cache_ttl: int | None = None,
        use_cache: bool = True,
        pagination: str | None = None,
        max_pages: int = 5,
        pagination_params: dict | None = None,
        response_format: str = "auto",
        async_callback_url: str | None = None,
        rate_limit_cost: int = 1,
    ) -> dict:
        """
        Realiza una petición HTTP con todas las mejoras Sprint 5.

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE, PATCH)
            url: URL completa del endpoint
            headers: Headers adicionales
            body: Body de la petición (se envía como JSON)
            params: Query parameters
            auth_type: 'none', 'bearer', 'basic', 'api-key'
            auth_credentials: Credenciales según auth_type
            timeout: Timeout en segundos

            cache_ttl: TTL en segundos para cache (default: 300)
            use_cache: Si True, usa cache para GET requests
            pagination: 'page', 'cursor', 'offset' o None
            max_pages: Máximo de páginas a recolectar
            pagination_params: Parámetros adicionales de paginación
            response_format: 'auto', 'json', 'xml', 'text'
            async_callback_url: URL para callbacks asíncronos
            rate_limit_cost: Costo en tokens de rate limit

        Returns:
            dict con resultado completo
        """
        start_time = time.time()

        # ── 1. Validar URL ────────────────────────────────
        if not self.validate_url(url):
            return self._error(f"URL inválida: {url}", start_time)

        # ── 2. Normalizar método ──────────────────────────
        method = method.upper()
        if method not in self.ALLOWED_METHODS:
            return self._error(f"Método no soportado: {method}", start_time)

        # ── 3. Rate limiting ──────────────────────────────
        if rate_limit_cost > 0 and not self._rate_limiter.acquire(url, rate_limit_cost):
            return {
                "status_code": 429,
                "error": f"Rate limit excedido para {urlparse(url).netloc}",
                "duration_ms": self._elapsed(start_time),
                "rate_limited": True,
            }

        # ── 4. Cache check (solo GET) ─────────────────────
        if use_cache and method == "GET" and not pagination:
            cached = self._cache.get(method, url, body)
            if cached:
                cached["from_cache"] = True
                cached["duration_ms"] = self._elapsed(start_time)
                return cached

        # ── 5. Si es async, registrar callback ────────────
        if async_callback_url:
            callback_id = self._callbacks.register(
                callback_url=async_callback_url,
                original_request={
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "body": body,
                    "params": params,
                },
            )

        # ── 6. Ejecutar request (con paginación opcional) ──
        if pagination and method == "GET":
            result = self._request_with_pagination(
                method=method,
                url=url,
                headers=headers,
                params=params,
                auth_type=auth_type,
                auth_credentials=auth_credentials,
                timeout=timeout,
                pagination=pagination,
                max_pages=max_pages,
                pagination_params=pagination_params,
                start_time=start_time,
            )
        else:
            result = self._execute_request(
                method=method,
                url=url,
                headers=headers,
                body=body,
                params=params,
                auth_type=auth_type,
                auth_credentials=auth_credentials,
                timeout=timeout,
                start_time=start_time,
            )

        # ── 7. Transformar respuesta según formato ───────
        if result.get("status_code", 0) < 400:
            result = self._transform_response(result, response_format)

        # ── 8. Cachear resultado (solo GET exitoso) ──────
        if use_cache and method == "GET" and result.get("status_code", 0) < 400 and not pagination:
            self._cache.set(method, url, result, body, cache_ttl)

        # ── 9. Si es async, incluir callback_id ──────────
        if async_callback_url:
            result["async"] = True
            result["callback_id"] = callback_id
            result["callback_url"] = async_callback_url

        return result

    # ── Request con paginación ─────────────────────────────

    def _request_with_pagination(
        self,
        method: str,
        url: str,
        headers: dict | None,
        params: dict | None,
        auth_type: str,
        auth_credentials: dict | None,
        timeout: int,
        pagination: str,
        max_pages: int,
        pagination_params: dict | None,
        start_time: float,
    ) -> dict:
        """
        Realiza requests paginados y recolecta todos los resultados.

        Args:
            method: Método HTTP
            url: URL base
            headers: Headers
            params: Parámetros base
            auth_type: Tipo de auth
            auth_credentials: Credenciales
            timeout: Timeout
            pagination: 'page', 'cursor' o 'offset'
            max_pages: Máximo de páginas
            pagination_params: Parámetros extras de paginación
            start_time: Timestamp inicial

        Returns:
            dict con todos los items recolectados + metadata
        """
        all_items = []
        current_params = dict(params or {})
        current_url = url
        pages = 0
        errors = []

        # Inicializar parámetros de paginación
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
                response = self._execute_request(
                    method=method,
                    url=current_url,
                    headers=headers,
                    body=None,
                    params=current_params,
                    auth_type=auth_type,
                    auth_credentials=auth_credentials,
                    timeout=timeout,
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

            # Extraer items de la respuesta
            body = response.get("body", {})
            items = self._extract_items(body)
            if items:
                all_items.extend(items)

            pages += 1

            # Determinar siguiente página
            collector = self._paginator

            if pagination == "page":
                nav = collector.collect_page_based(
                    current_url,
                    current_params,
                    response,
                    max_pages - pages,
                )
            elif pagination == "cursor":
                nav = collector.collect_cursor_based(
                    current_url,
                    current_params,
                    response,
                    max_pages - pages,
                )
            elif pagination == "offset":
                nav = collector.collect_offset_based(
                    current_url,
                    current_params,
                    response,
                    max_pages - pages,
                )
            else:
                nav = {"next_url": None, "next_params": None, "stop": True}

            if nav.get("stop"):
                break

            current_url = nav["next_url"] or current_url
            current_params = nav["next_params"] or current_params

        # Determinar status_code: usar el de la última respuesta exitosa
        final_status = 200 if all_items else 500
        if pages > 0:
            # Buscar el status_code de la última respuesta
            pass  # Si llegamos aquí, al menos una página fue exitosa

        result = {
            "status_code": final_status,
            "body": all_items,  # Siempre lista para consistencia
            "pagination": {
                "strategy": pagination,
                "pages_collected": pages,
                "total_items": len(all_items),
                "max_pages": max_pages,
            },
            "duration_ms": self._elapsed(start_time),
        }

        if errors:
            result["pagination_errors"] = errors

        return result

    # ── Ejecución HTTP base ───────────────────────────────

    def _execute_request(
        self,
        method: str,
        url: str,
        headers: dict | None,
        body: dict | None,
        params: dict | None,
        auth_type: str,
        auth_credentials: dict | None,
        timeout: int,
        start_time: float,
    ) -> dict:
        """Ejecuta una request HTTP individual (sin paginación)."""
        import requests

        request_headers = dict(headers) if headers else {}

        # Configurar autenticación
        auth = None
        if auth_type == "bearer" and auth_credentials:
            token = auth_credentials.get("token", "")
            request_headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "basic" and auth_credentials:
            username = auth_credentials.get("username", "")
            password = auth_credentials.get("password", "")
            auth = (username, password)
        elif auth_type == "api-key" and auth_credentials:
            key_name = auth_credentials.get("key_name", "X-API-Key")
            key_value = auth_credentials.get("key_value", "")
            request_headers[key_name] = key_value

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers or None,
                json=body,
                params=params,
                auth=auth,
                timeout=timeout,
            )

            duration = self._elapsed(start_time)

            # Auto-detectar formato de respuesta
            content_type = response.headers.get("Content-Type", "")
            response_body = self._parse_response_body(response, content_type)

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "duration_ms": duration,
                "content_type": content_type,
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión a {url}: {e}")
            return self._error(f"Error de conexión: {e}", start_time)
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout en {url}: {e}")
            return self._error(f"Timeout después de {timeout}s", start_time)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en petición a {url}: {e}")
            return self._error(f"Error en petición: {e}", start_time)

    # ── Parseo de respuesta ───────────────────────────────

    @staticmethod
    def _parse_response_body(response, content_type: str) -> Any:
        """
        Parsea el body de la respuesta según Content-Type.

        Soporta:
        - application/json → dict/list
        - application/xml, text/xml → dict (via xmltodict)
        - text/plain, text/html → string
        - Otros → string
        """
        content_type_lower = content_type.lower()

        # JSON
        if "json" in content_type_lower:
            try:
                return response.json()
            except (ValueError, json.JSONDecodeError):
                pass

        # XML
        if "xml" in content_type_lower:
            try:
                import xmltodict

                return {"xml_parsed": xmltodict.parse(response.text)}
            except ImportError:
                return {"xml_raw": response.text}
            except Exception:
                pass

        # Texto plano
        return response.text

    @staticmethod
    def _transform_response(result: dict, response_format: str) -> dict:
        """
        Transforma la respuesta según el formato solicitado.

        Args:
            result: Resultado de la request
            response_format: 'auto', 'json', 'xml', 'text'

        Returns:
            Resultado transformado
        """
        if response_format == "auto":
            return result  # Ya se auto-detectó en _parse_response_body

        body = result.get("body")

        if response_format == "xml" and isinstance(body, str):
            try:
                import xmltodict

                result["body"] = {"xml_parsed": xmltodict.parse(body)}
                result["format"] = "xml"
            except ImportError:
                result["body"] = {"xml_raw": body}
                result["format"] = "xml_raw"
            except Exception as e:
                result["body"] = {"xml_error": str(e), "raw": body}
                result["format"] = "xml_error"

        elif response_format == "json" and isinstance(body, str):
            try:
                result["body"] = json.loads(body)
                result["format"] = "json"
            except (json.JSONDecodeError, TypeError):
                result["format"] = "text"

        elif response_format == "text" and not isinstance(body, str):
            result["body"] = json.dumps(body, indent=2)
            result["format"] = "text"

        return result

    # ── XML público ───────────────────────────────────────

    def xml_parse(self, xml_string: str) -> dict:
        """Parsea XML a dict (wrapper público)."""
        return self._xml.parse(xml_string)

    def xml_generate(self, data: dict, root_name: str = "root") -> str:
        """Genera XML desde dict (wrapper público)."""
        return self._xml.generate(data, root_name)

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _extract_items(body: Any) -> list:
        """
        Extrae items de una respuesta paginada.

        Busca en orden: data, items, results, records, results_list.
        Si el body es una lista, la retorna directamente.
        """
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in [
                "data",
                "items",
                "results",
                "records",
                "results_list",
                "products",
                "leads",
                "invoices",
                "users",
                "contacts",
            ]:
                val = body.get(key)
                if isinstance(val, list):
                    return val

            # Buscar cualquier valor que sea lista
            for val in body.values():
                if isinstance(val, list):
                    return val
        return []

    @staticmethod
    def validate_url(url: str) -> bool:
        """Valida que la URL sea HTTP/HTTPS válida."""
        if not url or not isinstance(url, str):
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        return parsed.netloc

    @staticmethod
    def _error(message: str, start_time: float) -> dict:
        return {
            "status_code": 0,
            "error": message,
            "duration_ms": int((time.time() - start_time) * 1000),
        }

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

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
                        {
                            "name": "method",
                            "type": "select",
                            "options": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                            "required": True,
                            "default": "GET",
                            "label": "Método HTTP",
                        },
                        {
                            "name": "url",
                            "type": "string",
                            "required": True,
                            "label": "URL",
                            "placeholder": "https://api.example.com/endpoint",
                        },
                        {"name": "headers", "type": "dict", "required": False, "default": {}, "label": "Headers"},
                        {"name": "body", "type": "dict", "required": False, "default": {}, "label": "Body (JSON)"},
                        {"name": "params", "type": "dict", "required": False, "default": {}, "label": "Query Params"},
                        {
                            "name": "auth_type",
                            "type": "select",
                            "options": ["none", "bearer", "basic", "api-key"],
                            "required": False,
                            "default": "none",
                            "label": "Autenticación",
                        },
                        {
                            "name": "auth_credentials",
                            "type": "dict",
                            "required": False,
                            "default": {},
                            "label": "Credenciales",
                        },
                        {
                            "name": "timeout",
                            "type": "number",
                            "required": False,
                            "default": 30,
                            "label": "Timeout (segundos)",
                        },
                        {
                            "name": "pagination",
                            "type": "select",
                            "options": [None, "page", "cursor", "offset"],
                            "required": False,
                            "default": None,
                            "label": "Paginación automática",
                        },
                        {
                            "name": "max_pages",
                            "type": "number",
                            "required": False,
                            "default": 5,
                            "label": "Máx. páginas a recolectar",
                        },
                        {
                            "name": "use_cache",
                            "type": "boolean",
                            "required": False,
                            "default": True,
                            "label": "Usar cache",
                        },
                        {
                            "name": "cache_ttl",
                            "type": "number",
                            "required": False,
                            "default": 300,
                            "label": "TTL de cache (segundos)",
                        },
                        {
                            "name": "response_format",
                            "type": "select",
                            "options": ["auto", "json", "xml", "text"],
                            "required": False,
                            "default": "auto",
                            "label": "Formato de respuesta",
                        },
                        {
                            "name": "async_callback_url",
                            "type": "string",
                            "required": False,
                            "default": "",
                            "label": "URL de callback (async)",
                        },
                    ],
                },
                "xml_parse": {
                    "name": "Parsear XML",
                    "description": "Convierte XML a dict",
                    "params": [
                        {"name": "xml_string", "type": "string", "required": True, "label": "String XML"},
                    ],
                },
                "xml_generate": {
                    "name": "Generar XML",
                    "description": "Convierte dict a XML",
                    "params": [
                        {"name": "data", "type": "dict", "required": True, "label": "Datos"},
                        {
                            "name": "root_name",
                            "type": "string",
                            "required": False,
                            "default": "root",
                            "label": "Elemento raíz",
                        },
                    ],
                },
                "cache_stats": {
                    "name": "Estadísticas de cache",
                    "description": "Muestra estado del cache de respuestas",
                    "params": [],
                },
                "rate_limit_status": {
                    "name": "Estado de rate limiting",
                    "description": "Muestra estado de los buckets",
                    "params": [],
                },
            },
        }
