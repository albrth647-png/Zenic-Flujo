"""
Workflow Determinista — Tests del WorkflowEngine
Tests unitarios para el motor de workflows: ciclo de vida, ejecución, pausa, reanudación.
"""

from unittest.mock import MagicMock

import pytest


class TestWorkflowEngine:
    """Tests para la clase WorkflowEngine."""

    def test_execute_simple_workflow(self, db_manager, sample_workflow, sample_context):
        """Test: ejecutar un workflow simple de principio a fin."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=sample_workflow["name"],
                description=sample_workflow["description"],
                trigger_type=sample_workflow["trigger_type"],
                trigger_config=sample_workflow["trigger_config"],
                steps=sample_workflow["steps"],
            )
        )

        engine = WorkflowEngine()

        # Mock the tools to avoid real dependencies
        mock_crm = MagicMock()
        mock_crm.create_lead.return_value = {"id": 1, "name": "Juan", "email": "juan@test.com"}
        engine.register_tool("crm", mock_crm)

        mock_notif = MagicMock()
        mock_notif.send_email.return_value = {"status": "sent"}
        engine.register_tool("notification", mock_notif)

        result = engine.execute(wf.id, sample_context["input"])

        assert result.status == "completed"
        assert result.execution_id is not None
        mock_crm.create_lead.assert_called_once()

    def test_execute_workflow_not_found(self, db_manager):
        """Test: intentar ejecutar un workflow inexistente debe fallar."""
        from src.workflow.engine import WorkflowEngine

        engine = WorkflowEngine()
        with pytest.raises(ValueError):
            engine.execute(99999, {})

    def test_pause_and_resume_workflow(self, db_manager, sample_workflow):
        """Test: pausar y reanudar un workflow cambia su estado correctamente."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=sample_workflow["name"],
                description=sample_workflow["description"],
                trigger_type=sample_workflow["trigger_type"],
                trigger_config=sample_workflow["trigger_config"],
                steps=sample_workflow["steps"],
            )
        )

        engine = WorkflowEngine()

        # Pausar
        assert engine.pause(wf.id) is True
        status = engine.get_status(wf.id)
        assert status["workflow"]["status"] == "paused"

        # Reanudar
        assert engine.resume(wf.id) is True
        status = engine.get_status(wf.id)
        assert status["workflow"]["status"] == "active"

    def test_archive_workflow(self, db_manager, sample_workflow):
        """Test: archivar un workflow cambia su estado a archived."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=sample_workflow["name"],
                description=sample_workflow["description"],
                trigger_type=sample_workflow["trigger_type"],
                trigger_config=sample_workflow["trigger_config"],
                steps=sample_workflow["steps"],
            )
        )

        engine = WorkflowEngine()
        assert engine.archive(wf.id) is True
        status = engine.get_status(wf.id)
        assert status["workflow"]["status"] == "archived"

    def test_get_status(self, db_manager, sample_workflow):
        """Test: get_status retorna la información correcta del workflow."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=sample_workflow["name"],
                description=sample_workflow["description"],
                trigger_type=sample_workflow["trigger_type"],
                trigger_config=sample_workflow["trigger_config"],
                steps=sample_workflow["steps"],
            )
        )

        engine = WorkflowEngine()
        status = engine.get_status(wf.id)
        assert status["workflow"]["status"] == "active"
        assert status["workflow"]["id"] == wf.id

    def test_execute_with_step_failure(self, db_manager, sample_workflow, sample_context):
        """Test: un workflow con un paso que falla debe marcar la ejecución como failed."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=sample_workflow["name"],
                description=sample_workflow["description"],
                trigger_type=sample_workflow["trigger_type"],
                trigger_config=sample_workflow["trigger_config"],
                steps=sample_workflow["steps"],
            )
        )

        engine = WorkflowEngine()

        # Mock tool that raises an exception
        mock_crm = MagicMock()
        mock_crm.create_lead.side_effect = Exception("CRM connection failed")
        engine.register_tool("crm", mock_crm)

        result = engine.execute(wf.id, sample_context["input"])
        assert result.status == "failed"

    def test_register_tool(self, db_manager):
        """Test: registrar una tool la hace disponible para ejecución."""
        from src.workflow.engine import WorkflowEngine

        engine = WorkflowEngine()
        mock_tool = MagicMock()
        engine.register_tool("test_tool", mock_tool)

        tools = engine.get_registered_tools()
        assert "test_tool" in tools

    def test_execute_conditional_step(self, db_manager, sample_context):
        """Test: un paso con condición que evalúa a False se omite."""
        from src.workflow.engine import WorkflowEngine
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        steps = [
            {
                "id": 1,
                "tool": "crm",
                "action": "create_lead",
                "params": {"name": "$input.nombre"},
                "condition": "1 == 2",
            },  # Always false
        ]

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="Conditional WF",
                description="Test conditional",
                trigger_type="manual",
                trigger_config={},
                steps=steps,
            )
        )

        engine = WorkflowEngine()
        mock_crm = MagicMock()
        mock_crm.create_lead.return_value = {"id": 1}
        engine.register_tool("crm", mock_crm)

        result = engine.execute(wf.id, {"nombre": "Test", "stock": 5})
        assert result.status == "completed"
        # Tool should NOT have been called because condition was false
        mock_crm.create_lead.assert_not_called()
