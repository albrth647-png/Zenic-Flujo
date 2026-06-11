"""
Workflow Determinista — Tests del FileWatcher
Tests unitarios para el monitor de cambios en archivos.
"""

import os
import time


class TestFileWatcher:
    """Tests del FileWatcher."""

    def test_init(self):
        """Verifica inicialización correcta."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        assert watcher._running is False
        assert watcher._interval == 5.0
        assert watcher._callback is None
        assert watcher._watched_dirs == {}

    def test_init_with_callback_and_interval(self):
        """Verifica inicialización con callback e intervalo personalizados."""
        from src.events.file_watcher import FileWatcher

        def callback(etype, data):
            return None

        watcher = FileWatcher(callback=callback, interval=2.0)
        assert watcher._callback is callback
        assert watcher._interval == 2.0

    def test_is_daemon_thread(self):
        """Verifica que el hilo se crea como daemon."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        assert watcher.daemon is True

    def test_stop(self):
        """Verifica que stop() cambia _running a False."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher._running = True
        watcher.stop()
        assert watcher._running is False

    def test_watch_directory(self, tmp_path):
        """Verifica que watch() agrega un directorio a la lista de monitoreo."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.watch(str(tmp_path))
        assert str(tmp_path.resolve()) in watcher._watched_dirs

    def test_watch_with_pattern(self, tmp_path):
        """Verifica que watch() almacena el patrón correctamente."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.watch(str(tmp_path), pattern="*.csv")
        dir_path = str(tmp_path.resolve())
        assert watcher._watched_dirs[dir_path]["pattern"] == "*.csv"

    def test_watch_with_recursive(self, tmp_path):
        """Verifica que watch() almacena recursive correctamente."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.watch(str(tmp_path), recursive=True)
        dir_path = str(tmp_path.resolve())
        assert watcher._watched_dirs[dir_path]["recursive"] is True

    def test_unwatch_directory(self, tmp_path):
        """Verifica que unwatch() elimina un directorio de la lista."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.watch(str(tmp_path))
        watcher.unwatch(str(tmp_path))
        assert str(tmp_path.resolve()) not in watcher._watched_dirs

    def test_unwatch_nonexistent(self, tmp_path):
        """Verifica que unwatch() no falla con directorio no monitoreado."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.unwatch(str(tmp_path))  # No debe lanzar excepción

    def test_snapshot_empty_directory(self, tmp_path):
        """Verifica que _snapshot() retorna dict vacío para directorio vacío."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        snapshot = watcher._snapshot(str(tmp_path), "*", False)
        assert snapshot == {}

    def test_snapshot_with_files(self, tmp_path):
        """Verifica que _snapshot() detecta archivos existentes."""
        from src.events.file_watcher import FileWatcher

        (tmp_path / "test.txt").write_text("hello")
        watcher = FileWatcher()
        snapshot = watcher._snapshot(str(tmp_path), "*", False)
        assert len(snapshot) == 1
        assert os.path.join(str(tmp_path), "test.txt") in snapshot

    def test_snapshot_with_pattern(self, tmp_path):
        """Verifica que _snapshot() filtra por patrón."""
        from src.events.file_watcher import FileWatcher

        (tmp_path / "data.csv").write_text("a,b")
        (tmp_path / "readme.txt").write_text("info")
        watcher = FileWatcher()
        snapshot = watcher._snapshot(str(tmp_path), "*.csv", False)
        assert len(snapshot) == 1
        key = next(iter(snapshot.keys()))
        assert key.endswith("data.csv")

    def test_snapshot_recursive(self, tmp_path):
        """Verifica que _snapshot() con recursive=True detecta en subdirectorios."""
        from src.events.file_watcher import FileWatcher

        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "deep.txt").write_text("deep")
        watcher = FileWatcher()
        snapshot = watcher._snapshot(str(tmp_path), "*", True)
        assert len(snapshot) == 1
        assert "deep.txt" in next(iter(snapshot.keys()))

    def test_matches_pattern_star(self):
        """Verifica que _matches_pattern '*' coincide con todo."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        assert watcher._matches_pattern("anything.txt", "*") is True
        assert watcher._matches_pattern("noext", "*") is True

    def test_matches_pattern_extension(self):
        """Verifica que _matches_pattern filtra por extensión."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        assert watcher._matches_pattern("data.csv", "*.csv") is True
        assert watcher._matches_pattern("data.txt", "*.csv") is False

    def test_emit_with_callback(self):
        """Verifica que _emit() llama al callback correctamente."""
        from src.events.file_watcher import FileWatcher

        received = []

        def callback(etype, data):
            received.append((etype, data))

        watcher = FileWatcher(callback=callback)
        watcher._emit("file.created", {"path": "/test/file.txt"})
        assert len(received) == 1
        assert received[0][0] == "file.created"

    def test_emit_without_callback(self):
        """Verifica que _emit() no falla sin callback."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher._emit("file.created", {"path": "/test/file.txt"})

    def test_emit_callback_exception_handled(self):
        """Verifica que excepción en callback no rompe el watcher."""
        from src.events.file_watcher import FileWatcher

        def bad_callback(etype, data):
            raise RuntimeError("fail")

        watcher = FileWatcher(callback=bad_callback)
        watcher._emit("file.created", {"path": "/test"})  # No debe lanzar

    def test_check_directory_detects_new_file(self, tmp_path):
        """Verifica que _check_directory() detecta archivos nuevos."""
        from src.events.file_watcher import FileWatcher

        received = []

        def callback(etype, data):
            received.append((etype, data))

        watcher = FileWatcher(callback=callback)
        watcher.watch(str(tmp_path))
        # Crear archivo nuevo
        (tmp_path / "new_file.txt").write_text("new content")
        # Forzar revisión
        with watcher._lock:
            watcher._check_directory(str(tmp_path.resolve()), "*", False)
        assert len(received) >= 1
        assert received[0][0] == "file.created"
        assert "new_file.txt" in received[0][1]["filename"]

    def test_check_directory_detects_modified_file(self, tmp_path):
        """Verifica que _check_directory() detecta archivos modificados."""
        from src.events.file_watcher import FileWatcher

        received = []

        def callback(etype, data):
            received.append((etype, data))

        watcher = FileWatcher(callback=callback)
        # Crear archivo y tomar baseline
        test_file = tmp_path / "mod.txt"
        test_file.write_text("original")
        watcher.watch(str(tmp_path))
        # Modificar archivo (esperar para cambiar mtime)
        time.sleep(0.05)
        test_file.write_text("modified")
        # Forzar revisión
        with watcher._lock:
            watcher._check_directory(str(tmp_path.resolve()), "*", False)
        # Debería detectar la modificación
        modified_events = [r for r in received if r[0] == "file.modified"]
        assert len(modified_events) >= 1

    def test_watch_same_directory_twice(self, tmp_path):
        """Verifica que agregar el mismo directorio dos veces no duplica."""
        from src.events.file_watcher import FileWatcher

        watcher = FileWatcher()
        watcher.watch(str(tmp_path))
        watcher.watch(str(tmp_path))
        assert len(watcher._watched_dirs) == 1
