"""
Zenic-Flijo — AuditRepository
===============================

Repositorio dedicado para el registro de auditoría.

Extraído de DatabaseManager (src/data/database_manager.py) para separar
responsabilidades y romper la clase dios.
"""

from __future__ import annotations

import os
import random

from src.data.interfaces import DatabaseInterface
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AuditRepository:
    """
    Repositorio de auditoría.

    Gestiona la tabla audit_log:
    - log: registrar un evento de auditoría
    - get_recent: obtener eventos recientes
    - count: contar eventos
    - purge: limpieza automática de registros viejos

    No debe contener lógica de negocio.
    Solo registro y consulta de eventos de auditoría.
    """

    def __init__(self, db: DatabaseInterface | None = None, max_logs: int | None = None):
        """
        Args:
            db: Instancia de DatabaseInterface. Si es None, usa el singleton DatabaseManager.
            max_logs: Máximo de registros antes de purgar (default: 10000 o WFD_MAX_AUDIT_LOGS)
        """
        if db is not None:
            self._db = db
        else:
            from src.data.database_manager import DatabaseManager
            self._db = DatabaseManager()
        self._max_logs = max_logs or int(os.environ.get("WFD_MAX_AUDIT_LOGS", "10000"))

    # ── Registro ─────────────────────────────────────────────

    def log(
        self,
        event: str,
        details: str | None = None,
        ip_address: str | None = None,
        user_id: int | None = None,
    ) -> None:
        """
        Registra un evento de auditoría.

        Args:
            event: Nombre del evento (ej. 'login.success', 'user.created')
            details: Detalles adicionales del evento
            ip_address: Dirección IP del usuario
            user_id: ID del usuario que realizó la acción
        """
        self._db.execute(
            "INSERT INTO audit_log (event, details, ip_address, user_id) VALUES (?, ?, ?, ?)",
            (event, details, ip_address, user_id),
        )

        # Purgar cada ~10 inserciones para mantener el tamaño controlado
        if random.random() < 0.1:
            self._purge_if_needed()

        self._db.commit()

    # ── Consultas ────────────────────────────────────────────

    def get_recent(self, limit: int = 100) -> list[dict]:
        """
        Retorna los eventos de auditoría más recientes.

        Args:
            limit: Máximo de eventos a retornar

        Returns:
            Lista de dicts con eventos ordenados por fecha descendente
        """
        return self._db.fetchall(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    def count(self) -> int:
        """
        Cuenta el total de eventos de auditoría.

        Returns:
            Número total de eventos
        """
        row = self._db.fetchone("SELECT COUNT(*) as c FROM audit_log")
        return row["c"] if row else 0

    def count_by_event(self, event: str) -> int:
        """
        Cuenta eventos de un tipo específico.

        Args:
            event: Tipo de evento a contar

        Returns:
            Número de eventos de ese tipo
        """
        row = self._db.fetchone(
            "SELECT COUNT(*) as c FROM audit_log WHERE event = ?",
            (event,),
        )
        return row["c"] if row else 0

    # ── Limpieza ─────────────────────────────────────────────

    def purge(self, max_records: int | None = None) -> int:
        """
        Elimina registros viejos para mantener el tamaño máximo.

        Args:
            max_records: Máximo de registros a mantener (default: self._max_logs)

        Returns:
            Número de registros eliminados
        """
        max_records = max_records or self._max_logs
        count = self.count()
        if count <= max_records:
            return 0

        delete_count = count - max_records
        self._db.execute(
            "DELETE FROM audit_log WHERE id IN (SELECT id FROM audit_log ORDER BY created_at ASC LIMIT ?)",
            (delete_count,),
        )
        self._db.commit()
        logger.info(f"AuditRepository: {delete_count} registros purgados")
        return delete_count

    def _purge_if_needed(self) -> None:
        """Purga si se supera el máximo configurado."""
        count = self.count()
        if count > self._max_logs:
            self.purge()
