"""
Workflow Determinista — Helpers y estado compartido
Funciones auxiliares y objetos singleton para la web app.
"""

import html as _html
import re as _re
import time as _time
import urllib.parse as _urlparse
from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from src.config import (
    FREE_TIER_ALLOWED_TOOLS,
    FREE_TIER_MAX_WORKFLOWS,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_MINUTES,
)
from src.data.database_manager import DatabaseManager
from src.events.bus import EventBus
from src.events.workflow_subscriber import WorkflowSubscriber
from src.license.validator import LicenseValidator
from src.utils.logger import setup_logging
from src.workflow.repository import WorkflowRepository

logger = setup_logging(__name__)

# ── Shared state (configurable via helpers.init()) ───────────

db = DatabaseManager()
repo = WorkflowRepository()
event_bus: EventBus = EventBus()
# WorkflowSubscriber requiere event_bus y event_queue en __init__.
# Inicializamos diferido: se asigna correctamente vía helpers.init() en main.py.
# El valor None indica "no inicializado todavía" — los endpoints que lo usen
# deben verificar o ser llamados después de helpers.init().
workflow_subscriber: WorkflowSubscriber | None = None
_login_attempts: dict[str, list[float]] = {}


def init(event_bus_instance: EventBus | None = None, subscriber: WorkflowSubscriber | None = None) -> None:
    """
    Inicializa el estado compartido con dependencias inyectadas.

    Args:
        event_bus_instance: Instancia de EventBus (crea una nueva si es None)
        subscriber: Instancia de WorkflowSubscriber
    """
    global event_bus, workflow_subscriber
    if event_bus_instance is not None:
        event_bus = event_bus_instance
    if subscriber is not None:
        workflow_subscriber = subscriber


# ── Sanitization ───────────────────────────────────────────

def _sanitize(s: str) -> str:
    """Limpia inputs de texto contra XSS.
    Preserva texto plano, elimina tags HTML, entidades codificadas,
    y URI schemes maliciosos (javascript:, data:, vbscript:).
    """
    unquoted = _urlparse.unquote(s)
    unescaped = _html.unescape(unquoted)
    cleaned = _re.sub(r"<[^>]*>", "", unescaped)
    cleaned = _re.sub(r"<[^>]+$", "", cleaned)
    cleaned = _re.sub(r"(javascript|vbscript|data):", "", cleaned, flags=_re.IGNORECASE)
    return cleaned.strip()


# ── Rate limiting ──────────────────────────────────────────

def _check_rate_limit(ip: str) -> bool:
    """Verifica rate limiting: max LOGIN_MAX_ATTEMPTS intentos FALLIDOS cada LOGIN_WINDOW_MINUTES por IP.
    Los logins exitosos NO cuentan contra el límite — solo los fallidos se registran."""
    now = _time.time()
    window = LOGIN_WINDOW_MINUTES * 60
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]
    if len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS:
        return False
    # NO registrar aquí — solo registrar cuando el login FALLA (ver _register_failed_login)
    return True


def _register_failed_login(ip: str) -> None:
    """Registra un intento de login fallido para rate limiting.
    Los logins exitosos NO llaman esta función, por lo que no cuentan contra el límite."""
    now = _time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(now)


# ── Decorators ─────────────────────────────────────────────

def login_required(f):
    """Decorador: requiere sesión iniciada."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("pages.login_page"))
        return f(*args, **kwargs)
    return decorated


def check_trial():
    """Verifica si el trial ha expirado."""
    validator = LicenseValidator()
    status = validator.get_trial_status()
    return status["status"] == "expired" and status.get("is_trial", False)


def check_free_tier():
    """Decorador: verifica límites del Free Tier antes de crear workflows.
    Si la licencia es trial o free, impone:
    - Máximo FREE_TIER_MAX_WORKFLOWS workflows
    - Solo herramientas en FREE_TIER_ALLOWED_TOOLS en los pasos del workflow
    Retorna 403 con mensaje descriptivo si se viola algún límite.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            validator = LicenseValidator()
            license_info = validator.get_license_info()
            is_restricted = license_info.get("is_trial", False) or license_info.get("type") == "free"

            if is_restricted:
                current_count = len(repo.list_all())
                if current_count >= FREE_TIER_MAX_WORKFLOWS:
                    return jsonify(
                        {"error": "Free tier limitado a 3 workflows. Activa tu licencia para workflows ilimitados."}
                    ), 403

                data = request.get_json() or {}
                steps = data.get("steps", [])
                for step in steps:
                    tool = step.get("tool", "")
                    if tool and tool not in FREE_TIER_ALLOWED_TOOLS:
                        return jsonify(
                            {
                                "error": "Free tier solo permite CRM. "
                                "Activa tu licencia para usar todas las herramientas."
                            }
                        ), 403

            return f(*args, **kwargs)

        return decorated
    return decorator


def require_role(role: str):
    """Decorador: requiere un rol específico para acceder a la ruta."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return jsonify({"error": "No autenticado"}), 401
            user_role = session.get("role", "")
            roles_hierarchy = {"admin": 3, "editor": 2, "viewer": 1}
            if roles_hierarchy.get(user_role, 0) < roles_hierarchy.get(role, 0):
                return jsonify({"error": f"Se requiere rol '{role}'"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
