"""
Conector GitLab — CI/CD y Proyectos via GitLab API
=======================================================

Permite gestionar proyectos, pipelines, jobs y merge
requests via la GitLab REST API.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class GitlabConnector(BaseConnector):
    """Conector para GitLab: proyectos, pipelines y merge requests."""

    name = "gitlab"
    version = "1.0.0"
    description = "Gestiona proyectos, pipelines y merge requests via GitLab API"
    category = "devops_monitoring"
    icon = "git-merge"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://gitlab.com/api/v4"
        self._http: HttpClient | None = None

    def _get_token(self) -> str:
        """Extract the private token from the auth provider."""
        if not self._auth_provider:
            return ""
        # Use apply_auth on a dummy request to extract credentials
        request: dict[str, Any] = {"headers": {}, "params": {}}
        self._auth_provider.apply_auth(request)
        # Check for Authorization header (Bearer or Token)
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
        for attr in ("_api_key", "_token", "_access_token", "_private_token"):
            if hasattr(self._auth_provider, attr):
                val = getattr(self._auth_provider, attr, "")
                if isinstance(val, str) and val:
                    return val
        return ""

    def connect(self) -> bool:
        """Establece conexion con la GitLab API."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("GitlabConnector: Private Token no configurado")
            return False

        token = self._get_token()
        if not token:
            logger.error("GitlabConnector: No se pudo extraer el token del auth provider")
            return False

        self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
        # GitLab uses PRIVATE-TOKEN header
        self._http.set_header("PRIVATE-TOKEN", token)

        # Validate credentials by fetching current user
        try:
            resp = self._http.get("/user")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Private Token configurado y validado")
                return True
            else:
                logger.error(f"GitlabConnector: Validacion de token fallida - {resp.status_code}")
                self._http = None
                return False
        except HTTPClientError as e:
            logger.error(f"GitlabConnector: Error validando token - {e}")
            self._http = None
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector GitLab.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "list_projects": self._list_projects,
            "get_project": self._get_project,
            "list_pipelines": self._list_pipelines,
            "trigger_pipeline": self._trigger_pipeline,
            "create_merge_request": self._create_merge_request,
            "list_merge_requests": self._list_merge_requests,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Private Token de GitLab este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con GitLab."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_projects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista proyectos de GitLab.

        Args:
            params: Opcionalmente 'membership', 'search', 'per_page', 'page',
                    'owned', 'starred', 'simple', 'archived', 'visibility'
        """
        self._log_operation("list_projects", f"per_page={params.get('per_page', 20)}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("membership", "owned", "starred", "search", "simple",
                     "archived", "visibility", "order_by", "sort", "per_page", "page"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_projects: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 20)
            max_pages = params.get("max_pages", 20)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get("/projects", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitLab API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                projects = resp.json()
                if not isinstance(projects, list) or len(projects) == 0:
                    break

                all_projects.extend(projects)

                # GitLab uses X-Next-Page header for pagination
                next_page = resp.headers.get("X-Next-Page", "")
                if not next_page:
                    break

            # Get total count from header
            total = resp.headers.get("X-Total", str(len(all_projects)))  # type: ignore[possibly-undefined]

            return {
                "success": True,
                "projects": all_projects,
                "total_count": int(total) if total.isdigit() else len(all_projects),
            }

        except HTTPClientError as e:
            logger.error(f"GitlabConnector list_projects error: {e}")
            return {"success": False, "error": str(e)}

    def _get_project(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un proyecto por su ID.

        Args:
            params: Debe contener 'project_id'
        """
        project_id = params.get("project_id", "")
        if not project_id:
            return {"success": False, "error": "Parametro requerido: project_id"}
        self._log_operation("get_project", f"id={project_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        # URL-encode the project ID (needed for NAMESPACE/PROJECT format)
        import urllib.parse
        encoded_id = urllib.parse.quote(str(project_id), safe="")

        try:
            resp = self._http.get(f"/projects/{encoded_id}")
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"GitLab API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "id": data.get("id"),
                    "name": data.get("name", ""),
                    "path_with_namespace": data.get("path_with_namespace", ""),
                    "web_url": data.get("web_url", ""),
                    "description": data.get("description", ""),
                    "default_branch": data.get("default_branch", ""),
                    "visibility": data.get("visibility", ""),
                    "created_at": data.get("created_at", ""),
                    "last_activity_at": data.get("last_activity_at", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GitlabConnector get_project error: {e}")
            return {"success": False, "error": str(e)}

    def _list_pipelines(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista pipelines de un proyecto.

        Args:
            params: Debe contener 'project_id' y opcionalmente 'status', 'per_page', 'page',
                    'ref', 'sha', 'yaml_errors', 'name', 'username', 'order_by', 'sort'
        """
        project_id = params.get("project_id", "")
        if not project_id:
            return {"success": False, "error": "Parametro requerido: project_id"}
        self._log_operation("list_pipelines", f"project={project_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        import urllib.parse
        encoded_id = urllib.parse.quote(str(project_id), safe="")

        query_params: dict[str, Any] = {}
        for key in ("status", "ref", "sha", "yaml_errors", "name", "username",
                     "order_by", "sort", "per_page", "page"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_pipelines: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 20)
            max_pages = params.get("max_pages", 10)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get(f"/projects/{encoded_id}/pipelines", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitLab API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                pipelines = resp.json()
                if not isinstance(pipelines, list) or len(pipelines) == 0:
                    break

                all_pipelines.extend(pipelines)

                # GitLab pagination header
                next_page = resp.headers.get("X-Next-Page", "")
                if not next_page:
                    break

            return {
                "success": True,
                "pipelines": all_pipelines,
                "total_count": len(all_pipelines),
            }

        except HTTPClientError as e:
            logger.error(f"GitlabConnector list_pipelines error: {e}")
            return {"success": False, "error": str(e)}

    def _trigger_pipeline(self, params: dict[str, Any]) -> dict[str, Any]:
        """Dispara un pipeline en un proyecto.

        Args:
            params: Debe contener 'project_id' y 'ref', opcionalmente 'variables'
        """
        project_id = params.get("project_id", "")
        ref = params.get("ref", "main")
        if not project_id:
            return {"success": False, "error": "Parametro requerido: project_id"}
        self._log_operation("trigger_pipeline", f"project={project_id}, ref={ref}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        import urllib.parse
        encoded_id = urllib.parse.quote(str(project_id), safe="")

        body: dict[str, Any] = {"ref": ref}
        if "variables" in params:
            # GitLab expects variables as [{"key": "VAR", "value": "val"}]
            variables = params["variables"]
            if isinstance(variables, dict):
                body["variables"] = [
                    {"key": k, "value": v} for k, v in variables.items()
                ]
            elif isinstance(variables, list):
                body["variables"] = variables

        try:
            resp = self._http.post(f"/projects/{encoded_id}/pipeline", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"GitLab API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "id": data.get("id"),
                    "status": data.get("status", "pending"),
                    "ref": data.get("ref", ref),
                    "sha": data.get("sha", ""),
                    "web_url": data.get("web_url", ""),
                    "created_at": data.get("created_at", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GitlabConnector trigger_pipeline error: {e}")
            return {"success": False, "error": str(e)}

    def _create_merge_request(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un merge request en un proyecto.

        Args:
            params: Debe contener 'project_id', 'source_branch', 'target_branch', 'title'
        """
        project_id = params.get("project_id", "")
        source_branch = params.get("source_branch", "")
        title = params.get("title", "")
        target_branch = params.get("target_branch", "main")
        if not project_id or not source_branch or not title:
            return {"success": False, "error": "Parametros requeridos: project_id, source_branch, title"}
        self._log_operation("create_merge_request", f"project={project_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        import urllib.parse
        encoded_id = urllib.parse.quote(str(project_id), safe="")

        body: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
        }
        for key in ("description", "assignee_ids", "reviewer_ids", "labels", "milestone_id", "remove_source_branch", "squash"):
            if key in params:
                body[key] = params[key]

        try:
            resp = self._http.post(f"/projects/{encoded_id}/merge_requests", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"GitLab API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "iid": data.get("iid"),
                    "title": data.get("title", title),
                    "state": data.get("state", "opened"),
                    "web_url": data.get("web_url", ""),
                    "source_branch": data.get("source_branch", source_branch),
                    "target_branch": data.get("target_branch", target_branch),
                    "author": data.get("author", {}).get("username", ""),
                    "created_at": data.get("created_at", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GitlabConnector create_merge_request error: {e}")
            return {"success": False, "error": str(e)}

    def _list_merge_requests(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista merge requests de un proyecto.

        Args:
            params: Debe contener 'project_id' y opcionalmente 'state', 'per_page', 'page',
                    'order_by', 'sort', 'milestone', 'labels', 'author_id', 'assignee_id',
                    'search', 'source_branch', 'target_branch'
        """
        project_id = params.get("project_id", "")
        if not project_id:
            return {"success": False, "error": "Parametro requerido: project_id"}
        self._log_operation("list_merge_requests", f"project={project_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        import urllib.parse
        encoded_id = urllib.parse.quote(str(project_id), safe="")

        query_params: dict[str, Any] = {}
        for key in ("state", "order_by", "sort", "milestone", "labels",
                     "author_id", "assignee_id", "search", "source_branch",
                     "target_branch", "per_page", "page"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_mrs: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 20)
            max_pages = params.get("max_pages", 10)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get(f"/projects/{encoded_id}/merge_requests", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitLab API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                mrs = resp.json()
                if not isinstance(mrs, list) or len(mrs) == 0:
                    break

                all_mrs.extend(mrs)

                # GitLab pagination header
                next_page = resp.headers.get("X-Next-Page", "")
                if not next_page:
                    break

            return {
                "success": True,
                "merge_requests": all_mrs,
                "total_count": len(all_mrs),
            }

        except HTTPClientError as e:
            logger.error(f"GitlabConnector list_merge_requests error: {e}")
            return {"success": False, "error": str(e)}


GITLAB_SCHEMA = ConnectorSchema(
    name="gitlab",
    version="1.0.0",
    description="Gestiona proyectos, pipelines y merge requests via GitLab API",
    category="devops_monitoring",
    icon="git-merge",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_projects", description="Lista proyectos", category="read"),
        ActionDefinition(name="get_project", description="Obtiene un proyecto", category="read"),
        ActionDefinition(name="list_pipelines", description="Lista pipelines", category="read"),
        ActionDefinition(name="trigger_pipeline", description="Dispara un pipeline", category="write"),
        ActionDefinition(name="create_merge_request", description="Crea un MR", category="write"),
        ActionDefinition(name="list_merge_requests", description="Lista MRs", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["private_token"], description="GitLab Private Token")
    ],
)
