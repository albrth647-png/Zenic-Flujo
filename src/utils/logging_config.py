"""
Zenic-Flujo — Configuracion Centralizada de Logging
=====================================================

Define la configuracion estandar de logging para toda la aplicacion.
Todas las funciones de logging deben usar configure_logger() o
setup_logging() (en src.utils.logger) en lugar de configurar
handlers manualmente.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logger(
    name: str,
    level: int = logging.INFO,
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    date_format: str = "%Y-%m-%d %H:%M:%S",
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


# ── Formatos predefinidos ──────────────────────────────────

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
