"""
Blueprints — Auth, Dashboard, License y System API
"""

from flask import Blueprint, jsonify, request, session

from src.core.config import FREE_TIER_ALLOWED_TOOLS, FREE_TIER_MAX_WORKFLOWS
from src.core.logging import setup_logging
from src.core.repositories.audit_repository import AuditRepository
from src.core.repositories.settings_repository import SettingsRepository
from src.core.repositories.user_repository import UserRepository
from src.license.validator import LicenseValidator
from src.schemas import (
    AuthStatusResponse,
    DashboardStatsResponse,
    ErrorResponse,
    LicenseInfoResponse,
    LoginResponse,
    StatusResponse,
)
from src.web.helpers import _check_rate_limit, _register_failed_login, db, login_required, repo, require_role

users = UserRepository()
audit = AuditRepository()
settings = SettingsRepository()

logger = setup_logging(__name__)

bp = Blueprint("auth", __name__)


# ── Metrics helper (M10.4) ──────────────────────────────────

def _record_login_metric(username: str, success: bool, method: str = "password") -> None:
    """Registra un intento de login en TelemetryService (best-effort).

    Métricas NUNCA deben romper el flujo de autenticación.
    """
    try:
        from src.core.observability.telemetry import TelemetryService
        TelemetryService().record_login_attempt(
            username=username,
            status="success" if success else "failed",
            method=method,
        )
    except Exception:
        pass  # metrics are best-effort


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
        import hmac as _hmac
        try:
            parts = stored_hash.split(":")
            algo = parts[1]
            iterations = int(parts[2])
            salt = parts[3]
            expected = parts[4]
            computed = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), iterations).hex()
            # Fix Sprint 3 bug #31: usar hmac.compare_digest para comparación
            # constant-time y prevenir timing attacks (aunque el hash está en
            # DB, no en input, la comparación constant-time es buena práctica).
            return _hmac.compare_digest(computed, expected)
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
                _record_login_metric(username, success=True)
                return jsonify(LoginResponse(status="ok", user=username).model_dump())
        _register_failed_login(ip)
        audit.log("login.failed", f"Intento fallido para {username}", ip)
        _record_login_metric(username, success=False)
        return jsonify(ErrorResponse(error="auth_error", message="Credenciales invalidas").model_dump()), 401

    if not user.get("is_active", 1):
        _register_failed_login(ip)
        _record_login_metric(username, success=False)
        return jsonify(ErrorResponse(error="user_disabled", message="Usuario desactivado").model_dump()), 403

    valid = _verify_password(password, user["password_hash"])
    if not valid:
        _register_failed_login(ip)
        audit.log("login.failed", f"Intento fallido para {username}", ip, user["id"])
        _record_login_metric(username, success=False)
        return jsonify(ErrorResponse(error="auth_error", message="Credenciales invalidas").model_dump()), 401

    session["user"] = username
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session.permanent = True
    audit.log("login.success", f"Login exitoso: {username}", ip, user["id"])
    db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
    db.commit()
    _record_login_metric(username, success=True)
    return jsonify(LoginResponse(status="ok", user=username, role=user["role"]).model_dump())


@bp.route("/api/auth/register", methods=["POST"])
@login_required
@require_role("admin")  # M10.3: solo admin puede registrar nuevos usuarios.
# Antes este endpoint era público y permitía self-signup, lo que abría la puerta
# a creación arbitraria de cuentas. Ahora requiere sesión admin activa.
# Para crear usuarios en flujos self-service, usar el endpoint admin dedicado
# /api/users (POST) que ya tiene @require_role("admin").
def api_register():
    """Register a new user account.

    M10.3: Endpoint cerrado a admins. Antes era público y permitía
    self-registration, lo que era un vector de abuso (creación masiva
    de cuentas, spam, escalada de superficie de ataque).
    """
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
    from src.core.db.backup_engine import BackupEngine
    be = BackupEngine()
    path = be.backup_now()
    return jsonify({"path": path, "status": "completed"})  # Return dict directly (dynamic path)


