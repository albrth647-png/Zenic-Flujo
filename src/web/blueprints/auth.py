"""
Blueprints — Auth, Dashboard, License y System API
"""

from flask import Blueprint, jsonify, request, session

from src.config import FREE_TIER_ALLOWED_TOOLS, FREE_TIER_MAX_WORKFLOWS
from src.data.audit_repository import AuditRepository
from src.data.settings_repository import SettingsRepository
from src.data.user_repository import UserRepository
from src.license.validator import LicenseValidator
from src.schemas import (
    AuthStatusResponse,
    DashboardStatsResponse,
    ErrorResponse,
    LicenseInfoResponse,
    LoginResponse,
    StatusResponse,
)
from src.utils.logger import setup_logging
from src.web.helpers import _check_rate_limit, _register_failed_login, db, login_required, repo, require_role

users = UserRepository()
audit = AuditRepository()
settings = SettingsRepository()

logger = setup_logging(__name__)

bp = Blueprint("auth", __name__)


# ── Helpers de verificación de contraseña ───────────────────

def _verify_password(password: str, stored_hash: str) -> bool:
    """Verifica contraseña contra hash en formato bcrypt o pbkdf2."""
    if stored_hash.startswith("$2"):
        # Formato bcrypt
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except ImportError:
            return False
        except (ValueError, TypeError):
            return False
    elif stored_hash.startswith("pbkdf2:"):
        # Formato pbkdf2:sha256:iterations:salt:hash
        import hashlib
        try:
            parts = stored_hash.split(":")
            algo = parts[1]
            iterations = int(parts[2])
            salt = parts[3]
            expected = parts[4]
            computed = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), iterations).hex()
            return computed == expected
        except (IndexError, ValueError, TypeError):
            return False
    return False


# ── API: Auth (multi-user) ──────────────────────────────────

@bp.route("/api/auth/login", methods=["POST"])
def api_login():
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify(ErrorResponse(error="rate_limit", message="Demasiados intentos. Espera 15 minutos.").model_dump()), 429
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")

    user = users.get_user_by_username(username)
    if not user:
        stored_hash = settings.get_setting("admin_password_hash")
        if stored_hash and isinstance(stored_hash, str) and _verify_password(password, stored_hash):
                session["user"] = username
                session["user_id"] = 1
                session["role"] = "admin"
                session.permanent = True
                audit.log("login.success", f"Login legacy: {username}", ip, 1)
                return jsonify(LoginResponse(status="ok", user=username).model_dump())
        _register_failed_login(ip)
        audit.log("login.failed", f"Intento fallido para {username}", ip)
        return jsonify(ErrorResponse(error="auth_error", message="Credenciales invalidas").model_dump()), 401

    if not user.get("is_active", 1):
        _register_failed_login(ip)
        return jsonify(ErrorResponse(error="user_disabled", message="Usuario desactivado").model_dump()), 403

    valid = _verify_password(password, user["password_hash"])
    if not valid:
        _register_failed_login(ip)
        audit.log("login.failed", f"Intento fallido para {username}", ip, user["id"])
        return jsonify(ErrorResponse(error="auth_error", message="Credenciales invalidas").model_dump()), 401

    session["user"] = username
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session.permanent = True
    audit.log("login.success", f"Login exitoso: {username}", ip, user["id"])
    db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
    db.commit()
    return jsonify(LoginResponse(status="ok", user=username, role=user["role"]).model_dump())


@bp.route("/api/auth/register", methods=["POST"])
def api_register():
    """Register a new user account."""
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    display_name = data.get("display_name", username)
    email = data.get("email", "")

    # ── Validaciones ───────────────────────────────────────
    if not username or not password:
        return jsonify(ErrorResponse(error="validation_error", message="Usuario y contrasena son requeridos").model_dump()), 400

    if len(username) < 3:
        return jsonify(ErrorResponse(error="validation_error", message="El usuario debe tener al menos 3 caracteres").model_dump()), 400

    if len(password) < 6:
        return jsonify(ErrorResponse(error="validation_error", message="La contrasena debe tener al menos 6 caracteres").model_dump()), 400

    # Verificar que el usuario no exista
    existing = users.get_user_by_username(username)
    if existing:
        return jsonify(ErrorResponse(error="duplicate_user", message="El nombre de usuario ya esta registrado").model_dump()), 409

    try:
        user = users.create_user(
            username=username,
            password=password,
            role="editor",
            display_name=display_name,
            email=email,
        )
        # Auto-login after registration
        session["user"] = username
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session.permanent = True

        ip = request.remote_addr or "unknown"
        audit.log("register.success", f"Nuevo usuario registrado: {username}", ip, user["id"])

        return jsonify(LoginResponse(status="ok", user=username, role=user["role"], id=user["id"]).model_dump()), 201
    except Exception as e:
        logger.error(f"Error registrando usuario: {e}")
        return jsonify(ErrorResponse(error="server_error", message="Error al crear la cuenta. Intenta de nuevo.").model_dump()), 500


@bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.pop("user", None)
    return jsonify(StatusResponse(status="ok").model_dump())


@bp.route("/api/auth/status")
def api_auth_status():
    authenticated = "user" in session
    return jsonify(AuthStatusResponse(
        authenticated=authenticated,
        username=session.get("user") if authenticated else None,
        role=session.get("role") if authenticated else None,
    ).model_dump())


# ── API: Dashboard ─────────────────────────────────────────

@bp.route("/api/dashboard/stats")
@login_required
def api_dashboard_stats():
    stats = repo.get_stats()
    trial = LicenseValidator().get_trial_status()
    return jsonify(DashboardStatsResponse(stats=stats, trial=trial).model_dump())


@bp.route("/api/dashboard/timeline")
@login_required
def api_dashboard_timeline():
    """Retorna ejecuciones agrupadas por día para gráficos."""
    days = int(request.args.get("days", 14))
    raw = db.fetchall(
        """SELECT DATE(started_at) as day, status, COUNT(*) as count
           FROM workflow_executions
           WHERE started_at >= datetime('now', ? || ' days')
           GROUP BY day, status
           ORDER BY day ASC""",
        (f"-{days}",),
    )
    tools_raw = db.fetchall(
        """SELECT tool, COUNT(*) as count
           FROM workflow_step_logs
           GROUP BY tool
           ORDER BY count DESC LIMIT 10"""
    )
    daily: dict[str, dict] = {}
    for r in raw:
        day = r["day"]
        if day not in daily:
            daily[day] = {"day": day, "completed": 0, "failed": 0, "total": 0}
        status = r["status"]
        count = r["count"]
        if status == "completed":
            daily[day]["completed"] += count
        elif status == "failed":
            daily[day]["failed"] += count
        daily[day]["total"] += count

    return jsonify(
        {
            "daily": sorted(daily.values(), key=lambda x: x["day"]),
            "tools": tools_raw,
        }
    )


# ── API: License ───────────────────────────────────────────

@bp.route("/api/license/validate", methods=["POST"])
def api_validate_license():
    data = request.get_json() or {}
    key = data.get("key", "")
    validator = LicenseValidator()
    result = validator.validate(key)
    if result["valid"]:
        validator.activate_key(key, result.get("type", "individual"), result.get("client_name", ""))
    # Return raw result dict (license validation returns dynamic schema)
    return jsonify(result)


@bp.route("/api/license/info")
def api_license_info():
    """Retorna información completa de la licencia incluyendo límites del Free Tier."""
    validator = LicenseValidator()
    info = validator.get_license_info()
    info["is_free"] = info.get("type") == "free"
    info["max_workflows"] = FREE_TIER_MAX_WORKFLOWS if info.get("is_free") or info.get("is_trial") else -1
    info["allowed_tools"] = FREE_TIER_ALLOWED_TOOLS if info.get("is_free") or info.get("is_trial") else ["all"]
    return jsonify(LicenseInfoResponse(**info).model_dump())


# ── API: System ────────────────────────────────────────────

@bp.route("/api/system/backup", methods=["POST"])
@login_required
@require_role("admin")
def api_system_backup():
    from src.data.backup_engine import BackupEngine
    be = BackupEngine()
    path = be.backup_now()
    return jsonify({"path": path, "status": "completed"})  # Return dict directly (dynamic path)



@bp.route("/api/system/logs", methods=["GET"])
@login_required
def api_system_logs():
    """Retorna los últimos 100 registros del audit log."""
    limit = min(int(request.args.get("limit", 100)), 100)
    logs = db.fetchall(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return jsonify(logs)


@bp.route("/api/system/status")
def api_system_status():
    return jsonify(
        {
            "version": "1.0.0",
            "status": "running",
            "db_path": str(db._db_path),
        }
    )  # System status endpoint (keeps raw dict for compatibility)
