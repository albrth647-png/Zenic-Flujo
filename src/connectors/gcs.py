"""
Conector Google Cloud Storage — Operaciones de Almacenamiento
================================================================

Permite subir, descargar, listar y gestionar objetos en
buckets de Google Cloud Storage usando la REST API v1.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import time
from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class GcsConnector(BaseConnector):
    """Conector para Google Cloud Storage: operaciones CRUD en buckets y objetos.

    Usa la REST API de GCS (storage.googleapis.com/storage/v1)
    con autenticacion OAuth2 Bearer token.
    """

    name = "gcs"
    version = "1.0.0"
    description = "Sube, descarga y gestiona archivos en buckets de Google Cloud Storage"
    category = "cloud_storage"
    icon = "cloud"
    author = "Zenic-Flijo"

    # URL base de la GCS JSON API
    _GCS_API_BASE = "https://storage.googleapis.com/storage/v1"
    _GCS_UPLOAD_BASE = "https://storage.googleapis.com/upload/storage/v1"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = self._GCS_API_BASE
        self._http: HttpClient | None = None
        self._access_token: str = ""
        self._project_id: str = ""

    # ── Conexion ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establece conexion con Google Cloud Storage."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("GcsConnector: credenciales no configuradas")
            return False

        # Extraer credenciales
        creds = self._auth_provider.get_credentials() if hasattr(self._auth_provider, "get_credentials") else {}
        self._access_token = creds.get("access_token", os.environ.get("GCS_ACCESS_TOKEN", ""))
        self._project_id = creds.get("project_id", os.environ.get("GCP_PROJECT_ID", ""))

        # Si hay service_account_json, obtener access_token via JWT
        sa_json = creds.get("service_account_json", os.environ.get("GCS_SERVICE_ACCOUNT_JSON", ""))
        if not self._access_token and sa_json:
            self._access_token = self._get_access_token_from_sa(sa_json)

        if not self._access_token:
            logger.error("GcsConnector: access_token no proporcionado")
            return False

        # Inicializar HttpClient
        self._http = HttpClient(
            base_url=self._GCS_API_BASE,
            connector_name=self.name,
            timeout=30,
        )
        self._http.set_auth("Bearer", token=self._access_token)

        # Verificar conexion listando buckets del proyecto
        try:
            params = {}
            if self._project_id:
                params["project"] = self._project_id
            resp = self._http.get("/b", params=params)
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"GCS API OK, project={self._project_id}")
                return True
            # 403 puede significar que el token es valido pero sin permisos de list
            if resp.status_code == 403:
                self._connected = True
                self._log_operation("connect", f"GCS API OK (403 en list buckets, token valido), project={self._project_id}")
                return True
            logger.error(f"GcsConnector: GCS API respondio {resp.status_code}: {resp.body}")
            return False
        except HTTPClientError as exc:
            logger.error(f"GcsConnector: GCS API fallo: {exc}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector GCS."""
        action_map: dict[str, Any] = {
            "upload_file": self._upload_file,
            "download_file": self._download_file,
            "list_objects": self._list_objects,
            "delete_object": self._delete_object,
            "get_signed_url": self._get_signed_url,
            "list_buckets": self._list_buckets,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de GCS esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Google Cloud Storage."""
        self._connected = False
        self._http = None
        self._log_operation("disconnect")
        return True

    # ── Acciones ───────────────────────────────────────────────

    def _upload_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sube un archivo a un bucket de GCS usando resumable upload.

        Args:
            params: Debe contener 'bucket', 'object_name' y 'content' (o 'file_path')
        """
        bucket = params.get("bucket", "")
        object_name = params.get("object_name", "")
        content = params.get("content")
        file_path = params.get("file_path")

        if not bucket or not object_name:
            return {"success": False, "error": "Parametros requeridos: bucket, object_name"}
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
        self._log_operation("upload_file", f"bucket={bucket}, object={object_name}, size={len(content)}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            # Paso 1: Iniciar sesion de upload resumable
            upload_http = HttpClient(
                base_url=self._GCS_UPLOAD_BASE,
                connector_name=self.name,
                timeout=30,
            )
            upload_http.set_auth("Bearer", token=self._access_token)

            init_resp = upload_http.post(
                f"/b/{bucket}/o",
                json={
                    "name": object_name,
                },
                headers={
                    "X-Upload-Content-Type": content_type,
                    "X-Upload-Content-Length": str(len(content)),
                    "Content-Type": "application/json; charset=UTF-8",
                },
                timeout=30,
            )

            # Obtener la URI de upload del header Location
            upload_url = init_resp.headers.get("Location", "")
            if not upload_url:
                # Si no hay resumable, intentar upload simple (multipart)
                return self._upload_simple(bucket, object_name, content, content_type)

            # Paso 2: Subir el contenido a la URI de upload
            import requests as req_lib

            put_resp = req_lib.put(
                upload_url,
                data=content,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                },
                timeout=60,
            )

            if 200 <= put_resp.status_code < 300:
                result = {}
                with contextlib.suppress(json.JSONDecodeError, ValueError):
                    result = put_resp.json()
                return {
                    "success": True,
                    "bucket": bucket,
                    "object_name": object_name,
                    "generation": str(result.get("generation", "")),
                    "size": len(content),
                }
            return {"success": False, "error": f"Upload PUT fallo: HTTP {put_resp.status_code}"}

        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": f"Error inesperado: {exc}"}

    def _upload_simple(
        self, bucket: str, object_name: str, content: bytes, content_type: str
    ) -> dict[str, Any]:
        """Upload simple (multipart/form-data) para archivos pequenos (< 5MB)."""
        import requests as req_lib

        # Codificar contenido en base64 para el JSON API
        base64.b64encode(content).decode("ascii")

        # Usar el endpoint de upload simple con media upload
        url = f"{self._GCS_UPLOAD_BASE}/b/{bucket}/o?uploadType=media&name={object_name}"

        resp = req_lib.post(
            url,
            data=content,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": content_type,
            },
            timeout=60,
        )

        if 200 <= resp.status_code < 300:
            result = {}
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                result = resp.json()
            return {
                "success": True,
                "bucket": bucket,
                "object_name": object_name,
                "generation": str(result.get("generation", "")),
                "size": len(content),
            }
        return {"success": False, "error": f"Upload simple fallo: HTTP {resp.status_code}"}

    def _download_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Descarga un archivo de un bucket de GCS.

        Args:
            params: Debe contener 'bucket' y 'object_name'
        """
        bucket = params.get("bucket", "")
        object_name = params.get("object_name", "")
        if not bucket or not object_name:
            return {"success": False, "error": "Parametros requeridos: bucket, object_name"}

        self._log_operation("download_file", f"bucket={bucket}, object={object_name}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            # Obtener metadata del objeto
            metadata_resp = self._http.get(f"/b/{bucket}/o/{object_name}")
            if not metadata_resp.ok:
                return {"success": False, "error": f"HTTP {metadata_resp.status_code}: {metadata_resp.body}"}

            metadata = metadata_resp.json() if isinstance(metadata_resp.body, str) else metadata_resp.body

            # Descargar contenido usando alt=media
            download_http = HttpClient(
                base_url=self._GCS_API_BASE,
                connector_name=self.name,
                timeout=60,
            )
            download_http.set_auth("Bearer", token=self._access_token)

            content_resp = download_http.get(
                f"/b/{bucket}/o/{object_name}",
                params={"alt": "media"},
            )

            content = content_resp.raw if content_resp.raw else b""
            content_type = metadata.get("contentType", "application/octet-stream") if isinstance(metadata, dict) else "application/octet-stream"
            size = metadata.get("size", len(content)) if isinstance(metadata, dict) else len(content)

            return {
                "success": True,
                "bucket": bucket,
                "object_name": object_name,
                "content": content,
                "size_bytes": int(size) if isinstance(size, (int, str)) else len(content),
                "content_type": content_type,
                "metadata": metadata,
            }

        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _list_objects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista objetos en un bucket de GCS con paginacion.

        Args:
            params: Debe contener 'bucket' y opcionalmente 'prefix', 'limit', 'page_token'
        """
        bucket = params.get("bucket", "")
        prefix = params.get("prefix", "")
        limit = params.get("limit", 1000)
        page_token = params.get("page_token", "")

        if not bucket:
            return {"success": False, "error": "Parametro requerido: bucket"}

        self._log_operation("list_objects", f"bucket={bucket}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            query_params: dict[str, Any] = {"maxResults": limit}
            if prefix:
                query_params["prefix"] = prefix
            if page_token:
                query_params["pageToken"] = page_token

            resp = self._http.get(f"/b/{bucket}/o", params=query_params)

            if not resp.ok:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}

            body = resp.json() if isinstance(resp.body, str) else resp.body
            if not isinstance(body, dict):
                return {"success": False, "error": "Respuesta inesperada de GCS API"}

            objects = []
            for item in body.get("items", []):
                objects.append({
                    "name": item.get("name", ""),
                    "size": item.get("size", "0"),
                    "content_type": item.get("contentType", ""),
                    "updated": item.get("updated", ""),
                    "generation": item.get("generation", ""),
                    "md5_hash": item.get("md5Hash", ""),
                })

            return {
                "success": True,
                "bucket": bucket,
                "objects": objects,
                "total": len(objects),
                "next_page_token": body.get("nextPageToken", ""),
                "prefixes": body.get("prefixes", []),
            }

        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _delete_object(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un objeto de un bucket de GCS.

        Args:
            params: Debe contener 'bucket' y 'object_name'
        """
        bucket = params.get("bucket", "")
        object_name = params.get("object_name", "")
        if not bucket or not object_name:
            return {"success": False, "error": "Parametros requeridos: bucket, object_name"}

        self._log_operation("delete_object", f"bucket={bucket}, object={object_name}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            resp = self._http.delete(f"/b/{bucket}/o/{object_name}")
            if resp.ok or resp.status_code == 204:
                return {"success": True, "deleted": True, "bucket": bucket, "object_name": object_name}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _get_signed_url(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una URL firmada para acceder a un objeto de GCS.

        Args:
            params: Debe contener 'bucket', 'object_name' y opcionalmente 'expires_in'
        """
        bucket = params.get("bucket", "")
        object_name = params.get("object_name", "")
        expires_in = params.get("expires_in", 3600)

        if not bucket or not object_name:
            return {"success": False, "error": "Parametros requeridos: bucket, object_name"}

        self._log_operation("get_signed_url", f"bucket={bucket}, object={object_name}")

        # Para generar URLs firmadas reales se necesita una service account
        # con private key. Aqui generamos la URL directa como fallback.
        # Si se tiene service_account_json, se puede firmar correctamente.
        creds = {}
        if self._auth_provider and hasattr(self._auth_provider, "get_credentials"):
            creds = self._auth_provider.get_credentials()

        sa_json = creds.get("service_account_json", os.environ.get("GCS_SERVICE_ACCOUNT_JSON", ""))
        if sa_json:
            try:
                signed_url = self._create_signed_url(bucket, object_name, expires_in, sa_json)
                return {"success": True, "url": signed_url, "expires_in": expires_in}
            except Exception as exc:
                logger.warning(f"GcsConnector: error generando signed URL: {exc}")

        # Fallback: URL directa (solo funciona para objetos publicos)
        url = f"https://storage.googleapis.com/{bucket}/{object_name}"
        return {"success": True, "url": url, "expires_in": expires_in, "note": "URL sin firmar (requiere service_account_json para URL firmada)"}

    def _list_buckets(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los buckets de GCS del proyecto con paginacion.

        Args:
            params: Opcionalmente 'project_id' y 'page_token'
        """
        project_id = params.get("project_id", self._project_id)
        page_token = params.get("page_token", "")

        if not project_id:
            return {"success": False, "error": "Parametro requerido: project_id (o configurar en connect)"}

        self._log_operation("list_buckets", f"project={project_id}")

        if not self._http:
            return {"success": False, "error": "HttpClient no inicializado. Llame connect() primero."}

        try:
            query_params: dict[str, Any] = {"project": project_id}
            if page_token:
                query_params["pageToken"] = page_token

            resp = self._http.get("/b", params=query_params)

            if not resp.ok:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}

            body = resp.json() if isinstance(resp.body, str) else resp.body
            if not isinstance(body, dict):
                return {"success": False, "error": "Respuesta inesperada de GCS API"}

            buckets = []
            for item in body.get("items", []):
                buckets.append({
                    "name": item.get("name", ""),
                    "location": item.get("location", ""),
                    "storage_class": item.get("storageClass", ""),
                    "created": item.get("timeCreated", ""),
                })

            return {
                "success": True,
                "buckets": buckets,
                "project_id": project_id,
                "next_page_token": body.get("nextPageToken", ""),
            }

        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    # ── Helpers ─────────────────────────────────────────────────

    def _get_access_token_from_sa(self, sa_json_str: str) -> str:
        """Obtiene un access token de Google OAuth2 usando una Service Account JSON.

        Args:
            sa_json_str: JSON string de la service account

        Returns:
            Access token de Google OAuth2
        """
        import requests as req_lib

        sa_info = json.loads(sa_json_str)
        client_email = sa_info.get("client_email", "")
        private_key = sa_info.get("private_key", "")
        token_uri = sa_info.get("token_uri", "https://oauth2.googleapis.com/token")

        if not client_email or not private_key:
            raise ValueError("Service account JSON debe contener client_email y private_key")

        # Crear JWT
        now = int(time.time())
        payload = {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/devstorage.read_write",
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }

        # Codificar JWT manualmente (sin dependencia de pyjwt)
        header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sign_input = f"{header_b64}.{payload_b64}"

        # Firmar con RSA
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(), password=None
            )
            signature = private_key_obj.sign(
                sign_input.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
            jwt_token = f"{sign_input}.{sig_b64}"
        except ImportError:
            # Fallback sin cryptography — usar pyjwt si esta disponible
            try:
                import jwt
                jwt_token = jwt.encode(payload, private_key, algorithm="RS256")
            except ImportError:
                raise ValueError("Se necesita 'cryptography' o 'pyjwt' para firmar JWT con service account") from None

        # Intercambiar JWT por access token
        resp = req_lib.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            raise ValueError(f"Error obteniendo access token: {resp.status_code} {resp.text}")

        return resp.json().get("access_token", "")

    def _create_signed_url(
        self, bucket: str, object_name: str, expires_in: int, sa_json_str: str
    ) -> str:
        """Crea una URL firmada V4 para un objeto de GCS.

        Args:
            bucket: Nombre del bucket
            object_name: Nombre del objeto
            expires_in: Tiempo de expiracion en segundos
            sa_json_str: JSON string de la service account

        Returns:
            URL firmada
        """
        import hashlib
        from urllib.parse import quote

        sa_info = json.loads(sa_json_str)
        client_email = sa_info.get("client_email", "")
        private_key = sa_info.get("private_key", "")

        now = int(time.time())
        now + expires_in

        # Construct the string to sign (V4 signing)
        date_stamp = time.strftime("%Y%m%d", time.gmtime(now))
        time_stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        credential_scope = f"{date_stamp}/auto/storage/goog4_request"

        encoded_object = quote(object_name, safe="")

        canonical_request = "\n".join([
            "GET",
            f"/{bucket}/{encoded_object}",
            f"X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential={quote(client_email + '/' + credential_scope)}&X-Goog-Date={time_stamp}&X-Goog-Expires={expires_in}&X-Goog-SignedHeaders=host",
            "host:storage.googleapis.com",
            "",
            "host",
            "UNSIGNED-PAYLOAD",
        ])

        string_to_sign = "\n".join([
            "GOOG4-RSA-SHA256",
            time_stamp,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])

        # Firmar
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(), password=None
            )
            signature = private_key_obj.sign(
                string_to_sign.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sig_encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        except ImportError:
            raise ValueError("Se necesita 'cryptography' para generar URLs firmadas") from None

        signed_url = (
            f"https://storage.googleapis.com/{bucket}/{encoded_object}"
            f"?X-Goog-Algorithm=GOOG4-RSA-SHA256"
            f"&X-Goog-Credential={quote(client_email + '/' + credential_scope)}"
            f"&X-Goog-Date={time_stamp}"
            f"&X-Goog-Expires={expires_in}"
            f"&X-Goog-SignedHeaders=host"
            f"&X-Goog-Signature={sig_encoded}"
        )

        return signed_url


GCS_SCHEMA = ConnectorSchema(
    name="gcs",
    version="1.0.0",
    description="Sube, descarga y gestiona archivos en buckets de Google Cloud Storage",
    category="cloud_storage",
    icon="cloud",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="upload_file", description="Sube un archivo a GCS", category="write"),
        ActionDefinition(name="download_file", description="Descarga un archivo de GCS", category="read"),
        ActionDefinition(name="list_objects", description="Lista objetos en un bucket", category="read"),
        ActionDefinition(name="delete_object", description="Elimina un objeto de GCS", category="delete"),
        ActionDefinition(name="get_signed_url", description="Genera URL firmada", category="read"),
        ActionDefinition(name="list_buckets", description="Lista buckets del proyecto", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_email", "private_key"], description="Service Account de GCP")
    ],
)
