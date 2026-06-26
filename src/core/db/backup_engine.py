"""
Workflow Determinista — BackupEngine
Backup automático programado con soporte para directorios externos (USB).

Responsabilidades (cobertura SOC 2 A1.3):
- Backup manual (`backup_now`) → Flask route `POST /api/system/backup`.
- Backup automático (`start_auto_backup` / `stop_auto_backup`) →
  Flask routes `POST/GET /api/system/backup/auto`.
- Listado de backups disponibles (`get_backup_info`) →
  Flask route `GET /api/system/backups`.
- Restauración de backups (`restore`) → Flask route `POST /api/system/restore`.

Diseño:
- Singleton (mismo patrón que `DatabaseManager`). Es necesario porque el
  auto-backup se arranca en `main.py:39` sobre una instancia y los endpoints
  Flask instancian otra (`auth.py: BackupEngine()`). Si no se compartiera el
  estado interno (`_running`, `_timer`, `_interval_hours`, `_last_backup_at`),
  los endpoints `start/stop_auto_backup` no afectarían al timer ya corriendo.
- Lock dedicado `_restore_lock` para serializar restauraciones (operación
  destructiva: reemplaza la DB activa). Concurrent restore = corrupción.
- Lock dedicado `_auto_lock` para start/stop del timer (evitar race conditions
  si dos requests llegan simultáneamente).
"""

import datetime
import os
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Magic header de SQLite — primeros 16 bytes de todo archivo .db/.sqlite válido.
# Referencia: https://www.sqlite.org/fileformat.html#the_database_header
_SQLITE_MAGIC = b"SQLite format 3\x00"


