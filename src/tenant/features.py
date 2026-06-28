"""
Zenic-Flujo — Tenant Feature Flags
====================================

Gestion de feature flags por tenant.
Permite habilitar/deshabilitar funcionalidades especificas por tenant.
"""

from __future__ import annotations

from typing import Any

from src.core.db import DatabaseManager, RedisService
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TenantFeatureManager:
    """
    Gestion de feature flags por tenant.

    Los tenants con plan Enterprise tienen feature 'all' que
    automaticamente concede acceso a cualquier feature.
    """

    def __init__(self) -> None:
        self._db = DatabaseManager()
        self._redis = RedisService()

    def set_feature(self, tenant_id: str, feature: str, enabled: bool) -> dict[str, Any]:
        """
        Habilita o deshabilita una feature para un tenant.

        Args:
            tenant_id: ID del tenant
            feature: Nombre de la feature
            enabled: True para habilitar, False para deshabilitar

        Returns:
            dict con status, feature y enabled
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "INSERT OR REPLACE INTO tenant_features (tenant_id, feature_name, enabled) VALUES (?, ?, ?)",
            (tenant_id, feature, 1 if enabled else 0),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")
        self._redis.delete(f"tenant:features:{tenant_id}")

        logger.info(f"Tenant: Feature '{feature}' {'habilitada' if enabled else 'deshabilitada'} para {tenant_id}")
        return {"status": "ok", "feature": feature, "enabled": enabled}

    def check_feature(self, tenant_id: str, feature: str) -> bool:
        """
        Verifica si una feature esta habilitada para un tenant.

        Args:
            tenant_id: ID del tenant
            feature: Nombre de la feature

        Returns:
            True si la feature esta habilitada
        """
        # Verificar cache primero
        cached = self._redis.get_json(f"tenant:features:{tenant_id}")
        if cached and feature in cached:
            return cached[feature]

        # Verificar si tiene 'all' (enterprise)
        all_row = self._db.fetchone(
            "SELECT enabled FROM tenant_features WHERE tenant_id = ? AND feature_name = 'all'",
            (tenant_id,),
        )
        if all_row and all_row["enabled"]:
            return True

        # Verificar feature especifica
        row = self._db.fetchone(
            "SELECT enabled FROM tenant_features WHERE tenant_id = ? AND feature_name = ?",
            (tenant_id, feature),
        )
        result = bool(row and row["enabled"])

        # Actualizar cache
        features_cache = cached or {}
        features_cache[feature] = result
        self._redis.set_json(f"tenant:features:{tenant_id}", features_cache, ttl=3600)

        return result

    def get_all_features(self, tenant_id: str) -> dict[str, bool]:
        """
        Obtiene todas las features de un tenant.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con nombre de feature -> bool
        """
        rows = self._db.fetchall(
            "SELECT feature_name, enabled FROM tenant_features WHERE tenant_id = ?",
            (tenant_id,),
        )
        return {row["feature_name"]: bool(row["enabled"]) for row in rows}

    def get_features_for_plan(self, plan: str) -> list[str]:
        """
        Obtiene las features incluidas en un plan.

        Args:
            plan: Nombre del plan

        Returns:
            Lista de nombres de features
        """
        from src.tenant.storage import TENANT_PLANS

        plan_config = TENANT_PLANS.get(plan, {})
        return list(plan_config.get("features", []))
