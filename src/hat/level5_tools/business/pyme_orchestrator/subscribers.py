"""Suscriptores automáticos que orquestan Lead→Deal→Invoice→Stock→WhatsApp.

Estos suscriptores se registran al startup de la app (main.py) y conectan
los servicios existentes sin tocar su código.

Eventos suscritos:
1. invoice.paid          → descontar stock + WhatsApp al cliente
2. invoice.overdue       → WhatsApp recordatorio al cliente
3. inventory.stock_low   → WhatsApp al dueño
4. inventory.stock_out   → WhatsApp urgente al dueño
5. crm.lead.stage_changed → si closed_won, sugerir crear Deal
6. crm.lead.created      → welcome WhatsApp si tiene phone
"""
from __future__ import annotations

import contextlib
from typing import Any

from src.core.logging import setup_logging
from src.events.bus import EventBus
from src.hat.level5_tools.business.crm.service import CRMService
from src.hat.level5_tools.business.inventory.service import InventoryService
from src.hat.level5_tools.business.invoice.service import InvoiceService
from src.hat.level5_tools.communications.notification.service import NotificationService

logger = setup_logging(__name__)


class _PYMEServices:
    """Contenedor thread-safe de servicios PYME con inicialización lazy.

    Reemplaza el patrón anterior de 4 variables globales (``_crm``, ``_inv``,
    ``_inv_svc``, ``_notif``) que causaba race conditions bajo concurrencia.
    """

    def __init__(self) -> None:
        self.crm: CRMService = CRMService()
        self.inv: InvoiceService = InvoiceService()
        self.inv_svc: InventoryService = InventoryService()
        self.notif: NotificationService = NotificationService()


# Singleton thread-safe: se inicializa UNA vez al importar el módulo.
_services = _PYMEServices()


def _get_services() -> tuple[CRMService, InvoiceService, InventoryService, NotificationService]:
    return _services.crm, _services.inv, _services.inv_svc, _services.notif


def register_subscribers(event_bus: EventBus) -> None:
    """Registra los 6 suscriptores automáticos del PYME bundle."""
    event_bus.subscribe("invoice.paid", _on_invoice_paid)
    event_bus.subscribe("invoice.overdue", _on_invoice_overdue)
    event_bus.subscribe("inventory.stock_low", _on_stock_low)
    event_bus.subscribe("inventory.stock_out", _on_stock_out)
    event_bus.subscribe("crm.lead.stage_changed", _on_lead_stage_changed)
    event_bus.subscribe("crm.lead.created", _on_lead_created)
    logger.info("PYME orchestrator: 6 suscriptores registrados")


# ── 1. Pago de factura → descontar stock + WhatsApp al cliente ────────

def _on_invoice_paid(event_data: dict[str, Any]) -> None:
    """Cuando una factura se marca pagada:
       1. Descontar stock de cada item (si tiene SKU)
       2. Enviar WhatsApp de confirmación al cliente
    """
    _crm, inv, inv_svc, notif = _get_services()
    invoice_id = event_data.get("invoice_id")
    if not invoice_id:
        return

    invoice = inv.get_invoice(invoice_id)
    if not invoice:
        return

    # 1. Descontar stock por SKU (si existe)
    for item in invoice.get("items", []):
        sku = item.get("sku")
        qty = item.get("quantity", 0)
        if sku and qty > 0:
            products = inv_svc.list_products()
            for p in products:
                if p.get("sku") == sku:
                    inv_svc.update_stock(
                        p["id"], qty,
                        movement_type="out",
                        reason=f"Factura #{invoice_id} pagada",
                    )
                    break

    # 2. WhatsApp al cliente (si tiene phone)
    client_phone = invoice.get("client_phone") or _get_client_phone(invoice)
    if client_phone:
        total = invoice.get("total", 0)
        currency = invoice.get("currency", "MXN")
        msg = (
            f"✅ Pago confirmado. Factura #{invoice_id} por "
            f"{currency} {total:.2f}. ¡Gracias por su compra!"
        )
        try:
            notif.send_whatsapp(client_phone, msg)
        except Exception as e:
            logger.warning(f"WhatsApp post-pago falló: {e}")


# ── 2. Factura vencida → WhatsApp recordatorio ───────────────────────

