"""Compatibility shim — re-exports from src.core.logging.

The canonical logging module is src.core.logging (M1.4 refactor).
This shim exists so that legacy imports like
``from src.utils.logger import setup_logging`` continue to work.
"""
from src.core.logging import setup_logging, get_logger, AuditLogger  # noqa: F401

__all__ = ["setup_logging", "get_logger", "AuditLogger"]