class BackupEngine:
    """
    Gestiona backups automáticos de la base de datos.

    Soporta:
    - Backup programado (cada N horas)
    - Backup a USB / directorio externo
    - Retención configurable
    - Restauración desde un archivo de backup (SOC 2 A1.3)
    - Listado e inspección de backups disponibles

    Singleton: la primera instanciación crea el estado compartido; las
    siguientes `BackupEngine()` devuelven la misma instancia. Esto permite
    que `main.py` arranque el auto-backup y los endpoints Flask lo
    controlen (start/stop) sobre el mismo objeto.
    """

    _instance: "BackupEngine | None" = None
    _instance_lock = threading.Lock()

    # Lock dedicado para serializar restauraciones (operación destructiva).
    # No se usa el mismo lock que el auto-backup porque una restauración
    # puede correr mientras un backup automático está en vuelo — el backup
    # fallará limpiamente (DB cerrada), pero el restore debe poder tomar
    # el control exclusivo.
    _restore_lock = threading.Lock()
    _restore_in_progress = False

    # Lock para coordinar start/stop del timer de auto-backup.
    _auto_lock = threading.Lock()

    def __new__(cls) -> "BackupEngine":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._instance_lock:
            if self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._running = False
            self._timer: threading.Timer | None = None
            self._interval_hours: int = 24
            # ISO timestamp del último backup completado (manual o automático).
            # None si nunca se ha ejecutado un backup en esta instancia.
            self._last_backup_at: str | None = None

    # ── Backup manual ────────────────────────────────────────

    def backup_now(self, dest_path: str | Path | None = None) -> str:
        """
        Realiza un backup inmediato de la base de datos.

        Args:
            dest_path: Directorio destino. Si es None, usa DATA_DIR/backups/

        Returns:
            Ruta del archivo de backup creado
        """
        if dest_path is None:
            from src.core.config import DATA_DIR

            dest_path = DATA_DIR / "backups"

        dest = Path(dest_path)
        dest.mkdir(parents=True, exist_ok=True)

        backup_path = self._db.backup(dest)
        self._last_backup_at = datetime.datetime.now().isoformat()
        logger.info(f"Backup manual completado: {backup_path}")
        return backup_path

    # ── Backup automático ────────────────────────────────────

    def start_auto_backup(self, interval_hours: int = 24) -> None:
        """
        Inicia el backup automático programado.

        Idempotente: si ya está corriendo, cancela el timer anterior y
        reprograma con el nuevo intervalo.

        Args:
            interval_hours: Intervalo entre backups en horas (mínimo 1)
        """
        if interval_hours < 1:
            raise ValueError("interval_hours debe ser >= 1")

        with self._auto_lock:
            # Si ya hay un timer corriendo, cancelarlo antes de reprogramar.
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            self._running = True
            self._interval_hours = interval_hours
            self._schedule_next()
            logger.info(f"Backup automático iniciado (cada {interval_hours}h)")

    def stop_auto_backup(self) -> None:
        """
        Detiene el backup automático.

        Idempotente: si no hay timer corriendo, no hace nada (no-op).
        Limpia `_running` y `_timer` para que `get_auto_backup_status()`
        refleje el estado correcto.
        """
        with self._auto_lock:
            self._running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            logger.info("Backup automático detenido")

    def get_auto_backup_status(self) -> dict:
        """
        Retorna el estado actual del backup automático.

        Returns:
            Dict con: enabled (bool), interval_hours (int|None),
            last_backup_at (str|None, ISO)
        """
        return {
            "enabled": self._running,
            "interval_hours": self._interval_hours if self._running else None,
            "last_backup_at": self._last_backup_at,
        }

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
            from src.core.config import DATA_DIR

            backup_dir = DATA_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            path = self._db.backup(backup_dir)
            self._last_backup_at = datetime.datetime.now().isoformat()
            self._cleanup_old_backups(backup_dir)
            logger.info(f"Backup automático: {path}")

        except (OSError, sqlite3.Error, ValueError) as e:
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

    # ── Listado / info de backups ────────────────────────────

    def get_backup_info(self) -> dict:
        """
        Retorna información sobre los backups disponibles en DATA_DIR/backups/.

        Cada backup incluye:
        - filename (str): nombre del archivo
        - path (str): ruta absoluta
        - name (str): alias de filename (backward compat)
        - size_bytes (int): tamaño en bytes
        - size_mb (float): tamaño en MiB (backward compat)
        - created_at (str, ISO): fecha de modificación del archivo
        - is_valid (bool): el archivo abre como SQLite válido

        Returns:
            Dict con: backups (list), total_backups (int), total_size_mb (float)
        """
        from src.core.config import DATA_DIR

        backup_dir = DATA_DIR / "backups"

        if not backup_dir.exists():
            return {"backups": [], "total_backups": 0, "total_size_mb": 0}

        # Incluimos .db y .sqlite para ser permisivos con backups externos.
        patterns = ("*.db", "*.sqlite", "*.sqlite3")
        files: list[Path] = []
        for pat in patterns:
            files.extend(backup_dir.glob(pat))
        # Deduplica (por si un archivo coincide con varios patterns) y ordena
        # por mtime descendente (más reciente primero).
        files = sorted(set(files), key=os.path.getmtime, reverse=True)

        total_size = sum(f.stat().st_size for f in files if f.is_file())

        return {
            "backups": [
                {
                    "filename": f.name,
                    "path": str(f),
                    "name": f.name,  # backward compat
                    "size_bytes": f.stat().st_size,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "created_at": datetime.datetime.fromtimestamp(
                        f.stat().st_mtime
                    ).isoformat(),
                    "is_valid": self._is_valid_sqlite(f),
                }
                for f in files[:20]
            ],
            "total_backups": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    @staticmethod
    def _is_valid_sqlite(path: Path) -> bool:
        """
        Valida que un archivo sea una DB SQLite legible.

        Estrategia:
        1. Lee los primeros 16 bytes y compara contra el magic header
           ``b"SQLite format 3\\x00"``. Es la verificación más barata y
           determinista (sqlite.org/fileformat.html#the_database_header).
        2. Abre el archivo en modo read-only y ejecuta ``PRAGMA integrity_check``
           para confirmar que no está corrupto. Cualquier error → False.

        Args:
            path: Ruta al archivo a validar

        Returns:
            True si el archivo es una DB SQLite válida, False en caso contrario
        """
        try:
            with open(path, "rb") as fh:
                header = fh.read(16)
            if header != _SQLITE_MAGIC:
                return False
            # integrity_check es la verificación canónica de no-corrupción.
            # mode=ro evita bloqueos contra el archivo activo en producción.
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                cur = conn.execute("PRAGMA integrity_check")
                result = cur.fetchone()
                # integrity_check devuelve ("ok",) si la DB está sana.
                return bool(result) and result[0] == "ok"
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            return False

    # ── Restauración ─────────────────────────────────────────

    def restore(self, backup_path: str | Path) -> str:
        """
        Restaura la base de datos activa desde un archivo de backup.

        Operación destructiva: reemplaza la DB activa (DB_PATH) con el
        contenido del backup. Antes de sobrescribir, crea un safety backup
        timestamped del estado actual, de modo que un restore equivocado
        pueda deshacerse manualmente.

        Pasos:
        1. Adquirir `_restore_lock` (fail-fast si ya hay un restore en curso).
        2. Validar que el archivo exista y sea SQLite válido (header +
           integrity_check).
        3. Cerrar todas las conexiones abiertas a la DB activa.
        4. Crear un safety backup del estado actual en
           ``DATA_DIR/backups/pre_restore_<timestamp>.db``.
        5. Copiar el backup sobre la DB activa atómicamente (tmp + rename).
        6. Reabrir la conexión (lazy: la próxima llamada a
           `DatabaseManager.get_connection()` la abre).
        7. Auditar el evento y loguear.

        Args:
            backup_path: Ruta al archivo de backup (.db o .sqlite) a restaurar

        Returns:
            Ruta absoluta de la DB restaurada (DB_PATH)

        Raises:
            FileNotFoundError: si el archivo no existe
            ValueError: si el archivo no es una DB SQLite válida
            RuntimeError: si ya hay un restore en progreso
            sqlite3.Error / OSError: si falla la copia o la reapertura
        """
        src = Path(backup_path).expanduser().resolve()

        # ── 1. Lock anti-restore-concurrente ─────────────────
        # `acquire(blocking=False)` → si no se obtiene, otro restore está
        # corriendo. Fallamos rápido en vez de encolar (un restore encolado
        # podría confundir al usuario: ve "éxito" pero la DB quedó en estado
        # intermedio del primer restore).
        if not self._restore_lock.acquire(blocking=False):
            raise RuntimeError(
                "Ya hay una restauración de backup en progreso. "
                "Espera a que termine antes de iniciar otra."
            )
        try:
            self._restore_in_progress = True

            # ── 2. Validación del archivo origen ──────────────
            if not src.is_file():
                raise FileNotFoundError(f"Archivo de backup no encontrado: {src}")
            if not self._is_valid_sqlite(src):
                raise ValueError(
                    f"El archivo no es una DB SQLite válida o está corrupto: {src}"
                )

            # Resolvemos la ruta destino desde el singleton DatabaseManager.
            # Accedemos al atributo privado `_db_path` porque DatabaseManager
            # no expone un getter público (es un detalle de implementación
            # estable desde la M4). Si cambia, este break se detecta en tests.
            dest = Path(self._db._db_path)  # noqa: SLF001 — acceso intencional

            logger.warning(
                f"INICIO restore: src={src} dest={dest} "
                f"(operación destructiva — se creará safety backup)"
            )

            # ── 3. Cerrar conexiones activas ──────────────────
            # close_all() cierra la conexión del hilo actual. En Flask
            # (single-threaded por request) es suficiente. El modo WAL de
            # SQLite permite que otros hilos lectores sigan sin bloquear,
            # pero un rename del archivo subyacente fallaría si hay file
            # handles abiertos en Windows; en POSIX (Linux/macOS) el rename
            # es atómico y los handles abiertos siguen apuntando al inodo
            # antiguo. Cerramos por higiene.
            self._db.close_all()

            # ── 4. Safety backup del estado actual ────────────
            # Solo si la DB activa existe y es válida. Si la DB activa está
            # corrupta o ausente, no tiene sentido hacer safety backup.
            safety_path: Path | None = None
            if dest.is_file() and self._is_valid_sqlite(dest):
                from src.core.config import DATA_DIR

                safety_dir = DATA_DIR / "backups"
                safety_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safety_path = safety_dir / f"pre_restore_{ts}.db"
                try:
                    shutil.copy2(dest, safety_path)
                    logger.info(
                        f"Safety backup creado antes del restore: {safety_path}"
                    )
                except OSError as e:
                    # Si el safety backup falla, NO continuamos: perderíamos
                    # la única forma de deshacer el restore.
                    raise RuntimeError(
                        f"No se pudo crear el safety backup previo al restore: {e}. "
                        "Operación abortada para preservar la DB actual."
                    ) from e

            # ── 5. Copia atómica: tmp + rename ────────────────
            # Escribir directamente sobre `dest` con un `shutil.copy2(src, dest)`
            # dejaría la DB en estado parcial si el proceso muere a mitad de
            # copia. Usamos un archivo temporal en el mismo directorio (para
            # que el rename sea atómico en POSIX) y luego `os.replace` (que
            # sobrescribe atómicamente).
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Side-effect de WAL: borrar los archivos -wal y -shm que pudieran
            # quedar de la sesión anterior (si no, SQLite los reusaría al
            # reabrir y vería datos inconsistentes con la DB restaurada).
            for suffix in ("-wal", "-shm"):
                sidecar = dest.with_name(dest.name + suffix)
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError as e:
                        logger.warning(
                            f"No se pudo eliminar sidecar {sidecar}: {e}"
                        )

            try:
                with tempfile.NamedTemporaryFile(
                    dir=str(dest.parent),
                    prefix=".restore_tmp_",
                    suffix=".db",
                    delete=False,
                ) as tmp_fh:
                    tmp_path = Path(tmp_fh.name)
                shutil.copy2(src, tmp_path)
                os.replace(tmp_path, dest)
            except (OSError, shutil.Error) as e:
                # Limpieza del tmp si falló el copy o el rename.
                if "tmp_path" in locals() and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                # Si hicimos safety backup, intentar revertir.
                if safety_path is not None and safety_path.exists():
                    try:
                        shutil.copy2(safety_path, dest)
                        logger.warning(
                            f"Restore fallido; DB revertida al safety backup: {safety_path}"
                        )
                    except OSError as revert_err:
                        logger.error(
                            f"Restore fallido Y no se pudo revertir desde {safety_path}: "
                            f"{revert_err}. La DB puede quedar en estado inconsistente."
                        )
                raise RuntimeError(f"Error copiando backup a DB activa: {e}") from e

            # ── 6. Reabrir la conexión (lazy) ─────────────────
            # No llamamos get_connection() aquí: si la abrimos en este hilo
            # y luego el request Flask termina, la conexión queda colgando en
            # el thread-local. Es mejor dejar que el próximo endpoint la abra.
            # Pero sí forzamos una verificación de integridad post-restore.
            try:
                conn = sqlite3.connect(str(dest))
                try:
                    cur = conn.execute("PRAGMA integrity_check")
                    result = cur.fetchone()
                    if not result or result[0] != "ok":
                        raise sqlite3.DatabaseError(
                            f"Post-restore integrity_check falló: {result}"
                        )
                finally:
                    conn.close()
            except sqlite3.Error as e:
                # La DB se copió pero no pasa integrity_check: grave. Lo
                # logueamos y relanzamos; el safety backup sigue existiendo.
                logger.error(
                    f"Restore completado pero integrity_check falló: {e}. "
                    f"Safety backup disponible en: {safety_path}"
                )
                raise

            # ── 7. Auditar y loguear ──────────────────────────
            try:
                self._db.audit(
                    "backup.restore",
                    f"DB restaurada desde {src.name}",
                )
            except Exception as audit_err:
                # El audit es best-effort: no debe romper el flujo del restore
                # (que ya tuvo éxito en este punto).
                logger.warning(f"Restore OK pero audit falló: {audit_err}")

            logger.warning(
                f"FIN restore exitoso: {src} -> {dest} (safety: {safety_path})"
            )
            return str(dest)

        finally:
            self._restore_in_progress = False
            self._restore_lock.release()
