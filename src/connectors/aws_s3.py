"""
Conector AWS S3 — Operaciones de Almacenamiento de Archivos
==============================================================

Permite subir, descargar, listar y gestionar objetos en
buckets de Amazon S3 usando boto3 (preferido) o la API REST
de S3 con firmas AWS Signature V4.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Intentar importar boto3 para el path preferido
try:
    import boto3
    from botocore.config import Config as BotoConfig

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False


class AwsS3Connector(BaseConnector):
    """Conector para AWS S3: operaciones CRUD en buckets y objetos.

    Usa boto3 si esta disponible; de lo contrario, recurre a la
    API REST de S3 con firmas AWS Signature V4 via HttpClient.
    """

    name = "aws_s3"
    version = "1.0.0"
    description = "Sube, descarga y gestiona archivos en buckets de Amazon S3"
    category = "cloud_storage"
    icon = "hard-drive"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://s3.amazonaws.com"
        self._http: HttpClient | None = None
        self._boto_client: Any = None
        # AWS credentials — extraidos del auth_provider o params
        self._access_key_id: str = ""
        self._secret_access_key: str = ""
        self._region: str = "us-east-1"
        self._session_token: str = ""

    # ── Conexion ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establece conexion con AWS S3 usando las credenciales configuradas."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("AwsS3Connector: credenciales AWS no configuradas")
            return False

        # Extraer credenciales del auth_provider
        creds = self._auth_provider.get_credentials() if hasattr(self._auth_provider, "get_credentials") else {}
        self._access_key_id = creds.get("access_key_id", os.environ.get("AWS_ACCESS_KEY_ID", ""))
        self._secret_access_key = creds.get("secret_access_key", os.environ.get("AWS_SECRET_ACCESS_KEY", ""))
        self._region = creds.get("region", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        self._session_token = creds.get("session_token", os.environ.get("AWS_SESSION_TOKEN", ""))

        if not self._access_key_id or not self._secret_access_key:
            logger.error("AwsS3Connector: access_key_id o secret_access_key no proporcionados")
            return False

        # Inicializar boto3 si esta disponible
        if _BOTO3_AVAILABLE:
            try:
                self._boto_client = boto3.client(
                    "s3",
                    aws_access_key_id=self._access_key_id,
                    aws_secret_access_key=self._secret_access_key,
                    aws_session_token=self._session_token or None,
                    region_name=self._region,
                    config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
                )
                # Verificar que la conexion funciona listando buckets (operacion ligera)
                self._boto_client.list_buckets()
                self._connected = True
                self._log_operation("connect", f"boto3 OK, region={self._region}")
                return True
            except Exception as exc:
                logger.warning(f"AwsS3Connector: boto3 fallo ({exc}), usando REST API")

        # Fallback: REST API con HttpClient
        self._http = HttpClient(
            base_url=f"https://s3.{self._region}.amazonaws.com",
            connector_name=self.name,
            timeout=30,
        )
        # Verificar conexion con una peticion HEAD al servicio
        try:
            resp = self._signed_request("GET", "/", {})
            if resp.status_code in (200, 403, 404):
                # 403/404 son aceptables — significan que el endpoint responde
                self._connected = True
                self._log_operation("connect", f"REST API OK, region={self._region}")
                return True
            logger.error(f"AwsS3Connector: REST API respondio {resp.status_code}")
            return False
        except HTTPClientError as exc:
            logger.error(f"AwsS3Connector: REST API fallo: {exc}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector AWS S3."""
        action_map: dict[str, Any] = {
            "upload_file": self._upload_file,
            "download_file": self._download_file,
            "list_objects": self._list_objects,
            "delete_object": self._delete_object,
            "get_object_url": self._get_object_url,
            "copy_object": self._copy_object,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales AWS esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con AWS S3."""
        self._connected = False
        self._boto_client = None
        self._http = None
        self._log_operation("disconnect")
        return True

    # ── Acciones ───────────────────────────────────────────────

    def _upload_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sube un archivo a un bucket de S3.

        Args:
            params: Debe contener 'bucket', 'key' y 'content' (o 'file_path')
        """
        bucket = params.get("bucket", "")
        key = params.get("key", "")
        content = params.get("content")
        file_path = params.get("file_path")

        if not bucket or not key:
            return {"success": False, "error": "Parametros requeridos: bucket, key"}
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
        self._log_operation("upload_file", f"bucket={bucket}, key={key}, size={len(content)}")

        # boto3 path
        if self._boto_client is not None:
            try:
                extra_args: dict[str, Any] = {"ContentType": content_type}
                self._boto_client.put_object(
                    Bucket=bucket, Key=key, Body=content, **extra_args
                )
                return {
                    "success": True,
                    "bucket": bucket,
                    "key": key,
                    "size": len(content),
                }
            except Exception as exc:
                return {"success": False, "error": f"boto3 put_object fallo: {exc}"}

        # REST API path
        try:
            resp = self._signed_request(
                "PUT",
                f"/{bucket}/{key}",
                {},
                body=content,
                headers={"Content-Type": content_type},
            )
            if resp.ok:
                etag = resp.headers.get("ETag", "")
                return {
                    "success": True,
                    "bucket": bucket,
                    "key": key,
                    "etag": etag,
                    "size": len(content),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _download_file(self, params: dict[str, Any]) -> dict[str, Any]:
        """Descarga un archivo de un bucket de S3.

        Args:
            params: Debe contener 'bucket' y 'key'
        """
        bucket = params.get("bucket", "")
        key = params.get("key", "")
        if not bucket or not key:
            return {"success": False, "error": "Parametros requeridos: bucket, key"}

        self._log_operation("download_file", f"bucket={bucket}, key={key}")

        # boto3 path
        if self._boto_client is not None:
            try:
                response = self._boto_client.get_object(Bucket=bucket, Key=key)
                body = response["Body"].read()
                return {
                    "success": True,
                    "bucket": bucket,
                    "key": key,
                    "content": body,
                    "size_bytes": len(body),
                    "content_type": response.get("ContentType", "application/octet-stream"),
                }
            except Exception as exc:
                return {"success": False, "error": f"boto3 get_object fallo: {exc}"}

        # REST API path
        try:
            resp = self._signed_request("GET", f"/{bucket}/{key}", {})
            if resp.ok:
                return {
                    "success": True,
                    "bucket": bucket,
                    "key": key,
                    "content": resp.raw,
                    "size_bytes": len(resp.raw) if resp.raw else 0,
                    "content_type": resp.headers.get("Content-Type", "application/octet-stream"),
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _list_objects(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista objetos en un bucket de S3.

        Args:
            params: Debe contener 'bucket' y opcionalmente 'prefix', 'limit', 'marker'
        """
        bucket = params.get("bucket", "")
        prefix = params.get("prefix", "")
        limit = params.get("limit", 1000)
        marker = params.get("marker", "")

        if not bucket:
            return {"success": False, "error": "Parametro requerido: bucket"}

        self._log_operation("list_objects", f"bucket={bucket}, prefix={prefix}")

        # boto3 path
        if self._boto_client is not None:
            try:
                kwargs: dict[str, Any] = {"Bucket": bucket, "MaxKeys": limit}
                if prefix:
                    kwargs["Prefix"] = prefix
                if marker:
                    kwargs["Marker"] = marker

                response = self._boto_client.list_objects_v2(**kwargs)
                objects = []
                for obj in response.get("Contents", []):
                    objects.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat() if hasattr(obj["LastModified"], "isoformat") else str(obj["LastModified"]),
                        "etag": obj.get("ETag", ""),
                        "storage_class": obj.get("StorageClass", "STANDARD"),
                    })
                return {
                    "success": True,
                    "bucket": bucket,
                    "objects": objects,
                    "total": response.get("KeyCount", len(objects)),
                    "is_truncated": response.get("IsTruncated", False),
                    "next_continuation_token": response.get("NextContinuationToken", ""),
                }
            except Exception as exc:
                return {"success": False, "error": f"boto3 list_objects_v2 fallo: {exc}"}

        # REST API path
        try:
            query_params: dict[str, Any] = {"list-type": "2", "max-keys": str(limit)}
            if prefix:
                query_params["prefix"] = prefix
            if marker:
                query_params["start-after"] = marker

            resp = self._signed_request("GET", f"/{bucket}", query_params)
            if resp.ok:
                body = resp.json() if resp.body else {}
                # Parsear la respuesta XML/JSON de S3
                objects = []
                # S3 list v2 devuelve XML por defecto; parsear basico
                content_list = body.get("Contents", []) if isinstance(body, dict) else []
                for obj in content_list:
                    objects.append({
                        "key": obj.get("Key", ""),
                        "size": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified", ""),
                        "etag": obj.get("ETag", ""),
                    })
                return {
                    "success": True,
                    "bucket": bucket,
                    "objects": objects,
                    "total": len(objects),
                    "is_truncated": body.get("IsTruncated", "false") == "true" if isinstance(body, dict) else False,
                }
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _delete_object(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un objeto de un bucket de S3.

        Args:
            params: Debe contener 'bucket' y 'key'
        """
        bucket = params.get("bucket", "")
        key = params.get("key", "")
        if not bucket or not key:
            return {"success": False, "error": "Parametros requeridos: bucket, key"}

        self._log_operation("delete_object", f"bucket={bucket}, key={key}")

        # boto3 path
        if self._boto_client is not None:
            try:
                self._boto_client.delete_object(Bucket=bucket, Key=key)
                return {"success": True, "bucket": bucket, "key": key, "deleted": True}
            except Exception as exc:
                return {"success": False, "error": f"boto3 delete_object fallo: {exc}"}

        # REST API path
        try:
            resp = self._signed_request("DELETE", f"/{bucket}/{key}", {})
            if resp.ok or resp.status_code == 204:
                return {"success": True, "bucket": bucket, "key": key, "deleted": True}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    def _get_object_url(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una URL firmada para acceder a un objeto de S3.

        Args:
            params: Debe contener 'bucket', 'key' y opcionalmente 'expires_in'
        """
        bucket = params.get("bucket", "")
        key = params.get("key", "")
        expires_in = params.get("expires_in", 3600)

        if not bucket or not key:
            return {"success": False, "error": "Parametros requeridos: bucket, key"}

        self._log_operation("get_object_url", f"bucket={bucket}, key={key}")

        # boto3 path — genera URL firmada real
        if self._boto_client is not None:
            try:
                url = self._boto_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
                return {"success": True, "url": url, "expires_in": expires_in}
            except Exception as exc:
                return {"success": False, "error": f"boto3 generate_presigned_url fallo: {exc}"}

        # REST API path — URL directa sin firmar (para buckets publicos)
        url = f"https://{bucket}.s3.{self._region}.amazonaws.com/{key}"
        return {"success": True, "url": url, "expires_in": expires_in, "note": "URL sin firmar (boto3 no disponible)"}

    def _copy_object(self, params: dict[str, Any]) -> dict[str, Any]:
        """Copia un objeto entre buckets o dentro del mismo bucket.

        Args:
            params: Debe contener 'source_bucket', 'source_key', 'dest_bucket', 'dest_key'
        """
        source_bucket = params.get("source_bucket", "")
        source_key = params.get("source_key", "")
        dest_bucket = params.get("dest_bucket", "")
        dest_key = params.get("dest_key", "")

        if not source_bucket or not source_key or not dest_bucket or not dest_key:
            return {"success": False, "error": "Parametros requeridos: source_bucket, source_key, dest_bucket, dest_key"}

        self._log_operation("copy_object", f"{source_bucket}/{source_key} -> {dest_bucket}/{dest_key}")

        # boto3 path
        if self._boto_client is not None:
            try:
                copy_source = {"Bucket": source_bucket, "Key": source_key}
                self._boto_client.copy_object(
                    CopySource=copy_source, Bucket=dest_bucket, Key=dest_key
                )
                return {"success": True, "dest_bucket": dest_bucket, "dest_key": dest_key}
            except Exception as exc:
                return {"success": False, "error": f"boto3 copy_object fallo: {exc}"}

        # REST API path
        try:
            resp = self._signed_request(
                "PUT",
                f"/{dest_bucket}/{dest_key}",
                {},
                headers={"x-amz-copy-source": f"/{source_bucket}/{source_key}"},
            )
            if resp.ok:
                return {"success": True, "dest_bucket": dest_bucket, "dest_key": dest_key}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.body}"}
        except HTTPClientError as exc:
            return {"success": False, "error": str(exc)}

    # ── AWS Signature V4 ───────────────────────────────────────

    def _signed_request(
        self,
        method: str,
        path: str,
        query_params: dict[str, Any],
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Ejecuta una peticion HTTP firmada con AWS Signature V4.

        Args:
            method: Metodo HTTP (GET, PUT, DELETE, etc.)
            path: Ruta del recurso (e.g. /bucket/key)
            query_params: Parametros de query string
            body: Cuerpo de la peticion (bytes)
            headers: Headers adicionales

        Returns:
            HTTPResponse del HttpClient
        """
        if not self._http:
            raise HTTPClientError(message="HttpClient no inicializado. Llame connect() primero.")

        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        # Construir canonical query string
        canonical_querystring = "&".join(
            f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
            for k, v in sorted(query_params.items())
        )

        # Preparar payload
        if body is None:
            body = b""
        payload_hash = hashlib.sha256(body).hexdigest()

        # Headers para firmar
        host = f"s3.{self._region}.amazonaws.com"
        signed_headers_dict: dict[str, str] = {
            "host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if self._session_token:
            signed_headers_dict["x-amz-security-token"] = self._session_token

        # Headers adicionales del caller
        if headers:
            for k, v in headers.items():
                signed_headers_dict[k.lower()] = v

        # Canonical headers y signed headers
        canonical_headers = ""
        signed_headers_list = sorted(signed_headers_dict.keys())
        for h in signed_headers_list:
            canonical_headers += f"{h}:{signed_headers_dict[h]}\n"
        signed_headers = ";".join(signed_headers_list)

        # Canonical request
        canonical_request = "\n".join([
            method,
            path,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])

        # String to sign
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        # Signing key
        signing_key = self._get_signing_key(date_stamp)

        # Signature
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # Authorization header
        authorization = (
            f"AWS4-HMAC-SHA256 "
            f"Credential={self._access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        # Construir headers finales
        final_headers: dict[str, str] = {
            "Authorization": authorization,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if self._session_token:
            final_headers["x-amz-security-token"] = self._session_token
        if headers:
            final_headers.update(headers)

        # Ejecutar la peticion usando HttpClient internamente
        # Necesitamos usar requests directamente porque HttpClient no soporta body bytes
        import requests as req_lib

        url = f"https://{host}{path}"
        if canonical_querystring:
            url += f"?{canonical_querystring}"

        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": final_headers,
            "data": body if body else None,
            "timeout": 30,
            "verify": True,
        }

        resp = req_lib.request(**request_kwargs)
        from src.sdk.http_client import HTTPResponse

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

    def _get_signing_key(self, date_stamp: str) -> bytes:
        """Deriva la clave de firma AWS Signature V4.

        Args:
            date_stamp: Fecha en formato YYYYMMDD

        Returns:
            Clave de firma en bytes
        """
        k_date = hmac.new(
            f"AWS4{self._secret_access_key}".encode(),
            date_stamp.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        k_region = hmac.new(k_date, self._region.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        return k_signing


AWS_S3_SCHEMA = ConnectorSchema(
    name="aws_s3",
    version="1.0.0",
    description="Sube, descarga y gestiona archivos en buckets de Amazon S3",
    category="cloud_storage",
    icon="hard-drive",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="upload_file", description="Sube un archivo a S3", category="write"),
        ActionDefinition(name="download_file", description="Descarga un archivo de S3", category="read"),
        ActionDefinition(name="list_objects", description="Lista objetos en un bucket", category="read"),
        ActionDefinition(name="delete_object", description="Elimina un objeto de S3", category="delete"),
        ActionDefinition(name="get_object_url", description="Genera URL firmada para objeto", category="read"),
        ActionDefinition(name="copy_object", description="Copia un objeto entre buckets", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["access_key_id", "secret_access_key"], description="Credenciales AWS IAM")
    ],
)