def _on_invoice_overdue(event_data: dict[str, Any]) -> None:
    """Factura vencida → WhatsApp recordatorio al cliente."""
    _, inv, _, notif = _get_services()
    inv_id = event_data.get("invoice_id")
    days = event_data.get("days_overdue", 0)
    if not inv_id:
        return

    invoice = inv.get_invoice(inv_id)
    if not invoice:
        return

    phone = invoice.get("client_phone") or _get_client_phone(invoice)
    if phone:
        msg = (
            f"⏰ Recordatorio: Factura #{inv_id} vencida hace {days} día(s). "
            f"Total: {invoice.get('currency', 'MXN')} {invoice.get('total', 0):.2f}."
        )
        with contextlib.suppress(Exception):
            notif.send_whatsapp(phone, msg)


# ── 3. Stock bajo → WhatsApp al dueño ─────────────────────────────────

def _on_stock_low(event_data: dict[str, Any]) -> None:
    """Stock bajo → WhatsApp al dueño del negocio."""
    _, _, _, notif = _get_services()
    name = event_data.get("name", event_data.get("product_name", ""))
    stock = event_data.get("stock", event_data.get("current_stock", 0))
    min_s = event_data.get("min_stock", 0)

    admin_phone = _get_admin_phone()
    if admin_phone:
        msg = (
            f"⚠️ Stock bajo: {name}. Actual: {stock}, mínimo: {min_s}. "
            f"Reabastece pronto."
        )
        with contextlib.suppress(Exception):
            notif.send_whatsapp(admin_phone, msg)


# ── 4. Stock agotado → WhatsApp urgente ───────────────────────────────

def _on_stock_out(event_data: dict[str, Any]) -> None:
    """Stock agotado → WhatsApp urgente al dueño."""
    _, _, _, notif = _get_services()
    name = event_data.get("name", event_data.get("product_name", ""))

    admin_phone = _get_admin_phone()
    if admin_phone:
        msg = f"🔴 AGOTADO: {name}. Stock = 0. No podrás facturar este producto."
        with contextlib.suppress(Exception):
            notif.send_whatsapp(admin_phone, msg)


# ── 5. Lead avanza a closed_won → sugerir crear Deal ─────────────────

def _on_lead_stage_changed(event_data: dict[str, Any]) -> None:
    """Cuando un Lead cierra ganado, publicar sugerencia de Deal."""
    crm, _, _, _ = _get_services()
    lead_id = event_data.get("lead_id")
    new_stage = event_data.get("to_stage")
    if new_stage != "closed_won":
        return

    lead = crm.get_lead(lead_id)
    if not lead:
        return

    # Auto-crear Deal sin monto (el usuario lo edita después)
    try:
        crm.convert_lead_to_deal(
            lead_id=lead_id,
            title=f"Deal - {lead['name']}",
            amount=0.0,
            currency="MXN",
        )
        logger.info(f"Lead {lead_id} closed_won → Deal auto-creado")
    except Exception as e:
        logger.warning(f"No se pudo auto-crear Deal para lead {lead_id}: {e}")


# ── 6. Lead creado → welcome WhatsApp si tiene phone ──────────────────

def _on_lead_created(event_data: dict[str, Any]) -> None:
    """Lead creado → WhatsApp de bienvenida si tiene phone."""
    _, _, _, notif = _get_services()
    phone = event_data.get("phone")
    name = event_data.get("name", "")
    if phone:
        msg = (
            f"¡Hola {name}! Gracias por tu interés. "
            f"Te contactaremos pronto. — Equipo Zenic"
        )
        with contextlib.suppress(Exception):
            notif.send_whatsapp(phone, msg)


# ── Helpers ────────────────────────────────────────────────────────────

def _get_admin_phone() -> str | None:
    """Lee el teléfono del admin desde settings."""
    try:
        from src.core.db.sqlite_manager import DatabaseManager
        db = DatabaseManager()
        result = db.fetchone("SELECT value FROM settings WHERE key = 'admin_phone'")
        return result["value"] if result else None
    except Exception:
        return None


def _get_client_phone(invoice: dict[str, Any]) -> str | None:
    """Intenta obtener el phone del cliente desde el invoice o el lead."""
    # Si el invoice tiene lead_id, buscar el lead
    lead_id = invoice.get("lead_id")
    if lead_id:
        try:
            crm, _, _, _ = _get_services()
            lead = crm.get_lead(lead_id)
            if lead and lead.get("phone"):
                return lead["phone"]
        except Exception as e:
            logger.warning(
                "No se pudo obtener phone del cliente desde lead %s: %s",
                lead_id, e,
            )
    return None
