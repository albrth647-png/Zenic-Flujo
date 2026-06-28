"""
Zenic-Flujo — Multi-Tenancy Service
=====================================

Servicio de multi-tenancy con modelo hibrido: DB-per-tenant (enterprise) y
schema-per-tenant (SMB). Permite aislamiento de datos, resolucion de tenant
por subdominio/dominio/header/sesion, y configuracion por tenant.

Funcionalidades:
- Resolucion de tenant: subdominio, dominio custom, header X-Tenant-ID, sesion
- Gestion de tenants: CRUD, suspender/activar, eliminar con cleanup
- Aislamiento de BD: schema-per-tenant o DB-per-tenant
- Propagacion de contexto: thread-local tenant context + middleware Flask
- Feature flags por tenant
- Rate limits por tenant
- Branding custom por tenant (logo, colores, dominio)
- Data residency por tenant (region de almacenamiento)

Componentes extraidos:
- context.py: Contexto thread-local (get/set/clear tenant_id)
- storage.py: Aprovisionamiento de BD (TenantStorageProvisioner, TenantConnectionPool)
- middleware.py: Middleware Flask (TenantMiddleware)
- features.py: Feature flags por tenant (TenantFeatureManager)

Configuracion via variables de entorno:
- WFD_TENANT_DEFAULT_PLAN: Plan por defecto (default: free)
- WFD_TENANT_DOMAIN: Dominio base (default: zenic-flijo.com)
- WFD_TENANT_CACHE_TTL: TTL de cache Redis en segundos (default: 3600)
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from typing import Any

from src.core.db import DatabaseManager, RedisService, quote_identifier
from src.core.logging import setup_logging
from src.tenant.features import TenantFeatureManager
from src.tenant.storage import TENANT_PLANS, TenantConnectionPool, TenantStorageProvisioner

logger = setup_logging(__name__)

# ── Constantes ────────────────────────────────────────────────

_DEFAULT_PLAN: str = os.environ.get("WFD_TENANT_DEFAULT_PLAN", "free")
_TENANT_DOMAIN: str = os.environ.get("WFD_TENANT_DOMAIN", "zenic-flijo.com")
_TENANT_CACHE_TTL: int = int(os.environ.get("WFD_TENANT_CACHE_TTL", "3600"))


# ── Tenant Service ────────────────────────────────────────────


class TenantService:
    """Servicio de multi-tenancy con modelo hibrido de aislamiento."""

    _instance: TenantService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> TenantService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._redis = RedisService()
            self._provisioner = TenantStorageProvisioner()
            self._connection_pool = TenantConnectionPool()
            self._features = TenantFeatureManager()
            self._ensure_tables()
            logger.info("Tenant Service inicializado")

    # ── Inicializacion de tablas ──────────────────────────

    def _ensure_tables(self) -> None:
        """Crea las tablas de gestion de tenants en la BD de administracion."""
        conn = self._db.get_connection()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT UNIQUE NOT NULL,
                domain      TEXT,
                plan        TEXT DEFAULT 'free',
                status      TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'deleted')),
                config      TEXT DEFAULT '{}',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tenant_features (
                tenant_id   TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                PRIMARY KEY (tenant_id, feature_name),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id   TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (tenant_id, key),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS tenant_databases (
                tenant_id       TEXT NOT NULL,
                db_type         TEXT NOT NULL CHECK(db_type IN ('schema', 'database')),
                connection_string TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
            CREATE INDEX IF NOT EXISTS idx_tenants_domain ON tenants(domain);
            CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
            CREATE INDEX IF NOT EXISTS idx_tenant_features_tenant ON tenant_features(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_tenant_settings_tenant ON tenant_settings(tenant_id);
        """)
        conn.commit()

    # ── Gestion de tenants ────────────────────────────────

    def create_tenant(self, name: str, slug: str, plan: str = "free", config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Crea un nuevo tenant y aprovisiona su almacenamiento de datos.

        Args:
            name: Nombre legible del tenant
            slug: Identificador unico URL-safe (ej: 'acme-corp')
            plan: Plan de suscripcion ('free', 'smb', 'enterprise')
            config: Configuracion adicional del tenant

        Returns:
            dict con status y tenant_id
        """
        if plan not in TENANT_PLANS:
            return {"status": "error", "message": f"Plan invalido. Validos: {', '.join(TENANT_PLANS)}"}

        # Verificar slug unico
        existing = self._db.fetchone("SELECT id FROM tenants WHERE slug = ?", (slug,))
        if existing:
            return {"status": "error", "message": f"Slug '{slug}' ya existe"}

        tenant_id = str(uuid.uuid4())
        config = config or {}
        plan_config = TENANT_PLANS[plan]
        config.setdefault("max_workflows", plan_config["max_workflows"])
        config.setdefault("max_users", plan_config["max_users"])
        config.setdefault("max_executions_per_day", plan_config["max_executions_per_day"])

        # Branding default
        config.setdefault(
            "branding",
            {
                "logo_url": "",
                "primary_color": "#4A90D9",
                "secondary_color": "#2C3E50",
            },
        )

        # Data residency
        config.setdefault("data_residency", "us-east-1")

        config_json = json.dumps(config, default=str, ensure_ascii=False)

        # Crear tenant en BD
        self._db.execute(
            "INSERT INTO tenants (id, name, slug, plan, status, config) VALUES (?, ?, ?, ?, 'active', ?)",
            (tenant_id, name, slug, plan, config_json),
        )
        self._db.commit()

        # Aprovisionar almacenamiento de datos
        db_type = plan_config["db_isolation"]
        provision_result = self._provisioner.provision(tenant_id, slug, db_type)

        if provision_result.get("status") != "ok":
            # Rollback: eliminar tenant si falla aprovisionamiento
            self._db.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
            self._db.commit()
            return provision_result

        # Habilitar features del plan usando TenantFeatureManager
        for feature in plan_config.get("features", []):
            self._features.set_feature(tenant_id, feature, True)

        # Cache en Redis
        self._cache_tenant(
            tenant_id,
            {
                "id": tenant_id,
                "name": name,
                "slug": slug,
                "plan": plan,
                "status": "active",
                "config": config,
            },
        )

        self._db.audit("tenant.created", f"Tenant '{name}' creado (plan={plan}, id={tenant_id})")
        logger.info(f"Tenant: '{name}' creado (plan={plan}, db_type={db_type}, id={tenant_id})")

        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "name": name,
            "slug": slug,
            "plan": plan,
            "db_type": db_type,
        }

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        """Obtiene la informacion completa de un tenant.

        Verifica primero en cache Redis, luego en BD.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con datos del tenant, o None si no existe
        """
        # Verificar cache Redis
        cached = self._redis.get_json(f"tenant:{tenant_id}")
        if cached:
            return cached

        # Consultar BD
        row = self._db.fetchone("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        if not row:
            return None

        tenant_data = self._tenant_row_to_dict(row)
        # Cargar features y settings usando los managers especializados
        tenant_data["features"] = self._features.get_all_features(tenant_id)
        tenant_data["settings"] = self._get_tenant_settings(tenant_id)

        # Cache en Redis
        self._cache_tenant(tenant_id, tenant_data)

        return tenant_data

    def get_tenant_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Obtiene un tenant por su slug."""
        row = self._db.fetchone("SELECT * FROM tenants WHERE slug = ?", (slug,))
        if not row:
            return None
        return self._tenant_row_to_dict(row)

    # legítimo: Flask Request no tipado por compatibilidad
    def resolve_tenant(self, request: Any) -> dict[str, Any] | None:
        """Resuelve el tenant a partir de una request HTTP.

        Orden de resolucion:
        1. Header X-Tenant-ID (para API)
        2. Sesion Flask (si ya se resolvio antes)
        3. Subdominio (tenant.zenic-flijo.com)
        4. Dominio custom

        Args:
            request: Objeto request de Flask

        Returns:
            dict con tenant_id y datos del tenant, o None
        """
        # 1. Header X-Tenant-ID
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            tenant = self.get_tenant(tenant_id)
            if tenant and tenant.get("status") == "active":
                return tenant

        # 2. Sesion Flask
        try:
            from flask import session

            session_tenant_id = session.get("tenant_id")
            if session_tenant_id:
                tenant = self.get_tenant(session_tenant_id)
                if tenant and tenant.get("status") == "active":
                    return tenant
        except RuntimeError:
            pass  # No hay contexto de solicitud Flask

        # 3. Subdominio (tenant.zenic-flijo.com)
        host = request.host.split(":")[0]  # Remover puerto
        if host.endswith(f".{_TENANT_DOMAIN}"):
            subdomain = host[: -len(f".{_TENANT_DOMAIN}")]
            if subdomain and subdomain != "www":
                # Buscar por slug = subdomain
                tenant = self.get_tenant_by_slug(subdomain)
                if tenant and tenant.get("status") == "active":
                    return tenant

        # 4. Dominio custom
        tenant_row = self._db.fetchone("SELECT * FROM tenants WHERE domain = ? AND status = 'active'", (host,))
        if tenant_row:
            return self._tenant_row_to_dict(tenant_row)

        return None

    def update_tenant(self, tenant_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Actualiza los datos de un tenant.

        Args:
            tenant_id: ID del tenant
            updates: Campos a actualizar (name, domain, plan, config, status)

        Returns:
            dict con status
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        allowed_fields = {"name", "domain", "plan", "status", "config", "updated_at"}
        # Pre-procesar fields: serializar config y validar plan
        processed_fields = {}
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key == "config":
                value = json.dumps(value, default=str, ensure_ascii=False)
            if key == "plan" and value not in TENANT_PLANS:
                return {"status": "error", "message": f"Plan invalido: {value}"}
            processed_fields[key] = value

        # Usar quote_identifier para validar tabla y columnas (mitiga B608).
        # No usamos build_update_query porque necesitamos CURRENT_TIMESTAMP
        # (función SQL, no un valor parametrizable).
        if not processed_fields:
            return {"status": "ok", "message": "Sin cambios"}

        set_clauses = []
        params = []
        for key, value in processed_fields.items():
            set_clauses.append(f"{quote_identifier(key)} = ?")
            params.append(value)
        # updated_at con función SQL (no placeholder)
        set_clauses.append(f'{quote_identifier("updated_at")} = CURRENT_TIMESTAMP')
        params.append(tenant_id)

        table_quoted = quote_identifier("tenants")
        sql = f"UPDATE {table_quoted} SET {', '.join(set_clauses)} WHERE id = ?"  # nosec B608 — identificadores validados
        self._db.execute(sql, tuple(params))
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")
        self._redis.delete(f"tenant:slug:{existing.get('slug', '')}")

        self._db.audit("tenant.updated", f"Tenant {tenant_id} actualizado")
        logger.info(f"Tenant: {tenant_id} actualizado")

        return {"status": "ok"}

    def suspend_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Suspende un tenant (no se puede acceder pero se conservan datos).

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        return self._set_tenant_status(tenant_id, "suspended")

    def activate_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Reactiva un tenant suspendido.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        return self._set_tenant_status(tenant_id, "active")

    def delete_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Elimina un tenant y todos sus datos asociados.

        Advertencia: Esta operacion es irreversible. Elimina:
        - Datos del tenant en la BD de administracion
        - Features y settings del tenant
        - Schema o BD del tenant (segun tipo de aislamiento)
        - Cache Redis del tenant

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        # 1. Marcar como deleted (soft delete inicial)
        self._db.execute(
            "UPDATE tenants SET status = 'deleted', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (tenant_id,)
        )
        self._db.commit()

        # 2. Eliminar features y settings
        self._db.execute("DELETE FROM tenant_features WHERE tenant_id = ?", (tenant_id,))
        self._db.execute("DELETE FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))

        # 3. Eliminar almacenamiento de datos del tenant
        db_info = self._db.fetchone(
            "SELECT db_type, connection_string FROM tenant_databases WHERE tenant_id = ?", (tenant_id,)
        )
        if db_info:
            try:
                self._provisioner.deprovision(tenant_id, db_info["db_type"], db_info["connection_string"])
            except Exception as e:
                logger.error(f"Tenant: Error eliminando almacenamiento de tenant {tenant_id}: {e}")

        self._db.execute("DELETE FROM tenant_databases WHERE tenant_id = ?", (tenant_id,))

        # 4. Eliminar registro del tenant
        self._db.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        self._db.commit()

        # 5. Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")
        slug = tenant.get("slug", "")
        if slug:
            self._redis.delete(f"tenant:slug:{slug}")

        # 6. Cerrar conexion del tenant si existe
        self._connection_pool.close(tenant_id)

        self._db.audit("tenant.deleted", f"Tenant '{tenant.get('name', tenant_id)}' eliminado")
        logger.info(f"Tenant: '{tenant.get('name', tenant_id)}' eliminado completamente")

        return {"status": "ok"}

    def list_tenants(self, status: str | None = None) -> list[dict]:
        """Lista todos los tenants, opcionalmente filtrados por estado.

        Args:
            status: Filtrar por estado ('active', 'suspended', 'deleted')

        Returns:
            Lista de dicts con datos de cada tenant
        """
        if status:
            rows = self._db.fetchall(
                "SELECT * FROM tenants WHERE status = ? ORDER BY name",
                (status,),
            )
        else:
            rows = self._db.fetchall("SELECT * FROM tenants ORDER BY name")

        return [self._tenant_row_to_dict(row) for row in rows]

    def _set_tenant_status(self, tenant_id: str, status: str) -> dict[str, Any]:
        """Establece el estado de un tenant."""
        existing = self._db.fetchone("SELECT id, status FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "UPDATE tenants SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, tenant_id),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")

        self._db.audit(f"tenant.{status}", f"Tenant {tenant_id} cambiado a estado '{status}'")
        logger.info(f"Tenant: {tenant_id} cambiado a estado '{status}'")

        return {"status": "ok", "tenant_id": tenant_id, "new_status": status}

    # ── Aislamiento de BD ─────────────────────────────────
    # NOTA: La logica de aprovisionamiento y conexiones se ha movido a:
    #   src/tenant/storage.py — TenantStorageProvisioner, TenantConnectionPool
    #
    # Metodos extraidos:
    #   _provision_tenant_storage → self._provisioner.provision()
    #   _deprovision_tenant_storage → self._provisioner.deprovision()
    #   get_tenant_db → self._connection_pool.get_connection()

    def get_tenant_db(self, tenant_id: str) -> Any | None:
        """Obtiene la conexion a la BD del tenant.

        Delega en TenantConnectionPool para gestion de conexiones.

        Args:
            tenant_id: ID del tenant

        Returns:
            Conexion a BD, o None si el tenant no existe o no esta activo
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant or tenant.get("status") != "active":
            return None

        db_info = self._db.fetchone(
            "SELECT db_type, connection_string FROM tenant_databases WHERE tenant_id = ?",
            (tenant_id,),
        )
        if not db_info:
            return None

        return self._connection_pool.get_connection(
            tenant_id, db_info["db_type"], db_info["connection_string"]
        )

    # NOTA: Metodos de feature flags movidos a src/tenant/features.py
    #   - set_feature() → self._features.set_feature()
    #   - check_feature() → self._features.check_feature()
    #   - _get_tenant_features() → self._features.get_all_features()

    def set_feature(self, tenant_id: str, feature: str, enabled: bool) -> dict[str, Any]:
        """
        Habilita o deshabilita una feature para un tenant.
        Delega en TenantFeatureManager.
        """
        return self._features.set_feature(tenant_id, feature, enabled)

    def check_feature(self, tenant_id: str, feature: str) -> bool:
        """
        Verifica si una feature esta habilitada para un tenant.
        Delega en TenantFeatureManager.
        """
        return self._features.check_feature(tenant_id, feature)

    def get_features(self, tenant_id: str) -> dict[str, bool]:
        """
        Obtiene todas las features de un tenant.
        Delega en TenantFeatureManager.
        """
        return self._features.get_all_features(tenant_id)

    # ── Settings por tenant ───────────────────────────────

    def get_setting(self, tenant_id: str, key: str) -> str | None:
        """Obtiene un setting de un tenant.

        Args:
            tenant_id: ID del tenant
            key: Clave del setting

        Returns:
            Valor del setting, o None si no existe
        """
        row = self._db.fetchone(
            "SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = ?",
            (tenant_id, key),
        )
        return row["value"] if row else None

    def set_setting(self, tenant_id: str, key: str, value: str) -> dict[str, Any]:
        """
        Establece un setting para un tenant.

        Args:
            tenant_id: ID del tenant
            key: Clave del setting
            value: Valor del setting

        Returns:
            dict con status
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "INSERT OR REPLACE INTO tenant_settings (tenant_id, key, value) VALUES (?, ?, ?)",
            (tenant_id, key, value),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")

        return {"status": "ok"}

    def _get_tenant_settings(self, tenant_id: str) -> dict[str, str]:
        """Obtiene todos los settings de un tenant como dict."""
        rows = self._db.fetchall(
            "SELECT key, value FROM tenant_settings WHERE tenant_id = ?",
            (tenant_id,),
        )
        return {row["key"]: row["value"] for row in rows}

    # ── Rate limiting por tenant ──────────────────────────

    def check_rate_limit(self, tenant_id: str, action: str = "api") -> dict[str, Any]:
        """Verifica el rate limit de un tenant para una accion.

        Usa Redis para contar requests en ventana deslizante.

        Args:
            tenant_id: ID del tenant
            action: Tipo de accion (api, execution, etc.)

        Returns:
            dict con allowed, remaining, reset_at
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "remaining": 0, "reset_at": 0, "reason": "Tenant no encontrado"}

        config = tenant.get("config", {})
        max_per_day = config.get("max_executions_per_day", 100)
        if max_per_day == -1:  # Sin limite
            return {"allowed": True, "remaining": -1, "reset_at": 0}

        return self._redis.check_rate_limit(
            f"tenant:{tenant_id}:{action}",
            max_requests=max_per_day,
            window_seconds=86400,  # 24 horas
        )

    # ── Helpers ───────────────────────────────────────────

    def _tenant_row_to_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convierte una fila de la tabla tenants a dict con config parseado."""
        result = dict(row)
        if "config" in result and isinstance(result["config"], str):
            try:
                result["config"] = json.loads(result["config"])
            except (json.JSONDecodeError, TypeError):
                result["config"] = {}
        return result

    def _cache_tenant(self, tenant_id: str, data: dict[str, Any]) -> None:
        """Almacena datos del tenant en cache Redis."""
        self._redis.set_json(f"tenant:{tenant_id}", data, ttl=_TENANT_CACHE_TTL)

    def invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Invalida la cache Redis de un tenant."""
        self._redis.delete(f"tenant:{tenant_id}")
        tenant = self._db.fetchone("SELECT slug FROM tenants WHERE id = ?", (tenant_id,))
        if tenant and tenant.get("slug"):
            self._redis.delete(f"tenant:slug:{tenant['slug']}")

    def close_all_tenant_connections(self) -> None:
        """Cierra todas las conexiones de BD de tenants.

        Delega en TenantConnectionPool.
        """
        self._connection_pool.close_all()

    # ── Reset para tests (fix Sprint 5 BUG-ARCH-01) ─────────

    @classmethod
    def _reset(cls) -> None:
        """Resetea el singleton (para tests).

        Fix Sprint 5 BUG-ARCH-01: expuesto para permitir test isolation.
        """
        with cls._lock:
            if cls._instance is not None:
                with contextlib.suppress(Exception):
                    cls._instance.close_all_tenant_connections()
                cls._instance = None
        logger.info("Tenant: Todas las conexiones de tenant cerradas")
