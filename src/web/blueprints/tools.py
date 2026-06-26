"""
Blueprints — Tools (CRM, Inventory, Invoice), Settings y WhatsApp
"""

import secrets

from flask import Blueprint, jsonify, request, session

from src.core.repositories import AuditRepository
from src.core.repositories import SettingsRepository
from src.core.repositories import UserRepository
from src.web.helpers import db, login_required, require_role

users = UserRepository()
audit = AuditRepository()
settings = SettingsRepository()

bp = Blueprint("tools", __name__)


# ── API: Tools — CRM ───────────────────────────────────────

@bp.route("/api/tools/crm/leads", methods=["GET"])
@login_required
def api_list_leads():
    from src.hat.level5_tools.business.crm.service import CRMService
    crm = CRMService()
    stage = request.args.get("stage")
    leads = crm.list_leads(stage)
    return jsonify(leads)


@bp.route("/api/tools/crm/leads", methods=["POST"])
@login_required
@require_role("editor")
def api_create_lead():
    from src.hat.level5_tools.business.crm.service import CRMService
    crm = CRMService()
    data = request.get_json() or {}
    lead = crm.create_lead(
        name=data.get("name", ""),
        email=data.get("email"),
        phone=data.get("phone"),
        company=data.get("company"),
        source=data.get("source", "web_form"),
        notes=data.get("notes"),
        user_id=session.get("user_id"),
    )
    return jsonify(lead), 201


@bp.route("/api/tools/crm/leads/<int:lead_id>", methods=["PUT"])
@login_required
@require_role("editor")
def api_update_lead(lead_id: int):
    from src.hat.level5_tools.business.crm.service import CRMService
    crm = CRMService()
    data = request.get_json() or {}
    lead = crm.update_lead(lead_id, **data)
    if not lead:
        return jsonify({"error": "Lead no encontrado"}), 404
    return jsonify(lead)


@bp.route("/api/tools/crm/leads/<int:lead_id>", methods=["DELETE"])
@login_required
@require_role("editor")
def api_delete_lead(lead_id: int):
    from src.hat.level5_tools.business.crm.service import CRMService
    crm = CRMService()
    if crm.delete_lead(lead_id):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Lead no encontrado"}), 404


@bp.route("/api/tools/crm/leads/<int:lead_id>/advance", methods=["POST"])
@login_required
@require_role("editor")
def api_advance_lead(lead_id: int):
    from src.hat.level5_tools.business.crm.service import CRMService
    crm = CRMService()
    result = crm.advance_stage(lead_id)
    if not result:
        return jsonify({"error": "Lead no encontrado"}), 404
    return jsonify(result)


# ── API: Tools — Inventory ─────────────────────────────────

@bp.route("/api/tools/inventory/products", methods=["GET"])
@login_required
def api_list_products():
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    low_stock = request.args.get("low_stock", "false").lower() == "true"
    products = inv.list_products(low_stock_only=low_stock)
    return jsonify(products)


@bp.route("/api/tools/inventory/products/<int:product_id>", methods=["PUT"])
@login_required
@require_role("editor")
def api_update_product(product_id: int):
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    data = request.get_json() or {}
    product = inv.update_product(product_id, **data)
    if not product:
        return jsonify({"error": "Producto no encontrado"}), 404
    return jsonify(product)


@bp.route("/api/tools/inventory/products/<int:product_id>", methods=["DELETE"])
@login_required
@require_role("editor")
def api_delete_product(product_id: int):
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    if inv.delete_product(product_id):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Producto no encontrado"}), 404


@bp.route("/api/tools/inventory/products", methods=["POST"])
@login_required
@require_role("editor")
def api_create_product():
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    data = request.get_json() or {}
    product = inv.add_product(
        sku=data.get("sku", ""),
        name=data.get("name", ""),
        description=data.get("description", ""),
        category=data.get("category", ""),
        stock=data.get("stock", 0),
        min_stock=data.get("min_stock", 10),
        price=data.get("price", 0.0),
        user_id=session.get("user_id"),
    )
    return jsonify(product), 201


@bp.route("/api/tools/inventory/stock-movement", methods=["POST"])
@login_required
@require_role("editor")
def api_stock_movement():
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    data = request.get_json() or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity", 0)
    movement_type = data.get("type", "adjustment")
    reason = data.get("reason", "")
    if not product_id:
        return jsonify({"error": "product_id es requerido"}), 400
    result = inv.update_stock(product_id, quantity, movement_type, reason)
    if not result:
        return jsonify({"error": "Producto no encontrado"}), 404
    return jsonify(result)


@bp.route("/api/tools/inventory/low-stock", methods=["GET"])
@login_required
def api_low_stock():
    from src.hat.level5_tools.business.inventory.service import InventoryService
    inv = InventoryService()
    return jsonify(inv.get_low_stock_products())


# ── API: Tools — Invoice ───────────────────────────────────

@bp.route("/api/tools/invoice/create", methods=["POST"])
@login_required
@require_role("editor")
def api_create_invoice():
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    invs = InvoiceService()
    data = request.get_json() or {}
    client_name = data.get("client_name", "")
    if not client_name:
        return jsonify({"error": "client_name es requerido"}), 400
    invoice = invs.create_invoice(
        client_name=client_name,
        client_email=data.get("client_email"),
        items=data.get("items", []),
        tax_rate=data.get("tax_rate", 0.16),
        discount=data.get("discount", 0.0),
        due_days=data.get("due_days", 30),
        notes=data.get("notes"),
        user_id=session.get("user_id"),
    )
    return jsonify(invoice), 201


