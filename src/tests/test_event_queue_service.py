"""
Zenic-Flijo — Tests del EventQueueService
==========================================

Tests unitarios para el servicio de persistencia de cola de eventos.
Cubre: save, update_status, consultas, reprocesamiento y limpieza.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock


class TestEventQueueService:
    """Tests para la clase EventQueueService."""

    def test_save_event(self, db_manager):
        """Test: save inserta un evento en la cola con estado 'pending'."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)
        event_id = queue.save("test.event", {"key": "value"})

        assert event_id > 0
        event = queue.get(event_id)
        assert event is not None
        assert event["event_type"] == "test.event"
        assert event["status"] == "pending"

    def test_save_event_with_string_data(self, db_manager):
        """Test: save acepta data como string JSON."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)
        event_id = queue.save("test.string", '{"raw": "json"}')

        assert event_id > 0
        event = queue.get(event_id)
        assert event is not None
        assert event["event_type"] == "test.string"

    def test_update_status(self, db_manager):
        """Test: update_status cambia el estado de un evento."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)
        event_id = queue.save("test.status", {"data": "test"})

        queue.update_status(event_id, "processing")
        event = queue.get(event_id)
        assert event["status"] == "processing"

        queue.update_status(event_id, "completed")
        event = queue.get(event_id)
        assert event["status"] == "completed"

    def test_list_pending(self, db_manager):
        """Test: list_pending retorna solo eventos pendientes."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        # Crear varios eventos
        id1 = queue.save("test.pending1", {"a": 1})
        id2 = queue.save("test.pending2", {"b": 2})
        id3 = queue.save("test.pending3", {"c": 3})

        # Marcar uno como completed
        queue.update_status(id2, "completed")

        pending = queue.list_pending()
        pending_ids = [e["id"] for e in pending]

        assert id1 in pending_ids
        assert id2 not in pending_ids  # completed, no debe estar
        assert id3 in pending_ids

    def test_list_failed(self, db_manager):
        """Test: list_failed retorna solo eventos fallidos."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        id1 = queue.save("test.fail1", {"x": 1})
        id2 = queue.save("test.fail2", {"y": 2})

        queue.update_status(id1, "failed")

        failed = queue.list_failed()
        failed_ids = [e["id"] for e in failed]

        assert id1 in failed_ids
        assert id2 not in failed_ids  # pending, no debe estar

    def test_list_by_type(self, db_manager):
        """Test: list_by_type filtra eventos por tipo."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        queue.save("type.a", {"data": 1})
        queue.save("type.b", {"data": 2})
        queue.save("type.a", {"data": 3})

        type_a_events = queue.list_by_type("type.a")
        type_b_events = queue.list_by_type("type.b")

        assert len(type_a_events) == 2
        assert len(type_b_events) == 1
        assert all(e["event_type"] == "type.a" for e in type_a_events)

    def test_get_nonexistent(self, db_manager):
        """Test: get retorna None para IDs inexistentes."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)
        event = queue.get(99999)
        assert event is None

    def test_count_by_status(self, db_manager):
        """Test: count_by_status cuenta eventos por estado."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        for i in range(5):
            queue.save("test.count", {"i": i})
        # Marcar algunos
        events = queue.list_pending()
        queue.update_status(events[0]["id"], "processing")
        queue.update_status(events[1]["id"], "completed")
        queue.update_status(events[2]["id"], "failed")

        assert queue.count_by_status("pending") == 2
        assert queue.count_by_status("processing") == 1
        assert queue.count_by_status("completed") == 1
        assert queue.count_by_status("failed") == 1

    def test_get_stats(self, db_manager):
        """Test: get_stats retorna estadísticas completas."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        for i in range(10):
            queue.save("test.stats", {"i": i})
        events = queue.list_pending()
        queue.update_status(events[0]["id"], "completed")
        queue.update_status(events[1]["id"], "failed")

        stats = queue.get_stats()

        assert stats["pending"] == 8
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        assert stats["total"] == 10

    def test_reprocess_pending_with_publish_fn(self, db_manager):
        """Test: reprocess_pending llama a publish_fn para eventos pendientes."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        queue.save("test.repro", {"msg": "hello"})
        queue.save("test.repro", {"msg": "world"})

        mock_publish = MagicMock()
        count = queue.reprocess_pending(publish_fn=mock_publish)

        assert count == 2
        assert mock_publish.call_count == 2
        # Los eventos deben quedar como 'completed'
        assert queue.count_by_status("completed") == 2

    def test_reprocess_pending_without_fn(self, db_manager):
        """Test: reprocess_pending sin publish_fn solo marca como processing."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        queue.save("test.repro2", {"msg": "no-fn"})
        count = queue.reprocess_pending()

        assert count == 1
        # Sin publish_fn, pasa a completed igual
        assert queue.count_by_status("completed") == 1

    def test_reprocess_failed(self, db_manager):
        """Test: reprocess_failed reprocesa eventos fallidos."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        eid = queue.save("test.fail-repro", {"retry": True})
        queue.update_status(eid, "failed")

        mock_publish = MagicMock()
        count = queue.reprocess_failed(publish_fn=mock_publish)

        assert count == 1
        mock_publish.assert_called_once_with("test.fail-repro", {"retry": True})
        assert queue.count_by_status("completed") == 1

    def test_cleanup_removes_old_events(self, db_manager):
        """Test: cleanup elimina eventos completados/fallidos viejos."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        # Crear un evento completado con timestamp viejo
        db_manager.execute(
            "INSERT INTO event_queue (event_type, event_data, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("test.old", "{}", "completed", (datetime.utcnow() - timedelta(hours=48)).isoformat()),
        )
        db_manager.commit()

        # Crear un evento reciente
        fresh_id = queue.save("test.fresh", {})

        deleted = queue.cleanup(max_age_hours=24)

        assert deleted == 1
        # El evento fresco debe seguir existiendo
        assert queue.get(fresh_id) is not None

    def test_cleanup_keeps_pending_events(self, db_manager):
        """Test: cleanup no elimina eventos pendientes aunque sean viejos."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        db_manager.execute(
            "INSERT INTO event_queue (event_type, event_data, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("test.old-pending", "{}", "pending", (datetime.utcnow() - timedelta(hours=48)).isoformat()),
        )
        db_manager.commit()

        # Crear un evento fallido viejo
        db_manager.execute(
            "INSERT INTO event_queue (event_type, event_data, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("test.old-failed", "{}", "failed", (datetime.utcnow() - timedelta(hours=48)).isoformat()),
        )
        db_manager.commit()

        deleted = queue.cleanup(max_age_hours=24)

        # Solo limpia el failed (pending se conserva aunque sea viejo)
        assert deleted == 1
        assert queue.count_by_status("pending") >= 1

    def test_list_pending_with_limit(self, db_manager):
        """Test: list_pending respeta el límite."""
        from src.events.queue_service import EventQueueService

        queue = EventQueueService(db_manager)

        for i in range(10):
            queue.save("test.limit", {"i": i})

        limited = queue.list_pending(limit=3)
        assert len(limited) == 3

    def test_multiple_queues_independent(self, db_manager):
        """Test: dos instancias de EventQueueService comparten la misma DB."""
        from src.events.queue_service import EventQueueService

        q1 = EventQueueService(db_manager)
        q2 = EventQueueService(db_manager)

        eid = q1.save("test.shared", {"shared": True})
        event = q2.get(eid)

        assert event is not None
        assert event["event_type"] == "test.shared"
