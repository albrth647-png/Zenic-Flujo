"""
SSO — Flask Routes para SAML y OIDC login/callback endpoints.
"""

from __future__ import annotations

from typing import Any

from src.data.database_manager import DatabaseManager
from src.security.sso.mapping import create_or_link_user, link_existing_user
from src.security.sso.oidc import OIDCHandler
from src.security.sso.saml import SAMLHandler
from src.security.sso.session import create_sso_session


# legítimo: Flask app no tipado por compatibilidad
def register_sso_routes(app: Any, db: DatabaseManager | None = None) -> None:
    if db is None:
        db = DatabaseManager()
    """Registra las rutas SSO en la aplicacion Flask.

    Rutas registradas:
    - GET  /api/v1/auth/saml/<provider>/login    — Iniciar login SAML
    - POST /api/v1/auth/saml/<provider>/callback  — Callback SAML
    - GET  /api/v1/auth/oidc/<provider>/login     — Iniciar login OIDC
    - GET  /api/v1/auth/oidc/<provider>/callback   — Callback OIDC
    - GET  /api/v1/auth/sso/providers              — Listar proveedores
    - POST /api/v1/auth/sso/link                   — Vincular cuenta existente
    """
    from src.data.redis_service import RedisService

    redis = RedisService()
    saml_handler = SAMLHandler(db, redis)
    oidc_handler = OIDCHandler(db, redis)

    @app.route("/api/v1/auth/saml/<provider>/login")
    def sso_saml_login(provider: str):
        """Inicia el flujo de login SAML redirigiendo al IdP."""
        from flask import jsonify, redirect

        provider_row = db.fetchone("SELECT * FROM sso_providers WHERE name = ? AND enabled = 1", (provider,))
        if not provider_row:
            return jsonify({"status": "error", "message": f"Proveedor '{provider}' no disponible"}), 400

        import json as _json
        config = _json.loads(provider_row["config"]) if isinstance(provider_row["config"], str) else provider_row["config"]
        result = saml_handler.initiate_login(config, provider)
        if result.get("status") != "ok":
            return jsonify(result), 400
        return redirect(result["redirect_url"])

    @app.route("/api/v1/auth/saml/<provider>/callback", methods=["POST"])
    def sso_saml_callback(provider: str):
        """Procesa la respuesta SAML del IdP."""
        from flask import jsonify, request, session

        provider_row = db.fetchone("SELECT * FROM sso_providers WHERE name = ?", (provider,))
        if not provider_row:
            return jsonify({"error": f"Proveedor '{provider}' no encontrado"}), 400

        import json as _json
        config = _json.loads(provider_row["config"]) if isinstance(provider_row["config"], str) else provider_row["config"]

        saml_response = request.form.get("SAMLResponse", "")
        if not saml_response:
            return jsonify({"error": "SAMLResponse no encontrada en el POST"}), 400

        result = saml_handler.handle_callback(config, saml_response)
        if result.get("status") != "ok":
            return jsonify(result), 401

        user_info = result["user_info"]
        user_result = create_or_link_user(db, provider, user_info["external_id"], user_info)
        if user_result.get("status") != "ok":
            return jsonify(user_result), 400

        session_result = create_sso_session(db, redis, provider, user_result["user_id"])
        user = db.get_user(user_result["user_id"])
        if user:
            session["user"] = user["username"]
            session["user_id"] = user_result["user_id"]
            session["role"] = user.get("role", "editor")
            session["sso_session_id"] = session_result["session_id"]
            session["sso_provider"] = provider
            session.permanent = True
            db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_result["user_id"],))
            db.commit()

        return jsonify({"status": "ok", "user": user, "sso_session_id": session_result["session_id"]})

    @app.route("/api/v1/auth/oidc/<provider>/login")
    def sso_oidc_login(provider: str):
        """Inicia el flujo de login OIDC redirigiendo al IdP."""
        from flask import jsonify, redirect

        provider_row = db.fetchone("SELECT * FROM sso_providers WHERE name = ? AND enabled = 1", (provider,))
        if not provider_row:
            return jsonify({"status": "error", "message": f"Proveedor '{provider}' no disponible"}), 400

        import json as _json
        config = _json.loads(provider_row["config"]) if isinstance(provider_row["config"], str) else provider_row["config"]
        config["_provider_name"] = provider

        result = oidc_handler.initiate_login(config, provider)
        if result.get("status") != "ok":
            return jsonify(result), 400
        return redirect(result["redirect_url"])

    @app.route("/api/v1/auth/oidc/<provider>/callback")
    def sso_oidc_callback(provider: str):
        """Procesa el callback OIDC tras la autorizacion del usuario."""
        from flask import jsonify, request, session

        provider_row = db.fetchone("SELECT * FROM sso_providers WHERE name = ?", (provider,))
        if not provider_row:
            return jsonify({"error": f"Proveedor '{provider}' no encontrado"}), 400

        import json as _json
        config = _json.loads(provider_row["config"]) if isinstance(provider_row["config"], str) else provider_row["config"]
        config["_provider_name"] = provider

        code = request.args.get("code", "")
        state = request.args.get("state", "")
        if not code or not state:
            return jsonify({"error": "Parametros code y state son requeridos"}), 400

        result = oidc_handler.handle_callback(config, code, state)
        if result.get("status") != "ok":
            return jsonify(result), 401

        user_info = result["user_info"]
        user_result = create_or_link_user(db, provider, user_info["external_id"], user_info)
        if user_result.get("status") != "ok":
            return jsonify(user_result), 400

        session_result = create_sso_session(db, redis, provider, user_result["user_id"], result.get("idp_session"))
        user = db.get_user(user_result["user_id"])
        if user:
            session["user"] = user["username"]
            session["user_id"] = user_result["user_id"]
            session["role"] = user.get("role", "editor")
            session["sso_session_id"] = session_result["session_id"]
            session["sso_provider"] = provider
            session.permanent = True
            db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_result["user_id"],))
            db.commit()

        return jsonify({"status": "ok", "user": user, "sso_session_id": session_result["session_id"]})

    @app.route("/api/v1/auth/sso/providers")
    def sso_list_providers():
        from flask import jsonify
        rows = db.fetchall("SELECT id, name, type, enabled, created_at, updated_at FROM sso_providers ORDER BY name")
        providers = [
            {"id": r["id"], "name": r["name"], "type": r["type"], "enabled": bool(r["enabled"]),
             "created_at": r["created_at"], "updated_at": r["updated_at"]}
            for r in rows
        ]
        return jsonify({"providers": providers})

    @app.route("/api/v1/auth/sso/link", methods=["POST"])
    def sso_link_account():
        from flask import jsonify, request, session
        if "user" not in session:
            return jsonify({"error": "No autenticado"}), 401
        data = request.get_json() or {}
        provider_name = data.get("provider", "")
        external_id = data.get("external_id", "")
        if not provider_name or not external_id:
            return jsonify({"error": "provider y external_id son requeridos"}), 400
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Sesion invalida"}), 401
        result = link_existing_user(db, user_id, provider_name, external_id)
        if result.get("status") != "ok":
            return jsonify(result), 400
        return jsonify(result)
