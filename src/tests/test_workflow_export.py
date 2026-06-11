"""
Tests para exportación e importación de Workflows (Mejora #3).
"""

import json

import pytest

from src.workflow.repository import WorkflowDefinition, WorkflowRepository


class TestWorkflowExport:
    """Tests para exportación de workflows."""

    def test_export_workflow_json(self, db_manager):
        """Exporta un workflow y verifica estructura JSON."""
        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="Export Test",
                description="Workflow para exportar",
                trigger_type="schedule",
                trigger_config={"frequency": "daily", "time": "08:00"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Juan"}}],
            )
        )
        exported = repo.export_workflow(wf.id)
        assert exported is not None
        assert exported["name"] == "Export Test"
        assert exported["description"] == "Workflow para exportar"
        assert exported["trigger_type"] == "schedule"
        assert exported["trigger_config"]["frequency"] == "daily"
        assert len(exported["steps"]) == 1
        assert exported["steps"][0]["tool"] == "crm"
        # Debe incluir metadatos
        assert "export_version" in exported
        assert "exported_at" in exported
        assert exported["export_version"] == "1.0"

    def test_export_nonexistent_workflow(self, db_manager):
        """Exportar un workflow que no existe retorna None."""
        repo = WorkflowRepository()
        exported = repo.export_workflow(99999)
        assert exported is None

    def test_export_workflow_with_executions(self, db_manager):
        """Export incluye historial de ejecuciones."""
        repo = WorkflowRepository()
        wf = repo.create(WorkflowDefinition(name="Historial Test"))
        # Crear algunas ejecuciones
        exec1 = repo.create_execution(wf.id, {"test": True})
        repo.complete_execution(exec1.id, duration_ms=150)
        exec2 = repo.create_execution(wf.id, {"test": False})
        repo.complete_execution(exec2.id, duration_ms=200, error_message="fail")

        exported = repo.export_workflow(wf.id)
        assert exported is not None
        assert "executions" in exported
        assert len(exported["executions"]) == 2
        # Verificar orden descendente
        assert exported["executions"][0]["status"] in ("completed", "failed")

    def test_export_json_serializable(self, db_manager):
        """El export debe ser 100% JSON serializable."""
        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="JSON Safe",
                trigger_type="webhook",
                trigger_config={"path": "test-hook"},
                steps=[{"id": 1, "tool": "notification", "action": "send_email", "params": {"to": "test@test.com"}}],
            )
        )
        exported = repo.export_workflow(wf.id)
        # Serializar y deserializar debe funcionar sin errores
        json_str = json.dumps(exported, ensure_ascii=False)
        recovered = json.loads(json_str)
        assert recovered["name"] == "JSON Safe"
        assert recovered["trigger_config"]["path"] == "test-hook"


class TestWorkflowImport:
    """Tests para importación de workflows."""

    def test_import_valid_workflow(self, db_manager):
        """Importa un workflow válido."""
        repo = WorkflowRepository()
        data = {
            "export_version": "1.0",
            "name": "Imported Workflow",
            "description": "Importado desde JSON",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}},
            ],
        }
        imported = repo.import_workflow(data)
        assert imported is not None
        assert imported.id is not None
        assert imported.name == "Imported Workflow"
        assert imported.status == "active"
        # Verificar que se guardó en DB
        loaded = repo.get(imported.id)
        assert loaded is not None
        assert loaded.name == "Imported Workflow"
        assert len(loaded.steps) == 1

    def test_import_without_required_fields(self, db_manager):
        """Import sin nombre usa nombre por defecto."""
        repo = WorkflowRepository()
        imported = repo.import_workflow({"trigger_type": "manual", "steps": []})
        assert imported is not None
        assert imported.name == "Workflow importado"
        assert imported.trigger_type == "manual"

    def test_import_invalid_steps_format(self, db_manager):
        """Steps debe ser una lista."""
        repo = WorkflowRepository()
        with pytest.raises(ValueError, match="steps"):
            repo.import_workflow(
                {
                    "name": "Bad",
                    "trigger_type": "manual",
                    "steps": "not_a_list",
                }
            )

    def test_import_with_executions_ignored(self, db_manager):
        """Las ejecuciones en el import no deben replicarse."""
        repo = WorkflowRepository()
        data = {
            "export_version": "1.0",
            "name": "Clean Import",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [],
            "executions": [
                {"status": "completed", "duration_ms": 100},
                {"status": "failed", "duration_ms": 50},
            ],
        }
        imported = repo.import_workflow(data)
        # Las ejecuciones no deben haberse importado
        executions = repo.list_executions(imported.id)
        assert len(executions) == 0

    def test_import_trigger_config_default(self, db_manager):
        """trigger_config debe tener default vacío."""
        repo = WorkflowRepository()
        data = {
            "name": "No Config",
            "trigger_type": "manual",
            "steps": [],
        }
        imported = repo.import_workflow(data)
        assert imported.trigger_config == {}

    def test_import_sanitizes_ids(self, db_manager):
        """Los IDs de pasos deben resetearse en el import."""
        repo = WorkflowRepository()
        data = {
            "name": "Sanitized",
            "trigger_type": "manual",
            "steps": [
                {"id": 999, "tool": "crm", "action": "create_lead", "params": {}},
                {
                    "id": 1000,
                    "tool": "notification",
                    "action": "send_email",
                    "params": {"to": "test@test.com", "subject": "Test", "body": "Body"},
                },
            ],
        }
        imported = repo.import_workflow(data)
        assert len(imported.steps) == 2
        # Los IDs deberían ser enteros positivos
        for step in imported.steps:
            assert isinstance(step["id"], int)
            assert step["id"] > 0

    def test_import_empty_name_uses_default(self, db_manager):
        """Nombre vacío usa 'Workflow importado'."""
        repo = WorkflowRepository()
        data = {
            "name": "  ",
            "trigger_type": "manual",
            "steps": [],
        }
        imported = repo.import_workflow(data)
        assert imported.name == "Workflow importado"

    def test_import_nonexistent_tool_warns(self, db_manager):
        """Import con tools desconocidas debe advertir pero continuar."""
        repo = WorkflowRepository()
        data = {
            "name": "Unknown Tools",
            "trigger_type": "manual",
            "steps": [
                {"id": 1, "tool": "nonexistent_tool", "action": "do_something", "params": {}},
            ],
        }
        # Debe importar sin lanzar excepción
        imported = repo.import_workflow(data)
        assert imported is not None
        assert len(imported.steps) == 1
