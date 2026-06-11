"""
Workflow Determinista — Tests del EmailWatcher
Tests unitarios para el monitor de correo IMAP.
"""

from unittest.mock import patch


class TestEmailWatcher:
    """Tests del EmailWatcher."""

    def test_init(self):
        """Verifica inicialización correcta del EmailWatcher."""
        from src.events.email_watcher import EmailWatcher

        watcher = EmailWatcher()
        assert watcher._running is False
        assert watcher._interval == 300
        assert watcher._last_uids == set()
        assert watcher._callback is None

    def test_init_with_callback(self):
        """Verifica inicialización con callback personalizado."""
        from src.events.email_watcher import EmailWatcher

        def callback(etype, data):
            return None

        watcher = EmailWatcher(callback=callback)
        assert watcher._callback is callback

    def test_stop(self):
        """Verifica que stop() cambia _running a False."""
        from src.events.email_watcher import EmailWatcher

        watcher = EmailWatcher()
        watcher._running = True
        watcher.stop()
        assert watcher._running is False

    def test_emit_with_callback(self):
        """Verifica que _emit() llama al callback con los datos correctos."""
        from src.events.email_watcher import EmailWatcher

        received = []

        def callback(etype, data):
            received.append((etype, data))

        watcher = EmailWatcher(callback=callback)
        watcher._emit("email.received", {"subject": "Test", "from": "a@b.com"})
        assert len(received) == 1
        assert received[0][0] == "email.received"
        assert received[0][1]["subject"] == "Test"

    def test_emit_without_callback(self):
        """Verifica que _emit() no falla sin callback."""
        from src.events.email_watcher import EmailWatcher

        watcher = EmailWatcher()
        watcher._emit("email.received", {"subject": "Test"})  # No debe lanzar excepción

    def test_emit_callback_exception_handled(self):
        """Verifica que una excepción en el callback no rompe el watcher."""
        from src.events.email_watcher import EmailWatcher

        def bad_callback(etype, data):
            raise RuntimeError("Callback error")

        watcher = EmailWatcher(callback=bad_callback)
        watcher._emit("email.received", {"subject": "Test"})  # No debe lanzar excepción

    def test_check_config_no_imap(self, db_manager):
        """Verifica que sin configuración IMAP, se omite silenciosamente."""
        from src.events.email_watcher import EmailWatcher

        watcher = EmailWatcher()
        # No hay imap_server en settings, así que no debería hacer nada
        watcher._check_config_and_poll()  # No debe lanzar excepción

    def test_is_daemon_thread(self):
        """Verifica que el hilo se crea como daemon."""
        from src.events.email_watcher import EmailWatcher

        watcher = EmailWatcher()
        assert watcher.daemon is True

    def test_check_config_reads_interval(self, db_manager):
        """Verifica que se lee el intervalo de configuración."""
        from src.events.email_watcher import EmailWatcher

        db_manager.set_setting("imap_server", "imap.test.com")
        db_manager.set_setting("email_check_interval", "600")
        watcher = EmailWatcher()
        # _check_config_and_poll leerá el intervalo pero fallará en _poll_imap
        # porque no hay credenciales reales, lo cual es esperado
        with patch.object(watcher, "_poll_imap"):
            watcher._check_config_and_poll()
            assert watcher._interval == 600

    def test_check_config_invalid_interval_uses_default(self, db_manager):
        """Verifica que un intervalo inválido usa el default (300)."""
        from src.events.email_watcher import EmailWatcher

        db_manager.set_setting("imap_server", "imap.test.com")
        db_manager.set_setting("email_check_interval", "not_a_number")
        watcher = EmailWatcher()
        with patch.object(watcher, "_poll_imap"):
            watcher._check_config_and_poll()
            assert watcher._interval == 300
