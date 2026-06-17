"""
Tests del módulo EnvironmentService + PromotionService (Sprint 9 — Multi-entorno).

Cubre:
- EnvironmentService: asignación, validación, listado, eliminación de entornos.
- PromotionService: flujo dev→staging→prod, promociones inválidas bloqueadas.
- PromotionService: diff calculation, auditoría, histórico de promociones.
- Integración con WorkflowVersionRepository (cada promoción crea nueva versión).
"""
from __future__ import annotations

import pytest

from src.workflow.versioning import (
    ENVIRONMENTS,
    PROMOTION_FLOW,
    EnvironmentNotFoundError,
    EnvironmentService,
    InvalidPromotionError,
    PromotionService,
    WorkflowVersionRepository,
)


@pytest.fixture
def env_service(db_manager) -> EnvironmentService:
    return EnvironmentService(db=db_manager)


@pytest.fixture
def version_repo(db_manager) -> WorkflowVersionRepository:
    return WorkflowVersionRepository(db=db_manager, retention=50)


@pytest.fixture
def promotion_service(db_manager, version_repo, env_service) -> PromotionService:
    return PromotionService(
        db=db_manager,
        version_repo=version_repo,
        env_service=env_service,
    )


@pytest.fixture
def sample_workflow(db_manager) -> int:
    """Crea un workflow de prueba y retorna su ID."""
    from src.workflow.repository import WorkflowDefinition, WorkflowRepository

    repo = WorkflowRepository()
    repo._db = db_manager
    wf = repo.create(
        WorkflowDefinition(
            name="Test Env Workflow",
            description="Workflow para tests de entornos",
            trigger_type="event",
            trigger_config={"event": "test.event"},
            steps=[],
        ),
        user_id=1,
    )
    return wf.id  # type: ignore[return-value]


@pytest.fixture
def sample_workflow_definition() -> dict:
    """Definición de workflow para usar en promociones."""
    return {
        "name": "Test Workflow",
        "description": "Test description",
        "trigger_type": "event",
        "trigger_config": {"event": "test.event"},
        "steps": [
            {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "John"}},
        ],
    }


# ─── EnvironmentService Tests ────────────────────────────────────────────


class TestEnvironmentValidation:
    """Tests de validación de entornos."""

    def test_validate_environment_accepts_dev(self, env_service):
        assert env_service.validate_environment("dev") == "dev"

    def test_validate_environment_accepts_staging(self, env_service):
        assert env_service.validate_environment("staging") == "staging"

    def test_validate_environment_accepts_prod(self, env_service):
        assert env_service.validate_environment("prod") == "prod"

    @pytest.mark.parametrize("invalid_env", ["", "production", "DEV", "qa", "test", "develop"])
    def test_validate_environment_rejects_invalid(self, env_service, invalid_env):
        with pytest.raises(ValueError, match="Entorno inválido"):
            env_service.validate_environment(invalid_env)

    def test_environments_constant_is_ordered_tuple(self):
        assert ENVIRONMENTS == ("dev", "staging", "prod")
        assert len(ENVIRONMENTS) == 3

    def test_promotion_flow_constant(self):
        # Solo se puede promover dev→staging y staging→prod
        assert PROMOTION_FLOW == {"dev": "staging", "staging": "prod"}


