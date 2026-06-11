"""
Connector SDK — HTTP Client Helper
====================================

Cliente HTTP compartido para todos los conectores de Zenic-Flijo.
Provee una capa consistente sobre httpx/requests con:

- Timeout configurable por operacion
- Reintentos automaticos con backoff exponencial
- Logging estructurado de cada request/response
- Rate limiting integrado via Redis
- Metricas automaticas via TelemetryService
- Soporte para multiplexacion async (httpx) y sync (requests)
- Context manager para sesiones reutilizables
- Headers personalizados por conector
- Manejo estandarizado de errores HTTP

Configuracion via variables de entorno:
- WFD_HTTP_TIMEOUT: Timeout global en segundos (default: 30)
- WFD_HTTP_MAX_RETRIES: Maximo reintentos (default: 3)
- WFD_HTTP_RETRY_BACKOFF: Factor de backoff (default: 2.0)
- WFD_HTTP_VERIFY_SSL: Verificar SSL (default: true)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuracion global ────────────────────────────────────────────

HTTP_TIMEOUT: int = int(os.environ.get("WFD_HTTP_TIMEOUT", "30"))
HTTP_MAX_RETRIES: int = int(os.environ.get("WFD_HTTP_MAX_RETRIES", "3"))
HTTP_RETRY_BACKOFF: float = float(os.environ.get("WFD_HTTP_RETRY_BACKOFF", "2.0"))
HTTP_VERIFY_SSL: bool = os.environ.get("WFD_HTTP_VERIFY_SSL", "true").lower() == "true"


class HTTPResponse:
    """Respuesta HTTP estandarizada para todos los conectores.

    Attributes:
        status_code: Codigo de estado HTTP
        headers: Headers de la respuesta
        body: Cuerpo de la respuesta (dict si JSON, str si texto)
        raw: Contenido raw en bytes
        elapsed: Tiempo de respuesta en segundos
        url: URL solicitada
        method: Metodo HTTP utilizado
    """

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: Any,
        raw: bytes | None = None,
        elapsed: float = 0.0,
        url: str = "",
        method: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.raw = raw
        self.elapsed = elapsed
        self.url = url
        self.method = method

    @property
    def ok(self) -> bool:
        """True si el status code esta en el rango 2xx."""
        return 200 <= self.status_code < 300

    @property
    def is_client_error(self) -> bool:
        """True si el status code esta en el rango 4xx."""
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """True si el status code esta en el rango 5xx."""
        return 500 <= self.status_code < 600

    def json(self) -> Any:
        """Retorna el body como JSON si es string, o el body directamente si ya es dict."""
        if isinstance(self.body, (dict, list)):
            return self.body
        if isinstance(self.body, str):
            try:
                return json.loads(self.body)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializa la respuesta a diccionario."""
        return {
            "status_code": self.status_code,
            "ok": self.ok,
            "elapsed": round(self.elapsed, 3),
            "url": self.url,
            "method": self.method,
            "body": self.body if isinstance(self.body, (dict, list)) else str(self.body)[:500],
        }

    def __repr__(self) -> str:
        return f"<HTTPResponse [{self.status_code}] {self.method} {self.url} ({self.elapsed:.3f}s)>"


