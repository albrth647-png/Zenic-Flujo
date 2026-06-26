"""
Marketplace — Servicio Principal del Marketplace de Conectores
================================================================

Orquesta las operaciones del marketplace: publicacion, busqueda,
instalacion, desinstalacion y estadisticas. Usa ConnectorRepository
para persistencia y RedisService para cache.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from src.core.db import RedisService
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.marketplace.certification import CertificationEngine, CertificationStatus
from src.marketplace.repository import ConnectorRepository

logger = setup_logging(__name__)

# TTL del cache en segundos
_CACHE_TTL = 300  # 5 minutos
_STATS_CACHE_TTL = 60  # 1 minuto

# Fix MISC-02: constantes de validacion estricta de api_key.
# Antes del fix, publish_connector solo verificaba len(api_key) >= 10,
# permitiendo que cualquier string aleatorio publicara conectores.
_MIN_API_KEY_LENGTH = 32  # Minimo razonable para una api_key criptograficamente fuerte.
_HAS_UPPERCASE = re.compile(r"[A-Z]")
_HAS_LOWERCASE = re.compile(r"[a-z]")
_HAS_DIGIT = re.compile(r"\d")


def _hash_api_key(api_key: str) -> str:
    """Hash SHA-256 hex de una api_key para almacenamiento y comparacion.

    Usamos SHA-256 (en vez de bcrypt) para no anadir dependencias nuevas.
    En produccion se deberia usar bcrypt o argon2 con sal individual por key.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _validate_api_key_structure(api_key: str) -> tuple[bool, str]:
    """Valida la estructura de una api_key de publisher.

    Fix MISC-02: la validacion anterior (``len >= 10``) aceptaba cualquier
    string. Ahora exigimos:
    1. Longitud >= 32 caracteres (minimo razonable para una api_key fuerte).
    2. Al menos una mayuscula.
    3. Al menos una minuscula.
    4. Al menos un digito.

    Returns:
        Tupla (valido: bool, razon: str). Si valido es True, razon es "".
    """
    if not api_key or not isinstance(api_key, str):
        return False, "API key vacia o invalida"
    if len(api_key) < _MIN_API_KEY_LENGTH:
        return False, f"API key demasiado corta (minimo {_MIN_API_KEY_LENGTH} caracteres)"
    if not _HAS_UPPERCASE.search(api_key):
        return False, "API key debe contener al menos una mayuscula"
    if not _HAS_LOWERCASE.search(api_key):
        return False, "API key debe contener al menos una minuscula"
    if not _HAS_DIGIT.search(api_key):
        return False, "API key debe contener al menos un digito"
    return True, ""


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
        self._db = DatabaseManager()

    def _validate_publisher_api_key(self, api_key: str) -> tuple[bool, str]:
        """Valida una api_key de publisher por estructura y (opcional) contra DB.

        Fix MISC-02:
        1. Valida la estructura (longitud >= 32, mayuscula, minuscula, digito).
        2. Si la tabla ``marketplace_publisher_keys`` tiene alguna key registrada,
           exige que la api_key este en la tabla (modo estricto — production).
        3. Si la tabla esta vacia (modo desarrollo), la validacion estructural
           es suficiente para no bloquear el onboarding inicial.

        Returns:
            Tupla (valido: bool, razon: str).
        """
        valido, razon = _validate_api_key_structure(api_key)
        if not valido:
            return False, razon

        # Verificar contra DB si hay keys registradas.
        try:
            row = self._db.fetchone(
                "SELECT COUNT(*) AS total FROM marketplace_publisher_keys"
            )
            total_registered = row["total"] if row else 0
        except Exception as e:
            # Si la tabla no existe o falla la consulta, loggear y permitir
            # (no bloquear publicacion por un error de infraestructura).
            logger.warning(f"MarketplaceService: no se pudo consultar marketplace_publisher_keys: {e}")
            return True, ""

        if total_registered == 0:
            # Modo desarrollo: la tabla esta vacia, validacion estructural basta.
            return True, ""

        # Modo estricto: la api_key debe estar registrada (comparacion por hash).
        api_key_hash = _hash_api_key(api_key)
        row = self._db.fetchone(
            "SELECT partner_name FROM marketplace_publisher_keys WHERE api_key_hash = ?",
            (api_key_hash,),
        )
        if row is None:
            return False, "API key no registrada en marketplace_publisher_keys"
        return True, ""

    def register_publisher_api_key(self, api_key: str, partner_name: str) -> dict[str, Any]:
        """Registra una api_key de publisher en la tabla ``marketplace_publisher_keys``.

        Util para onboarding inicial y para tests. En produccion, este metodo
        deberia restringirse a un flujo administrativo (RBAC + auditoria).

        Args:
            api_key: API key a registrar (debe pasar la validacion estructural).
            partner_name: Nombre del partner asociado a la key.

        Returns:
            Dict con success y, si aplica, error.
        """
        valido, razon = _validate_api_key_structure(api_key)
        if not valido:
            return {"success": False, "error": razon}
        api_key_hash = _hash_api_key(api_key)
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO marketplace_publisher_keys (api_key_hash, partner_name) VALUES (?, ?)",
                (api_key_hash, partner_name),
            )
            self._db.commit()
            logger.info(f"MarketplaceService: api_key registrada para partner '{partner_name}'")
            return {"success": True}
        except Exception as e:
            logger.error(f"MarketplaceService: error registrando api_key: {e}")
            return {"success": False, "error": str(e)}

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
        # Validar API key del publicador (Fix MISC-02).
        # Antes: solo len(api_key) >= 10. Ahora: estructura + DB opcional.
        valido, razon = self._validate_publisher_api_key(api_key)
        if not valido:
            return {"success": False, "error": f"API key invalida: {razon}"}

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
