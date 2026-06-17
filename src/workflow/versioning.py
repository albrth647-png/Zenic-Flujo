"""
Sprint 9 — Versioning + Multi-entorno + Promoción
==================================================

Tres servicios coordinados:

1. WorkflowVersionRepository
   - Snapshot inmutable de cada UPDATE de un workflow.
   - Retención configurable (default: 20 versiones por workflow).
   - Rollback a versión anterior sin perder la versión actual.

2. EnvironmentService
   - Resolución y validación de entornos (dev, staging, prod).
   - Mantiene la tabla workflow_environments sincronizada.
   - Un workflow puede existir en 0, 1, 2 o los 3 entornos.

3. PromotionService
   - Promueve un workflow de un entorno a otro (dev → staging → prod).
   - Calcula diff antes/después de promover.
   - Registra auditoría en workflow_promotions.
   - Respeta el orden lineal dev → staging → prod (no se puede saltar).

Diseño:
- Las versiones son inmutables (solo se crean y se leen, nunca se editan).
- El rollback crea una nueva versión (no destruye el histórico).
- La promoción copia el snapshot del entorno origen al destino.
- Toda operación es auditable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.data.database_manager import DatabaseManager
from src.utils.helpers import now_iso
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────

ENVIRONMENTS = ("dev", "staging", "prod")
"""Tupla ordenada de entornos válidos. El orden define el flujo de promoción."""

DEFAULT_RETENTION = 20
"""Número máximo de versiones retenidas por workflow. Las más antiguas se eliminan."""

PROMOTION_FLOW = {"dev": "staging", "staging": "prod"}
"""
Mapeo origen → destino permitido en promociones.
- dev → staging ✅
- staging → prod ✅
- dev → prod ❌ (debe pasar por staging primero)
- prod → * ❌ (no se puede promover desde prod)
"""


class VersioningError(Exception):
    """Error base del módulo de versioning."""


class VersionNotFoundError(VersioningError):
    """La versión solicitada no existe."""


class EnvironmentNotFoundError(VersioningError):
    """El entorno solicitado no existe para ese workflow."""


class InvalidPromotionError(VersioningError):
    """La promoción solicitada viola el flujo dev → staging → prod."""


# ─── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class WorkflowVersion:
    """Snapshot inmutable de un workflow en un momento dado."""

    id: int | None = None
    workflow_id: int = 0
    version_number: int = 0
    name: str = ""
    description: str = ""
    trigger_type: str = ""
    trigger_config: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    change_summary: str = ""
    created_by: int = 1
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "version_number": self.version_number,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "steps": self.steps,
            "change_summary": self.change_summary,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> WorkflowVersion:
        """Construye una WorkflowVersion desde una fila de DB."""
        return cls(
            id=row["id"],
            workflow_id=row["workflow_id"],
            version_number=row["version_number"],
            name=row["name"],
            description=row.get("description") or "",
            trigger_type=row["trigger_type"],
            trigger_config=_safe_json_loads(row.get("trigger_config", "{}")),
            steps=_safe_json_loads(row.get("steps", "[]")),
            change_summary=row.get("change_summary") or "",
            created_by=row.get("created_by") or 1,
            created_at=row.get("created_at") or "",
        )


@dataclass
class WorkflowEnvironment:
    """Asociación de un workflow con un entorno."""

    id: int | None = None
    workflow_id: int = 0
    environment: str = "dev"
    promoted_from: str | None = None
    promoted_at: str | None = None
    promoted_by: int = 1
    is_current: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "environment": self.environment,
            "promoted_from": self.promoted_from,
            "promoted_at": self.promoted_at,
            "promoted_by": self.promoted_by,
            "is_current": self.is_current,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> WorkflowEnvironment:
        return cls(
            id=row["id"],
            workflow_id=row["workflow_id"],
            environment=row["environment"],
            promoted_from=row.get("promoted_from"),
            promoted_at=row.get("promoted_at"),
            promoted_by=row.get("promoted_by") or 1,
            is_current=bool(row.get("is_current")),
            notes=row.get("notes") or "",
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
        )


@dataclass
class WorkflowPromotion:
    """Registro de auditoría de una promoción entre entornos."""

    id: int | None = None
    workflow_id: int = 0
    source_env: str = ""
    target_env: str = ""
    source_version: int | None = None
    target_version: int | None = None
    diff_summary: str = ""
    status: str = "completed"
    promoted_by: int = 1
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "source_env": self.source_env,
            "target_env": self.target_env,
            "source_version": self.source_version,
            "target_version": self.target_version,
            "diff_summary": self.diff_summary,
            "status": self.status,
            "promoted_by": self.promoted_by,
            "created_at": self.created_at,
        }


# ─── 1. WorkflowVersionRepository ────────────────────────────────────────


class WorkflowVersionRepository:
    """CRUD de versiones de workflows. Las versiones son inmutables."""

    def __init__(self, db: DatabaseManager | None = None, retention: int = DEFAULT_RETENTION):
        self._db = db or DatabaseManager()
        self.retention = max(1, retention)

    def create_version(
        self,
        workflow_id: int,
        name: str,
        description: str,
        trigger_type: str,
        trigger_config: dict,
        steps: list,
        change_summary: str = "",
        created_by: int = 1,
    ) -> WorkflowVersion:
        """
        Crea una nueva versión del workflow. Asigna automáticamente el siguiente
        version_number secuencial. Aplica política de retención (elimina las
        versiones más antiguas que excedan el límite).
        """
        # Calcular siguiente version_number
        row = self._db.fetchone(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version "
            "FROM workflow_versions WHERE workflow_id = ?",
            (workflow_id,),
        )
        next_version = row["next_version"] if row else 1

        cursor = self._db.execute(
            """INSERT INTO workflow_versions
               (workflow_id, version_number, name, description, trigger_type,
                trigger_config, steps, change_summary, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id,
                next_version,
                name,
                description,
                trigger_type,
                json.dumps(trigger_config),
                json.dumps(steps),
                change_summary,
                created_by,
            ),
        )
        self._db.commit()
        version_id = cursor.lastrowid

        # Aplicar retención: si hay más de `retention` versiones, borrar las más antiguas
        self._apply_retention(workflow_id)

        logger.info(
            f"Versión {next_version} creada para workflow {workflow_id} (ID: {version_id})"
        )

        return self.get_version(workflow_id, next_version)  # type: ignore[return-value]

    def get_version(self, workflow_id: int, version_number: int) -> WorkflowVersion | None:
        """Obtiene una versión específica por número."""
        row = self._db.fetchone(
            "SELECT * FROM workflow_versions WHERE workflow_id = ? AND version_number = ?",
            (workflow_id, version_number),
        )
        return WorkflowVersion.from_row(row) if row else None

    def list_versions(
        self, workflow_id: int, limit: int = 50, offset: int = 0
    ) -> list[WorkflowVersion]:
        """Lista las versiones de un workflow, las más recientes primero."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_versions
               WHERE workflow_id = ?
               ORDER BY version_number DESC
               LIMIT ? OFFSET ?""",
            (workflow_id, limit, offset),
        )
        return [WorkflowVersion.from_row(r) for r in rows]

    def get_latest_version(self, workflow_id: int) -> WorkflowVersion | None:
        """Obtiene la versión más reciente del workflow."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_versions
               WHERE workflow_id = ?
               ORDER BY version_number DESC
               LIMIT 1""",
            (workflow_id,),
        )
        return WorkflowVersion.from_row(rows[0]) if rows else None

    def count_versions(self, workflow_id: int) -> int:
        """Cuenta el número total de versiones de un workflow."""
        row = self._db.fetchone(
            "SELECT COUNT(*) AS c FROM workflow_versions WHERE workflow_id = ?",
            (workflow_id,),
        )
        return row["c"] if row else 0

    def delete_version(self, workflow_id: int, version_number: int) -> bool:
        """
        Elimina una versión específica. No se puede eliminar la única versión.
        Retorna False si la versión no existe (sin lanzar error).
        Lanza VersioningError si se intenta eliminar la única versión restante.
        """
        # Primero verificar si la versión existe (sin contar todas)
        target = self.get_version(workflow_id, version_number)
        if target is None:
            return False

        # Verificar que no sea la única versión
        count = self.count_versions(workflow_id)
        if count <= 1:
            raise VersioningError(
                f"No se puede eliminar la única versión del workflow {workflow_id}"
            )

        cursor = self._db.execute(
            "DELETE FROM workflow_versions WHERE workflow_id = ? AND version_number = ?",
            (workflow_id, version_number),
        )
        self._db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Versión {version_number} eliminada del workflow {workflow_id}")
        return deleted

    def _apply_retention(self, workflow_id: int) -> int:
        """Elimina las versiones que excedan la política de retención."""
        count = self.count_versions(workflow_id)
        if count <= self.retention:
            return 0

        # Borrar las (count - retention) versiones más antiguas
        to_delete = count - self.retention
        cursor = self._db.execute(
            """DELETE FROM workflow_versions
               WHERE rowid IN (
                   SELECT rowid FROM workflow_versions
                   WHERE workflow_id = ?
                   ORDER BY version_number ASC
                   LIMIT ?
               )""",
            (workflow_id, to_delete),
        )
        self._db.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info(
                f"Retención aplicada en workflow {workflow_id}: {deleted} versiones antiguas eliminadas"
            )
        return deleted