class TestEnvironmentAssignment:
    """Tests de asignación de workflows a entornos."""

    def test_assign_to_dev_creates_record(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        env = env_service.assign_to_environment(
            workflow_id=sample_workflow,
            environment="dev",
            notes="Initial assignment",
        )
        assert env.id is not None
        assert env.workflow_id == sample_workflow
        assert env.environment == "dev"
        assert env.is_current is True
        assert env.notes == "Initial assignment"
        assert env.promoted_from is None  # primera asignación no viene de otro env

    def test_assign_to_same_environment_updates_metadata(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        # Primera asignación
        env_service.assign_to_environment(sample_workflow, "dev", notes="v1")
        # Reasignación (simula promoción sobre el mismo env)
        env = env_service.assign_to_environment(
            sample_workflow, "dev",
            promoted_from="staging",
            promoted_by=2,
            notes="v2",
        )
        # Debe ser la misma fila, con metadata actualizada
        assert env.promoted_from == "staging"
        assert env.promoted_by == 2
        assert env.notes == "v2"

    def test_assign_to_all_three_environments(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        for env_name in ENVIRONMENTS:
            env_service.assign_to_environment(sample_workflow, env_name)

        envs = env_service.list_environments(sample_workflow)
        assert len(envs) == 3
        env_names = {e.environment for e in envs}
        assert env_names == {"dev", "staging", "prod"}

    def test_list_environments_returns_ordered(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        # Asignar en orden inverso para verificar ordenamiento
        env_service.assign_to_environment(sample_workflow, "prod")
        env_service.assign_to_environment(sample_workflow, "staging")
        env_service.assign_to_environment(sample_workflow, "dev")

        envs = env_service.list_environments(sample_workflow)
        env_order = [e.environment for e in envs]
        # Deben estar en orden dev → staging → prod
        assert env_order == ["dev", "staging", "prod"]

    def test_list_environments_empty_for_unassigned_workflow(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        envs = env_service.list_environments(sample_workflow)
        assert envs == []

    def test_get_environment_returns_none_if_not_assigned(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        assert env_service.get_environment(sample_workflow, "dev") is None

    def test_get_environment_returns_record_if_assigned(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        env_service.assign_to_environment(sample_workflow, "dev")
        env = env_service.get_environment(sample_workflow, "dev")
        assert env is not None
        assert env.environment == "dev"

    def test_is_in_environment(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        assert env_service.is_in_environment(sample_workflow, "dev") is False
        env_service.assign_to_environment(sample_workflow, "dev")
        assert env_service.is_in_environment(sample_workflow, "dev") is True
        assert env_service.is_in_environment(sample_workflow, "prod") is False

    def test_remove_from_environment(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        env_service.assign_to_environment(sample_workflow, "dev")
        assert env_service.remove_from_environment(sample_workflow, "dev") is True
        assert env_service.is_in_environment(sample_workflow, "dev") is False

    def test_remove_from_nonexistent_environment_returns_false(
        self, env_service: EnvironmentService, sample_workflow: int
    ):
        assert env_service.remove_from_environment(sample_workflow, "dev") is False


# ─── PromotionService Tests ──────────────────────────────────────────────


class TestPromotionValidation:
    """Tests de validación del flujo de promoción."""

    def test_validate_promotion_flow_dev_to_staging(self, promotion_service):
        # No debe lanzar error
        promotion_service._validate_promotion_flow("dev", "staging")

    def test_validate_promotion_flow_staging_to_prod(self, promotion_service):
        promotion_service._validate_promotion_flow("staging", "prod")

    def test_validate_promotion_flow_dev_to_prod_blocked(self, promotion_service):
        with pytest.raises(InvalidPromotionError, match="dev → prod"):
            promotion_service._validate_promotion_flow("dev", "prod")

    def test_validate_promotion_flow_prod_to_dev_blocked(self, promotion_service):
        with pytest.raises(InvalidPromotionError, match="No se puede promover desde"):
            promotion_service._validate_promotion_flow("prod", "dev")

    def test_validate_promotion_flow_same_environment_blocked(self, promotion_service):
        with pytest.raises(InvalidPromotionError, match="mismo entorno"):
            promotion_service._validate_promotion_flow("dev", "dev")

    def test_validate_promotion_flow_staging_to_dev_blocked(self, promotion_service):
        with pytest.raises(InvalidPromotionError, match="solo se puede promover a 'prod'"):
            promotion_service._validate_promotion_flow("staging", "dev")

    @pytest.mark.parametrize("invalid_env", ["qa", "test", "production", ""])
    def test_validate_promotion_flow_invalid_env(
        self, promotion_service, invalid_env
    ):
        with pytest.raises(InvalidPromotionError):
            promotion_service._validate_promotion_flow(invalid_env, "staging")


class TestPromotionExecution:
    """Tests de ejecución de promociones."""

    def test_promote_dev_to_staging_creates_version_and_env(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        version_repo: WorkflowVersionRepository,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        # Pre-requisito: workflow debe estar en dev
        env_service.assign_to_environment(sample_workflow, "dev")
        # Crear versión inicial (para que el diff no sea "initial")
        version_repo.create_version(
            workflow_id=sample_workflow,
            name=sample_workflow_definition["name"],
            description=sample_workflow_definition["description"],
            trigger_type=sample_workflow_definition["trigger_type"],
            trigger_config=sample_workflow_definition["trigger_config"],
            steps=sample_workflow_definition["steps"],
            change_summary="Initial",
        )

        promotion = promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="dev",
            target_env="staging",
            workflow_definition=sample_workflow_definition,
        )

        # Verificar promotion record
        assert promotion.id is not None
        assert promotion.source_env == "dev"
        assert promotion.target_env == "staging"
        assert promotion.target_version is not None
        assert promotion.status == "completed"

        # Verificar que se creó nueva versión
        versions = version_repo.list_versions(sample_workflow)
        assert len(versions) >= 2  # la inicial + la nueva

        # Verificar que el workflow quedó asignado a staging
        assert env_service.is_in_environment(sample_workflow, "staging") is True

    def test_promote_without_source_env_raises_not_found(
        self,
        promotion_service: PromotionService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        # No asignar el workflow a ningún entorno primero
        with pytest.raises(EnvironmentNotFoundError, match="no está asignado al entorno"):
            promotion_service.promote(
                workflow_id=sample_workflow,
                source_env="dev",
                target_env="staging",
                workflow_definition=sample_workflow_definition,
            )

    def test_promote_dev_to_prod_blocked(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        env_service.assign_to_environment(sample_workflow, "dev")

        with pytest.raises(InvalidPromotionError, match="dev → prod"):
            promotion_service.promote(
                workflow_id=sample_workflow,
                source_env="dev",
                target_env="prod",
                workflow_definition=sample_workflow_definition,
            )

    def test_full_flow_dev_to_staging_to_prod(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        # 1. Asignar a dev
        env_service.assign_to_environment(sample_workflow, "dev")

        # 2. Promover dev → staging
        promotion1 = promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="dev",
            target_env="staging",
            workflow_definition=sample_workflow_definition,
        )
        assert promotion1.target_env == "staging"

        # 3. Promover staging → prod
        promotion2 = promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="staging",
            target_env="prod",
            workflow_definition=sample_workflow_definition,
        )
        assert promotion2.target_env == "prod"

        # 4. Verificar que está en los 3 entornos
        envs = env_service.list_environments(sample_workflow)
        env_names = {e.environment for e in envs}
        assert env_names == {"dev", "staging", "prod"}


class TestPromotionDiff:
    """Tests del cálculo de diff entre versiones."""

    def test_diff_initial_promotion_has_no_changes(
        self, promotion_service: PromotionService
    ):
        source = {"name": "Test", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": []}
        diff = promotion_service._compute_diff(source, None)
        assert diff["is_initial"] is True
        assert "Promoción inicial" in diff["summary"]

    def test_diff_detects_name_change(self, promotion_service: PromotionService):
        source = {"name": "New Name", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": []}
        target = {"name": "Old Name", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": []}
        diff = promotion_service._compute_diff(source, target)
        assert diff["is_initial"] is False
        assert any("name" in c for c in diff["changes"])

    def test_diff_detects_steps_change(self, promotion_service: PromotionService):
        source = {"name": "x", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": [{"id": 1}, {"id": 2}]}
        target = {"name": "x", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": [{"id": 1}]}
        diff = promotion_service._compute_diff(source, target)
        assert any("steps modificados" in c for c in diff["changes"])

    def test_diff_no_changes(self, promotion_service: PromotionService):
        source = {"name": "x", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": []}
        target = {"name": "x", "description": "", "trigger_type": "event",
                  "trigger_config": {}, "steps": []}
        diff = promotion_service._compute_diff(source, target)
        assert diff["summary"] == "Sin cambios detectados"
        assert diff["changes"] == []


class TestPromotionHistory:
    """Tests del histórico de promociones."""

    def test_list_promotions_empty_initially(
        self,
        promotion_service: PromotionService,
        sample_workflow: int,
    ):
        promos = promotion_service.list_promotions(sample_workflow)
        assert promos == []

    def test_list_promotions_after_promotion(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        env_service.assign_to_environment(sample_workflow, "dev")
        promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="dev",
            target_env="staging",
            workflow_definition=sample_workflow_definition,
        )

        promos = promotion_service.list_promotions(sample_workflow)
        assert len(promos) == 1
        assert promos[0].source_env == "dev"
        assert promos[0].target_env == "staging"

    def test_list_promotions_ordered_by_created_at_desc(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        env_service.assign_to_environment(sample_workflow, "dev")

        # Promoción 1: dev → staging
        promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="dev",
            target_env="staging",
            workflow_definition=sample_workflow_definition,
        )
        # Promoción 2: staging → prod
        promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="staging",
            target_env="prod",
            workflow_definition=sample_workflow_definition,
        )

        promos = promotion_service.list_promotions(sample_workflow)
        assert len(promos) == 2
        # La más reciente primero
        assert promos[0].target_env == "prod"
        assert promos[1].target_env == "staging"

    def test_get_promotion_history_summary(
        self,
        promotion_service: PromotionService,
        env_service: EnvironmentService,
        sample_workflow: int,
        sample_workflow_definition: dict,
    ):
        env_service.assign_to_environment(sample_workflow, "dev")
        promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="dev",
            target_env="staging",
            workflow_definition=sample_workflow_definition,
        )
        promotion_service.promote(
            workflow_id=sample_workflow,
            source_env="staging",
            target_env="prod",
            workflow_definition=sample_workflow_definition,
        )

        summary = promotion_service.get_promotion_history_summary(sample_workflow)
        assert "staging" in summary
        assert "prod" in summary
        assert summary["staging"]["count"] == 1
        assert summary["prod"]["count"] == 1
