"""
Workflow Determinista — FileWatcher
Monitorea cambios en directorios del sistema de archivos.
"""

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class FileWatcher(threading.Thread):
    """
    Monitorea un directorio en busca de archivos nuevos o modificados.

    Cuando detecta cambios, emite eventos a través de un callback.
    """

    def __init__(self, callback: Callable | None = None, interval: float = 5.0):
        """
        Args:
            callback: Función llamada con (event_type, data) cuando hay cambios
            interval: Intervalo de revisión en segundos
        """
        super().__init__(daemon=True)
        self._callback = callback
        self._interval = interval
        self._watched_dirs: dict[str, set[str]] = {}  # dir -> set of baselines
        self._running = False
        self._lock = threading.Lock()

    def watch(self, directory: str, pattern: str = "*", recursive: bool = False) -> None:
        """
        Comienza a monitorear un directorio.

        Args:
            directory: Ruta del directorio a monitorear
            pattern: Patrón de archivos ("*.csv", "*.txt")
            recursive: Si debe monitorear subdirectorios
        """
        dir_path = str(Path(directory).resolve())
        with self._lock:
            if dir_path not in self._watched_dirs:
                baseline = self._snapshot(dir_path, pattern, recursive)
                self._watched_dirs[dir_path] = {
                    "pattern": pattern,
                    "recursive": recursive,
                }
                # Guardamos el baseline en un dict separado
                if not hasattr(self, "_baselines"):
                    self._baselines = {}
                self._baselines[dir_path] = baseline
                logger.info(f"Monitoreando: {dir_path} (patrón: {pattern})")

    def unwatch(self, directory: str) -> None:
        """Deja de monitorear un directorio."""
        dir_path = str(Path(directory).resolve())
        with self._lock:
            self._watched_dirs.pop(dir_path, None)
            if hasattr(self, "_baselines"):
                self._baselines.pop(dir_path, None)
            logger.info(f"Dejando de monitorear: {dir_path}")

    def run(self) -> None:
        """Hilo principal de monitoreo."""
        self._running = True
        logger.info("FileWatcher iniciado")

        while self._running:
            try:
                with self._lock:
                    for dir_path, config in list(self._watched_dirs.items()):
                        self._check_directory(
                            dir_path,
                            config["pattern"],
                            config["recursive"],
                        )
            except OSError as e:
                logger.error(f"Error en FileWatcher: {e}")

            time.sleep(self._interval)

    def stop(self) -> None:
        """Detiene el monitoreo."""
        self._running = False
        logger.info("FileWatcher detenido")

    def _snapshot(self, directory: str, pattern: str, recursive: bool) -> dict[str, float]:
        """Toma una instantánea del estado actual de los archivos."""
        snapshot = {}

        if recursive:
            for root, _, files in os.walk(directory):
                for fname in files:
                    if self._matches_pattern(fname, pattern):
                        fpath = os.path.join(root, fname)
                        try:
                            snapshot[fpath] = os.path.getmtime(fpath)
                        except OSError:
                            continue
        else:
            for fname in os.listdir(directory):
                if self._matches_pattern(fname, pattern):
                    fpath = os.path.join(directory, fname)
                    try:
                        snapshot[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        continue

        return snapshot

    def _check_directory(self, directory: str, pattern: str, recursive: bool) -> None:
        """Compara el estado actual con la última instantánea."""
        if not hasattr(self, "_baselines"):
            return

        current = self._snapshot(directory, pattern, recursive)
        baseline = self._baselines.get(directory, {})

        # Archivos nuevos
        for fpath in current:
            if fpath not in baseline:
                logger.info(f"Archivo nuevo detectado: {fpath}")
                self._emit(
                    "file.created",
                    {
                        "path": fpath,
                        "filename": os.path.basename(fpath),
                        "size": os.path.getsize(fpath) if os.path.exists(fpath) else 0,
                        "extension": os.path.splitext(fpath)[1],
                    },
                )

        # Archivos modificados
        for fpath, mtime in current.items():
            if fpath in baseline and mtime != baseline.get(fpath):
                logger.info(f"Archivo modificado detectado: {fpath}")
                self._emit(
                    "file.modified",
                    {
                        "path": fpath,
                        "filename": os.path.basename(fpath),
                    },
                )

        # Actualizar baseline
        self._baselines[directory] = current

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Verifica si un archivo coincide con el patrón."""
        if pattern == "*":
            return True
        import fnmatch

        return fnmatch.fnmatch(filename, pattern)

    def _emit(self, event_type: str, data: dict) -> None:
        """Emite un evento a través del callback."""
        if self._callback:
            try:
                self._callback(event_type, data)
            # El callback puede lanzar cualquier excepción — la capturamos para
            # que el FileWatcher no se detenga por un error en un callback.
            except Exception as e:
                logger.error(f"Error en callback de FileWatcher: {e}")
