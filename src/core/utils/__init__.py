"""src.core.utils — General-purpose helpers (split from src/utils/helpers.py).

Re-exporta todos los simbolos de los 7 submodulos para que la API publica
se mantenga estable::

    from src.core.utils import generate_id, now_iso, resolve_variables

Submodulos:
    ids         — generate_id, generate_secure_token
    time        — now_iso
    text        — truncate
    templating  — safe_get, resolve_variables
    numeric     — coerce_numeric
    binaries    — resolve_binary (+ _RESOLVED_BIN_CACHE)
    cron        — parse_cron_expression, should_run_now
"""

from src.core.utils.binaries import resolve_binary
from src.core.utils.cron import parse_cron_expression, should_run_now
from src.core.utils.ids import generate_id, generate_secure_token
from src.core.utils.numeric import coerce_numeric
from src.core.utils.templating import resolve_variables, safe_get
from src.core.utils.text import truncate
from src.core.utils.time import now_iso

__all__ = [
    "coerce_numeric",
    "generate_id",
    "generate_secure_token",
    "now_iso",
    "parse_cron_expression",
    "resolve_binary",
    "resolve_variables",
    "safe_get",
    "should_run_now",
    "truncate",
]