@bp.route("/api/tools/invoice/list", methods=["GET"])
@login_required
def api_list_invoices():
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    invs = InvoiceService()
    status = request.args.get("status")
    invoices = invs.list_invoices(status)
    return jsonify(invoices)


@bp.route("/api/tools/invoice/<int:invoice_id>/pay", methods=["POST"])
@login_required
@require_role("editor")
def api_pay_invoice(invoice_id: int):
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    invs = InvoiceService()
    invoice = invs.mark_paid(invoice_id)
    if not invoice:
        return jsonify({"error": "Factura no encontrada"}), 404
    return jsonify(invoice)


@bp.route("/api/tools/invoice/<int:invoice_id>/cancel", methods=["POST"])
@login_required
@require_role("editor")
def api_cancel_invoice(invoice_id: int):
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    invs = InvoiceService()
    invoice = invs.cancel(invoice_id)
    if not invoice:
        return jsonify({"error": "Factura no encontrada"}), 404
    return jsonify(invoice)


# ── API: Settings ──────────────────────────────────────────

@bp.route("/api/settings", methods=["GET"])
@login_required
def api_get_settings():
    return jsonify({
        "smtp_server": settings.get_setting("smtp_server", ""),
        "smtp_port": settings.get_setting("smtp_port", "587"),
        "email_user": settings.get_setting("email_user", ""),
        "webhook_api_key": settings.get_setting("webhook_api_key", ""),
        "api_key": settings.get_setting("webhook_api_key", ""),
    })


@bp.route("/api/settings/api-key", methods=["GET", "POST"])
@login_required
@require_role("admin")
def api_settings_api_key():
    """GET: retorna la API key actual. POST: genera/regenera una nueva."""
    if request.method == "GET":
        key = settings.get_setting("webhook_api_key", "")
        return jsonify({"api_key": key})

    # POST: regenerar
    new_key = f"wf_{secrets.token_hex(24)}"
    settings.set_setting("webhook_api_key", new_key)
    audit.log("api_key.regenerated", "API Key regenerada", request.remote_addr, session.get("user_id"))
    return jsonify({"api_key": new_key, "status": "regenerated"})


@bp.route("/api/settings", methods=["PUT"])
@login_required
@require_role("admin")
def api_update_settings():
    data = request.get_json() or {}
    for key in ["smtp_server", "smtp_port", "email_user", "email_password",
                 "webhook_api_key", "imap_server", "imap_port"]:
        if key in data:
            settings.set_setting(key, str(data[key]))
    return jsonify({"status": "saved"})


@bp.route("/api/settings/change-password", methods=["POST"])
@login_required
def api_change_password():
    import bcrypt

    data = request.get_json() or {}
    current = data.get("current_password", "")
    new_pass = data.get("new_password", "")

    if len(new_pass) < 6:
        return jsonify({"error": "La nueva contraseña debe tener al menos 6 caracteres"}), 400

    user_id = session.get("user_id")
    if user_id:
        user_row = users.get_user(user_id)
        if user_row:
            user_full = users.get_user_by_username(user_row["username"])
            if user_full and user_full.get("password_hash"):
                try:
                    stored = user_full["password_hash"]
                    if not bcrypt.checkpw(current.encode(), stored.encode()):
                        return jsonify({"error": "Contraseña actual incorrecta"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Error verificando contraseña"}), 400
                new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt(rounds=12)).decode()
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
                db.commit()
                audit.log("password.changed", "Contraseña cambiada", request.remote_addr, user_id)
                return jsonify({"status": "ok"})

    stored_hash = settings.get_setting("admin_password_hash")
    if stored_hash and isinstance(stored_hash, str):
        try:
            if not bcrypt.checkpw(current.encode(), stored_hash.encode()):
                return jsonify({"error": "Contraseña actual incorrecta"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Error verificando contraseña"}), 400

    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt(rounds=12)).decode()
    settings.set_setting("admin_password_hash", new_hash)
    audit.log("password.changed", "Contraseña cambiada", request.remote_addr)
    return jsonify({"status": "ok"})


@bp.route("/api/settings/test-email", methods=["POST"])
@login_required
def api_test_email():
    from src.hat.level5_tools.communications.notification.service import NotificationService
    ns = NotificationService()
    result = ns.test_connection()
    return jsonify(result)


# ── API: WhatsApp Settings ─────────────────────────────────

@bp.route("/api/settings/whatsapp", methods=["GET"])
@login_required
def api_get_whatsapp():
    from src.hat.level5_tools.communications.notification.service import NotificationService
    ns = NotificationService()
    return jsonify(ns.get_whatsapp_status())


@bp.route("/api/settings/whatsapp", methods=["PUT"])
@login_required
def api_update_whatsapp():
    data = request.get_json() or {}
    token = data.get("token", "")
    phone_number_id = data.get("phone_number_id", "")
    if not token or not phone_number_id:
        return jsonify({"error": "token y phone_number_id son requeridos"}), 400
    from src.hat.level5_tools.communications.notification.service import NotificationService
    ns = NotificationService()
    ns.configure_whatsapp(token, phone_number_id)
    return jsonify({"status": "saved"})


@bp.route("/api/settings/whatsapp/test", methods=["POST"])
@login_required
def api_test_whatsapp():
    data = request.get_json() or {}
    test_number = data.get("test_number", "")
    if not test_number:
        return jsonify({"error": "Número de prueba requerido"}), 400
    from src.hat.level5_tools.communications.notification.service import NotificationService
    ns = NotificationService()
    result = ns.send_whatsapp(
        to=test_number,
        message="🧪 Conexión WhatsApp exitosa desde Workflow Determinista",
    )
    return jsonify(result)
