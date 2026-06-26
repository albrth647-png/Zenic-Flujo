"""
Conector Jira — Gestion de Issues via Jira API
===================================================

Permite crear, buscar, actualizar y gestionar issues,
proyectos y sprints en Jira via la REST API usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class JiraConnector(BaseConnector):
    """Conector para Jira: issues, proyectos y sprints."""

    name = "jira"
    version = "1.0.0"
    description = "Gestiona issues, proyectos y sprints en Jira"
    category = "project_management"
    icon = "check-square"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._domain: str = ""
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Jira."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("JiraConnector: credenciales no configuradas")
            return False

        # Extract domain and credentials
        self._domain = getattr(self._auth_provider, "_domain", "") or ""
        email = getattr(self._auth_provider, "_username", "") or getattr(self._auth_provider, "_email", "")
        api_token = getattr(self._auth_provider, "_password", "") or getattr(self._auth_provider, "_api_token", "")

        if not self._domain:
            # Try to get from custom attributes
            self._domain = getattr(self._auth_provider, "domain", "")

        if not self._domain:
            logger.error("JiraConnector: domain no configurado")
            return False

        self._base_url = f"https://{self._domain}.atlassian.net/rest/api/3"
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )

        # Jira uses Basic Auth with email:api_token
        if email and api_token:
            self._http.set_auth("Basic", username=email, password=api_token)
        else:
            # Try Bearer token
            access_token = getattr(self._auth_provider, "_access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)
            else:
                logger.error("JiraConnector: no se pudieron obtener las credenciales")
                return False

        # Validate credentials
        try:
            response = self._http.get("/myself")
            if response.status_code == 401:
                logger.error("JiraConnector: credenciales invalidas (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"JiraConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "Conexion Jira establecida")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Jira.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_issue": self._create_issue,
            "get_issue": self._get_issue,
            "search_issues": self._search_issues,
            "update_issue": self._update_issue,
            "add_comment": self._add_comment,
            "list_projects": self._list_projects,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Jira esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Jira."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un issue en Jira.

        Args:
            params: Debe contener 'project_key', 'summary', 'issue_type' y opcionalmente 'description'
        """
        project_key = params.get("project_key", "")
        summary = params.get("summary", "")
        issue_type = params.get("issue_type", "Task")
        description = params.get("description", "")
        if not project_key or not summary:
            return {"success": False, "error": "Parametros requeridos: project_key, summary"}
        self._log_operation("create_issue", f"project={project_key}")

        try:
            issue_body: dict[str, Any] = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": issue_type},
                }
            }
            if description:
                issue_body["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                }
            # Add any additional fields
            extra_fields = params.get("fields", {})
            if extra_fields:
                issue_body["fields"].update(extra_fields)

            response = self._http.post("/issue", json=issue_body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "key": data.get("key", ""),
                "self": data.get("self", ""),
                "id": data.get("id", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un issue por su clave.

        Args:
            params: Debe contener 'issue_key'
        """
        issue_key = params.get("issue_key", "")
        fields = params.get("fields", "")
        if not issue_key:
            return {"success": False, "error": "Parametro requerido: issue_key"}
        self._log_operation("get_issue", f"key={issue_key}")

        try:
            query_params: dict[str, Any] | None = None
            if fields:
                query_params = {"fields": fields}
            response = self._http.get(f"/issue/{issue_key}", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            fields_data = data.get("fields", {})
            return {
                "success": True,
                "key": data.get("key", issue_key),
                "id": data.get("id", ""),
                "fields": fields_data,
                "self": data.get("self", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _search_issues(self, params: dict[str, Any]) -> dict[str, Any]:
        """Busca issues usando JQL.

        Args:
            params: Debe contener 'jql' y opcionalmente 'max_results'
        """
        jql = params.get("jql", "")
        max_results = params.get("max_results", 50)
        start_at = params.get("start_at", 0)
        fields = params.get("fields", "")
        if not jql:
            return {"success": False, "error": "Parametro requerido: jql"}
        self._log_operation("search_issues", f"jql={jql[:80]}...")

        try:
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at,
            }
            if fields:
                body["fields"] = fields.split(",") if isinstance(fields, str) else fields

            response = self._http.post("/search", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "issues": data.get("issues", []),
                "total": data.get("total", 0),
                "maxResults": data.get("maxResults", max_results),
                "startAt": data.get("startAt", start_at),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _update_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza campos de un issue en Jira.

        Args:
            params: Debe contener 'issue_key' y 'fields' (dict de campos a actualizar)
        """
        issue_key = params.get("issue_key", "")
        fields = params.get("fields", {})
        if not issue_key or not fields:
            return {"success": False, "error": "Parametros requeridos: issue_key, fields"}
        self._log_operation("update_issue", f"key={issue_key}")

        try:
            response = self._http.put(f"/issue/{issue_key}", json={"fields": fields})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            return {"success": True, "key": issue_key}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _add_comment(self, params: dict[str, Any]) -> dict[str, Any]:
        """Anade un comentario a un issue de Jira.

        Args:
            params: Debe contener 'issue_key' y 'body'
        """
        issue_key = params.get("issue_key", "")
        body = params.get("body", "")
        if not issue_key or not body:
            return {"success": False, "error": "Parametros requeridos: issue_key, body"}
        self._log_operation("add_comment", f"key={issue_key}")

        try:
            comment_body = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
                }
            }
            response = self._http.post(f"/issue/{issue_key}/comment", json=comment_body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", ""),
                "issue_key": issue_key,
                "created": data.get("created", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_projects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los proyectos de Jira accesibles."""
        self._log_operation("list_projects")

        try:
            query_params: dict[str, Any] = {}
            if params.get("start_at"):
                query_params["startAt"] = params["start_at"]
            if params.get("max_results"):
                query_params["maxResults"] = params["max_results"]

            response = self._http.get("/project", params=query_params if query_params else None)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {"success": True, "projects": data if isinstance(data, list) else []}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


JIRA_SCHEMA = ConnectorSchema(
    name="jira",
    version="1.0.0",
    description="Gestiona issues, proyectos y sprints en Jira",
    category="project_management",
    icon="check-square",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_issue", description="Crea un issue", category="write"),
        ActionDefinition(name="get_issue", description="Obtiene un issue", category="read"),
        ActionDefinition(name="search_issues", description="Busca issues con JQL", category="read"),
        ActionDefinition(name="update_issue", description="Actualiza un issue", category="write"),
        ActionDefinition(name="add_comment", description="Anade un comentario", category="write"),
        ActionDefinition(name="list_projects", description="Lista proyectos", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="basic", required_fields=["email", "api_token", "domain"], description="Jira API Token + Domain")
    ],
)
