"""
Blueprints — Integraciones externas (Gmail, Sheets, Telegram, Slack)
====================================================================

Endpoints para configurar, probar y obtener estado de las integraciones.
Cada integración guarda sus credenciales en settings de la DB.
"""

from flask import Blueprint, jsonify, request, session

from src.web.helpers import db, login_required

bp = Blueprint("integrations", __name__)


# ── Helpers ───────────────────────────────────────────────

_INTEGRATIONS = {
    "gmail": {
        "name": "Gmail",
        "icon": "mail",
        "description": "Envía y gestiona emails vía Gmail API",
        "settings_key": "gmail_credentials",
        "fields": [
            {"key": "client_id", "label": "Client ID", "type": "text", "required": True},
            {"key": "client_secret", "label": "Client Secret", "type": "password", "required": True},
            {"key": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
        ],
    },
    "sheets": {
        "name": "Google Sheets",
        "icon": "table",
        "description": "Lee y escribe datos en Google Sheets",
        "settings_key": "sheets_service_account",
        "fields": [
            {"key": "service_account_json", "label": "Service Account JSON", "type": "textarea", "required": True},
        ],
    },
    "telegram": {
        "name": "Telegram",
        "icon": "message-circle",
        "description": "Envía mensajes y gestiona chats vía Telegram Bot API",
        "settings_key": "telegram_bot_token",
        "fields": [
            {"key": "bot_token", "label": "Bot Token", "type": "password", "required": True},
        ],
    },
    "slack": {
        "name": "Slack",
        "icon": "slack",
        "description": "Envía mensajes y gestiona canales vía Slack Web API",
        "settings_key": "slack_bot_token",
        "fields": [
            {"key": "bot_token", "label": "Bot Token", "type": "password", "required": True},
        ],
    },
}


def _get_integration_service(name: str):
    """Importa y retorna la instancia del servicio de integración."""
    if name == "gmail":
        from src.hat.level5_tools.communications.gmail_service import GmailService
        return GmailService()
    elif name == "sheets":
        from src.hat.level5_tools.data.sheets_service import SheetsService
        return SheetsService()
    elif name == "telegram":
        from src.hat.level5_tools.communications.telegram_service import TelegramService
        return TelegramService()
    elif name == "slack":
        from src.hat.level5_tools.communications.slack_service import SlackService
        return SlackService()
    return None


# ── Endpoints ─────────────────────────────────────────────


@bp.route("/api/integrations", methods=["GET"])
@login_required
def api_list_integrations():
    """Lista todas las integraciones con su estado."""
    results = []
    for name, meta in _INTEGRATIONS.items():
        service = _get_integration_service(name)
        status = service.get_status() if service else {"configured": False}
        results.append({
            "name": name,
            "title": meta["name"],
            "icon": meta["icon"],
            "description": meta["description"],
            "fields": meta["fields"],
            "configured": status.get("configured", False),
        })
    return jsonify(results)


@bp.route("/api/integrations/<name>/status", methods=["GET"])
@login_required
def api_integration_status(name: str):
    """Obtiene el estado de una integración específica."""
    if name not in _INTEGRATIONS:
        return jsonify({"error": "Integración no encontrada"}), 404

    service = _get_integration_service(name)
    if not service:
        return jsonify({"error": "Error al cargar el servicio"}), 500

    status = service.get_status()
    return jsonify({
        "name": name,
        "title": _INTEGRATIONS[name]["name"],
        "fields": _INTEGRATIONS[name]["fields"],
        **status,
    })


@bp.route("/api/integrations/<name>/configure", methods=["POST"])
@login_required
def api_integration_configure(name: str):
    """Configura una integración con las credenciales proporcionadas."""
    if name not in _INTEGRATIONS:
        return jsonify({"error": "Integración no encontrada"}), 404

    service = _get_integration_service(name)
    if not service:
        return jsonify({"error": "Error al cargar el servicio"}), 500

    data = request.get_json() or {}

    if name == "gmail":
        ok = service.configure(
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            refresh_token=data.get("refresh_token", ""),
        )
    elif name == "sheets":
        ok = service.configure(
            service_account_json=data.get("service_account_json", "{}"),
        )
    elif name in ("telegram", "slack"):
        ok = service.configure(
            bot_token=data.get("bot_token", ""),
        )
    else:
        return jsonify({"error": "Integración no soportada"}), 400

    if ok:
        db.audit(f"integration.{name}.configured", f"Integración {name} configurada", request.remote_addr, session.get("user_id"))
        return jsonify({"status": "configured", "message": f"{_INTEGRATIONS[name]['name']} configurado correctamente"})
    return jsonify({"error": "Error al guardar la configuración"}), 500


@bp.route("/api/integrations/<name>/test", methods=["POST"])
@login_required
def api_integration_test(name: str):
    """Prueba la conexión de una integración."""
    if name not in _INTEGRATIONS:
        return jsonify({"error": "Integración no encontrada"}), 404

    service = _get_integration_service(name)
    if not service:
        return jsonify({"error": "Error al cargar el servicio"}), 500

    result = service.test_connection()
    return jsonify(result)


@bp.route("/api/integrations/<name>/disconnect", methods=["POST"])
@login_required
def api_integration_disconnect(name: str):
    """Desconecta una integración eliminando sus credenciales."""
    if name not in _INTEGRATIONS:
        return jsonify({"error": "Integración no encontrada"}), 404

    key = _INTEGRATIONS[name]["settings_key"]
    db.set_setting(key, "")
    db.audit(f"integration.{name}.disconnected", f"Integración {name} desconectada", request.remote_addr, session.get("user_id"))
    return jsonify({"status": "disconnected", "message": f"{_INTEGRATIONS[name]['name']} desconectado"})
