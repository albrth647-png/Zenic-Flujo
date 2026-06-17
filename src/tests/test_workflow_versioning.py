"""
Tests del módulo WorkflowVersionRepository (Sprint 9 — Versioning).

Cubre:
- Creación de versiones con auto-incremento de version_number.
- Listado de versiones (orden descendente).
- get_latest_version.
- count_versions.
- Política de retención (elimina versiones antiguas cuando se excede el límite).
- delete_version (no permite eliminar la única versión).
- Inmutabilidad: las versiones son solo-create, no se editan.
"""
from __future__ import annotations

import pytest

from src.workflow.versioning import (
    VersioningError,
    WorkflowVersion,
    WorkflowVersionRepository,
)


@pytest.fixture
def version_repo(db_manager) -> WorkflowVersionRepository:
    """Repository aislado por test, con retención baja para testear el límite."""
    return WorkflowVersionRepository(db=db_manager, retention=5)


@pytest.fixture
def sample_workflow(db_manager) -> int:
    """Crea un workflow de prueba y retorna su ID."""
    from src.workflow.repository import WorkflowDefinition, WorkflowRepository

    repo = WorkflowRepository()
    # Forzar el db_manager en el repo para usar la DB temporal del test
    repo._db = db_manager

    wf = repo.create(
        WorkflowDefinition(
            name="Test Versioning Workflow",
            description="Workflow para tests de versioning",
            trigger_type="event",
            trigger_config={"event": "test.event"},
            steps=[
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "John"}},
            ],
        ),
        user_id=1,
    )
    return wf.id  # type: ignore[return-value]