# ─── 2. EnvironmentService ───────────────────────────────────────────────


class EnvironmentService:
    """
    Gestiona la asociación de workflows con entornos (dev/staging/prod).
    Un workflow puede estar en 0, 1, 2 o los 3 entornos simultáneamente.
    """

    def __init__(self, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager()

    @staticmethod
    def validate_environment(env: str) -> str:
        """Valida que el entorno sea uno de los permitidos. Lanza ValueError si no."""
        if env not in ENVIRONMENTS:
            raise ValueError(
                f"Entorno inválido: {env!r}. Debe ser uno de {ENVIRONMENTS}"
            )
        return env

    def assign_to_environment(
        self,
        workflow_id: int,
        environment: str,
        promoted_from: str | None = None,
        promoted_by: int = 1,
        notes: str = "",
    ) -> WorkflowEnvironment:
        """
        Asigna (o reasigna) un workflow a un entorno.
        Si ya existe la asociación, actualiza promoted_from/at/by.
        Si no existe, la crea.
        """
        self.validate_environment(environment)

        existing = self.get_environment(workflow_id, environment)
        now = now_iso()

        if existing:
            # Reasignación: actualizar metadatos de promoción
            self._db.execute(
                """UPDATE workflow_environments
                   SET promoted_from = ?, promoted_at = ?, promoted_by = ?,
                       notes = ?, updated_at = ?, is_current = 1
                   WHERE id = ?""",
                (promoted_from, now, promoted_by, notes, now, existing.id),
            )
            self._db.commit()
            return self.get_environment(workflow_id, environment)  # type: ignore[return-value]
        else:
            # Creación nueva
            cursor = self._db.execute(
                """INSERT INTO workflow_environments
                   (workflow_id, environment, promoted_from, promoted_at,
                    promoted_by, is_current, notes)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (workflow_id, environment, promoted_from, now, promoted_by, notes),
            )
            self._db.commit()
            env_id = cursor.lastrowid
            logger.info(
                f"Workflow {workflow_id} asignado a entorno '{environment}' (ID: {env_id})"
            )
            return self.get_environment(workflow_id, environment)  # type: ignore[return-value]

    def get_environment(
        self, workflow_id: int, environment: str
    ) -> WorkflowEnvironment | None:
        """Obtiene la asociación de un workflow con un entorno, o None si no existe."""
        self.validate_environment(environment)
        row = self._db.fetchone(
            "SELECT * FROM workflow_environments WHERE workflow_id = ? AND environment = ?",
            (workflow_id, environment),
        )
        return WorkflowEnvironment.from_row(row) if row else None

    def list_environments(self, workflow_id: int) -> list[WorkflowEnvironment]:
        """Lista todos los entornos donde está presente el workflow."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_environments
               WHERE workflow_id = ?
               ORDER BY CASE environment
                   WHEN 'dev' THEN 1
                   WHEN 'staging' THEN 2
                   WHEN 'prod' THEN 3
                   ELSE 4
               END""",
            (workflow_id,),
        )
        return [WorkflowEnvironment.from_row(r) for r in rows]

    def remove_from_environment(self, workflow_id: int, environment: str) -> bool:
        """Elimina la asociación de un workflow con un entorno."""
        self.validate_environment(environment)
        cursor = self._db.execute(
            "DELETE FROM workflow_environments WHERE workflow_id = ? AND environment = ?",
            (workflow_id, environment),
        )
        self._db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(
                f"Workflow {workflow_id} eliminado del entorno '{environment}'"
            )
        return deleted

    def is_in_environment(self, workflow_id: int, environment: str) -> bool:
        """True si el workflow está asignado al entorno dado."""
        return self.get_environment(workflow_id, environment) is not None


# ─── 3. PromotionService ─────────────────────────────────────────────────


class PromotionService:
    """
    Orquesta promociones entre entornos.
    Respeta el flujo lineal dev → staging → prod.
    Calcula diff antes de promover y registra auditoría.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        version_repo: WorkflowVersionRepository | None = None,
        env_service: EnvironmentService | None = None,
    ):
        self._db = db or DatabaseManager()
        self._versions = version_repo or WorkflowVersionRepository(self._db)
        self._envs = env_service or EnvironmentService(self._db)

    @staticmethod
    def _validate_promotion_flow(source: str, target: str) -> None:
        """Valida que la promoción source → target respete el flujo."""
        if source not in ENVIRONMENTS:
            raise InvalidPromotionError(f"Entorno origen inválido: {source!r}")
        if target not in ENVIRONMENTS:
            raise InvalidPromotionError(f"Entorno destino inválido: {target!r}")
        if source == target:
            raise InvalidPromotionError(
                f"Origen y destino son el mismo entorno: {source!r}"
            )
        if source not in PROMOTION_FLOW:
            raise InvalidPromotionError(
                f"No se puede promover desde el entorno '{source}'. "
                f"El flujo permitido es dev → staging → prod."
            )
        expected_target = PROMOTION_FLOW[source]
        if target != expected_target:
            raise InvalidPromotionError(
                f"Promoción no permitida: {source} → {target}. "
                f"Desde '{source}' solo se puede promover a '{expected_target}'."
            )

    @staticmethod
    def _compute_diff(
        source_workflow: dict, target_workflow: dict | None
    ) -> dict[str, Any]:
        """
        Calcula un diff simple entre dos definiciones de workflow.
        Retorna un dict con los campos cambiados y un resumen legible.
        """
        if target_workflow is None:
            # Promoción inicial: no hay versión previa en el entorno destino
            return {
                "is_initial": True,
                "summary": f"Promoción inicial al entorno. Workflow: {source_workflow.get('name', '')}",
                "changes": ["workflow_created"],
            }

        changes: list[str] = []
        for field_name in ("name", "description", "trigger_type"):
            old_val = target_workflow.get(field_name)
            new_val = source_workflow.get(field_name)
            if old_val != new_val:
                changes.append(f"{field_name}: {old_val!r} → {new_val!r}")

        # Comparar trigger_config y steps serializados
        old_tc = json.dumps(target_workflow.get("trigger_config", {}), sort_keys=True)
        new_tc = json.dumps(source_workflow.get("trigger_config", {}), sort_keys=True)
        if old_tc != new_tc:
            changes.append("trigger_config modificado")

        old_steps = json.dumps(target_workflow.get("steps", []), sort_keys=True)
        new_steps = json.dumps(source_workflow.get("steps", []), sort_keys=True)
        if old_steps != new_steps:
            old_count = len(target_workflow.get("steps", []))
            new_count = len(source_workflow.get("steps", []))
            changes.append(
                f"steps modificados ({old_count} → {new_count} pasos)"
            )

        return {
            "is_initial": False,
            "summary": "; ".join(changes) if changes else "Sin cambios detectados",
            "changes": changes,
        }

    def promote(
        self,
        workflow_id: int,
        source_env: str,
        target_env: str,
        workflow_definition: dict,
        source_version: int | None = None,
        promoted_by: int = 1,
        notes: str = "",
    ) -> WorkflowPromotion:
        """
        Promueve un workflow de source_env a target_env.

        Pasos:
        1. Validar flujo (dev → staging → prod, no se puede saltar).
        2. Verificar que el workflow está en source_env.
        3. Calcular diff vs versión actual en target_env (si existe).
        4. Crear nueva versión del workflow (snapshot).
        5. Asignar (o reasignar) workflow a target_env.
        6. Registrar auditoría en workflow_promotions.
        """
        # 1. Validar flujo
        self._validate_promotion_flow(source_env, target_env)

        # 2. Verificar que está en source_env
        if not self._envs.is_in_environment(workflow_id, source_env):
            raise EnvironmentNotFoundError(
                f"El workflow {workflow_id} no está asignado al entorno '{source_env}'. "
                f"No se puede promover desde un entorno donde no existe."
            )

        # 3. Calcular diff vs target_env actual (si existe)
        # Para el diff, comparamos el workflow_definition entrante con la última
        # versión registrada del workflow (que es la que se quiere reemplazar).
        latest_version = self._versions.get_latest_version(workflow_id)
        target_workflow_for_diff: dict | None = None
        if latest_version:
            target_workflow_for_diff = {
                "name": latest_version.name,
                "description": latest_version.description,
                "trigger_type": latest_version.trigger_type,
                "trigger_config": latest_version.trigger_config,
                "steps": latest_version.steps,
            }

        diff = self._compute_diff(workflow_definition, target_workflow_for_diff)

        # 4. Crear nueva versión
        new_version = self._versions.create_version(
            workflow_id=workflow_id,
            name=workflow_definition.get("name", ""),
            description=workflow_definition.get("description", ""),
            trigger_type=workflow_definition.get("trigger_type", ""),
            trigger_config=workflow_definition.get("trigger_config", {}),
            steps=workflow_definition.get("steps", []),
            change_summary=diff["summary"],
            created_by=promoted_by,
        )

        # 5. Asignar (o reasignar) al entorno destino
        self._envs.assign_to_environment(
            workflow_id=workflow_id,
            environment=target_env,
            promoted_from=source_env,
            promoted_by=promoted_by,
            notes=notes,
        )

        # 6. Registrar auditoría
        cursor = self._db.execute(
            """INSERT INTO workflow_promotions
               (workflow_id, source_env, target_env, source_version,
                target_version, diff_summary, status, promoted_by)
               VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)""",
            (
                workflow_id,
                source_env,
                target_env,
                source_version,
                new_version.version_number,
                diff["summary"],
                promoted_by,
            ),
        )
        self._db.commit()
        promotion_id = cursor.lastrowid

        logger.info(
            f"Workflow {workflow_id} promovido: {source_env} → {target_env} "
            f"(versión {new_version.version_number}, promoción ID: {promotion_id})"
        )

        return WorkflowPromotion(
            id=promotion_id,
            workflow_id=workflow_id,
            source_env=source_env,
            target_env=target_env,
            source_version=source_version,
            target_version=new_version.version_number,
            diff_summary=diff["summary"],
            status="completed",
            promoted_by=promoted_by,
            created_at=now_iso(),
        )

    def list_promotions(
        self, workflow_id: int, limit: int = 50
    ) -> list[WorkflowPromotion]:
        """Lista el histórico de promociones de un workflow."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_promotions
               WHERE workflow_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (workflow_id, limit),
        )
        return [
            WorkflowPromotion(
                id=r["id"],
                workflow_id=r["workflow_id"],
                source_env=r["source_env"],
                target_env=r["target_env"],
                source_version=r.get("source_version"),
                target_version=r.get("target_version"),
                diff_summary=r.get("diff_summary") or "",
                status=r["status"],
                promoted_by=r.get("promoted_by") or 1,
                created_at=r.get("created_at") or "",
            )
            for r in rows
        ]

    def get_promotion_history_summary(self, workflow_id: int) -> dict[str, Any]:
        """Resumen agregado de promociones para dashboard."""
        rows = self._db.fetchall(
            """SELECT target_env, COUNT(*) AS count, MAX(created_at) AS last_at
               FROM workflow_promotions
               WHERE workflow_id = ?
               GROUP BY target_env""",
            (workflow_id,),
        )
        return {
            r["target_env"]: {"count": r["count"], "last_at": r["last_at"]}
            for r in rows
        }


# ─── Helpers ─────────────────────────────────────────────────────────────


def _safe_json_loads(value: Any) -> Any:
    """Parsea JSON de forma segura. Si falla, retorna el valor original."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value