@bp.route("/api/system/restore", methods=["POST"])
@login_required
@require_role("admin")
def api_system_restore():
    """Restaura la DB activa desde un archivo de backup.

    Body JSON:
        {"backup_path": "<abs-path>"}      — ruta absoluta al backup
        {"backup_filename": "<name>"}      — nombre dentro de DATA_DIR/backups/

    Si se envían ambos, ``backup_path`` tiene prioridad. ``backup_filename``
    se resuelve contra ``DATA_DIR/backups/`` para evitar path traversal
    (no permitimos rutas con ``..`` ni absolutas en este campo).

    SOC 2 A1.3: este endpoint cierra la brecha de "test restoration".

    Returns:
        200 {"success": true, "restored_path": "...", "message": "..."}
        400 validation_error (faltan campos / filename con path traversal)
        404 file_not_found
        409 restore_in_progress
        500 server_error
    """
    from pathlib import Path

    from src.core.config import DATA_DIR
    from src.core.db.backup_engine import BackupEngine

    data = request.get_json(silent=True) or {}
    backup_path_raw = data.get("backup_path")
    backup_filename = data.get("backup_filename")

    if not backup_path_raw and not backup_filename:
        return jsonify(ErrorResponse(
            error="validation_error",
            message="Se requiere 'backup_path' o 'backup_filename'.",
        ).model_dump()), 400

    # Resolución de la ruta final.
    if backup_path_raw:
        # Ruta absoluta explícita: el caller (admin) sabe lo que hace.
        # Aun así, expandimos ~ y resolvemos.
        try:
            resolved = Path(str(backup_path_raw)).expanduser().resolve()
        except (OSError, ValueError) as e:
            return jsonify(ErrorResponse(
                error="validation_error",
                message=f"Ruta inválida: {e}",
            ).model_dump()), 400
    else:
        # Resolución desde DATA_DIR/backups/. Rechazamos cualquier componente
        # que intente escapar del directorio (path traversal).
        fname = str(backup_filename)
        if not fname or fname.startswith("/") or ".." in Path(fname).parts:
            return jsonify(ErrorResponse(
                error="validation_error",
                message="'backup_filename' debe ser un nombre de archivo plano (sin rutas).",
            ).model_dump()), 400
        resolved = (DATA_DIR / "backups" / fname).resolve()
        # Doble check: el path resuelto debe seguir dentro de backups/.
        backups_root = (DATA_DIR / "backups").resolve()
        try:
            resolved.relative_to(backups_root)
        except ValueError:
            return jsonify(ErrorResponse(
                error="validation_error",
                message="'backup_filename' escapa del directorio de backups.",
            ).model_dump()), 400

    be = BackupEngine()
    try:
        restored = be.restore(resolved)
    except FileNotFoundError as e:
        return jsonify(ErrorResponse(
            error="file_not_found",
            message=str(e),
        ).model_dump()), 404
    except ValueError as e:
        # Backup corrupto o no-SQLite.
        return jsonify(ErrorResponse(
            error="invalid_backup",
            message=str(e),
        ).model_dump()), 422
    except RuntimeError as e:
        msg = str(e)
        if "restore" in msg.lower() and "en progreso" in msg.lower():
            return jsonify(ErrorResponse(
                error="restore_in_progress",
                message=msg,
            ).model_dump()), 409
        return jsonify(ErrorResponse(
            error="restore_failed",
            message=msg,
        ).model_dump()), 500
    except Exception as e:
        logger.exception("Error inesperado en /api/system/restore")
        return jsonify(ErrorResponse(
            error="server_error",
            message=f"Error al restaurar: {e}",
        ).model_dump()), 500

    return jsonify({
        "success": True,
        "restored_path": restored,
        "message": "Base de datos restaurada correctamente. Se creó un safety backup previo.",
    })


@bp.route("/api/system/backups", methods=["GET"])
@login_required
@require_role("admin")
def api_system_backups():
    """Lista los backups disponibles en DATA_DIR/backups/.

    Returns:
        200 {"backups": [...], "total_backups": int, "total_size_mb": float}
    """
    from src.core.db.backup_engine import BackupEngine

    be = BackupEngine()
    info = be.get_backup_info()
    return jsonify(info)


@bp.route("/api/system/backup/auto", methods=["GET"])
@login_required
@require_role("admin")
def api_system_backup_auto_get():
    """Retorna el estado del backup automático.

    Returns:
        200 {"enabled": bool, "interval_hours": int|null, "last_backup_at": str|null}
    """
    from src.core.db.backup_engine import BackupEngine

    be = BackupEngine()
    return jsonify(be.get_auto_backup_status())


@bp.route("/api/system/backup/auto", methods=["POST"])
@login_required
@require_role("admin")
def api_system_backup_auto_set():
    """Activa/desactiva el backup automático y/o cambia el intervalo.

    Body JSON:
        {"enabled": true, "interval_hours": 24}  — activa con intervalo
        {"enabled": false}                        — desactiva

    Si ``enabled`` es true, ``interval_hours`` es obligatorio (>= 1).

    Returns:
        200 {"success": true, "enabled": bool, "interval_hours": int|null}
        400 validation_error
        500 server_error
    """
    from src.core.db.backup_engine import BackupEngine

    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    interval_hours = data.get("interval_hours")

    if enabled is None:
        return jsonify(ErrorResponse(
            error="validation_error",
            message="Se requiere 'enabled' (bool).",
        ).model_dump()), 400

    be = BackupEngine()
    try:
        if bool(enabled):
            if interval_hours is None:  # noqa: SIM108
                # Si no se especifica intervalo, usar el actual o el default.
                interval = be._interval_hours or 24
            else:
                interval = int(interval_hours)
            if interval < 1:
                return jsonify(ErrorResponse(
                    error="validation_error",
                    message="'interval_hours' debe ser >= 1.",
                ).model_dump()), 400
            be.start_auto_backup(interval_hours=interval)
            return jsonify({
                "success": True,
                "enabled": True,
                "interval_hours": interval,
            })
        else:
            be.stop_auto_backup()
            return jsonify({
                "success": True,
                "enabled": False,
                "interval_hours": None,
            })
    except ValueError as e:
        return jsonify(ErrorResponse(
            error="validation_error",
            message=str(e),
        ).model_dump()), 400
    except Exception as e:
        logger.exception("Error inesperado en /api/system/backup/auto")
        return jsonify(ErrorResponse(
            error="server_error",
            message=f"Error al configurar backup automático: {e}",
        ).model_dump()), 500


@bp.route("/api/system/logs", methods=["GET"])
@login_required
@require_role("admin")
def api_system_logs():
    """Retorna los últimos 100 registros del audit log.

    Solo admin. Logs contienen IPs, user IDs y eventos sensibles de auth.
    """
    limit = min(int(request.args.get("limit", 100)), 100)
    logs = db.fetchall(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return jsonify(logs)


@bp.route("/api/system/status")
@login_required
@require_role("admin")
def api_system_status():
    """Status del sistema para admins.

    No expone el path exacto de la DB (info disclosure). Solo tipo y versión.
    """
    return jsonify(
        {
            "version": "1.0.0",
            "status": "running",
            "db_type": "sqlite",
        }
    )  # System status endpoint (keeps raw dict for compatibility)
