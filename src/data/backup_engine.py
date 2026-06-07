"""
Workflow Determinista — BackupEngine
Backup automático programado con soporte para directorios externos (USB).
"""
import datetime
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class BackupEngine:
    """
    Gestiona backups automáticos de la base de datos.
    
    Soporta:
    - Backup programado (cada N horas)
    - Backup a USB / directorio externo
    - Retención configurable
    """

    def __init__(self):
        self._db = DatabaseManager()
        self._running = False
        self._timer: threading.Timer | None = None

    def backup_now(self, dest_path: str | Path | None = None) -> str:
        """
        Realiza un backup inmediato de la base de datos.
        
        Args:
            dest_path: Directorio destino. Si es None, usa DATA_DIR/backups/
        
        Returns:
            Ruta del archivo de backup creado
        """
        if dest_path is None:
            from src.config import DATA_DIR
            dest_path = DATA_DIR / "backups"

        dest = Path(dest_path)
        dest.mkdir(parents=True, exist_ok=True)

        backup_path = self._db.backup(dest)
        logger.info(f"Backup manual completado: {backup_path}")
        return backup_path

    def start_auto_backup(self, interval_hours: int = 24) -> None:
        """
        Inicia el backup automático programado.
        
        Args:
            interval_hours: Intervalo entre backups en horas
        """
        self._running = True
        self._interval_hours = interval_hours
        self._schedule_next()
        logger.info(f"Backup automático iniciado (cada {interval_hours}h)")

    def stop_auto_backup(self) -> None:
        """Detiene el backup automático."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Backup automático detenido")

    def _schedule_next(self) -> None:
        """Programa el siguiente backup."""
        if not self._running:
            return
        interval_seconds = self._interval_hours * 3600
        self._timer = threading.Timer(interval_seconds, self._auto_backup_tick)
        self._timer.daemon = True
        self._timer.start()

    def _auto_backup_tick(self) -> None:
        """Ejecuta el backup automático y programa el siguiente."""
        try:
            # Usar directorio configurado o por defecto
            from src.config import DATA_DIR
            backup_dir = DATA_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            path = self._db.backup(backup_dir)
            self._cleanup_old_backups(backup_dir)
            logger.info(f"Backup automático: {path}")

        except Exception as e:
            logger.error(f"Error en backup automático: {e}")

        finally:
            self._schedule_next()

    def _cleanup_old_backups(self, backup_dir: Path, max_backups: int = 10) -> None:
        """
        Elimina backups antiguos manteniendo solo los más recientes.
        
        Args:
            backup_dir: Directorio de backups
            max_backups: Número máximo de backups a conservar
        """
        backups = sorted(backup_dir.glob("*.db"), key=os.path.getmtime, reverse=True)
        for old_backup in backups[max_backups:]:
            try:
                old_backup.unlink()
                logger.debug(f"Backup antiguo eliminado: {old_backup}")
            except OSError as e:
                logger.warning(f"No se pudo eliminar backup antiguo {old_backup}: {e}")

    def get_backup_info(self) -> dict:
        """Retorna información sobre los backups disponibles."""
        from src.config import DATA_DIR
        backup_dir = DATA_DIR / "backups"

        if not backup_dir.exists():
            return {"backups": [], "total_backups": 0, "total_size_mb": 0}

        backups = sorted(backup_dir.glob("*.db"), key=os.path.getmtime, reverse=True)
        total_size = sum(f.stat().st_size for f in backups if f.is_file())

        return {
            "backups": [
                {
                    "path": str(f),
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "created_at": datetime.datetime.fromtimestamp(
                        f.stat().st_mtime
                    ).isoformat(),
                }
                for f in backups[:20]
            ],
            "total_backups": len(backups),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }
