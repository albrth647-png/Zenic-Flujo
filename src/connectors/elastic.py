"""
Conector Elasticsearch — Busqueda e Indexacion
==================================================

Permite indexar documentos, ejecutar busquedas, gestionar
indices y analisis en clusters de Elasticsearch usando
la REST API nativa via HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class ElasticConnector(BaseConnector):
    """Conector para Elasticsearch: busqueda, indexacion y gestion de indices."""

    name = "elastic"
    version = "1.0.0"
    description = "Indexa documentos y ejecuta busquedas en Elasticsearch"
    category = "databases"
    icon = "search"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "http://localhost:9200"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con Elasticsearch."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("ElasticConnector: credenciales no configuradas")
            return False

        # Extract connection parameters from auth provider
        host = getattr(self._auth_provider, "_host", "") or getattr(self._auth_provider, "host", "localhost")
        port = int(getattr(self._auth_provider, "_port", 9200) or 9200)
        username = getattr(self._auth_provider, "_username", "") or getattr(self._auth_provider, "username", "")
        password = getattr(self._auth_provider, "_password", "") or getattr(self._auth_provider, "password", "")

        # Allow custom base URL
        custom_url = getattr(self._auth_provider, "_base_url", "") or getattr(self._auth_provider, "base_url", "")
        if custom_url:
            self._base_url = custom_url
        else:
            self._base_url = f"http://{host}:{port}"

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )

        # Set authentication
        if username and password:
            self._http.set_auth("Basic", username=username, password=password)
        else:
            # Try API key auth
            api_key = getattr(self._auth_provider, "_api_key", "") or getattr(self._auth_provider, "api_key", "")
            if api_key:
                self._http.set_auth("ApiKey", token=api_key)

        # Validate connection with a ping
        try:
            response = self._http.get("/")
            if response.status_code == 401:
                logger.error("ElasticConnector: credenciales invalidas (401)")
                return False
            if not response.ok:
                logger.warning(f"ElasticConnector: respuesta inesperada del cluster: {response.status_code}")
        except HTTPClientError as e:
            logger.warning(f"ElasticConnector: error validando conexion: {e}")

        self._connected = True
        self._log_operation("connect", "Conexion Elasticsearch establecida")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Elasticsearch.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "index_document": self._index_document,
            "search": self._search,
            "get_document": self._get_document,
            "delete_document": self._delete_document,
            "create_index": self._create_index,
            "list_indices": self._list_indices,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Elasticsearch esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Elasticsearch."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _index_document(self, params: dict[str, Any]) -> dict[str, Any]:
        """Indexa un documento en Elasticsearch.

        Args:
            params: Debe contener 'index', 'document' y opcionalmente 'id'
        """
        index = params.get("index", "")
        document = params.get("document", {})
        doc_id = params.get("id", "")
        refresh = params.get("refresh", "false")
        pipeline = params.get("pipeline", "")
        if not index or not document:
            return {"success": False, "error": "Parametros requeridos: index, document"}
        self._log_operation("index_document", f"index={index}, id={doc_id}")

        try:
            query_params: dict[str, Any] = {"refresh": refresh}
            if pipeline:
                query_params["pipeline"] = pipeline

            if doc_id:
                # Use PUT for explicit ID
                response = self._http.put(f"/{index}/_doc/{doc_id}", json=document, params=query_params)
            else:
                # Use POST for auto-generated ID
                response = self._http.post(f"/{index}/_doc", json=document, params=query_params)

            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "index": data.get("_index", index),
                "id": data.get("_id", doc_id),
                "result": data.get("result", "created"),
                "version": data.get("_version", 1),
                "seq_no": data.get("_seq_no", None),
                "primary_term": data.get("_primary_term", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta una busqueda en Elasticsearch.

        Args:
            params: Debe contener 'index' y 'query' (dict con query DSL)
        """
        index = params.get("index", "")
        query = params.get("query", {})
        size = params.get("size", 10)
        from_ = params.get("from", 0)
        sort = params.get("sort")
        source = params.get("_source")
        if not index or not query:
            return {"success": False, "error": "Parametros requeridos: index, query"}
        self._log_operation("search", f"index={index}")

        try:
            body: dict[str, Any] = {
                "query": query,
                "size": size,
                "from": from_,
            }
            if sort:
                body["sort"] = sort
            if source is not None:
                body["_source"] = source
            if params.get("aggs"):
                body["aggs"] = params["aggs"]
            if params.get("highlight"):
                body["highlight"] = params["highlight"]

            # Support searching multiple indices
            index_path = index if isinstance(index, str) else ",".join(index)
            response = self._http.post(f"/{index_path}/_search", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            hits = data.get("hits", {})
            return {
                "success": True,
                "hits": hits,
                "took": data.get("took", 0),
                "timed_out": data.get("timed_out", False),
                "_shards": data.get("_shards", {}),
                "aggregations": data.get("aggregations", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_document(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un documento por ID de Elasticsearch.

        Args:
            params: Debe contener 'index' y 'id'
        """
        index = params.get("index", "")
        doc_id = params.get("id", "")
        params.get("_source")
        source_includes = params.get("_source_includes", "")
        source_excludes = params.get("_source_excludes", "")
        if not index or not doc_id:
            return {"success": False, "error": "Parametros requeridos: index, id"}
        self._log_operation("get_document", f"index={index}, id={doc_id}")

        try:
            query_params: dict[str, Any] = {}
            if source_includes:
                query_params["_source_includes"] = source_includes
            if source_excludes:
                query_params["_source_excludes"] = source_excludes

            response = self._http.get(
                f"/{index}/_doc/{doc_id}",
                params=query_params if query_params else None,
            )
            if not response.ok:
                if response.status_code == 404:
                    return {"success": False, "error": f"Documento no encontrado: {index}/{doc_id}"}
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "index": data.get("_index", index),
                "id": data.get("_id", doc_id),
                "found": data.get("found", True),
                "_source": data.get("_source", {}),
                "_version": data.get("_version", 1),
                "_seq_no": data.get("_seq_no", None),
                "_primary_term": data.get("_primary_term", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _delete_document(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un documento de Elasticsearch.

        Args:
            params: Debe contener 'index' y 'id'
        """
        index = params.get("index", "")
        doc_id = params.get("id", "")
        refresh = params.get("refresh", "false")
        if not index or not doc_id:
            return {"success": False, "error": "Parametros requeridos: index, id"}
        self._log_operation("delete_document", f"index={index}, id={doc_id}")

        try:
            query_params: dict[str, Any] = {"refresh": refresh}
            response = self._http.delete(f"/{index}/_doc/{doc_id}", params=query_params)
            if not response.ok:
                if response.status_code == 404:
                    return {"success": False, "error": f"Documento no encontrado: {index}/{doc_id}"}
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "index": data.get("_index", index),
                "id": data.get("_id", doc_id),
                "result": data.get("result", "deleted"),
                "_version": data.get("_version", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_index(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un indice en Elasticsearch.

        Args:
            params: Debe contener 'index' y opcionalmente 'mappings', 'settings'
        """
        index = params.get("index", "")
        if not index:
            return {"success": False, "error": "Parametro requerido: index"}
        self._log_operation("create_index", f"index={index}")

        try:
            body: dict[str, Any] = {}
            if params.get("mappings"):
                body["mappings"] = params["mappings"]
            if params.get("settings"):
                body["settings"] = params["settings"]
            if params.get("aliases"):
                body["aliases"] = params["aliases"]

            response = self._http.put(f"/{index}", json=body if body else None)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "index": data.get("index", index),
                "acknowledged": data.get("acknowledged", False),
                "shards_acknowledged": data.get("shards_acknowledged", False),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_indices(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los indices de Elasticsearch."""
        self._log_operation("list_indices")

        try:
            # Use the _cat/indices API for a clean list
            format_param = params.get("format", "json")
            response = self._http.get("/_cat/indices", params={"format": format_param})
            if not response.ok:
                # Fallback to _all/_mapping
                response = self._http.get("/_all/_mapping")
                if not response.ok:
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
                data = response.json()
                indices = list(data.keys())
                return {"success": True, "indices": indices}

            data = response.json()
            if isinstance(data, list):
                # _cat/indices returns a list of index info
                indices = [idx.get("index", idx.get("i", "")) for idx in data]
            elif isinstance(data, dict):
                indices = list(data.keys())
            else:
                indices = []

            return {"success": True, "indices": indices}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


ELASTIC_SCHEMA = ConnectorSchema(
    name="elastic",
    version="1.0.0",
    description="Indexa documentos y ejecuta busquedas en Elasticsearch",
    category="databases",
    icon="search",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="index_document", description="Indexa un documento", category="write"),
        ActionDefinition(name="search", description="Ejecuta una busqueda", category="read"),
        ActionDefinition(name="get_document", description="Obtiene un documento", category="read"),
        ActionDefinition(name="delete_document", description="Elimina un documento", category="delete"),
        ActionDefinition(name="create_index", description="Crea un indice", category="write"),
        ActionDefinition(name="list_indices", description="Lista indices", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="basic", required_fields=["host", "username", "password"], description="Credenciales Elasticsearch")
    ],
)
