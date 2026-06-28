"""
Conector Azure Blob Storage — Operaciones de Almacenamiento
==============================================================

Permite subir, descargar, listar y gestionar blobs en
contenedores de Azure Blob Storage usando la REST API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class AzureBlobConnector(BaseConnector):
    """Conector para Azure Blob Storage: operaciones CRUD en contenedores y blobs.

    Usa la REST API de Azure Blob Storage con autenticacion SharedKey
    o SAS token via HttpClient.
    """

    name = "azure_blob"
    version = "1.0.0"
    description = "Sube, descarga y gestiona blobs en contenedores de Azure Blob Storage"
    category = "cloud_storage"
    icon = "database"
    author = "Zenic-Flijo"

    # Azure Blob Storage API version
    _API_VERSION = "2023-01-03"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://{account}.blob.core.windows.net"
        self._http: HttpClient | None = None
        self._account_name: str = ""
        self._account_key: str = ""
        self._sas_token: str = ""
        self._connection_string: str = ""

    # ── Conexion ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establece conexion con Azure Blob Storage."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("AzureBlobConnector: credenciales no configuradas")
            return False

        # Extraer credenciales
        creds = self._auth_provider.get_credentials() if hasattr(self._auth_provider, "get_credentials") else {}
        self._connection_string = creds.get(
            "connection_string", os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        )
        self._account_name = creds.get(
            "account_name", os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
        )
        self._account_key = creds.get(
            "account_key", os.environ.get("AZURE_STORAGE_ACCOUNT_KEY", "")
        )
        self._sas_token = creds.get(
            "sas_token", os.environ.get("AZURE_STORAGE_SAS_TOKEN", "")
        )

        # Parsear connection string si esta disponible
        if self._connection_string and not self._account_name:
            self._parse_connection_string(self._connection_string)

        if not self._account_name:
            logger.error("AzureBlobConnector: account_name no proporcionado")
            return False

        if not self._account_key and not self._sas_token:
            logger.error("AzureBlobConnector: account_key o sas_token no proporcionados")
            return False

        # Construir base_url
        base_url = f"https://{self._account_name}.blob.core.windows.net"

        # Inicializar HttpClient
        self._http = HttpClient(
            base_url=base_url,
            connector_name=self.name,
            timeout=30,
        )
        self._base_url = base_url

        # Configurar autenticacion
        if self._sas_token:
            self._http.set_header("Authorization", "")  # SAS va en query params
            self._log_operation("connect", f"SAS token configurado, account={self._account_name}")
        else:
            self._log_operation("connect", f"SharedKey configurado, account={self._account_name}")

        # Verificar conexion listando contenedores
        try:
            resp = self._azure_request("GET", "/?comp=list")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"Azure Blob API OK, account={self._account_name}")
                return True
            # 403 es aceptable — el endpoint responde pero permisos limitados
            if resp.status_code == 403:
                self._connected = True
                self._log_operation("connect", f"Azure Blob API OK (403 en list containers), account={self._account_name}")
                return True
            logger.error(f"AzureBlobConnector: API respondio {resp.status_code}: {resp.body}")
            return False
        except HTTPClientError as exc:
            logger.error(f"AzureBlobConnector: API fallo: {exc}")
            return False

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Azure Blob Storage."""
        action_map: dict[str, Any] = {
            "upload_blob": self._upload_blob,
            "download_blob": self._download_blob,
            "list_blobs": self._list_blobs,
            "delete_blob": self._delete_blob,
            "get_blob_url": self._get_blob_url,
            "list_containers": self._list_containers,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Azure esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Azure Blob Storage."""
        self._connected = False
        self._http = None
        self._log_operation("disconnect")
        return True

    # ── Acciones ───────────────────────────────────────────────

    def _upload_blob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sube un blob a un contenedor de Azure.

        Args:
            params: Debe contener 'container', 'blob_name' y 'content' (o 'file_path')
        """
        container = params.get("container", "")
        blob_name = params.get("blob_name", "")
        content = params.get("content")
        file_path = params.get("file_path")

        if not container or not blob_name:
            return {"success": False, "error": "Parametros requeridos: container, blob_name"}
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

        content_type = params.get("content_type", "application/octet-stream")
        self._log_operation("upload_blob", f"container={container}, blob={blob_name}, size={len(content)}")

        try:
            encoded_blob = quote(blob_name, safe="")
            resp = self._azure_request(
                "PUT",
                f"/{container}/{encoded_blob}",
                body=content,
                headers={
                    "Content-Type": content_type,
                    "x-ms-blob-type": "BlockBlob",
                    "Content-Length": str(len(content)),
                },
            )
            if resp.ok or resp.status_code == 201:
                etag = resp.headers.get("ETag", "")
                return {
                    "success": True,
                    "container": container,
                    "blob_name": blob_name,
                    "etag": etag,
                    "size": len(content),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _download_blob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Descarga un blob de un contenedor de Azure.

        Args:
            params: Debe contener 'container' y 'blob_name'
        """
        container = params.get("container", "")
        blob_name = params.get("blob_name", "")
        if not container or not blob_name:
            return {"success": False, "error": "Parametros requeridos: container, blob_name"}

        self._log_operation("download_blob", f"container={container}, blob={blob_name}")

        try:
            encoded_blob = quote(blob_name, safe="")
            resp = self._azure_request("GET", f"/{container}/{encoded_blob}")
            if resp.ok:
                content = resp.raw if resp.raw else b""
                return {
                    "success": True,
                    "container": container,
                    "blob_name": blob_name,
                    "content": content,
                    "size_bytes": len(content),
                    "content_type": resp.headers.get("Content-Type", "application/octet-stream"),
                    "etag": resp.headers.get("ETag", ""),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _list_blobs(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista blobs en un contenedor de Azure con paginacion.

        Args:
            params: Debe contener 'container' y opcionalmente 'prefix', 'limit', 'marker'
        """
        container = params.get("container", "")
        prefix = params.get("prefix", "")
        limit = params.get("limit", 5000)
        marker = params.get("marker", "")

        if not container:
            return {"success": False, "error": "Parametro requerido: container"}

        self._log_operation("list_blobs", f"container={container}")

        try:
            query = f"restype=container&comp=list&maxresults={limit}"
            if prefix:
                query += f"&prefix={quote(prefix)}"
            if marker:
                query += f"&marker={quote(marker)}"

            resp = self._azure_request("GET", f"/{container}?{query}")
            if not resp.ok:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}

            # Parsear XML de respuesta de Azure
            body_str = resp.body if isinstance(resp.body, str) else str(resp.body)
            blobs = self._parse_blob_list_xml(body_str)
            next_marker = self._extract_xml_value(body_str, "NextMarker")

            return {
                "success": True,
                "container": container,
                "blobs": blobs,
                "total": len(blobs),
                "next_marker": next_marker,
            }
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _delete_blob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un blob de un contenedor de Azure.

        Args:
            params: Debe contener 'container' y 'blob_name'
        """
        container = params.get("container", "")
        blob_name = params.get("blob_name", "")
        if not container or not blob_name:
            return {"success": False, "error": "Parametros requeridos: container, blob_name"}

        self._log_operation("delete_blob", f"container={container}, blob={blob_name}")

        try:
            encoded_blob = quote(blob_name, safe="")
            resp = self._azure_request("DELETE", f"/{container}/{encoded_blob}")
            if resp.ok or resp.status_code in (202, 204):
                return {"success": True, "deleted": True, "container": container, "blob_name": blob_name}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _get_blob_url(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una URL SAS para acceder a un blob de Azure.

        Args:
            params: Debe contener 'container', 'blob_name' y opcionalmente 'expires_in', 'permissions'
        """
        container = params.get("container", "")
        blob_name = params.get("blob_name", "")
        expires_in = params.get("expires_in", 3600)
        permissions = params.get("permissions", "r")  # read por defecto

        if not container or not blob_name:
            return {"success": False, "error": "Parametros requeridos: container, blob_name"}

        self._log_operation("get_blob_url", f"container={container}, blob={blob_name}")

        encoded_blob = quote(blob_name, safe="")
        base_url = f"https://{self._account_name}.blob.core.windows.net/{container}/{encoded_blob}"

        # Si tenemos SAS token, usarlo
        if self._sas_token:
            url = f"{base_url}?{self._sas_token}"
            return {"success": True, "url": url, "expires_in": expires_in}

        # Si tenemos account key, generar SAS signature
        if self._account_key:
            try:
                sas_url = self._generate_sas_url(container, blob_name, permissions, expires_in)
                return {"success": True, "url": sas_url, "expires_in": expires_in}
            except Exception as exc:
                logger.warning(f"AzureBlobConnector: error generando SAS URL: {exc}")

        # Fallback: URL directa (solo funciona para blobs publicos)
        return {"success": True, "url": base_url, "expires_in": expires_in, "note": "URL sin SAS (requiere account_key o sas_token para SAS)"}

    def _list_containers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los contenedores de la cuenta de Azure Storage con paginacion.

        Args:
            params: Opcionalmente 'prefix', 'marker'
        """
        prefix = params.get("prefix", "")
        marker = params.get("marker", "")

        self._log_operation("list_containers")

        try:
            query = "comp=list"
            if prefix:
                query += f"&prefix={quote(prefix)}"
            if marker:
                query += f"&marker={quote(marker)}"

            resp = self._azure_request("GET", f"/?{query}")
            if not resp.ok:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}

            body_str = resp.body if isinstance(resp.body, str) else str(resp.body)
            containers = self._parse_container_list_xml(body_str)
            next_marker = self._extract_xml_value(body_str, "NextMarker")

            return {
                "success": True,
                "containers": containers,
                "next_marker": next_marker,
            }
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    # ── Azure REST API con SharedKey ────────────────────────────

    # legítimo: retorna respuesta HTTP raw de API externa (skill §9.1)
    def _azure_request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Ejecuta una peticion HTTP a Azure Blob Storage con autenticacion SharedKey.

        Args:
            method: Metodo HTTP
            path: Ruta del recurso
            body: Cuerpo de la peticion (bytes)
            headers: Headers adicionales

        Returns:
            HTTPResponse
        """
        import requests as req_lib

        from src.sdk.http_client import HTTPResponse

        now = datetime.now(UTC)
        date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        # Preparar body
        if body is None:
            body = b""

        content_length = str(len(body)) if body else "0"
        if headers:
            headers.get("Content-Type", "")

        # Construir headers base
        request_headers: dict[str, str] = {
            "x-ms-date": date_str,
            "x-ms-version": self._API_VERSION,
            "Content-Length": content_length,
        }
        if headers:
            request_headers.update(headers)

        # Si tenemos SAS token, agregarlo al query string
        if self._sas_token and "?" not in path:
            path = f"{path}?{self._sas_token}"
        elif self._sas_token and "?" in path:
            path = f"{path}&{self._sas_token}"

        # Si tenemos account key, firmar con SharedKey
        if self._account_key and not self._sas_token:
            authorization = self._compute_shared_key_signature(
                method, path, request_headers, body
            )
            request_headers["Authorization"] = authorization

        # Construir URL
        url = f"https://{self._account_name}.blob.core.windows.net{path}"

        # Ejecutar peticion
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": request_headers,
            "data": body if body else None,
            "timeout": 30,
            "verify": True,
        }

        resp = req_lib.request(**request_kwargs)

        # legítimo: JSON decoded de API externa, se valida al consumir (skill §9.1)
        resp_body: Any
        try:
            resp_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            resp_body = resp.text

        return HTTPResponse(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=resp_body,
            raw=resp.content,
            elapsed=resp.elapsed.total_seconds() if hasattr(resp.elapsed, "total_seconds") else 0,
            url=url,
            method=method,
        )

    def _compute_shared_key_signature(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> str:
        """Computa la firma SharedKey para Azure Blob Storage REST API.

        Args:
            method: Metodo HTTP
            path: Ruta del recurso
            headers: Headers de la peticion
            body: Cuerpo de la peticion

        Returns:
            String de autorizacion "SharedKey {account}:{signature}"
        """
        # Construir string to sign segun especificacion Azure
        content_encoding = headers.get("Content-Encoding", "")
        content_language = headers.get("Content-Language", "")
        content_length = headers.get("Content-Length", "")
        # Azure requiere Content-Length vacio para GET/DELETE, sino el valor
        if method in ("GET", "DELETE", "HEAD") and content_length == "0":
            content_length = ""
        content_md5 = headers.get("Content-MD5", "")
        content_type = headers.get("Content-Type", "")
        date = ""
        if_modified_since = headers.get("If-Modified-Since", "")
        if_unmodified_since = headers.get("If-Unmodified-Since", "")
        range_header = headers.get("Range", "")

        # Recopilar x-ms-headers en orden lexicografico
        ms_headers = sorted(
            [(k.lower(), v) for k, v in headers.items() if k.lower().startswith("x-ms-")]
        )
        ms_headers_str = "\n".join(f"{k}:{v}" for k, v in ms_headers) + "\n"

        # Extraer ruta sin query params
        path_only = path.split("?")[0]

        string_to_sign = "\n".join([
            method,
            content_encoding,
            content_language,
            content_length,
            content_md5,
            content_type,
            date,
            if_modified_since,
            if_unmodified_since,
            range_header,
        ]) + "\n" + ms_headers_str + "/" + self._account_name + path_only

        # Firmar con HMAC-SHA256
        decoded_key = base64.b64decode(self._account_key)
        signature = hmac.new(
            decoded_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.b64encode(signature).decode("utf-8")

        return f"SharedKey {self._account_name}:{encoded_signature}"

    def _generate_sas_url(
        self, container: str, blob_name: str, permissions: str, expires_in: int
    ) -> str:
        """Genera una URL con SAS token para un blob.

        Args:
            container: Nombre del contenedor
            blob_name: Nombre del blob
            permissions: Permisos (r, w, d, etc.)
            expires_in: Tiempo de expiracion en segundos

        Returns:
            URL con SAS token
        """
        from datetime import timedelta

        expiry_time = datetime.now(UTC) + timedelta(seconds=expires_in)
        expiry_str = expiry_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Canonicalized resource
        canonical_resource = f"/blob/{self._account_name}/{container}/{blob_name}"

        # String to sign
        string_to_sign = "\n".join([
            permissions,   # signed permissions
            "",            # signed start (optional)
            expiry_str,    # signed expiry
            canonical_resource,  # canonical resource
            "",            # signed identifier
            "",            # signed IP
            "",            # signed protocol
            self._API_VERSION,  # signed version
            "",            # signed resource type
            "",            # signed snapshot time
            "",            # signed encryption scope
        ])

        # Firmar
        decoded_key = base64.b64decode(self._account_key)
        signature = hmac.new(
            decoded_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.b64encode(signature).decode("utf-8")

        # Construir URL
        encoded_blob = quote(blob_name, safe="")
        sas_params = (
            f"sv={self._API_VERSION}"
            f"&sr=b"
            f"&sp={permissions}"
            f"&se={quote(expiry_str)}"
            f"&sig={quote(encoded_signature)}"
        )

        return f"https://{self._account_name}.blob.core.windows.net/{container}/{encoded_blob}?{sas_params}"

    # ── Helpers XML ─────────────────────────────────────────────

    @staticmethod
    def _extract_xml_value(xml_str: str, tag: str) -> str:
        """Extrae el valor de un tag XML de la respuesta de Azure.

        Args:
            xml_str: String XML
            tag: Nombre del tag

        Returns:
            Valor del tag o string vacio
        """
        pattern = f"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, xml_str, re.DOTALL)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_blob_list_xml(xml_str: str) -> list[dict[str, str]]:
        """Parsea la respuesta XML de list blobs de Azure.

        Args:
            xml_str: String XML con la lista de blobs

        Returns:
            Lista de diccionarios con informacion de cada blob
        """
        blobs: list[dict[str, str]] = []
        # Extraer cada bloque <Blob>...</Blob>
        blob_pattern = re.compile(r"<Blob>(.*?)</Blob>", re.DOTALL)
        for match in blob_pattern.finditer(xml_str):
            blob_xml = match.group(1)
            blob_info: dict[str, str] = {}

            name_match = re.search(r"<Name>(.*?)</Name>", blob_xml)
            if name_match:
                blob_info["name"] = name_match.group(1)

            # Properties
            props_match = re.search(r"<Properties>(.*?)</Properties>", blob_xml, re.DOTALL)
            if props_match:
                props = props_match.group(1)
                for prop_tag in ("Content-Length", "Content-Type", "Last-Modified", "ETag", "BlobType"):
                    prop_match = re.search(f"<{prop_tag}>(.*?)</{prop_tag}>", props)
                    if prop_match:
                        blob_info[prop_tag.lower().replace("-", "_")] = prop_match.group(1)

            blobs.append(blob_info)

        return blobs

    @staticmethod
    def _parse_container_list_xml(xml_str: str) -> list[dict[str, str]]:
        """Parsea la respuesta XML de list containers de Azure.

        Args:
            xml_str: String XML con la lista de contenedores

        Returns:
            Lista de diccionarios con informacion de cada contenedor
        """
        containers: list[dict[str, str]] = []
        container_pattern = re.compile(r"<Container>(.*?)</Container>", re.DOTALL)
        for match in container_pattern.finditer(xml_str):
            container_xml = match.group(1)
            container_info: dict[str, str] = {}

            name_match = re.search(r"<Name>(.*?)</Name>", container_xml)
            if name_match:
                container_info["name"] = name_match.group(1)

            props_match = re.search(r"<Properties>(.*?)</Properties>", container_xml, re.DOTALL)
            if props_match:
                props = props_match.group(1)
                for prop_tag in ("Last-Modified", "ETag", "PublicAccess"):
                    prop_match = re.search(f"<{prop_tag}>(.*?)</{prop_tag}>", props)
                    if prop_match:
                        container_info[prop_tag.lower().replace("-", "_")] = prop_match.group(1)

            containers.append(container_info)

        return containers

    def _parse_connection_string(self, conn_str: str) -> None:
        """Parsea una connection string de Azure Storage.

        Args:
            conn_str: Connection string de Azure Storage
        """
        parts = conn_str.split(";")
        for part in parts:
            part = part.strip()
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key = key.lower().strip()
            value = value.strip()
            if key == "accountname":
                self._account_name = value
            elif key == "accountkey":
                self._account_key = value
            elif key == "sastoken":
                self._sas_token = value
            elif key == "blobendpoint":
                # Extraer account name del endpoint
                match = re.match(r"https://([^.]+)\.blob\.core\.windows\.net", value)
                if match and not self._account_name:
                    self._account_name = match.group(1)


AZURE_BLOB_SCHEMA = ConnectorSchema(
    name="azure_blob",
    version="1.0.0",
    description="Sube, descarga y gestiona blobs en contenedores de Azure Blob Storage",
    category="cloud_storage",
    icon="database",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="upload_blob", description="Sube un blob", category="write"),
        ActionDefinition(name="download_blob", description="Descarga un blob", category="read"),
        ActionDefinition(name="list_blobs", description="Lista blobs en contenedor", category="read"),
        ActionDefinition(name="delete_blob", description="Elimina un blob", category="delete"),
        ActionDefinition(name="get_blob_url", description="Genera URL SAS", category="read"),
        ActionDefinition(name="list_containers", description="Lista contenedores", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["connection_string"], description="Azure Storage Connection String")
    ],
)
