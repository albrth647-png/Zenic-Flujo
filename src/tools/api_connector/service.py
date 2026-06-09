"""
Workflow Determinista — APIConnectorService
Realiza peticiones HTTP a APIs externas desde los workflows.

Soporta:
- Métodos: GET, POST, PUT, DELETE, PATCH
- Auth: none, bearer, basic, api-key
- Headers personalizados
- Query params
- Timeout configurable
- Validación de URLs (solo http/https)
"""
import json
import time
from urllib.parse import urlparse
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class APIConnectorService:
    """
    Conecta con APIs externas vía HTTP.

    Uso en workflow:
    {
        "tool": "api_connector",
        "action": "request",
        "params": {
            "method": "GET",
            "url": "https://api.example.com/users",
            "headers": {"Authorization": "Bearer $input.token"},
            "params": {"limit": 10}
        }
    }
    """

    ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]

    def request(self, method: str = "GET", url: str = "",
                headers: dict | None = None,
                body: dict | None = None,
                params: dict | None = None,
                auth_type: str = "none",
                auth_credentials: dict | None = None,
                timeout: int = 30) -> dict:
        """
        Realiza una petición HTTP a una API externa.

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE, PATCH)
            url: URL completa del endpoint
            headers: Headers adicionales
            body: Body de la petición (se envía como JSON)
            params: Query parameters
            auth_type: Tipo de auth ('none', 'bearer', 'basic', 'api-key')
            auth_credentials: Credenciales según auth_type
            timeout: Timeout en segundos

        Returns:
            dict con: status_code, headers, body, duration_ms, error (opcional)
        """
        import requests

        start_time = time.time()

        # 1. Validar URL
        if not self.validate_url(url):
            return {
                "status_code": 0,
                "error": f"URL inválida o no permitida: {url}",
                "duration_ms": self._elapsed(start_time),
            }

        # 2. Normalizar método
        method = method.upper()
        if method not in self.ALLOWED_METHODS:
            return {
                "status_code": 0,
                "error": f"Método HTTP no soportado: {method}. Usa: {', '.join(self.ALLOWED_METHODS)}",
                "duration_ms": self._elapsed(start_time),
            }

        # 3. Preparar headers
        request_headers = dict(headers) if headers else {}

        # 4. Configurar autenticación
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

        # 5. Realizar petición
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers if request_headers else None,
                json=body,
                data=None,
                params=params,
                auth=auth,
                timeout=timeout,
            )

            duration = self._elapsed(start_time)

            # Intentar parsear como JSON, si no, devolver texto
            try:
                response_body = response.json()
            except (ValueError, json.JSONDecodeError):
                response_body = response.text

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "duration_ms": duration,
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión a {url}: {e}")
            return {
                "status_code": 0,
                "error": f"Error de conexión: {e}",
                "duration_ms": self._elapsed(start_time),
            }
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout en {url}: {e}")
            return {
                "status_code": 0,
                "error": f"Timeout después de {timeout}s: {e}",
                "duration_ms": self._elapsed(start_time),
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en petición a {url}: {e}")
            return {
                "status_code": 0,
                "error": f"Error en petición: {e}",
                "duration_ms": self._elapsed(start_time),
            }

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Valida que la URL sea HTTP/HTTPS válida y no sea peligrosa.
        
        Previene:
        - file:// (acceso a archivos locales)
        - ftp://
        - javascript:
        - URLs vacías
        """
        if not url or not isinstance(url, str):
            return False

        parsed = urlparse(url)
        allowed_schemes = {"http", "https"}

        if parsed.scheme not in allowed_schemes:
            return False
        if not parsed.netloc:
            return False

        return True

    @staticmethod
    def get_tool_definition() -> dict:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "api_connector",
            "name": "API Connector",
            "description": "Conecta con APIs externas vía HTTP",
            "actions": {
                "request": {
                    "name": "Petición HTTP",
                    "description": "Realiza una petición HTTP a una API externa",
                    "params": [
                        {"name": "method", "type": "select",
                         "options": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                         "required": True, "default": "GET",
                         "label": "Método HTTP"},
                        {"name": "url", "type": "string", "required": True,
                         "label": "URL",
                         "placeholder": "https://api.example.com/endpoint"},
                        {"name": "headers", "type": "dict",
                         "required": False, "default": {},
                         "label": "Headers",
                         "placeholder": '{"Authorization": "Bearer token"}'},
                        {"name": "body", "type": "dict",
                         "required": False, "default": {},
                         "label": "Body (JSON)",
                         "placeholder": '{"nombre": "$input.nombre"}'},
                        {"name": "params", "type": "dict",
                         "required": False, "default": {},
                         "label": "Query Params",
                         "placeholder": '{"limit": 10, "page": 1}'},
                        {"name": "auth_type", "type": "select",
                         "options": ["none", "bearer", "basic", "api-key"],
                         "required": False, "default": "none",
                         "label": "Autenticación"},
                        {"name": "auth_credentials", "type": "dict",
                         "required": False, "default": {},
                         "label": "Credenciales",
                         "placeholder": '{"token": "..."}'},
                        {"name": "timeout", "type": "number",
                         "required": False, "default": 30,
                         "label": "Timeout (segundos)"},
                    ],
                },
            },
        }

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)
