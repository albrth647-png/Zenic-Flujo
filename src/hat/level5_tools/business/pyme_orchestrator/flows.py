"""Flows de orquestación PYME: Lead→Deal→Invoice→Stock→WhatsApp.

Funciones de alto nivel que combinan múltiples services en un solo flujo.
A diferencia de subscribers.py (que reaccionan a eventos), estas funciones
se llaman explícitamente desde la API o el frontend.
"""
from __future__ import annotations

from src.core.logging import setup_logging
from src.events.bus import EventBus
from src.hat.level5_tools.business.crm.service import CRMService
from src.hat.level5_tools.business.inventory.service import InventoryService
from src.hat.level5_tools.business.invoice.service import InvoiceService

logger = setup_logging(__name__)


def lead_to_invoice_flow(
    lead_id: int,
    items: list[dict],
    tax_rate: float = 0.16,
    currency: str = "MXN",
    event_bus: EventBus | None = None,
) -> dict[str, object]:
    """Flujo completo: Lead → close_won → convert → create_invoice.

    1. Marca el lead como closed_won
    2. Convierte lead a client + deal
    3. Crea factura vinculada al lead y al client
    4. Retorna {client, deal, invoice}

    1. Marca el lead como closed_won
    2. Convierte lead a client + deal
    3. Crea factura vinculada al lead y al client
    4. Retorna {client, deal, invoice}

    Args:
        lead_id: ID del lead a convertir.
        items: Lista de items para la factura.
        tax_rate: Tasa de impuesto (default 0.16).
        currency: Moneda ISO 4217 (default MXN).
        event_bus: EventBus opcional (si None, crea uno nuevo).

    Returns:
        Dict[str, Any] con client, deal, invoice.
    """
    bus = event_bus or EventBus()
    crm = CRMService(event_bus=bus)
    inv = InvoiceService(event_bus=bus)

    # 1. Marcar lead como closed_won
    lead = crm.get_lead(lead_id)
    if not lead:
        raise ValueError(f"Lead {lead_id} no encontrado")

    if lead["stage"] != "closed_won":
        crm.close_won(lead_id)

    # 2. Convertir a client + deal
    conversion = crm.convert_lead_to_deal(
        lead_id=lead_id,
        title=f"Venta - {lead['name']}",
        amount=sum(i.get("quantity", 1) * i.get("unit_price", 0) for i in items),
        currency=currency,
        items=items,
    )
    client = conversion["client"]
    deal = conversion["deal"]

    # 3. Crear factura vinculada
    invoice = inv.create_invoice(
        client_name=client["name"],
        client_email=client.get("email"),
        items=items,
        tax_rate=tax_rate,
        currency=currency,
        lead_id=lead_id,
        client_id=client["id"],
    )

    logger.info(
        f"Flow lead_to_invoice: lead={lead_id} → client={client['id']} "
        f"deal={deal['id']} invoice={invoice['id']}"
    )

    return {"client": client, "deal": deal, "invoice": invoice}


def invoice_paid_to_stock_flow(
    invoice_id: int,
    event_bus: EventBus | None = None,
) -> dict[str, object]:
    """Flujo post-pago: marca factura pagada → descontar stock → WhatsApp.

    1. Marca la factura como pagada (dispara invoice.paid event)
    2. El subscriber _on_invoice_paid descuenta stock automáticamente
    3. El subscriber envía WhatsApp al cliente

    1. Marca la factura como pagada (dispara invoice.paid event)
    2. El subscriber _on_invoice_paid descuenta stock automáticamente
    3. El subscriber envía WhatsApp al cliente

    Args:
        invoice_id: ID de la factura a marcar pagada.
        event_bus: EventBus opcional.

    Returns:
        Dict[str, Any] con invoice actualizada.
    """
    bus = event_bus or EventBus()

    # Registrar subscribers si no están registrados
    from src.hat.level5_tools.business.pyme_orchestrator.subscribers import register_subscribers
    register_subscribers(bus)

    inv = InvoiceService(event_bus=bus)
    invoice = inv.mark_paid(invoice_id)

    if not invoice:
        raise ValueError(f"Factura {invoice_id} no encontrada")

    logger.info(f"Flow invoice_paid_to_stock: invoice={invoice_id} marcada pagada")
    return {"invoice": invoice}


def create_product_and_notify_flow(
    sku: str,
    name: str,
    stock: int,
    min_stock: int,
    price: float,
    event_bus: EventBus | None = None,) -> dict[str, object]:
    """Crea un producto y verifica stock inicial.

    Si stock <= min_stock, dispara alerta automáticamente.

    Args:
        sku: SKU del producto.
        name: Nombre del producto.
        stock: Stock inicial.
        min_stock: Stock mínimo.
        price: Precio unitario.
        event_bus: EventBus opcional.

    Returns:
        Dict[str, object] con product."""
    bus = event_bus or EventBus()

    # Registrar subscribers
    from src.hat.level5_tools.business.pyme_orchestrator.subscribers import register_subscribers
    register_subscribers(bus)

    inv_svc = InventoryService(event_bus=bus)
    product = inv_svc.add_product(
        sku=sku, name=name, stock=stock, min_stock=min_stock, price=price,
    )

    logger.info(f"Flow create_product: sku={sku} stock={stock}")
    return {"product": product}
