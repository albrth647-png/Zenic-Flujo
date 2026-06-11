"""
Workflow Determinista — Tests del DatabaseTrigger
Tests unitarios para la detección de cambios en tablas SQLite.
"""


class TestDatabaseTrigger:
    """Tests del DatabaseTrigger."""

    def test_init(self, db_manager):
        """Verifica inicialización correcta."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        assert trigger._db is not None
        assert trigger._event_bus is not None

    def test_table_events_mapping(self):
        """Verifica que TABLE_EVENTS tiene los mapeos correctos."""
        from src.events.db_trigger import DatabaseTrigger

        assert "leads" in DatabaseTrigger.TABLE_EVENTS
        assert "invoices" in DatabaseTrigger.TABLE_EVENTS
        assert "products" in DatabaseTrigger.TABLE_EVENTS
        assert "workflow_executions" in DatabaseTrigger.TABLE_EVENTS
        # Verificar eventos específicos
        assert DatabaseTrigger.TABLE_EVENTS["leads"]["insert"] == "crm.lead.created"
        assert DatabaseTrigger.TABLE_EVENTS["leads"]["update"] == "crm.lead.updated"
        assert DatabaseTrigger.TABLE_EVENTS["leads"]["delete"] == "crm.lead.deleted"
        assert DatabaseTrigger.TABLE_EVENTS["invoices"]["insert"] == "invoice.created"
        assert DatabaseTrigger.TABLE_EVENTS["products"]["insert"] == "inventory.product.created"

    def test_install_triggers(self, db_manager):
        """Verifica que install_triggers() instala los triggers SQL."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        # Verificar que los triggers existen en sqlite_master
        rows = db_manager.fetchall("SELECT name FROM sqlite_master WHERE type='trigger'")
        trigger_names = [r["name"] for r in rows]
        assert "trg_leads_insert" in trigger_names
        assert "trg_leads_update" in trigger_names
        assert "trg_invoices_insert" in trigger_names
        assert "trg_products_insert" in trigger_names

    def test_install_triggers_idempotent(self, db_manager):
        """Verifica que instalar triggers dos veces no falla."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        trigger.install_triggers()  # No debe lanzar excepción

    def test_trigger_fires_on_lead_insert(self, db_manager):
        """Verifica que insertar un lead genera un evento en la cola."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        # Insertar un lead directamente
        db_manager.execute(
            "INSERT INTO leads (name, email, stage) VALUES (?, ?, ?)",
            ("Test Lead", "test@test.com", "new"),
        )
        db_manager.commit()
        # Verificar que hay un evento pendiente
        events = db_manager.fetchall("SELECT * FROM event_queue WHERE event_type = 'crm.lead.created'")
        assert len(events) >= 1
        assert events[0]["event_type"] == "crm.lead.created"

    def test_trigger_fires_on_lead_update(self, db_manager):
        """Verifica que actualizar un lead genera un evento."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        # Insertar y luego actualizar
        db_manager.execute(
            "INSERT INTO leads (name, email, stage) VALUES (?, ?, ?)",
            ("Test Lead", "test@test.com", "new"),
        )
        db_manager.commit()
        db_manager.execute(
            "UPDATE leads SET stage = ? WHERE name = ?",
            ("contacted", "Test Lead"),
        )
        db_manager.commit()
        # Verificar evento de actualización
        events = db_manager.fetchall("SELECT * FROM event_queue WHERE event_type = 'crm.lead.updated'")
        assert len(events) >= 1

    def test_trigger_fires_on_product_insert(self, db_manager):
        """Verifica que insertar un producto genera un evento."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        db_manager.execute(
            "INSERT INTO products (sku, name, stock, price) VALUES (?, ?, ?, ?)",
            ("SKU-001", "Test Product", 10, 9.99),
        )
        db_manager.commit()
        events = db_manager.fetchall("SELECT * FROM event_queue WHERE event_type = 'inventory.product.created'")
        assert len(events) >= 1

    def test_trigger_fires_on_invoice_insert(self, db_manager):
        """Verifica que insertar una factura genera un evento."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        db_manager.execute(
            "INSERT INTO invoices (number, client_name, items, subtotal, total) VALUES (?, ?, ?, ?, ?)",
            ("FAC-001", "Cliente Test", "[]", 100.0, 116.0),
        )
        db_manager.commit()
        events = db_manager.fetchall("SELECT * FROM event_queue WHERE event_type = 'invoice.created'")
        assert len(events) >= 1

    def test_poll_changes_marks_completed(self, db_manager):
        """Verifica que poll_changes() marca eventos como completed."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        # Generar un evento
        db_manager.execute(
            "INSERT INTO leads (name, email, stage) VALUES (?, ?, ?)",
            ("Poll Test", "poll@test.com", "new"),
        )
        db_manager.commit()
        # Procesar eventos pendientes
        results = trigger.poll_changes()
        assert len(results) >= 1
        assert results[0]["status"] == "processed"
        # Verificar que ya no hay pendientes
        pending = db_manager.fetchall("SELECT * FROM event_queue WHERE status = 'pending'")
        assert len(pending) == 0

    def test_poll_changes_empty_queue(self, db_manager):
        """Verifica que poll_changes() con cola vacía retorna lista vacía."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        results = trigger.poll_changes()
        assert results == []

    def test_trigger_fires_on_lead_delete(self, db_manager):
        """Verifica que eliminar un lead genera un evento."""
        from src.events.db_trigger import DatabaseTrigger

        trigger = DatabaseTrigger()
        trigger.install_triggers()
        # Insertar y luego eliminar
        db_manager.execute(
            "INSERT INTO leads (name, email, stage) VALUES (?, ?, ?)",
            ("Delete Test", "del@test.com", "new"),
        )
        db_manager.commit()
        db_manager.execute("DELETE FROM leads WHERE name = ?", ("Delete Test",))
        db_manager.commit()
        events = db_manager.fetchall("SELECT * FROM event_queue WHERE event_type = 'crm.lead.deleted'")
        assert len(events) >= 1
