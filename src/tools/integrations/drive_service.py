"""
Google Drive Connector — Upload, list, download, search
============================================================

Sprint 6 del Roadmap Competitivo.
Conector para Google Drive API usando requests.
Requiere token de acceso OAuth 2.0 configurado en Settings.
"""

from __future__ import annotations

import json
import time
import base64

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class DriveService:
    """
    Conector Google Drive.

    Proporciona:
    - list_files: Listar archivos en una carpeta
    - upload: Subir archivo (base64 o URL)
    - download: Descargar archivo como base64
    - search: Buscar archivos por nombre/tipo
    - delete: Eliminar archivo
    - create_folder: Crear carpeta

    Uso en workflow:
    {
        "tool": "drive",
        "action": "list_files",
        "params": {
            "access_token": "$settings.drive_token",
            "folder_id": "root"
        }
    }

    El token de acceso se configura en Settings del sistema.
    """

    API_BASE = "https://www.googleapis.com/drive/v3"
    UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

    def list_files(self, access_token: str = "",
                   folder_id: str = "root",
                   page_size: int = 20,
                   query: str = "") -> dict:
        """
        Lista archivos en Google Drive.

        Args:
            access_token: Token OAuth 2.0
            folder_id: ID de la carpeta (default: root)
            page_size: Archivos por página (max 100)
            query: Filtro adicional

        Returns:
            dict con {files: [{id, name, mimeType, size, ...}], count}
        """
        if not access_token:
            return self._error("Token de acceso requerido")

        start_time = time.time()

        q = f"'{folder_id}' in parents and trashed = false"
        if query:
            q += f" and {query}"

        try:
            import requests
            resp = requests.get(
                f"{self.API_BASE}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "q": q,
                    "pageSize": min(page_size, 100),
                    "fields": "files(id, name, mimeType, size, createdTime, "
                              "modifiedTime, webViewLink, iconLink, owners)"
                              ", nextPageToken",
                },
                timeout=30,
            )

            if resp.status_code != 200:
                return self._error(f"Drive API error: {resp.text}")

            data = resp.json()
            files = [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f.get("mimeType", ""),
                    "size": f.get("size", 0),
                    "created_at": f.get("createdTime", ""),
                    "modified_at": f.get("modifiedTime", ""),
                    "web_link": f.get("webViewLink", ""),
                }
                for f in data.get("files", [])
            ]

            return {
                "files": files,
                "count": len(files),
                "next_page_token": data.get("nextPageToken"),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Drive list error: {e}")
            return self._error(str(e))

    def search(self, access_token: str = "",
               query: str = "",
               page_size: int = 20) -> dict:
        """
        Busca archivos en Google Drive.

        Args:
            access_token: Token OAuth 2.0
            query: Término de búsqueda
            page_size: Resultados por página

        Returns:
            dict con {files: [...], count}
        """
        if not access_token:
            return self._error("Token de acceso requerido")
        if not query:
            return self._error("Query de búsqueda requerido")

        return self.list_files(
            access_token=access_token,
            folder_id="root",
            page_size=page_size,
            query=f"name contains '{query}'",
        )

    def upload(self, access_token: str = "",
               file_name: str = "",
               content_base64: str = "",
               mime_type: str = "application/octet-stream",
               parent_folder_id: str = "root") -> dict:
        """
        Sube un archivo a Google Drive.

        Args:
            access_token: Token OAuth 2.0
            file_name: Nombre del archivo
            content_base64: Contenido del archivo en base64
            mime_type: Tipo MIME
            parent_folder_id: Carpeta destino

        Returns:
            dict con {id, name, mimeType, size, webViewLink}
        """
        if not access_token:
            return self._error("Token de acceso requerido")
        if not file_name:
            return self._error("Nombre de archivo requerido")
        if not content_base64:
            return self._error("Contenido requerido (base64)")

        start_time = time.time()

        try:
            import requests
            file_content = base64.b64decode(content_base64)

            # Metadata
            metadata = {
                "name": file_name,
                "parents": [parent_folder_id],
                "mimeType": mime_type,
            }

            # Subir con uploadType=multipart
            files = {
                "metadata": ("metadata", json.dumps(metadata),
                             "application/json"),
                "file": (file_name, file_content, mime_type),
            }

            resp = requests.post(
                f"{self.UPLOAD_BASE}/files?uploadType=multipart",
                headers={"Authorization": f"Bearer {access_token}"},
                files=files,
                timeout=60,
            )

            if resp.status_code != 200:
                return self._error(f"Drive upload error: {resp.text}")

            data = resp.json()
            return {
                "id": data["id"],
                "name": data["name"],
                "mime_type": data.get("mimeType", mime_type),
                "size": len(file_content),
                "web_link": data.get("webViewLink", ""),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except base64.binascii.Error:
            return self._error("Contenido base64 inválido")
        except Exception as e:
            logger.error(f"Drive upload error: {e}")
            return self._error(str(e))

    def download(self, access_token: str = "",
                 file_id: str = "") -> dict:
        """
        Descarga un archivo de Google Drive como base64.

        Args:
            access_token: Token OAuth 2.0
            file_id: ID del archivo

        Returns:
            dict con {content_base64, name, mime_type, size}
        """
        if not access_token:
            return self._error("Token de acceso requerido")
        if not file_id:
            return self._error("File ID requerido")

        start_time = time.time()

        try:
            import requests

            # Obtener metadata primero
            meta_resp = requests.get(
                f"{self.API_BASE}/files/{file_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": "id, name, mimeType, size, webViewLink"},
                timeout=15,
            )

            if meta_resp.status_code != 200:
                return self._error(
                    f"Error obteniendo metadata: {meta_resp.text}"
                )

            meta = meta_resp.json()
            file_name = meta.get("name", "unknown")
            mime_type = meta.get("mimeType", "application/octet-stream")

            # Descargar contenido
            content_resp = requests.get(
                f"{self.API_BASE}/files/{file_id}?alt=media",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=120,
            )

            if content_resp.status_code != 200:
                return self._error(
                    f"Error descargando: {content_resp.text}"
                )

            content_bytes = content_resp.content
            content_b64 = base64.b64encode(content_bytes).decode()

            return {
                "content_base64": content_b64,
                "name": file_name,
                "mime_type": mime_type,
                "size": len(content_bytes),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Drive download error: {e}")
            return self._error(str(e))

    def delete(self, access_token: str = "",
               file_id: str = "") -> dict:
        """
        Elimina un archivo de Google Drive.

        Args:
            access_token: Token OAuth 2.0
            file_id: ID del archivo

        Returns:
            dict con {deleted: True, file_id}
        """
        if not access_token:
            return self._error("Token de acceso requerido")
        if not file_id:
            return self._error("File ID requerido")

        try:
            import requests
            resp = requests.delete(
                f"{self.API_BASE}/files/{file_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )

            if resp.status_code not in (204, 200):
                return self._error(f"Error eliminando: {resp.text}")

            return {"deleted": True, "file_id": file_id}

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Drive delete error: {e}")
            return self._error(str(e))

    def create_folder(self, access_token: str = "",
                      folder_name: str = "",
                      parent_folder_id: str = "root") -> dict:
        """
        Crea una carpeta en Google Drive.

        Args:
            access_token: Token OAuth 2.0
            folder_name: Nombre de la carpeta
            parent_folder_id: Carpeta padre

        Returns:
            dict con {id, name, webViewLink}
        """
        if not access_token:
            return self._error("Token de acceso requerido")
        if not folder_name:
            return self._error("Nombre de carpeta requerido")

        try:
            import requests
            metadata = {
                "name": folder_name,
                "parents": [parent_folder_id],
                "mimeType": "application/vnd.google-apps.folder",
            }

            resp = requests.post(
                f"{self.API_BASE}/files",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=metadata,
                timeout=15,
            )

            if resp.status_code != 200:
                return self._error(f"Error creando carpeta: {resp.text}")

            data = resp.json()
            return {
                "id": data["id"],
                "name": data["name"],
                "web_link": data.get("webViewLink", ""),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Drive create folder error: {e}")
            return self._error(str(e))

    @staticmethod
    def _error(message: str) -> dict:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_tool_definition() -> dict:
        return {
            "tool": "drive",
            "name": "Google Drive",
            "description": "Almacenamiento en Google Drive",
            "actions": {
                "list_files": {
                    "name": "Listar archivos",
                    "description": "Lista archivos en una carpeta",
                    "params": [
                        {"name": "folder_id", "type": "string",
                         "default": "root", "label": "Carpeta ID"},
                    ],
                },
                "upload": {
                    "name": "Subir archivo",
                    "description": "Sube archivo a Drive (base64)",
                    "params": [
                        {"name": "file_name", "type": "string",
                         "required": True, "label": "Nombre"},
                        {"name": "content_base64", "type": "string",
                         "required": True, "label": "Contenido (base64)"},
                    ],
                },
                "search": {
                    "name": "Buscar",
                    "description": "Busca archivos por nombre",
                    "params": [
                        {"name": "query", "type": "string", "required": True,
                         "label": "Búsqueda"},
                    ],
                },
            },
        }
