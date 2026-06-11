"""
Conector Asana — Gestion de Tareas via Asana API
====================================================

Permite gestionar tareas, proyectos, secciones y etiquetas
en Asana via la REST API usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AsanaConnector(BaseConnector):
    """Conector para Asana: tareas, proyectos y secciones."""

    name = "asana"
    version = "1.0.0"
    description = "Gestiona tareas, proyectos y secciones en Asana"
    category = "project_management"
    icon = "list"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://app.asana.com/api/1.0"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Asana."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("AsanaConnector: Personal Access Token no configurado")
            return False

        # Extract PAT from auth provider
        pat = getattr(self._auth_provider, "_api_key", "") or getattr(self._auth_provider, "_token", "")
        if not pat:
            auth_request = self._auth_provider.apply_auth({"headers": {}})
            pat = auth_request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=pat)

        # Validate credentials
        try:
            response = self._http.get("/users/me")
            if response.status_code == 401:
                logger.error("AsanaConnector: PAT invalido (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"AsanaConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "PAT configurado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Asana.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_task": self._create_task,
            "get_task": self._get_task,
            "list_tasks": self._list_tasks,
            "update_task": self._update_task,
            "list_projects": self._list_projects,
            "create_project": self._create_project,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el PAT de Asana este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Asana."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_task(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una tarea en Asana.

        Args:
            params: Debe contener 'name' y 'projects' (lista de IDs), opcionalmente 'notes', 'assignee'
        """
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        self._log_operation("create_task", f"name={name}")

        try:
            # Build task data — Asana uses 'data' wrapper
            task_data: dict[str, Any] = {"name": name}
            if params.get("projects"):
                task_data["projects"] = params["projects"]
            if params.get("notes"):
                task_data["notes"] = params["notes"]
            if params.get("assignee"):
                task_data["assignee"] = params["assignee"]
            if params.get("due_on"):
                task_data["due_on"] = params["due_on"]
            if params.get("due_at"):
                task_data["due_at"] = params["due_at"]
            # Allow any additional fields
            extra = params.get("data", {})
            if isinstance(extra, dict):
                task_data.update(extra)

            response = self._http.post("/tasks", json={"data": task_data})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            task = result.get("data", {})
            return {
                "success": True,
                "gid": task.get("gid", ""),
                "name": task.get("name", name),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_task(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene una tarea por su GID.

        Args:
            params: Debe contener 'task_gid'
        """
        task_gid = params.get("task_gid", "")
        if not task_gid:
            return {"success": False, "error": "Parametro requerido: task_gid"}
        self._log_operation("get_task", f"gid={task_gid}")

        try:
            query_params: dict[str, Any] | None = None
            opt_fields = params.get("opt_fields", "")
            if opt_fields:
                query_params = {"opt_fields": opt_fields}

            response = self._http.get(f"/tasks/{task_gid}", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            task = result.get("data", {})
            return {
                "success": True,
                "gid": task.get("gid", task_gid),
                "name": task.get("name", ""),
                "completed": task.get("completed", False),
                "data": task,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_tasks(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista tareas de un proyecto o workspace.

        Args:
            params: Debe contener 'project_gid' o 'workspace_gid'
        """
        project_gid = params.get("project_gid", "")
        workspace_gid = params.get("workspace_gid", "")
        assignee_gid = params.get("assignee_gid", "")
        limit = params.get("limit", 20)
        offset = params.get("offset", "")
        self._log_operation("list_tasks", f"project={project_gid}")

        try:
            if project_gid:
                # List tasks in a project
                query_params: dict[str, Any] = {"limit": limit}
                if offset:
                    query_params["offset"] = offset
                opt_fields = params.get("opt_fields", "")
                if opt_fields:
                    query_params["opt_fields"] = opt_fields
                response = self._http.get(f"/projects/{project_gid}/tasks", params=query_params)
            elif workspace_gid and assignee_gid:
                # List tasks assigned to a user in a workspace
                query_params = {
                    "workspace": workspace_gid,
                    "assignee": assignee_gid,
                    "limit": limit,
                }
                if offset:
                    query_params["offset"] = offset
                response = self._http.get("/tasks", params=query_params)
            else:
                return {"success": False, "error": "Parametros requeridos: project_gid o (workspace_gid + assignee_gid)"}

            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
                "next_page": result.get("next_page", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _update_task(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza una tarea en Asana.

        Args:
            params: Debe contener 'task_gid' y 'fields' (dict de campos)
        """
        task_gid = params.get("task_gid", "")
        fields = params.get("fields", {})
        if not task_gid or not fields:
            return {"success": False, "error": "Parametros requeridos: task_gid, fields"}
        self._log_operation("update_task", f"gid={task_gid}")

        try:
            response = self._http.put(f"/tasks/{task_gid}", json={"data": fields})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            task = result.get("data", {})
            return {
                "success": True,
                "gid": task.get("gid", task_gid),
                "data": task,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_projects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista proyectos del workspace.

        Args:
            params: Debe contener 'workspace_gid' y opcionalmente 'archived'
        """
        workspace_gid = params.get("workspace_gid", "")
        archived = params.get("archived", False)
        limit = params.get("limit", 20)
        offset = params.get("offset", "")
        self._log_operation("list_projects")

        try:
            query_params: dict[str, Any] = {
                "workspace": workspace_gid,
                "archived": str(archived).lower(),
                "limit": limit,
            }
            if offset:
                query_params["offset"] = offset
            opt_fields = params.get("opt_fields", "")
            if opt_fields:
                query_params["opt_fields"] = opt_fields

            response = self._http.get("/projects", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
                "next_page": result.get("next_page", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_project(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un proyecto en Asana.

        Args:
            params: Debe contener 'name', 'workspace_gid' y opcionalmente 'color', 'notes'
        """
        name = params.get("name", "")
        workspace_gid = params.get("workspace_gid", "")
        if not name or not workspace_gid:
            return {"success": False, "error": "Parametros requeridos: name, workspace_gid"}
        self._log_operation("create_project", f"name={name}")

        try:
            project_data: dict[str, Any] = {
                "name": name,
                "workspace": workspace_gid,
            }
            if params.get("color"):
                project_data["color"] = params["color"]
            if params.get("notes"):
                project_data["notes"] = params["notes"]
            if params.get("team"):
                project_data["team"] = params["team"]
            # Allow any additional fields
            extra = params.get("data", {})
            if isinstance(extra, dict):
                project_data.update(extra)

            response = self._http.post("/projects", json={"data": project_data})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            project = result.get("data", {})
            return {
                "success": True,
                "gid": project.get("gid", ""),
                "name": project.get("name", name),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


ASANA_SCHEMA = ConnectorSchema(
    name="asana",
    version="1.0.0",
    description="Gestiona tareas, proyectos y secciones en Asana",
    category="project_management",
    icon="list",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_task", description="Crea una tarea", category="write"),
        ActionDefinition(name="get_task", description="Obtiene una tarea", category="read"),
        ActionDefinition(name="list_tasks", description="Lista tareas", category="read"),
        ActionDefinition(name="update_task", description="Actualiza una tarea", category="write"),
        ActionDefinition(name="list_projects", description="Lista proyectos", category="read"),
        ActionDefinition(name="create_project", description="Crea un proyecto", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["personal_access_token"], description="Asana Personal Access Token")
    ],
)
