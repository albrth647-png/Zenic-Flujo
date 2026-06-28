"""src.core.utils.time — Utilidades de timestamp.

Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Retorna timestamp actual en ISO 8601."""
    return datetime.now(UTC).isoformat()


__all__ = ["now_iso"]
