"""
Marketplace — Servicio Principal del Marketplace de Conectores
================================================================

Orquesta las operaciones del marketplace: publicacion, busqueda,
instalacion, desinstalacion y estadisticas. Usa ConnectorRepository
para persistencia y RedisService para cache.
"""

from __future__ import annotations

from typing import Any

from src.data.redis_service import RedisService
from src.marketplace.certification import CertificationEngine, CertificationStatus
from src.marketplace.repository import ConnectorRepository
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# TTL del cache en segundos
_CACHE_TTL = 300  # 5 minutos
_STATS_CACHE_TTL = 60  # 1 minuto


class MarketplaceService:
    """
    Servicio principal del marketplace de conectores.

    Orquesta la publicacion, certificacion, busqueda, instalacion
    y estadisticas de conectores. Usa ConnectorRepository para
    persistencia y RedisService para cache de consultas frecuentes.
    """

    def __init__(self) -> None:
        """Inicializa el servicio con repositorio, cache y motor de certificacion."""
        self._repo = ConnectorRepository()
        self._cache = RedisService()
        self._certification = CertificationEngine()

    def publish_connector(self, connector_zip_path: str, api_key: str) -> dict[str, Any]:
        """
        Publica un conector en el marketplace.

        Recibe un paquete de conector, valida la API key, ejecuta
        la certificacion automatica y publica el conector si pasa
        las verificaciones.

        Args:
            connector_zip_path: Ruta al archivo zip del conector
            api_key: API key del publicador para autenticacion

        Retorna:
            Diccionario con el resultado de la publicacion
        """
        # Validar API key del publicador
        if not api_key or len(api_key) < 10:
            return {"success": False, "error": "API key invalida"}

        # Ejecutar certificacion automatica
        cert_report = self._certification.auto_review(connector_zip_path)
        cert_status = cert_report.get("status", CertificationStatus.AUTO_FAILED.value)

        # Determinar estado del conector segun certificacion
        if cert_status == CertificationStatus.AUTO_PASSED.value:
            connector_status = "pending_review"
            cert_display = CertificationStatus.AUTO_PASSED.value
        else:
            connector_status = "draft"
            cert_display = CertificationStatus.AUTO_FAILED.value

        # Extraer nombre del conector desde el reporte o la ruta
        connector_name = cert_report.get("connector_name", "")
        if not connector_name:
            import os
            connector_name = os.path.basename(connector_zip_path).replace(".zip", "")

        # Crear el conector en el repositorio
        connector_data = {
            "name": connector_name,
            "status": connector_status,
            "certification_status": cert_display,
            "current_version": "1.0.0",
            "tags": [],
            "actions": [],
            "auth_types": [],
        }

        try:
            result = self._repo.create_connector(connector_data)
            self._invalidate_cache()
            logger.info(f"MarketplaceService: conector '{connector_name}' publicado con estado '{cert_display}'")
            return {
                "success": True,
                "connector": result,
                "certification_report": cert_report,
            }
        except Exception as e:
            logger.error(f"MarketplaceService: error publicando conector: {e}")
            return {"success": False, "error": str(e)}

    def search_connectors(
        self,
        query: str | None = None,
        category: str | None = None,
        certification_status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """
        Busca conectores en el marketplace con filtros.

        Soporta busqueda por texto libre, filtrado por categoria
        y estado de certificacion, con paginacion.

        Args:
            query: Texto de busqueda libre (busca en nombre, descripcion, autor)
            category: Filtrar por categoria
            certification_status: Filtrar por estado de certificacion
            page: Numero de pagina (empezando en 1)
            per_page: Resultados por pagina

        Retorna:
            Diccionario con resultados de busqueda y metadatos de paginacion
        """
        cache_key = f"mkt:search:{query}:{category}:{certification_status}:{page}:{per_page}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        if query:
            result = self._repo.search_connectors(query, page=page, per_page=per_page)
        else:
            result = self._repo.list_connectors(
                category=category,
                certification_status=certification_status,
                status="certified",
                page=page,
                per_page=per_page,
            )

        self._cache.set_json(cache_key, result, ttl=_CACHE_TTL)
        return result

    def get_connector_details(self, name: str) -> dict[str, Any] | None:
        """
        Obtiene los detalles completos de un conector.

        Args:
            name: Nombre del conector

        Retorna:
            Diccionario con los detalles del conector, o None si no existe
        """
        cache_key = f"mkt:connector:{name}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        result = self._repo.get_connector(name)
        if result:
            self._cache.set_json(cache_key, result, ttl=_CACHE_TTL)
        return result

    def install_connector(self, name: str, tenant_id: str) -> dict[str, Any]:
        """
        Instala un conector para un tenant especifico.

        Verifica que el conector este certificado y lo instala
        para el tenant. Actualiza el cache.

        Args:
            name: Nombre del conector a instalar
            tenant_id: ID del tenant

        Retorna:
            Diccionario con el resultado de la instalacion
        """
        connector = self._repo.get_connector(name)
        if not connector:
            return {"success": False, "error": f"Conector '{name}' no encontrado"}

        if connector.get("certification_status") not in ("certified", "auto_passed"):
            return {"success": False, "error": f"Conector '{name}' no esta certificado"}

        if connector.get("status") not in ("certified", "pending_review"):
            return {"success": False, "error": f"Conector '{name}' no esta disponible para instalacion"}

        try:
            result = self._repo.create_installation(name, tenant_id, connector.get("current_version", "1.0.0"))
            self._invalidate_cache()
            logger.info(f"MarketplaceService: conector '{name}' instalado para tenant '{tenant_id}'")
            return {"success": True, "installation": result}
        except Exception as e:
            logger.error(f"MarketplaceService: error instalando conector: {e}")
            return {"success": False, "error": str(e)}

    def uninstall_connector(self, name: str, tenant_id: str) -> dict[str, Any]:
        """
        Desinstala un conector de un tenant especifico.

        Args:
            name: Nombre del conector a desinstalar
            tenant_id: ID del tenant

        Retorna:
            Diccionario con el resultado de la desinstalacion
        """
        try:
            self._repo.delete_installation(name, tenant_id)
            self._invalidate_cache()
            logger.info(f"MarketplaceService: conector '{name}' desinstalado para tenant '{tenant_id}'")
            return {"success": True, "message": f"Conector '{name}' desinstalado"}
        except Exception as e:
            logger.error(f"MarketplaceService: error desinstalando conector: {e}")
            return {"success": False, "error": str(e)}

    def list_categories(self) -> list[dict[str, Any]]:
        """
        Lista todas las categorias del marketplace.

        Retorna:
            Lista de diccionarios con las categorias disponibles
        """
        cache_key = "mkt:categories"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        result = self._repo.list_categories()
        self._cache.set_json(cache_key, result, ttl=_CACHE_TTL)
        return result

    def get_stats(self) -> dict[str, Any]:
        """
        Obtiene estadisticas generales del marketplace.

        Incluye total de conectores, categorias, instalaciones,
        conectores certificados y pendientes de revision.

        Retorna:
            Diccionario con las estadisticas del marketplace
        """
        cache_key = "mkt:stats"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        result = self._repo.get_stats()
        self._cache.set_json(cache_key, result, ttl=_STATS_CACHE_TTL)
        return result

    def get_connector_metrics(self, name: str) -> dict[str, Any]:
        """
        Obtiene metricas de uso de un conector especifico.

        Incluye instalaciones totales, activas, calificacion
        promedio y distribucion de calificaciones.

        Args:
            name: Nombre del conector

        Retorna:
            Diccionario con las metricas del conector
        """
        cache_key = f"mkt:metrics:{name}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            return cached

        result = self._repo.get_connector_metrics(name)
        self._cache.set_json(cache_key, result, ttl=_STATS_CACHE_TTL)
        return result

    def _invalidate_cache(self) -> None:
        """Invalida todo el cache del marketplace."""
        self._cache.delete("mkt:stats")
        self._cache.delete("mkt:categories")
        # Nota: en produccion se usaria un patron de claves con SCAN para invalidar masivamente
        logger.debug("MarketplaceService: cache invalidado")
