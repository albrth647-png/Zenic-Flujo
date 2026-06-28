"""
src.core.logging — Centralized structured logging for Zenic-Flujo (HAT v2).

Merged from the legacy ``src/utils/logger.py`` and ``src/utils/logging_config.py``
during M1.4. Provides a single canonical entry point for obtaining configured
loggers across the entire codebase:

    from src.core.logging import setup_logging
    logger = setup_logging(__name__)

The configuration constants (LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, DATA_DIR,
LOG_FILE) are imported from ``src.core.config`` so changes there propagate
automatically.

Dead code removed (M1.4):
    The legacy ``JSON_FORMAT`` constant from ``logging_config.py`` was never
    referenced anywhere in the codebase — only ``DEFAULT_FORMAT`` and
    ``DEFAULT_DATE_FORMAT`` are kept.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.core.config import DATA_DIR, LOG_DATE_FORMAT, LOG_FORMAT, LOG_LEVEL

__all__ = [
    "DEFAULT_DATE_FORMAT",
    "DEFAULT_FORMAT",
    "AuditLogger",
    "configure_logger",
    "get_log_level",
    "get_logger",
    "setup_logging",
]


# ── Formatos predefinidos ──────────────────────────────────
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logger(
    name: str,
    level: int = logging.INFO,
    log_format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    log_dir: Path | None = None,
    log_file: str = "zenic_flujo.log",
    handlers: list[logging.Handler] | None = None,
) -> logging.Logger:
    """Configura un logger con formato y handlers estandar.

    Es la funcion central para crear loggers en toda la aplicacion.
    Todos los modulos deben usar setup_logging() que llama a esta
    funcion, en lugar de configurar sus propios handlers.

    Args:
        name: Nombre del logger (tipicamente __name__)
        level: Nivel de logging (default: logging.INFO)
        log_format: Formato del mensaje de log
        date_format: Formato de fecha/hora
        log_dir: Directorio para archivos de log (None = no archivo)
        log_file: Nombre del archivo de log
        handlers: Handlers personalizados (opcional)

    Retorna:
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if handlers:
        # Usar handlers proporcionados
        for handler in handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
        return logger

    if not logger.handlers:
        # Handler de consola (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        logger.addHandler(console_handler)

        # Handler de archivo (si hay directorio configurado)
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_dir / log_file,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(log_format, date_format))
            logger.addHandler(file_handler)

    return logger


def get_log_level(level_str: str) -> int:
    """Convierte un string de nivel de log a constante de logging.

    Args:
        level_str: Nivel como string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')

    Retorna:
        Constante de logging (default: logging.INFO si no es valido)
    """
    return getattr(logging, level_str.upper(), logging.INFO)


class AuditLogger:
    """Logger especifico para eventos de auditoria."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or DATA_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, details: str | None = None, ip_address: str | None = None) -> None:
        """Registra un evento de auditoria en el log y en la base de datos."""
        msg = f"[AUDIT] event={event}"
        if details:
            msg += f" details={details}"
        if ip_address:
            msg += f" ip={ip_address}"
        logging.getLogger("audit").info(msg)


def get_logger(name: str = "zenic_flujo") -> logging.Logger:
    """Alias de setup_logging para compatibilidad con imports existentes.

    Args:
        name: Nombre del logger (tipicamente __name__)

    Retorna:
        Logger configurado
    """
    return setup_logging(name)


def setup_logging(name: str = "zenic_flujo") -> logging.Logger:
    """Configura y retorna un logger para el modulo especificado.

    Es la funcion canonica para obtener loggers en toda la aplicacion.
    Usa configure_logger() para la configuracion centralizada.

    Args:
        name: Nombre del logger (tipicamente __name__)

    Retorna:
        Logger configurado con handler de consola y archivo
    """
    return configure_logger(
        name=name,
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        log_format=LOG_FORMAT,
        date_format=LOG_DATE_FORMAT,
        log_dir=DATA_DIR,
        log_file="zenic_flujo.log",
    )
