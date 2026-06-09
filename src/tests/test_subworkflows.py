"""
Tests para Sub-workflows (Mejora #7).
"""
import pytest


def _make_engine():
    """Helper: crear engine con una tool de prueba."""
    from src.workflow.engine import WorkflowEngine
    WorkflowEngine._reset()
    engine = WorkflowEngine()

    class TestTool:
        def echo(self, message: str = "") -> dict:
            return {"message": message, "echoed": True}

    engine.register_tool("test_tool", TestTool())
    return engine


class TestSubworkflowExecution:
    """Tests para la ejecucion de pasos de tipo subworkflow."""

    def test_subworkflow_step_executes_child(self, db_manager):
        """Un paso subworkflow ejecuta el workflow hijo."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        child = repo.create(WorkflowDefinition(
            name="Child WF",
            trigger_type="manual",
            steps=[
                {"id": 1, "tool": "test_tool", "action": "echo",
                 "params": {"message": "desde hijo"}},
            ],
        ))

        wf = repo.create(WorkflowDefinition(
            name="Parent WF",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(wf.id)
        assert result.status == "completed", f"Fallo: {result.error_message}"
        assert len(result.step_results) == 1
        assert result.step_results[0]["status"] == "completed"

    def test_subworkflow_with_input_mapping(self, db_manager):
        """Input mapping pasa datos del padre al hijo."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        child = repo.create(WorkflowDefinition(
            name="Child Input",
            trigger_type="manual",
            steps=[
                {"id": 1, "tool": "test_tool", "action": "echo",
                 "params": {"message": "$input.nombre"}},
            ],
        ))

        wf = repo.create(WorkflowDefinition(
            name="Parent Input",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {"nombre": "$input.nombre_usuario"},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(wf.id, {"nombre_usuario": "Juan"})
        assert result.status == "completed"
        assert result.step_results[0]["status"] == "completed"

    def test_subworkflow_child_not_found(self, db_manager):
        """Workflow_id invalido debe fallar gracefulmente."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        wf = repo.create(WorkflowDefinition(
            name="Parent No Child",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": 99999,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(wf.id)
        assert result.status == "failed"
        assert "no encontrado" in (result.error_message or "").lower()

    def test_subworkflow_child_not_active(self, db_manager):
        """Workflow hijo pausado debe fallar."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        child = repo.create(WorkflowDefinition(
            name="Inactive Child",
            trigger_type="manual",
            steps=[],
        ))
        engine.pause(child.id)

        wf = repo.create(WorkflowDefinition(
            name="Parent Inactive",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(wf.id)
        assert result.status == "failed"
        # Verificar que menciona el estado "no activo" (con o sin acento)
        err = (result.error_message or "").lower()
        assert "no est" in err, f"Mensaje: {err}"

    def test_subworkflow_nested_depth_limit(self, db_manager):
        """Subworkflows anidados funcionan correctamente."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        leaf = repo.create(WorkflowDefinition(
            name="Leaf WF",
            trigger_type="manual",
            steps=[
                {"id": 1, "tool": "test_tool", "action": "echo",
                 "params": {"message": "leaf"}},
            ],
        ))

        mid = repo.create(WorkflowDefinition(
            name="Mid WF",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": leaf.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        root = repo.create(WorkflowDefinition(
            name="Root WF",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": mid.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(root.id)
        assert result.status == "completed"

    def test_subworkflow_recursive_detection(self, db_manager):
        """Subworkflow que se apunta a si mismo debe detectarse como recursivo."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        wf = repo.create(WorkflowDefinition(
            name="Self Ref",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": 0,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))
        wf.steps[0]["workflow_id"] = wf.id
        repo.update(wf.id, {"steps": wf.steps})

        result = engine.execute(wf.id)
        assert result.status == "failed"
        assert "recursivo" in (result.error_message or "").lower()

    def test_subworkflow_execution_logged(self, db_manager):
        """La ejecucion del subworkflow debe quedar registrada."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        child = repo.create(WorkflowDefinition(
            name="Log Child",
            trigger_type="manual",
            steps=[],
        ))

        wf = repo.create(WorkflowDefinition(
            name="Log Parent",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        result = engine.execute(wf.id)
        assert result.status == "completed"

        execs = repo.list_executions(wf.id)
        assert len(execs) >= 1

        logs = repo.get_step_logs(execs[0].id)
        assert len(logs) >= 1
        assert logs[0]["tool"] == "subworkflow"

    def test_subworkflow_in_workflow_list(self, db_manager):
        """Workflow que contiene subworkflow debe listar correctamente."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        repo = WorkflowRepository()
        child = repo.create(WorkflowDefinition(name="Child", trigger_type="manual", steps=[]))

        parent = repo.create(WorkflowDefinition(
            name="Parent",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {},
                 "output_mapping": {}},
            ],
        ))

        loaded = repo.get(parent.id)
        assert loaded is not None
        assert loaded.steps[0]["type"] == "subworkflow"
        assert loaded.steps[0]["workflow_id"] == child.id


class TestSubworkflowWithOutputMapping:
    """Tests para output_mapping de subworkflows."""

    def test_subworkflow_with_output_mapping(self, db_manager):
        """Output mapping extrae datos del resultado del hijo."""
        from src.workflow.repository import WorkflowRepository, WorkflowDefinition

        engine = _make_engine()
        repo = WorkflowRepository()

        child = repo.create(WorkflowDefinition(
            name="Child Output",
            trigger_type="manual",
            steps=[
                {"id": 1, "tool": "test_tool", "action": "echo",
                 "params": {"message": "resultado_test"}},
            ],
        ))

        wf = repo.create(WorkflowDefinition(
            name="Parent Output",
            trigger_type="manual",
            steps=[
                {"id": 1, "type": "subworkflow", "tool": "subworkflow",
                 "action": "execute",
                 "workflow_id": child.id,
                 "input_mapping": {},
                 "output_mapping": {"resultado_final": "steps_output.1.message"}},
                {"id": 2, "tool": "test_tool", "action": "echo",
                 "params": {"message": "$steps_output.1.resultado_final"}},
            ],
        ))

        result = engine.execute(wf.id)
        assert result.status == "completed"
        assert result.step_results[1]["status"] == "completed"
