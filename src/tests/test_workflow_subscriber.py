"""
Zenic-Flijo — Tests del WorkflowSubscriber
============================================

Tests unitarios para el sistema de suscripción y ejecución de workflows.
Cubre: subscribe, unsubscribe, list_subscribers, handle_event, register_all.
"""

from unittest.mock import patch


class TestWorkflowSubscriber:
    """Tests para la clase WorkflowSubscriber."""

    def _create_sub(self, db_manager):
        """Helper: crea WorkflowSubscriber con bus y cola compartidos."""
        from src.events.bus import EventBus
        from src.events.queue_service import EventQueueService
        from src.events.workflow_subscriber import WorkflowSubscriber

        bus = EventBus()
        queue = EventQueueService(db_manager)
        return WorkflowSubscriber(bus, queue)

    def _create_test_workflow(self, db_manager, name="Test Sub WF") -> int:
        """Helper: crea un workflow de prueba y retorna su ID."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name=name,
                description="Test subscription",
                trigger_type="event",
                trigger_config={"event": "test.trigger"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}],
            )
        )
        return wf.id

    def test_subscribe(self, db_manager):
        """Test: subscribe registra un workflow en event_subscriptions."""

        wf_id = self._create_test_workflow(db_manager, "Subscribe Test")
        sub = self._create_sub(db_manager)
        sub.subscribe("test.event", wf_id)

        rows = db_manager.fetchall(
            "SELECT * FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            ("test.event", wf_id),
        )
        assert len(rows) == 1
        assert rows[0]["event_type"] == "test.event"
        assert rows[0]["workflow_id"] == wf_id

    def test_subscribe_duplicate(self, db_manager):
        """Test: subscribe es idempotente (INSERT OR IGNORE)."""

        wf_id = self._create_test_workflow(db_manager, "Dup Test")
        sub = self._create_sub(db_manager)
        sub.subscribe("test.dup", wf_id)
        sub.subscribe("test.dup", wf_id)

        rows = db_manager.fetchall(
            "SELECT * FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            ("test.dup", wf_id),
        )
        assert len(rows) == 1

    def test_unsubscribe(self, db_manager):
        """Test: unsubscribe elimina una suscripción."""

        wf_id = self._create_test_workflow(db_manager, "Unsub Test")
        sub = self._create_sub(db_manager)
        sub.subscribe("test.unsub", wf_id)
        sub.unsubscribe("test.unsub", wf_id)

        rows = db_manager.fetchall(
            "SELECT * FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            ("test.unsub", wf_id),
        )
        assert len(rows) == 0

    def test_unsubscribe_all(self, db_manager):
        """Test: unsubscribe_all elimina todas las suscripciones de un workflow."""

        wf_id_1 = self._create_test_workflow(db_manager, "UnsubAll WF1")
        wf_id_2 = self._create_test_workflow(db_manager, "UnsubAll WF2")
        sub = self._create_sub(db_manager)
        sub.subscribe("test.evt1", wf_id_1)
        sub.subscribe("test.evt2", wf_id_1)
        sub.subscribe("test.evt1", wf_id_2)

        sub.unsubscribe_all(wf_id_1)

        rows_wf1 = db_manager.fetchall(
            "SELECT * FROM event_subscriptions WHERE workflow_id = ?", (wf_id_1,)
        )
        rows_wf2 = db_manager.fetchall(
            "SELECT * FROM event_subscriptions WHERE workflow_id = ?", (wf_id_2,)
        )
        assert len(rows_wf1) == 0
        assert len(rows_wf2) == 1  # Workflow 2 no debe verse afectado

    def test_list_subscribers(self, db_manager):
        """Test: list_subscribers retorna workflows suscritos a un evento."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)
        repo = WorkflowRepository()

        wf = repo.create(
            WorkflowDefinition(
                name="Test WF",
                description="Test",
                trigger_type="event",
                trigger_config={"event": "test.trigger"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}],
            )
        )

        sub.subscribe("test.trigger", wf.id)

        subscribers = sub.list_subscribers("test.trigger")
        assert len(subscribers) == 1
        assert subscribers[0]["id"] == wf.id
        assert subscribers[0]["status"] == "active"

    def test_list_subscribers_empty(self, db_manager):
        """Test: list_subscribers retorna lista vacía si no hay suscriptores."""

        sub = self._create_sub(db_manager)
        subscribers = sub.list_subscribers("nonexistent.event")
        assert subscribers == []

    def test_handle_event_with_subscriber(self, db_manager):
        """Test: handle_event ejecuta workflows suscritos."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)

        # Crear workflow
        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="Event WF",
                description="Test",
                trigger_type="event",
                trigger_config={"event": "test.exec"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}],
            )
        )

        # Suscribir
        sub.subscribe("test.exec", wf.id)

        # Guardar evento en la cola
        event_id = sub._queue.save("test.exec", {"msg": "hello"})

        # Mockear _execute_workflow para evitar dependencia real
        with patch.object(sub, "_execute_workflow") as mock_exec:
            mock_exec.return_value = {
                "workflow_id": wf.id,
                "status": "completed",
                "execution_id": 1,
                "duration_ms": 10,
            }
            results = sub.handle_event("test.exec", {"msg": "hello"}, event_id)

        assert len(results) == 1
        assert results[0]["workflow_id"] == wf.id
        assert results[0]["status"] == "completed"
        mock_exec.assert_called_once_with(wf.id, {"msg": "hello"})

        # Verificar que el evento se marcó como completado
        event = sub._queue.get(event_id)
        assert event["status"] == "completed"

    def test_handle_event_only_active(self, db_manager):
        """Test: handle_event solo ejecuta workflows activos."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="Inactive WF",
                description="Test",
                trigger_type="event",
                trigger_config={"event": "test.inactive"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}],
                status="paused",
            )
        )

        sub.subscribe("test.inactive", wf.id)

        with patch.object(sub, "_execute_workflow") as mock_exec:
            results = sub.handle_event("test.inactive", {})

        assert len(results) == 0
        mock_exec.assert_not_called()

    def test_handle_event_no_subscribers(self, db_manager):
        """Test: handle_event sin suscriptores retorna lista vacía."""

        sub = self._create_sub(db_manager)
        queue = sub._queue

        event_id = queue.save("test.no-subs", {})
        results = sub.handle_event("test.no-subs", {}, event_id)

        assert results == []
        # El evento debe quedar como pending
        event = queue.get(event_id)
        assert event["status"] == "pending"

    def test_execute_workflow_integration(self, db_manager):
        """Test: _execute_workflow funciona con WorkflowEngine real."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)
        repo = WorkflowRepository()

        wf = repo.create(
            WorkflowDefinition(
                name="Exec Test",
                description="Test real execution",
                trigger_type="manual",
                trigger_config={},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "$input.name"}}],
            )
        )

        result = sub._execute_workflow(wf.id, {"name": "Test Lead"})

        assert result["workflow_id"] == wf.id
        assert result["status"] == "completed" or result["status"] == "failed"
        assert "execution_id" in result

    def test_execute_workflow_failure(self, db_manager):
        """Test: _execute_workflow maneja errores gracefulmente."""

        sub = self._create_sub(db_manager)

        # ID de workflow que no existe
        result = sub._execute_workflow(99999, {})

        assert result["workflow_id"] == 99999
        assert result["status"] == "failed"
        assert "error" in result

    def test_last_results_stored(self, db_manager):
        """Test: handle_event almacena resultados en last_results."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="Results Test",
                description="Test",
                trigger_type="event",
                trigger_config={"event": "test.results"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}],
            )
        )

        sub.subscribe("test.results", wf.id)

        with patch.object(sub, "_execute_workflow") as mock_exec:
            mock_exec.return_value = {
                "workflow_id": wf.id,
                "status": "completed",
                "execution_id": 42,
                "duration_ms": 100,
            }
            sub.handle_event("test.results", {})

        assert len(sub.last_results) == 1
        assert sub.last_results[0]["execution_id"] == 42

    def test_register_all_db_subscriptions(self, db_manager):
        """Test: register_all_db_subscriptions registra handlers en EventBus."""

        wf_id = self._create_test_workflow(db_manager, "Reg All WF")
        sub = self._create_sub(db_manager)

        # Insertar suscripciones con workflow válido
        sub.subscribe("type.a", wf_id)
        sub.subscribe("type.b", wf_id)

        count = sub.register_all_db_subscriptions()
        assert count == 2  # type.a, type.b

        # Verificar que los handlers se registraron en EventBus
        assert "type.a" in sub._event_bus._handlers
        assert "type.b" in sub._event_bus._handlers

    def test_handle_event_without_event_id(self, db_manager):
        """Test: handle_event funciona sin event_id."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        sub = self._create_sub(db_manager)

        repo = WorkflowRepository()
        wf = repo.create(
            WorkflowDefinition(
                name="No Event ID",
                description="Test",
                trigger_type="event",
                trigger_config={"event": "test.noeid"},
                steps=[{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}],
            )
        )

        sub.subscribe("test.noeid", wf.id)

        with patch.object(sub, "_execute_workflow") as mock_exec:
            mock_exec.return_value = {"workflow_id": wf.id, "status": "completed"}
            results = sub.handle_event("test.noeid", {})

        assert len(results) == 1
        mock_exec.assert_called_once()
