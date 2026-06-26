"""
Marketplace — Repositorio de Almacenamiento de Conectores
==========================================================

Gestiona la persistencia de conectores, categorias, instalaciones
y resenas en la base de datos marketplace.db (MarketplaceDBManager).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from src.core.db import MarketplaceDBManager
from src.core.logging import setup_logging
from src.core.db import build_update_query

logger = setup_logging(__name__)


class ConnectorRepository:
    """
    Repositorio de almacenamiento para conectores del marketplace.    marketplace dedicada, separada de la base de datos principal.
    """

    def __init__(self) -> None:
        """Inicializa el repositorio con su propia base de datos marketplace.db."""
        self._db = MarketplaceDBManager()
        logger.info("ConnectorRepository: inicializado con marketplace.db propio")

    # ── Conectores CRUD ───────────────────────────────────────

    def create_connector(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un nuevo conector en el marketplace.

        Args:
            data: Datos del conector a crear

        Retorna:
            Diccionario con los datos del conector creado
        """
        conn_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        self._db.execute(
            """INSERT INTO marketplace_connectors
               (id, name, display_name, description, category, icon, author,
                homepage, docs_url, status, certification_status, current_version,
                versions, tags, actions, auth_types, installs, rating, review_count,
                featured, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conn_id, data.get("name", ""), data.get("display_name", ""),
                data.get("description", ""), data.get("category", "general"),
                data.get("icon", "plug"), data.get("author", ""),
                data.get("homepage", ""), data.get("docs_url", ""),
                data.get("status", "draft"), data.get("certification_status", "pending"),
                data.get("current_version", "1.0.0"),
                json.dumps(data.get("versions", [])), json.dumps(data.get("tags", [])),
                json.dumps(data.get("actions", [])), json.dumps(data.get("auth_types", [])),
                data.get("installs", 0), data.get("rating", 0.0),
                data.get("review_count", 0), int(data.get("featured", False)),
                now, now,
            ),
        )
        self._db.commit()
        logger.info(f"ConnectorRepository: conector '{data.get('name')}' creado")
        return self.get_connector(data.get("name", ""))

    def get_connector(self, name: str) -> dict[str, Any] | None:
        """
        Obtiene un conector por su nombre.

        Args:
            name: Nombre del conector

        Retorna:
            Diccionario con los datos del conector, o None si no existe
        """
        row = self._db.fetchone("SELECT * FROM marketplace_connectors WHERE name = ?", (name,))
        if row is None:
            return None
        return self._row_to_connector(row)

    def update_connector(self, name: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """
        Actualiza un conector existente.

        Args:
            name: Nombre del conector
            updates: Campos a actualizar

        Retorna:
            Diccionario con los datos actualizados, o None si no existe
        """
        allowed = {
            "display_name", "description", "category", "icon", "author",
            "homepage", "docs_url", "status", "certification_status",
            "current_version", "versions", "tags", "actions", "auth_types",
            "installs", "rating", "review_count", "featured", "updated_at",
        }
        # Pre-procesar fields: serializar JSON y convertir featured a int
        processed_fields: dict[str, Any] = {}
        for key, value in updates.items():
            if key in allowed:
                if key in ("versions", "tags", "actions", "auth_types"):
                    value = json.dumps(value)
                elif key == "featured":
                    value = int(value)
                processed_fields[key] = value

        result = build_update_query(
            "marketplace_connectors",
            allowed,
            processed_fields,
            extra_set={"updated_at": datetime.now().isoformat()},
        )
        if result is None:
            return self.get_connector(name)

        sql, params = result
        self._db.execute(sql, (*params, name))
        self._db.commit()
        return self.get_connector(name)

    def delete_connector(self, name: str) -> bool:
        """
        Elimina un conector del marketplace.

        Args:
            name: Nombre del conector

        Retorna:
            True si se elimino correctamente
        """
        self._db.execute("DELETE FROM marketplace_connectors WHERE name = ?", (name,))
        self._db.commit()
        logger.info(f"ConnectorRepository: conector '{name}' eliminado")
        return True

    def list_connectors(
        self,
        category: str | None = None,
        certification_status: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """
        Lista conectores con filtros y paginacion.

        Args:
            category: Filtrar por categoria
            certification_status: Filtrar por estado de certificacion
            status: Filtrar por estado del conector
            page: Numero de pagina (empezando en 1)
            per_page: Resultados por pagina

        Retorna:
            Diccionario con conectores y metadatos de paginacion
        """
        conditions: list[str] = []
        params: list[Any] = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if certification_status:
            conditions.append("certification_status = ?")
            params.append(certification_status)
        if status:
            conditions.append("status = ?")
            params.append(status)

        # where se construye solo con strings hardcoded ("status = ?", "category = ?", etc.)
        # Sin interpolación de input externo. B608 es falso positivo.
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        total = self._db.fetchone(f"SELECT COUNT(*) as c FROM marketplace_connectors {where}", tuple(params))  # nosec B608 — where construido con literals
        total_count = total["c"] if total else 0

        offset = (page - 1) * per_page
        rows = self._db.fetchall(
            f"SELECT * FROM marketplace_connectors {where} ORDER BY installs DESC, rating DESC LIMIT ? OFFSET ?",  # nosec B608 — where construido con literals
            (*tuple(params), per_page, offset),
        )

        connectors = [self._row_to_connector(r) for r in rows]
        total_pages = max(1, (total_count + per_page - 1) // per_page)

        return {
            "connectors": connectors,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    def search_connectors(self, query: str, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """
        Busca conectores por texto libre.

        Args:
            query: Texto de busqueda
            page: Numero de pagina
            per_page: Resultados por pagina

        Retorna:
            Diccionario con resultados de busqueda y paginacion
        """
        search_pattern = f"%{query}%"
        total = self._db.fetchone(
            """SELECT COUNT(*) as c FROM marketplace_connectors
               WHERE name LIKE ? OR display_name LIKE ? OR description LIKE ?
               OR author LIKE ?""",
            (search_pattern, search_pattern, search_pattern, search_pattern),
        )
        total_count = total["c"] if total else 0

        offset = (page - 1) * per_page
        rows = self._db.fetchall(
            """SELECT * FROM marketplace_connectors
               WHERE name LIKE ? OR display_name LIKE ? OR description LIKE ?
               OR author LIKE ?
               ORDER BY installs DESC, rating DESC LIMIT ? OFFSET ?""",
            (search_pattern, search_pattern, search_pattern, search_pattern, per_page, offset),
        )

        connectors = [self._row_to_connector(r) for r in rows]
        total_pages = max(1, (total_count + per_page - 1) // per_page)

        return {
            "connectors": connectors,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }

    # ── Categorias ────────────────────────────────────────────

    def create_category(self, data: dict[str, Any]) -> dict[str, Any]:
        """Crea una nueva categoria en el marketplace."""
        cat_id = str(uuid.uuid4())
        self._db.execute(
            """INSERT INTO marketplace_categories (id, name, display_name, description, icon, parent_category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cat_id, data.get("name", ""), data.get("display_name", ""), data.get("description", ""),
             data.get("icon", "folder"), data.get("parent_category")),
        )
        self._db.commit()
        return self._db.fetchone("SELECT * FROM marketplace_categories WHERE id = ?", (cat_id,)) or {}

    def list_categories(self) -> list[dict[str, Any]]:
        """Lista todas las categorias del marketplace."""
        return self._db.fetchall("SELECT * FROM marketplace_categories ORDER BY name")

    # ── Instalaciones ─────────────────────────────────────────

    def create_installation(self, connector_name: str, tenant_id: str, version: str = "1.0.0") -> dict[str, Any]:
        """Registra una instalacion de conector para un tenant."""
        inst_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        self._db.execute(
            """INSERT OR REPLACE INTO marketplace_installations
               (id, connector_name, tenant_id, version, status, config, installed_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', '{}', ?, ?)""",
            (inst_id, connector_name, tenant_id, version, now, now),
        )

        # Incrementar contador de instalaciones
        self._db.execute(
            "UPDATE marketplace_connectors SET installs = installs + 1, updated_at = ? WHERE name = ?",
            (now, connector_name),
        )
        self._db.commit()
        logger.info(f"ConnectorRepository: conector '{connector_name}' instalado para tenant '{tenant_id}'")
        return self._db.fetchone("SELECT * FROM marketplace_installations WHERE id = ?", (inst_id,)) or {}

    def delete_installation(self, connector_name: str, tenant_id: str) -> bool:
        """Elimina una instalacion de conector para un tenant."""
        now = datetime.now().isoformat()
        self._db.execute(
            """UPDATE marketplace_installations SET status = 'uninstalled', uninstalled_at = ?, updated_at = ?
               WHERE connector_name = ? AND tenant_id = ?""",
            (now, now, connector_name, tenant_id),
        )
        self._db.commit()
        logger.info(f"ConnectorRepository: conector '{connector_name}' desinstalado para tenant '{tenant_id}'")
        return True

    def list_installations(self, tenant_id: str) -> list[dict[str, Any]]:
        """Lista las instalaciones activas de un tenant."""
        return self._db.fetchall(
            "SELECT * FROM marketplace_installations WHERE tenant_id = ? AND status = 'active'",
            (tenant_id,),
        )

    # ── Resenas ───────────────────────────────────────────────

    def create_review(self, connector_name: str, tenant_id: str, rating: int, title: str = "", comment: str = "") -> dict[str, Any]:
        """Crea una resena para un conector."""
        rev_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        self._db.execute(
            """INSERT INTO marketplace_reviews (id, connector_name, tenant_id, rating, title, comment, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (rev_id, connector_name, tenant_id, rating, title, comment, now, now),
        )

        # Recalcular rating promedio
        stats = self._db.fetchone(
            "SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM marketplace_reviews WHERE connector_name = ?",
            (connector_name,),
        )
        if stats:
            self._db.execute(
                "UPDATE marketplace_connectors SET rating = ?, review_count = ?, updated_at = ? WHERE name = ?",
                (round(stats["avg_rating"], 2), stats["count"], now, connector_name),
            )

        self._db.commit()
        return self._db.fetchone("SELECT * FROM marketplace_reviews WHERE id = ?", (rev_id,)) or {}

    def list_reviews(self, connector_name: str) -> list[dict[str, Any]]:
        """Lista las resenas de un conector."""
        return self._db.fetchall(
            "SELECT * FROM marketplace_reviews WHERE connector_name = ? ORDER BY created_at DESC",
            (connector_name,),
        )

    # ── Estadisticas ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Obtiene estadisticas generales del marketplace."""
        total = self._db.fetchone("SELECT COUNT(*) as c FROM marketplace_connectors")
        certified = self._db.fetchone("SELECT COUNT(*) as c FROM marketplace_connectors WHERE certification_status = 'certified'")
        pending = self._db.fetchone("SELECT COUNT(*) as c FROM marketplace_connectors WHERE certification_status = 'pending'")
        installs = self._db.fetchone("SELECT COALESCE(SUM(installs), 0) as c FROM marketplace_connectors")
        categories = self._db.fetchall(
            "SELECT category, COUNT(*) as count FROM marketplace_connectors GROUP BY category ORDER BY count DESC"
        )
        top = self._db.fetchall(
            "SELECT name, display_name, category, installs, rating FROM marketplace_connectors ORDER BY installs DESC LIMIT 10"
        )

        return {
            "total_connectors": total["c"] if total else 0,
            "total_categories": len(categories),
            "total_installs": installs["c"] if installs else 0,
            "certified_connectors": certified["c"] if certified else 0,
            "pending_review": pending["c"] if pending else 0,
            "category_distribution": {c["category"]: c["count"] for c in categories},
            "top_connectors": top,
        }

    def get_connector_metrics(self, name: str) -> dict[str, Any]:
        """Obtiene metricas de uso de un conector especifico."""
        connector = self.get_connector(name)
        if not connector:
            return {"error": f"Conector '{name}' no encontrado"}

        active_installs = self._db.fetchone(
            "SELECT COUNT(*) as c FROM marketplace_installations WHERE connector_name = ? AND status = 'active'",
            (name,),
        )
        reviews = self._db.fetchall(
            "SELECT rating FROM marketplace_reviews WHERE connector_name = ?",
            (name,),
        )
        rating_dist: dict[str, int] = {}
        for r in reviews:
            key = str(r["rating"])
            rating_dist[key] = rating_dist.get(key, 0) + 1

        return {
            "name": name,
            "total_installs": connector.get("installs", 0),
            "active_installs": active_installs["c"] if active_installs else 0,
            "average_rating": connector.get("rating", 0.0),
            "review_count": connector.get("review_count", 0),
            "rating_distribution": rating_dist,
        }

    # ── Helpers ───────────────────────────────────────────────

    def _row_to_connector(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convierte una fila de la base de datos a diccionario con JSON parseado."""
        result = dict(row)
        for key in ("versions", "tags", "actions", "auth_types"):
            if key in result and isinstance(result[key], str):
                try:
                    result[key] = json.loads(result[key])
                except (json.JSONDecodeError, TypeError):
                    result[key] = []
        if "featured" in result:
            result["featured"] = bool(result["featured"])
        return result
