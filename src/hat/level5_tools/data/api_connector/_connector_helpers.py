"""
Connector Helpers — Funciones auxiliares HTTP
================================================

Extraído de http_client.py + service.py. Responsabilidad única: ejecución
de peticiones HTTP, parseo, transformación, extracción de items y validación.

Absorbe http_client.py (que se mantiene como re-export).
"""

from __future__ import annotations

import json
import time
from typing import Any, TypedDict
from urllib.parse import urlparse

from src.core.logging import setup_logging

logger = setup_logging(__name__)

class ApiResult(TypedDict, total=False):
    """Respuesta estandarizada de una petición HTTP.

    Campos comunes:
    - ``status_code``: Código HTTP (0 si error de red)
    - ``body``: Body parseado (dict para JSON, str para texto, ``xml_parsed`` para XML)
    - ``headers``: Headers de la respuesta
    - ``error``: Mensaje de error (solo si status_code=0)
    - ``duration_ms``: Tiempo de ejecución
    - ``content_type``: Content-Type de la respuesta
    - ``format``: Formato aplicado tras transform_response()
    - ``rate_limited``: True si rate limit bloqueó
    - ``from_cache``: True si vino de cache
    """
    status_code: int
    body: object
    headers: dict[str, str]
    error: str
    duration_ms: int
    content_type: str
    format: str
    rate_limited: bool
    from_cache: bool


def execute_request(
    method: str, url: str, headers: dict[str, Any] | None, body: dict[str, Any] | None,
    params: dict[str, str] | None, auth_type: str, auth_credentials: dict[str, Any] | None,
    timeout: int, start_time: float,
) -> ApiResult:
    """Ejecuta una petición HTTP con autenticación y manejo de errores."""
    import requests

    request_headers = dict(headers) if headers else {}
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
            method=method, url=url, headers=request_headers or None,
            json=body, params=params, auth=auth, timeout=timeout,
        )
        duration = _elapsed(start_time)
        content_type = response.headers.get("Content-Type", "")
        response_body = _parse_response_body(response, content_type)
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
            "duration_ms": duration,
            "content_type": content_type,
        }
    except requests.exceptions.ConnectionError as e:
        logger.error("Error de conexión a %s: %s", url, e)
        return _error(f"Error de conexión: {e}", start_time)
    except requests.exceptions.Timeout as e:
        logger.error("Timeout en %s: %s", url, e)
        return _error(f"Timeout después de {timeout}s", start_time)
    except requests.exceptions.RequestException as e:
        logger.error("Error en petición a %s: %s", url, e)
        return _error(f"Error en petición: {e}", start_time)


# legítimo: parsea JSON dinámico de API externa (skill §9.1)
def _parse_response_body(response, content_type: str) -> Any:
    """Parsea el body de la respuesta según Content-Type."""
    content_type_lower = content_type.lower()
    if "json" in content_type_lower:
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError):
            logger.debug("No se pudo parsear respuesta como JSON", exc_info=True)
    if "xml" in content_type_lower:
        try:
            import xmltodict
            return {"xml_parsed": xmltodict.parse(response.text)}
        except ImportError:
            return {"xml_raw": response.text}
        except Exception:
            logger.debug("No se pudo parsear respuesta como XML", exc_info=True)
    return response.text


def transform_response(result: ApiResult, response_format: str) -> ApiResult:
    """Transforma el body de la respuesta al formato solicitado."""
    if response_format == "auto":
        return result
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


def extract_items(body: object) -> list[Any]:
    """Extrae items de un body paginado (dict con key 'data', 'items', etc.)."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ["data", "items", "results", "records", "results_list",
                     "products", "leads", "invoices", "users", "contacts"]:
            val = body.get(key)
            if isinstance(val, list):
                return val
        for val in body.values():
            if isinstance(val, list):
                return val
    return []


def validate_url(url: str) -> bool:
    """Valida que una URL sea HTTP/HTTPS válida."""
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _error(message: str, start_time: float) -> ApiResult:
    """Retorna un dict de error estandarizado."""
    return {
        "status_code": 0,
        "error": message,
        "duration_ms": int((time.time() - start_time) * 1000),
    }


def _elapsed(start_time: float) -> int:
    """Calcula ms transcurridos desde start_time."""
    return int((time.time() - start_time) * 1000)
