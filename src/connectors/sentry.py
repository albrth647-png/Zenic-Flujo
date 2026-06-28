"""
Conector Sentry — Seguimiento de Errores via Sentry API
===========================================================

Permite gestionar errores, liberaciones, proyectos y
alertas via la Sentry API.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class SentryConnector(BaseConnector):
    """Conector para Sentry: errores, liberaciones y alertas."""

    name = "sentry"
    version = "1.0.0"
    description = "Gestiona errores, liberaciones y alertas via Sentry"
    category = "devops_monitoring"
    icon = "alert-circle"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://sentry.io/api/0"
        self._http: HttpClient | None = None

    def _get_token(self) -> str:
        """Extract the auth token from the auth provider."""
        if not self._auth_provider:
            return ""
        # Use apply_auth on a dummy request to extract credentials
        request: dict[str, Any] = {"headers": {}, "params": {}}
        self._auth_provider.apply_auth(request)
        auth_header = request["headers"].get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        if auth_header.startswith("Token "):
            return auth_header[6:]
        # Try X-API-Key header
        api_key = request["headers"].get("X-API-Key", "")
        if api_key:
            return api_key
        # Try direct attribute access
        for attr in ("_api_key", "_token", "_access_token", "_auth_token"):
            if hasattr(self._auth_provider, attr):
                val = getattr(self._auth_provider, attr, "")
                if isinstance(val, str) and val:
                    return val
        return ""

    def connect(self) -> bool:
        """Establece conexion con la Sentry API."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SentryConnector: Auth Token no configurado")
            return False

        token = self._get_token()
        if not token:
            logger.error("SentryConnector: No se pudo extraer el token del auth provider")
            return False

        self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
        # Sentry uses Bearer token auth
        self._http.set_auth("Bearer", token=token)

        # Validate credentials by fetching organizations
        try:
            resp = self._http.get("/organizations/")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Auth Token configurado y validado")
                return True
            else:
                logger.error(f"SentryConnector: Validacion de token fallida - {resp.status_code}")
                self._http = None
                return False
        except HTTPClientError as e:
            logger.error(f"SentryConnector: Error validando token - {e}")
            self._http = None
            return False

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Sentry.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "create_release": self._create_release,
            "list_releases": self._list_releases,
            "list_projects": self._list_projects,
            "get_event": self._get_event,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Auth Token de Sentry este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Sentry."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_issues(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista issues (errores) de un proyecto de Sentry.

        Args:
            params: Debe contener 'organization_slug' y 'project_slug', opcionalmente
                    'query', 'limit', 'cursor', 'sort', 'statsPeriod'
        """
        org = params.get("organization_slug", "")
        project = params.get("project_slug", "")
        if not org or not project:
            return {"success": False, "error": "Parametros requeridos: organization_slug, project_slug"}
        self._log_operation("list_issues", f"org={org}, project={project}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {"project": project}
        for key in ("query", "sort", "statsPeriod", "cursor", "limit", "start", "end"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_issues: list[dict[str, Any]] = []
            max_pages = params.get("max_pages", 10)
            cursor = query_params.pop("cursor", None)

            for _ in range(max_pages):
                if cursor:
                    query_params["cursor"] = cursor
                resp = self._http.get(f"/organizations/{org}/issues/", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"Sentry API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                data = resp.json()
                if isinstance(data, list):
                    all_issues.extend(data)
                elif isinstance(data, dict):
                    all_issues.extend(data.get("data", []))

                # Sentry uses Link header for pagination
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

                # Extract cursor from next URL
                next_url = links.get("next", "")
                if "cursor=" in next_url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    cursor = qs.get("cursor", [None])[0]
                else:
                    break

            return {
                "success": True,
                "issues": all_issues,
            }

        except HTTPClientError as e:
            logger.error(f"SentryConnector list_issues error: {e}")
            return {"success": False, "error": str(e)}

    def _get_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un issue (error) por su ID.

        Args:
            params: Debe contener 'organization_slug' y 'issue_id'
        """
        org = params.get("organization_slug", "")
        issue_id = params.get("issue_id", "")
        if not org or not issue_id:
            return {"success": False, "error": "Parametros requeridos: organization_slug, issue_id"}
        self._log_operation("get_issue", f"org={org}, issue={issue_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        try:
            resp = self._http.get(f"/organizations/{org}/issues/{issue_id}/")
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Sentry API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "id": data.get("id", issue_id),
                    "title": data.get("title", ""),
                    "status": data.get("status", "unresolved"),
                    "level": data.get("level", ""),
                    "count": data.get("count", 0),
                    "userCount": data.get("userCount", 0),
                    "firstSeen": data.get("firstSeen", ""),
                    "lastSeen": data.get("lastSeen", ""),
                    "platform": data.get("platform", ""),
                    "project": data.get("project", {}).get("slug", "") if isinstance(data.get("project"), dict) else "",
                    "type": data.get("type", ""),
                    "shortId": data.get("shortId", ""),
                    "permalink": data.get("permalink", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"SentryConnector get_issue error: {e}")
            return {"success": False, "error": str(e)}

    def _create_release(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una liberacion en Sentry.

        Args:
            params: Debe contener 'organization_slug', 'version' y 'projects' (lista)
                    opcionalmente 'refs', 'commitCount', 'url', 'dateReleased'
        """
        org = params.get("organization_slug", "")
        version = params.get("version", "")
        projects = params.get("projects", [])
        if not org or not version or not projects:
            return {"success": False, "error": "Parametros requeridos: organization_slug, version, projects"}
        self._log_operation("create_release", f"org={org}, version={version}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"version": version, "projects": projects}
        for key in ("refs", "commitCount", "url", "dateReleased", "dateStarted"):
            if key in params:
                body[key] = params[key]

        try:
            resp = self._http.post(f"/organizations/{org}/releases/", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Sentry API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "version": data.get("version", version),
                    "projects": data.get("projects", projects),
                    "dateCreated": data.get("dateCreated", ""),
                    "dateReleased": data.get("dateReleased"),
                    "url": data.get("url", ""),
                    "shortVersion": data.get("shortVersion", ""),
                    "author": data.get("author", {}),
                    "commitCount": data.get("commitCount", 0),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"SentryConnector create_release error: {e}")
            return {"success": False, "error": str(e)}

    def _list_releases(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista liberaciones de un proyecto.

        Args:
            params: Debe contener 'organization_slug' y 'project_slug'
                    opcionalmente 'cursor', 'limit'
        """
        org = params.get("organization_slug", "")
        project = params.get("project_slug", "")
        if not org or not project:
            return {"success": False, "error": "Parametros requeridos: organization_slug, project_slug"}
        self._log_operation("list_releases", f"org={org}, project={project}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {"project": project}
        for key in ("cursor", "limit", "query"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_releases: list[dict[str, Any]] = []
            max_pages = params.get("max_pages", 10)
            cursor = query_params.pop("cursor", None)

            for _ in range(max_pages):
                if cursor:
                    query_params["cursor"] = cursor
                resp = self._http.get(f"/organizations/{org}/releases/", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"Sentry API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                data = resp.json()
                if isinstance(data, list):
                    all_releases.extend(data)
                elif isinstance(data, dict):
                    all_releases.extend(data.get("data", []))

                # Check pagination via Link header
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

                # Extract cursor from next URL
                next_url = links.get("next", "")
                if "cursor=" in next_url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    cursor = qs.get("cursor", [None])[0]
                else:
                    break

            return {
                "success": True,
                "releases": all_releases,
            }

        except HTTPClientError as e:
            logger.error(f"SentryConnector list_releases error: {e}")
            return {"success": False, "error": str(e)}

    def _list_projects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista proyectos de una organizacion en Sentry.

        Args:
            params: Debe contener 'organization_slug'
                    opcionalmente 'cursor', 'limit', 'query'
        """
        org = params.get("organization_slug", "")
        if not org:
            return {"success": False, "error": "Parametro requerido: organization_slug"}
        self._log_operation("list_projects", f"org={org}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("cursor", "limit", "query"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_projects: list[dict[str, Any]] = []
            max_pages = params.get("max_pages", 10)
            cursor = query_params.pop("cursor", None)

            for _ in range(max_pages):
                if cursor:
                    query_params["cursor"] = cursor
                resp = self._http.get(f"/organizations/{org}/projects/", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"Sentry API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                data = resp.json()
                if isinstance(data, list):
                    all_projects.extend(data)
                elif isinstance(data, dict):
                    all_projects.extend(data.get("data", []))

                # Check pagination via Link header
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

                # Extract cursor from next URL
                next_url = links.get("next", "")
                if "cursor=" in next_url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    cursor = qs.get("cursor", [None])[0]
                else:
                    break

            return {
                "success": True,
                "projects": all_projects,
            }

        except HTTPClientError as e:
            logger.error(f"SentryConnector list_projects error: {e}")
            return {"success": False, "error": str(e)}

    def _get_event(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un evento especifico de Sentry.

        Args:
            params: Debe contener 'organization_slug', 'project_slug' y 'event_id'
        """
        org = params.get("organization_slug", "")
        project = params.get("project_slug", "")
        event_id = params.get("event_id", "")
        if not org or not project or not event_id:
            return {"success": False, "error": "Parametros requeridos: organization_slug, project_slug, event_id"}
        self._log_operation("get_event", f"event={event_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        try:
            resp = self._http.get(f"/projects/{org}/{project}/events/{event_id}/")
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Sentry API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "id": data.get("id", event_id),
                    "eventID": data.get("eventID", ""),
                    "message": data.get("message", ""),
                    "title": data.get("title", ""),
                    "tags": data.get("tags", []),
                    "contexts": data.get("contexts", {}),
                    "dateCreated": data.get("dateCreated", ""),
                    "dateReceived": data.get("dateReceived", ""),
                    "level": data.get("level", ""),
                    "platform": data.get("platform", ""),
                    "environment": data.get("environment", ""),
                    "release": data.get("release", ""),
                    "user": data.get("user", {}),
                    "entries": data.get("entries", []),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"SentryConnector get_event error: {e}")
            return {"success": False, "error": str(e)}


SENTRY_SCHEMA = ConnectorSchema(
    name="sentry",
    version="1.0.0",
    description="Gestiona errores, liberaciones y alertas via Sentry",
    category="devops_monitoring",
    icon="alert-circle",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_issues", description="Lista errores", category="read"),
        ActionDefinition(name="get_issue", description="Obtiene un error", category="read"),
        ActionDefinition(name="create_release", description="Crea una liberacion", category="write"),
        ActionDefinition(name="list_releases", description="Lista liberaciones", category="read"),
        ActionDefinition(name="list_projects", description="Lista proyectos", category="read"),
        ActionDefinition(name="get_event", description="Obtiene un evento", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["auth_token"], description="Sentry Auth Token")
    ],
)