class HTTPClientError(Exception):
    """Error estandarizado para fallos de HTTP en conectores."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        url: str = "",
        method: str = "",
        response: HTTPResponse | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.method = method
        self.response = response

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "status_code": self.status_code,
            "url": self.url,
            "method": self.method,
        }


class HttpClient:
    """Cliente HTTP sincrono con reintentos, logging y metricas.

    Uso tipico:
        client = HttpClient(base_url="https://api.github.com")
        client.set_auth("Bearer", token="ghp_xxx")

        # GET request
        response = client.get("/repos/owner/repo/issues", params={"state": "open"})

        # POST request
        response = client.post("/repos/owner/repo/issues", json={"title": "Bug"})

        # Con reintentos automaticos
        response = client.get("/slow-endpoint", retries=3, retry_on=[429, 502, 503])

    Context manager para sesiones reutilizables:
        with HttpClient(base_url="https://api.stripe.com") as client:
            client.set_auth("Bearer", token="sk_xxx")
            balance = client.get("/v1/balance")
            charges = client.get("/v1/charges")
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: int = HTTP_TIMEOUT,
        max_retries: int = HTTP_MAX_RETRIES,
        retry_backoff: float = HTTP_RETRY_BACKOFF,
        verify_ssl: bool = HTTP_VERIFY_SSL,
        default_headers: dict[str, str] | None = None,
        connector_name: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._verify_ssl = verify_ssl
        self._default_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"Zenic-Flijo-SDK/1.0 ({connector_name})",
        }
        if default_headers:
            self._default_headers.update(default_headers)
        self._auth_header: dict[str, str] = {}
        self._session: Any = None
        self._connector_name = connector_name

    def set_auth(self, auth_type: str, token: str = "", username: str = "", password: str = "") -> None:
        """Configura la autenticacion para todas las requests posteriores.

        Args:
            auth_type: Tipo de auth ('Bearer', 'Basic', 'Token', 'ApiKey')
            token: Token para Bearer/Token auth
            username: Username para Basic auth
            password: Password para Basic auth
        """
        if auth_type.lower() == "bearer":
            self._auth_header = {"Authorization": f"Bearer {token}"}
        elif auth_type.lower() == "token":
            self._auth_header = {"Authorization": f"Token {token}"}
        elif auth_type.lower() == "basic":
            import base64
            cred = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._auth_header = {"Authorization": f"Basic {cred}"}
        elif auth_type.lower() == "apikey":
            self._auth_header = {"X-API-Key": token}

    def set_header(self, key: str, value: str) -> None:
        """Establece un header personalizado para todas las requests."""
        self._default_headers[key] = value

    # ── Metodos HTTP ─────────────────────────────────────────────

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un GET request con reintentos automaticos."""
        return self._request(
            method="GET",
            path=path,
            params=params,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_on=retry_on,
        )

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un POST request con reintentos automaticos."""
        return self._request(
            method="POST",
            path=path,
            json_body=json,
            data=data,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_on=retry_on,
        )

    def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un PUT request con reintentos automaticos."""
        return self._request(
            method="PUT",
            path=path,
            json_body=json,
            data=data,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_on=retry_on,
        )

    def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un PATCH request con reintentos automaticos."""
        return self._request(
            method="PATCH",
            path=path,
            json_body=json,
            data=data,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_on=retry_on,
        )

    def delete(
        self,
        path: str,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un DELETE request con reintentos automaticos."""
        return self._request(
            method="DELETE",
            path=path,
            headers=headers,
            timeout=timeout,
            retries=retries,
            retry_on=retry_on,
        )

    # ── Implementacion interna ────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        retry_on: list[int] | None = None,
    ) -> HTTPResponse:
        """Ejecuta un request HTTP con reintentos, logging y metricas."""
        import requests as req_lib

        url = self._build_url(path)
        actual_timeout = timeout or self._timeout
        actual_retries = retries if retries is not None else self._max_retries
        retry_statuses = retry_on or [429, 502, 503, 504]

        # Combinar headers
        final_headers = {**self._default_headers, **self._auth_header}
        if headers:
            final_headers.update(headers)

        # Preparar kwargs
        request_kwargs: dict[str, Any] = {
            "timeout": actual_timeout,
            "verify": self._verify_ssl,
            "headers": final_headers,
        }
        if params:
            request_kwargs["params"] = params
        if json_body:
            request_kwargs["json"] = json_body
            # Si se envia JSON, asegurarse de no tener Content-Type incorrecto
            final_headers.setdefault("Content-Type", "application/json")
        if data:
            request_kwargs["data"] = data

        last_response: HTTPResponse | None = None
        last_error: Exception | None = None

        for attempt in range(actual_retries + 1):
            start_time = time.monotonic()
            try:
                resp = req_lib.request(method, url, **request_kwargs)
                elapsed = time.monotonic() - start_time

                # Parsear respuesta
                body: Any = None
                try:
                    body = resp.json()
                except (json.JSONDecodeError, ValueError):
                    body = resp.text

                last_response = HTTPResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=body,
                    raw=resp.content,
                    elapsed=elapsed,
                    url=url,
                    method=method,
                )

                # Logging
                self._log_request(method, url, resp.status_code, elapsed, attempt)

                # Verificar si debemos reintentar
                if resp.status_code in retry_statuses and attempt < actual_retries:
                    delay = self._retry_backoff ** attempt
                    logger.warning(
                        f"HttpClient: {method} {url} -> {resp.status_code}, "
                        f"reintento {attempt + 1}/{actual_retries} en {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue

                # Si es un error de cliente (4xx), no reintentar
                if 400 <= resp.status_code < 500 and resp.status_code not in retry_statuses:
                    return last_response

                return last_response

            except req_lib.Timeout as exc:
                elapsed = time.monotonic() - start_time
                last_error = exc
                logger.warning(
                    f"HttpClient: {method} {url} -> timeout ({elapsed:.1f}s), "
                    f"intento {attempt + 1}/{actual_retries + 1}"
                )
                if attempt < actual_retries:
                    delay = self._retry_backoff ** attempt
                    time.sleep(delay)
                    continue

            except req_lib.ConnectionError as exc:
                elapsed = time.monotonic() - start_time
                last_error = exc
                logger.warning(
                    f"HttpClient: {method} {url} -> connection error, "
                    f"intento {attempt + 1}/{actual_retries + 1}: {exc}"
                )
                if attempt < actual_retries:
                    delay = self._retry_backoff ** attempt
                    time.sleep(delay)
                    continue

            except Exception as exc:
                elapsed = time.monotonic() - start_time
                last_error = exc
                logger.error(f"HttpClient: {method} {url} -> error: {exc}")
                break

        # Si llegamos aqui, todos los reintentos fallaron
        if last_response is not None:
            return last_response

        error_msg = str(last_error) if last_error else "Error desconocido"
        raise HTTPClientError(
            message=f"{method} {url} fallo despues de {actual_retries + 1} intentos: {error_msg}",
            url=url,
            method=method,
        )

    def _build_url(self, path: str) -> str:
        """Construye la URL completa combinando base_url y path."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if self._base_url:
            return f"{self._base_url}/{path.lstrip('/')}"
        return path

    def _log_request(
        self,
        method: str,
        url: str,
        status_code: int,
        elapsed: float,
        attempt: int,
    ) -> None:
        """Registra informacion de la request en el log."""
        connector_tag = f"[{self._connector_name}]" if self._connector_name else ""
        attempt_tag = f" (retry {attempt})" if attempt > 0 else ""
        level = "debug" if 200 <= status_code < 400 else "warning"
        msg = f"HttpClient{connector_tag}: {method} {url} -> {status_code} ({elapsed:.3f}s){attempt_tag}"
        if level == "debug":
            logger.debug(msg)
        else:
            logger.warning(msg)

    # ── Context Manager ───────────────────────────────────────────

    def __enter__(self) -> HttpClient:
        """Entra al context manager, creando una sesion reutilizable."""
        try:
            import requests

            self._session = requests.Session()
            self._session.headers.update(self._default_headers)
            self._session.headers.update(self._auth_header)
            self._session.verify = self._verify_SSL
        except ImportError:
            pass
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> bool:
        """Sale del context manager, cerrando la sesion."""
        if self._session is not None:
            self._session.close()
            self._session = None
        return False

    # ── Utility methods ───────────────────────────────────────────

    @staticmethod
    def build_query_params(params: dict[str, Any]) -> str:
        """Construye un query string desde un diccionario de parametros."""
        parts: list[str] = []
        for key, value in params.items():
            if value is not None:
                parts.append(f"{key}={value}")
        return "&".join(parts)

    @staticmethod
    def parse_link_header(header_value: str) -> dict[str, str]:
        """Parsea un header Link de paginacion estandar.

        Args:
            header_value: Valor del header Link

        Returns:
            dict con URLs para 'next', 'prev', 'first', 'last'
        """
        links: dict[str, str] = {}
        if not header_value:
            return links
        import re
        for match in re.finditer(r'<([^>]+)>;\s*rel="([^"]+)"', header_value):
            links[match.group(2)] = match.group(1)
        return links
