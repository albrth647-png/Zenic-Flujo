"""
Workflow Determinista — Logging Estructurado
"""
import logging
import sys
from pathlib import Path

from src.config import DATA_DIR, LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT


class AuditLogger:
    """Logger específico para eventos de auditoría."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or DATA_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, details: str | None = None, ip_address: str | None = None) -> None:
        """Registra un evento de auditoría en el log y en la base de datos."""
        msg = f"[AUDIT] event={event}"
        if details:
            msg += f" details={details}"
        if ip_address:
            msg += f" ip={ip_address}"
        logging.getLogger("audit").info(msg)


def setup_logging(name: str = "workflow_determinista") -> logging.Logger:
    """Configura el logging del sistema."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(handler)

        # File handler
        log_dir = DATA_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "workflow_determinista.log",
            encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger
