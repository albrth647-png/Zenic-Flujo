"""
Conector Dropbox — Operaciones de Almacenamiento de Archivos
================================================================

Permite subir, descargar, listar y gestionar archivos en
cuentas de Dropbox usando la API v2 (RPC-style).
"""

from __future__ import annotations

import json
import os
from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class DropboxConnector(BaseConnector):
    """Conector para Dropbox: operaciones CRUD en archivos y carpetas.

    Usa la Dropbox API v2 (https://api.dropboxapi.com/2/) con
    autenticacion OAuth2 Bearer token via HttpClient.
    """

    name = "dropbox"
    version = "1.0.0"
    description = "Sube, descarga y gestiona archivos en cuentas de Dropbox"
    category = "cloud_storage"
    icon = "folder"
    author = "Zenic-Flijo"

    # Dropbox API endpoints
    _API_BASE = "https://api.dropboxapi.com/2"
    _CONTENT_BASE = "https://content.dropboxapi.com/2"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = self._API_BASE
        self._http: HttpClient | None = None
        self._content_http: HttpClient | None = None
        self._access_token: str = ""

    # ── Conexion ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establece conexion con la API de Dropbox."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("DropboxConnector: credenciales OAuth2 no configuradas")
            return False

        # Extraer credenciales
        creds = self._auth_provider.get_credentials() if hasattr(self._auth_provider, "get_credentials") else {}
        self._access_token = creds.get("access_token", os.environ.get("DROPBOX_ACCESS_TOKEN", ""))

        if not self._access_token:
            logger.error("DropboxConnector: access_token no proporcionado")
            return False

        # Inicializar HttpClients
        self._http = HttpClient(
            base_url=self._API_BASE,
            connector_name=self.name,
            timeout=30,
            default_headers={
                "Content-Type": "application/json",
            },
        )
        self._http.set_auth("Bearer", token=self._access_token)

        self._content_http = HttpClient(
            base_url=self._CONTENT_BASE,
            connector_name=self.name,
            timeout=60,
            default_headers={
                "Content-Type": "application/octet-stream",
            },
        )
        self._content_http.set_auth("Bearer", token=self._access_token)

        # Verificar conexion obteniendo la cuenta del usuario
        try:
            resp = self._http.post("/users/get_current_account")
            if resp.ok:
                body = resp.json() if isinstance(resp.body, str) else resp.body
                account_id = body.get("account_id", "") if isinstance(body, dict) else ""
                self._connected = True
                self._log_operation("connect", f"Dropbox API OK, account_id={account_id}")
                return True
            logger.error(f"DropboxConnector: API respondio {resp.status_code}: {resp.body}")
            return False
        except HTTPClientError as exc:
            logger.error(f"DropboxConnector: API fallo: {exc}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Dropbox."""
        action_map: dict[str, Any] = {
            "upload_file": self._upload_file,
            "download_file": self._download_file,
            "list_folder": self._list_folder,
            "delete_file": self._delete_file,
            "create_folder": self._create_folder,
            "get_temporary_link": self._get_temporary_link,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Dropbox esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Dropbox."""
        self._connected = False
        self._http = None
        self._content_http = None
        self._log_operation("disconnect")
        return True

    # ── Acciones ───────────────────────────────────────────────

    def _upload_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sube un archivo a Dropbox usando upload session.

        Args:
            params: Debe contener 'path' y 'content' (o 'file_path')
        """
        path = params.get("path", "")
        content = params.get("content")
        file_path = params.get("file_path")
        mode = params.get("mode", "add")  # add, overwrite, update
        autorename = params.get("autorename", False)
        mute = params.get("mute", False)

        if not path:
            return {"success": False, "error": "Parametro requerido: path"}
        if content is None and not file_path:
            return {"success": False, "error": "Debe proporcionar 'content' o 'file_path'"}

        # Leer contenido
        if content is None and file_path:
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
            except OSError as exc:
                return {"success": False, "error": f"Error leyendo archivo: {exc}"}

        if isinstance(content, str):
            content = content.encode("utf-8")

        self._log_operation("upload_file", f"path={path}, size={len(content)}")

        if not self._content_http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            # Usar content-upload endpoint de Dropbox
            dropbox_api_args = json.dumps({
                "path": path,
                "mode": mode,
                "autorename": autorename,
                "mute": mute,
            })

            # Dropbox upload usa el endpoint de contenido
            import requests as req_lib

            url = f"{self._CONTENT_BASE}/files/upload"
            resp = req_lib.post(
                url,
                data=content,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/octet-stream",
                    "Dropbox-API-Arg": dropbox_api_args,
                },
                timeout=60,
            )

            if 200 <= resp.status_code < 300:
                result = resp.json()
                return {
                    "success": True,
                    "path": result.get("path_display", path),
                    "id": result.get("id", ""),
                    "size": result.get("size", len(content)),
                    "revision": result.get("rev", ""),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}

        except Exception as exc:
            return {"success": False, "error": f"Error inesperado: {exc}"}

    def _download_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Descarga un archivo de Dropbox.

        Args:
            params: Debe contener 'path'
        """
        path = params.get("path", "")
        if not path:
            return {"success": False, "error": "Parametro requerido: path"}

        self._log_operation("download_file", f"path={path}")

        try:
            import requests as req_lib

            dropbox_api_args = json.dumps({"path": path})

            url = f"{self._CONTENT_BASE}/files/download"
            resp = req_lib.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Dropbox-API-Arg": dropbox_api_args,
                },
                timeout=60,
            )

            if 200 <= resp.status_code < 300:
                # Dropbox devuelve metadata en el header Dropbox-API-Result
                api_result = resp.headers.get("Dropbox-API-Result", "{}")
                try:
                    metadata = json.loads(api_result)
                except json.JSONDecodeError:
                    metadata = {}

                return {
                    "success": True,
                    "path": path,
                    "content": resp.content,
                    "size_bytes": len(resp.content),
                    "metadata": metadata,
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}

        except Exception as exc:
            return {"success": False, "error": f"Error inesperado: {exc}"}

    def _list_folder(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista el contenido de una carpeta de Dropbox con paginacion.

        Args:
            params: Debe contener 'path' y opcionalmente 'limit', 'recursive', 'cursor'
        """
        path = params.get("path", "")
        limit = params.get("limit", 100)
        recursive = params.get("recursive", False)
        cursor = params.get("cursor", "")

        self._log_operation("list_folder", f"path={path}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            # Si hay cursor, continuar listando
            if cursor:
                resp = self._http.post(
                    "/files/list_folder/continue",
                    json={"cursor": cursor},
                )
            else:
                resp = self._http.post(
                    "/files/list_folder",
                    json={
                        "path": path,
                        "recursive": recursive,
                        "limit": limit,
                        "include_media_info": False,
                        "include_deleted": False,
                        "include_has_explicit_shared_members": False,
                    },
                )

            if not resp.ok:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}

            body = resp.json() if isinstance(resp.body, str) else resp.body
            if not isinstance(body, dict):
                return {"success": False, "error": "Respuesta inesperada de Dropbox API"}

            entries = []
            for entry in body.get("entries", []):
                entry_info: dict[str, Any] = {
                    "name": entry.get("name", ""),
                    "path_lower": entry.get("path_lower", ""),
                    "path_display": entry.get("path_display", ""),
                    "type": entry.get(".tag", ""),  # file or folder
                }
                # Metadata especifica de archivos
                if entry.get(".tag") == "file":
                    entry_info["size"] = entry.get("size", 0)
                    entry_info["content_type"] = entry.get("client_modified", "")
                    entry_info["revision"] = entry.get("rev", "")
                    entry_info["client_modified"] = entry.get("client_modified", "")
                    entry_info["server_modified"] = entry.get("server_modified", "")
                entries.append(entry_info)

            return {
                "success": True,
                "path": path,
                "entries": entries,
                "total": len(entries),
                "has_more": body.get("has_more", False),
                "cursor": body.get("cursor", ""),
            }

        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _delete_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un archivo o carpeta de Dropbox.

        Args:
            params: Debe contener 'path'
        """
        path = params.get("path", "")
        if not path:
            return {"success": False, "error": "Parametro requerido: path"}

        self._log_operation("delete_file", f"path={path}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            resp = self._http.post(
                "/files/delete_v2",
                json={"path": path},
            )

            if resp.ok:
                body = resp.json() if isinstance(resp.body, str) else resp.body
                metadata = body.get("metadata", {}) if isinstance(body, dict) else {}
                return {
                    "success": True,
                    "path": metadata.get("path_display", path),
                    "deleted": True,
                    "metadata": metadata,
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _create_folder(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una carpeta en Dropbox.

        Args:
            params: Debe contener 'path'
        """
        path = params.get("path", "")
        autorename = params.get("autorename", False)

        if not path:
            return {"success": False, "error": "Parametro requerido: path"}

        self._log_operation("create_folder", f"path={path}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            resp = self._http.post(
                "/files/create_folder_v2",
                json={"path": path, "autorename": autorename},
            )

            if resp.ok:
                body = resp.json() if isinstance(resp.body, str) else resp.body
                metadata = body.get("metadata", {}) if isinstance(body, dict) else {}
                return {
                    "success": True,
                    "path": metadata.get("path_display", path),
                    "id": metadata.get("id", ""),
                    "metadata": metadata,
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _get_temporary_link(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera un enlace temporal para descargar un archivo.

        Args:
            params: Debe contener 'path'
        """
        path = params.get("path", "")
        if not path:
            return {"success": False, "error": "Parametro requerido: path"}

        self._log_operation("get_temporary_link", f"path={path}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            resp = self._http.post(
                "/files/get_temporary_link",
                json={"path": path},
            )

            if resp.ok:
                body = resp.json() if isinstance(resp.body, str) else resp.body
                if isinstance(body, dict):
                    link = body.get("link", "")
                    metadata = body.get("metadata", {})
                    return {
                        "success": True,
                        "path": path,
                        "link": link,
                        "metadata": metadata,
                    }
                return {"success": False, "error": "Respuesta inesperada de Dropbox API"}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}


DROPBOX_SCHEMA = ConnectorSchema(
    name="dropbox",
    version="1.0.0",
    description="Sube, descarga y gestiona archivos en cuentas de Dropbox",
    category="cloud_storage",
    icon="folder",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="upload_file", description="Sube un archivo", category="write"),
        ActionDefinition(name="download_file", description="Descarga un archivo", category="read"),
        ActionDefinition(name="list_folder", description="Lista contenido de carpeta", category="read"),
        ActionDefinition(name="delete_file", description="Elimina un archivo", category="delete"),
        ActionDefinition(name="create_folder", description="Crea una carpeta", category="write"),
        ActionDefinition(name="get_temporary_link", description="Genera enlace temporal", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["access_token"], description="Dropbox OAuth2 Access Token")
    ],
)
