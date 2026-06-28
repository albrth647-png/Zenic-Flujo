"""
Conector GitHub — Repos, Issues y PRs via GitHub API
========================================================

Permite gestionar repositorios, issues, pull requests,
acciones y busqueda via la GitHub REST API.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class GithubConnector(BaseConnector):
    """Conector para GitHub: repos, issues, PRs y acciones."""

    name = "github"
    version = "1.0.0"
    description = "Gestiona repositorios, issues y pull requests via GitHub API"
    category = "devops_monitoring"
    icon = "git-branch"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.github.com"
        self._http: HttpClient | None = None

    def _get_token(self) -> str:
        """Extract the API token from the auth provider."""
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
        if auth_header.startswith("Basic "):
            return auth_header  # Use full Basic header
        # Try X-API-Key header
        api_key = request["headers"].get("X-API-Key", "")
        if api_key:
            return api_key
        # Try direct attribute access for common patterns
        for attr in ("_api_key", "_token", "_access_token"):
            if hasattr(self._auth_provider, attr):
                val = getattr(self._auth_provider, attr, "")
                if isinstance(val, str) and val:
                    return val
        return ""

    def connect(self) -> bool:
        """Establece conexion con la GitHub API."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("GithubConnector: Token no configurado")
            return False

        token = self._get_token()
        if not token:
            logger.error("GithubConnector: No se pudo extraer el token del auth provider")
            return False

        self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
        # GitHub uses token auth (not Bearer): Authorization: token <token>
        self._http.set_header("Authorization", f"token {token}")
        self._http.set_header("Accept", "application/vnd.github+json")

        # Validate credentials by fetching authenticated user
        try:
            resp = self._http.get("/user")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Token configurado y validado")
                return True
            else:
                logger.error(f"GithubConnector: Validacion de token fallida - {resp.status_code}")
                self._http = None
                return False
        except HTTPClientError as e:
            logger.error(f"GithubConnector: Error validando token - {e}")
            self._http = None
            return False

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector GitHub.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "list_repos": self._list_repos,
            "create_issue": self._create_issue,
            "list_issues": self._list_issues,
            "create_pull_request": self._create_pull_request,
            "list_pull_requests": self._list_pull_requests,
            "search": self._search,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Token de GitHub este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con GitHub."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_repos(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista repositorios del usuario autenticado.

        Args:
            params: Opcionalmente 'type' (all/owner/member), 'sort', 'per_page', 'page'
        """
        self._log_operation("list_repos", f"per_page={params.get('per_page', 30)}")
        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("type", "sort", "direction", "per_page", "page", "since", "visibility"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_repos: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 30)
            max_pages = params.get("max_pages", 10)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get("/user/repos", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitHub API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                repos = resp.json()
                if not isinstance(repos, list) or len(repos) == 0:
                    break

                all_repos.extend(repos)

                # Check pagination via Link header
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

            return {
                "success": True,
                "repos": all_repos,
                "total_count": len(all_repos),
            }

        except HTTPClientError as e:
            logger.error(f"GithubConnector list_repos error: {e}")
            return {"success": False, "error": str(e)}

    def _create_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un issue en un repositorio.

        Args:
            params: Debe contener 'owner', 'repo', 'title' y opcionalmente 'body', 'labels', 'assignees'
        """
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        title = params.get("title", "")
        if not owner or not repo or not title:
            return {"success": False, "error": "Parametros requeridos: owner, repo, title"}
        self._log_operation("create_issue", f"{owner}/{repo}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"title": title}
        for key in ("body", "labels", "assignees", "milestone", "state"):
            if key in params:
                body[key] = params[key]

        try:
            resp = self._http.post(f"/repos/{owner}/{repo}/issues", json=body)
            if not resp.ok:
                error_detail = resp.body if isinstance(resp.body, (dict, str)) else "Unknown error"
                return {
                    "success": False,
                    "error": f"GitHub API error: {resp.status_code}",
                    "details": error_detail,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "number": data.get("number"),
                    "title": data.get("title", title),
                    "state": data.get("state", "open"),
                    "html_url": data.get("html_url", ""),
                    "created_at": data.get("created_at", ""),
                    "user": data.get("user", {}).get("login", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GithubConnector create_issue error: {e}")
            return {"success": False, "error": str(e)}

    def _list_issues(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista issues de un repositorio.

        Args:
            params: Debe contener 'owner', 'repo' y opcionalmente 'state', 'labels', 'per_page', 'page'
        """
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        if not owner or not repo:
            return {"success": False, "error": "Parametros requeridos: owner, repo"}
        self._log_operation("list_issues", f"{owner}/{repo}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("state", "labels", "sort", "direction", "since", "per_page", "page", "milestone", "assignee", "creator"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_issues: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 30)
            max_pages = params.get("max_pages", 10)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get(f"/repos/{owner}/{repo}/issues", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitHub API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                issues = resp.json()
                if not isinstance(issues, list) or len(issues) == 0:
                    break

                all_issues.extend(issues)

                # Check pagination via Link header
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

            return {
                "success": True,
                "issues": all_issues,
                "total_count": len(all_issues),
            }

        except HTTPClientError as e:
            logger.error(f"GithubConnector list_issues error: {e}")
            return {"success": False, "error": str(e)}

    def _create_pull_request(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un pull request en un repositorio.

        Args:
            params: Debe contener 'owner', 'repo', 'title', 'head', 'base' y opcionalmente 'body'
        """
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        title = params.get("title", "")
        head = params.get("head", "")
        base_branch = params.get("base", "main")
        if not owner or not repo or not title or not head:
            return {"success": False, "error": "Parametros requeridos: owner, repo, title, head"}
        self._log_operation("create_pull_request", f"{owner}/{repo}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"title": title, "head": head, "base": base_branch}
        if "body" in params:
            body["body"] = params["body"]
        if "draft" in params:
            body["draft"] = params["draft"]

        try:
            resp = self._http.post(f"/repos/{owner}/{repo}/pulls", json=body)
            if not resp.ok:
                error_detail = resp.body if isinstance(resp.body, (dict, str)) else "Unknown error"
                return {
                    "success": False,
                    "error": f"GitHub API error: {resp.status_code}",
                    "details": error_detail,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "number": data.get("number"),
                    "title": data.get("title", title),
                    "state": data.get("state", "open"),
                    "html_url": data.get("html_url", ""),
                    "created_at": data.get("created_at", ""),
                    "head": data.get("head", {}).get("ref", head),
                    "base": data.get("base", {}).get("ref", base_branch),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GithubConnector create_pull_request error: {e}")
            return {"success": False, "error": str(e)}

    def _list_pull_requests(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista pull requests de un repositorio.

        Args:
            params: Debe contener 'owner', 'repo' y opcionalmente 'state', 'per_page', 'page'
        """
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        if not owner or not repo:
            return {"success": False, "error": "Parametros requeridos: owner, repo"}
        self._log_operation("list_pull_requests", f"{owner}/{repo}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("state", "head", "base", "sort", "direction", "per_page", "page"):
            if key in params:
                query_params[key] = params[key]

        try:
            all_prs: list[dict[str, Any]] = []
            page = query_params.get("page", 1)
            per_page = query_params.get("per_page", 30)
            max_pages = params.get("max_pages", 10)

            for current_page in range(page, page + max_pages):
                query_params["page"] = current_page
                query_params["per_page"] = per_page
                resp = self._http.get(f"/repos/{owner}/{repo}/pulls", params=query_params)

                if not resp.ok:
                    return {
                        "success": False,
                        "error": f"GitHub API error: {resp.status_code}",
                        "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                    }

                prs = resp.json()
                if not isinstance(prs, list) or len(prs) == 0:
                    break

                all_prs.extend(prs)

                # Check pagination via Link header
                link_header = resp.headers.get("Link", "")
                links = HttpClient.parse_link_header(link_header)
                if "next" not in links:
                    break

            return {
                "success": True,
                "pull_requests": all_prs,
                "total_count": len(all_prs),
            }

        except HTTPClientError as e:
            logger.error(f"GithubConnector list_pull_requests error: {e}")
            return {"success": False, "error": str(e)}

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Busca en GitHub (repositorios, issues, codigo, usuarios).

        Args:
            params: Debe contener 'query' y 'type' (repositories/issues/code/users)
        """
        query = params.get("query", "")
        search_type = params.get("type", "repositories")
        if not query:
            return {"success": False, "error": "Parametro requerido: query"}
        self._log_operation("search", f"type={search_type}, query={query[:50]}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        # Map search type to endpoint
        endpoint_map = {
            "repositories": "/search/repositories",
            "issues": "/search/issues",
            "code": "/search/code",
            "users": "/search/users",
        }
        endpoint = endpoint_map.get(search_type, "/search/repositories")

        query_params: dict[str, Any] = {"q": query}
        for key in ("sort", "order", "per_page", "page"):
            if key in params:
                query_params[key] = params[key]

        try:
            resp = self._http.get(endpoint, params=query_params)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"GitHub API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "items": data.get("items", []),
                    "total_count": data.get("total_count", 0),
                    "incomplete_results": data.get("incomplete_results", False),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"GithubConnector search error: {e}")
            return {"success": False, "error": str(e)}


GITHUB_SCHEMA = ConnectorSchema(
    name="github",
    version="1.0.0",
    description="Gestiona repositorios, issues y pull requests via GitHub API",
    category="devops_monitoring",
    icon="git-branch",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_repos", description="Lista repositorios", category="read"),
        ActionDefinition(name="create_issue", description="Crea un issue", category="write"),
        ActionDefinition(name="list_issues", description="Lista issues", category="read"),
        ActionDefinition(name="create_pull_request", description="Crea un PR", category="write"),
        ActionDefinition(name="list_pull_requests", description="Lista PRs", category="read"),
        ActionDefinition(name="search", description="Busca en GitHub", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["token"], description="GitHub Personal Access Token")
    ],
)
