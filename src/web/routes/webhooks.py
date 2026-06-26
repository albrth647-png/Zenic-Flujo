"""Webhooks receiver para MercadoPago y WhatsApp.

Endpoints:
- POST /webhooks/mercadopago  → recibe notificación de pago MP
- GET/POST /webhooks/whatsapp  → verificación Meta + recepción de mensajes
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@webhooks_bp.route("/mercadopago", methods=["POST"])
def mercadopago_webhook():
    """Webhook MercadoPago: recibe notificación de pago.

    MercadoPago envía POST con type, data.id.
    Si payment approved, marca invoice como pagada.
    """
    payload = request.json or {}
    logger.info(f"Webhook MP recibido: type={payload.get('type')}")

    if payload.get("type") == "payment":
        payment_id = payload.get("data", {}).get("id")
        if not payment_id:
            return jsonify({"received": True}), 200

        try:
            from src.hat.level5_tools.payments.mercadopago_service import MercadoPagoService
            mp = MercadoPagoService()
            payment = mp.get_payment(payment_id)

            if payment and payment.get("status") == "approved":
                external_ref = payment.get("external_reference", "")
                if external_ref:
                    parts = external_ref.split("-")
                    if len(parts) >= 2:
                        invoice_id = int(parts[-1])
                        from src.hat.level5_tools.business.invoice.service import InvoiceService
                        InvoiceService().mark_paid(invoice_id, amount=payment.get("amount", 0))
                        logger.info(f"Invoice {invoice_id} marcada pagada vía webhook MP")
        except Exception as e:
            logger.warning(f"Error procesando webhook MP: {e}")

    return jsonify({"received": True}), 200


@webhooks_bp.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    """Webhook Meta Cloud API: verificación GET + recepción POST."""
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        expected = current_app.config.get("WHATSAPP_VERIFY_TOKEN", "zenic_verify")

        if mode == "subscribe" and token == expected:
            logger.info("Webhook WhatsApp verificado por Meta")
            return challenge, 200
        return "Forbidden", 403

    # POST: mensaje entrante
    payload = request.json or {}

    # Verificar signature
    app_secret = current_app.config.get("WHATSAPP_APP_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    if app_secret and signature:
        expected_sig = "sha256=" + hmac.new(
            app_secret.encode(), request.get_data(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Webhook WhatsApp: signature inválida")
            return "Invalid signature", 403

    # Procesar mensaje
    try:
        from src.connectors.whatsapp import WhatsAppConnector
        processed = WhatsAppConnector.process_webhook_payload(payload)

        # BUG-3 fix: usar el event_bus compartido de app.config (el mismo que
        # usan los workers y subscribers en main.py). Antes se instanciaba
        # EventBus() nuevo, lo que creaba un bus vacío sin subscribers →
        # los eventos whatsapp.message.received nunca llegaban al PymeOrchestrator.
        bus = current_app.config.get("event_bus")
        if bus is None:
            # Fallback: si no se inyectó event_bus (ej. tests sin main.py),
            # crear uno efímero y loggear warning.
            logger.warning("Webhook WhatsApp: event_bus no inyectado en app.config — usando bus efímero (subscribers NO recibirán el evento)")
            from src.events.bus import EventBus
            bus = EventBus()

        for msg in processed.get("messages", []):
            bus.publish("whatsapp.message.received", msg)

        logger.info(f"Webhook WhatsApp: {len(processed.get('messages', []))} mensajes procesados y publicados al event_bus compartido")
    except Exception as e:
        logger.warning(f"Error procesando webhook WhatsApp: {e}")

    return jsonify({"received": True}), 200