class TestVersionCreation:
    """Tests de creación de versiones."""

    def test_create_first_version_assigns_version_number_1(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        v = version_repo.create_version(
            workflow_id=sample_workflow,
            name="v1",
            description="Primera versión",
            trigger_type="event",
            trigger_config={"event": "test"},
            steps=[],
            change_summary="Initial",
        )
        assert v.version_number == 1
        assert v.id is not None
        assert v.workflow_id == sample_workflow
        assert v.change_summary == "Initial"

    def test_create_multiple_versions_increments_sequentially(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        v1 = version_repo.create_version(
            workflow_id=sample_workflow,
            name="v1", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="1",
        )
        v2 = version_repo.create_version(
            workflow_id=sample_workflow,
            name="v2", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="2",
        )
        v3 = version_repo.create_version(
            workflow_id=sample_workflow,
            name="v3", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="3",
        )

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_version_preserves_complex_trigger_config_and_steps(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        complex_config = {"event": "crm.lead.created", "filter": {"stage": "new"}, "debounce_ms": 500}
        complex_steps = [
            {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "John", "email": "j@x.com"}},
            {"id": 2, "tool": "notification", "action": "send_email", "params": {"to": "admin@x.com"}},
        ]

        v = version_repo.create_version(
            workflow_id=sample_workflow,
            name="Complex", description="", trigger_type="event",
            trigger_config=complex_config, steps=complex_steps, change_summary="Complex",
        )

        # Reload from DB
        loaded = version_repo.get_version(sample_workflow, v.version_number)
        assert loaded is not None
        assert loaded.trigger_config == complex_config
        assert loaded.steps == complex_steps


class TestVersionListing:
    """Tests de listado de versiones."""

    def test_list_versions_returns_most_recent_first(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        for i in range(5):
            version_repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary=f"version {i}",
            )

        versions = version_repo.list_versions(sample_workflow)
        assert len(versions) == 5
        # La más reciente primero
        assert versions[0].version_number == 5
        assert versions[-1].version_number == 1

    def test_list_versions_respects_limit_and_offset(
        self, db_manager, sample_workflow: int
    ):
        # Usar un repo con retención alta para que no elimine versiones durante el test
        repo = WorkflowVersionRepository(db=db_manager, retention=50)

        for i in range(10):
            repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary="",
            )

        # Page 1 (limit=3, offset=0): versions 10, 9, 8
        page1 = repo.list_versions(sample_workflow, limit=3, offset=0)
        assert [v.version_number for v in page1] == [10, 9, 8]

        # Page 2 (limit=3, offset=3): versions 7, 6, 5
        page2 = repo.list_versions(sample_workflow, limit=3, offset=3)
        assert [v.version_number for v in page2] == [7, 6, 5]

    def test_get_latest_version(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        # Sin versiones
        assert version_repo.get_latest_version(sample_workflow) is None

        # Crear 3 versiones
        for i in range(3):
            version_repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary="",
            )

        latest = version_repo.get_latest_version(sample_workflow)
        assert latest is not None
        assert latest.version_number == 3

    def test_count_versions(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        assert version_repo.count_versions(sample_workflow) == 0

        for i in range(3):
            version_repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary="",
            )

        assert version_repo.count_versions(sample_workflow) == 3

    def test_list_versions_empty_for_workflow_without_versions(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        versions = version_repo.list_versions(sample_workflow)
        assert versions == []


class TestVersionRetrieval:
    """Tests de obtención de versiones específicas."""

    def test_get_version_by_number(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        version_repo.create_version(
            workflow_id=sample_workflow,
            name="v1", description="first", trigger_type="event",
            trigger_config={"event": "x"}, steps=[], change_summary="initial",
        )

        v = version_repo.get_version(sample_workflow, 1)
        assert v is not None
        assert v.name == "v1"
        assert v.description == "first"
        assert v.trigger_type == "event"

    def test_get_nonexistent_version_returns_none(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        assert version_repo.get_version(sample_workflow, 999) is None


class TestVersionDeletion:
    """Tests de eliminación de versiones."""

    def test_delete_version_removes_it(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        for i in range(3):
            version_repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary="",
            )

        assert version_repo.delete_version(sample_workflow, 2) is True
        assert version_repo.count_versions(sample_workflow) == 2
        assert version_repo.get_version(sample_workflow, 2) is None

    def test_delete_nonexistent_version_returns_false(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        assert version_repo.delete_version(sample_workflow, 999) is False

    def test_cannot_delete_only_remaining_version(
        self, version_repo: WorkflowVersionRepository, sample_workflow: int
    ):
        version_repo.create_version(
            workflow_id=sample_workflow,
            name="only", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="",
        )

        with pytest.raises(VersioningError, match="única versión"):
            version_repo.delete_version(sample_workflow, 1)


class TestRetentionPolicy:
    """Tests de la política de retención automática."""

    def test_retention_deletes_oldest_when_exceeded(
        self, db_manager, sample_workflow: int
    ):
        # Repo con retención = 3
        repo = WorkflowVersionRepository(db=db_manager, retention=3)

        # Crear 5 versiones
        for i in range(5):
            repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary=f"version {i+1}",
            )

        # Deben quedar solo las 3 más recientes (versiones 3, 4, 5)
        assert repo.count_versions(sample_workflow) == 3
        versions = repo.list_versions(sample_workflow)
        assert {v.version_number for v in versions} == {3, 4, 5}

    def test_retention_does_not_delete_when_under_limit(
        self, db_manager, sample_workflow: int
    ):
        repo = WorkflowVersionRepository(db=db_manager, retention=10)

        for i in range(3):
            repo.create_version(
                workflow_id=sample_workflow,
                name=f"v{i}", description="", trigger_type="event",
                trigger_config={}, steps=[], change_summary="",
            )

        assert repo.count_versions(sample_workflow) == 3  # No se eliminó nada

    def test_retention_minimum_is_1(
        self, db_manager, sample_workflow: int
    ):
        # Retención inválida (0 o negativa) se ajusta a 1
        repo = WorkflowVersionRepository(db=db_manager, retention=0)
        assert repo.retention == 1

        repo.create_version(
            workflow_id=sample_workflow,
            name="v1", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="",
        )
        repo.create_version(
            workflow_id=sample_workflow,
            name="v2", description="", trigger_type="event",
            trigger_config={}, steps=[], change_summary="",
        )

        # Solo debe quedar la versión 2 (la más reciente)
        assert repo.count_versions(sample_workflow) == 1
        latest = repo.get_latest_version(sample_workflow)
        assert latest is not None
        assert latest.version_number == 2


class TestVersionImmutability:
    """Las versiones son solo-create. No hay método update."""

    def test_no_update_method_exists(self):
        """WorkflowVersionRepository no debe tener método update_version."""
        assert not hasattr(WorkflowVersionRepository, "update_version")
        assert not hasattr(WorkflowVersionRepository, "edit_version")

    def test_version_dataclass_is_mutable_but_should_be_used_immutable(self):
        """La dataclass es mutable por defecto en Python, pero el contrato del repo
        no expone setters. Lo verificamos documentando el comportamiento esperado."""
        v = WorkflowVersion(workflow_id=1, version_number=1, name="test")
        # El campo name es assignable técnicamente, pero el repo no expone update.
        # Este test documenta que el contrato es append-only.
        assert v.name == "test"
