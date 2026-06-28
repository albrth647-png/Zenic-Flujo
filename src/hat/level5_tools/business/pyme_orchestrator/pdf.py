"""Generación de PDF de factura para PYME LATAM."""
from __future__ import annotations

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from typing import Any

OUTPUT_DIR = os.path.expanduser("~/.workflow_determinista/pdfs")


def generate_invoice_pdf(invoice: dict[str, Any], client: dict[str, Any] | None = None) -> str:
    """Genera PDF de factura y devuelve el path del archivo.

    Args:
        invoice: dict con id, client_name, items, subtotal, tax_rate,
                 tax_amount, discount, total, currency, due_date.
        client: dict opcional con fiscal_id, address, etc.

    Returns:
        Path del archivo PDF generado.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"factura_{invoice['id']:06d}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=letter,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []

    # Header
    story.append(Paragraph(f"<b>FACTURA #{invoice['id']:06d}</b>", styles["Title"]))
    story.append(Spacer(1, 5 * mm))

    # Datos cliente
    client_data = [
        ["Cliente:", client.get("name", invoice.get("client_name", "")) if client else invoice.get("client_name", "")],
        ["Fiscal ID:", client.get("fiscal_id", "") if client else ""],
        ["Fecha:", datetime.now().strftime("%d/%m/%Y")],
        ["Vencimiento:", invoice.get("due_date", "")],
        ["Moneda:", invoice.get("currency", "MXN")],
    ]
    t = Table(client_data, colWidths=[35 * mm, 100 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # Items
    items_data = [["Descripción", "Cant.", "Precio", "Subtotal"]]
    for item in invoice.get("items", []):
        qty = item.get("quantity", 0)
        price = item.get("unit_price", 0)
        items_data.append([
            item.get("description", item.get("name", "")),
            str(qty),
            f"{price:.2f}",
            f"{qty * price:.2f}",
        ])

    # Totales
    items_data.append(["", "", "Subtotal:", f"{invoice.get('subtotal', 0):.2f}"])
    items_data.append(["", "", f"IVA ({invoice.get('tax_rate', 0) * 100:.0f}%):",
                       f"{invoice.get('tax_amount', 0):.2f}"])
    if invoice.get("discount", 0) > 0:
        items_data.append(["", "", "Descuento:", f"-{invoice['discount']:.2f}"])
    items_data.append(["", "", "TOTAL:",
                       f"{invoice.get('currency', 'MXN')} {invoice.get('total', 0):.2f}"])

    t = Table(items_data, colWidths=[80 * mm, 20 * mm, 30 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -4), [colors.white, colors.HexColor("#F8FAFC")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#1E40AF")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#1E40AF")),
    ]))
    story.append(t)
    story.append(Spacer(1, 10 * mm))

    # Footer
    story.append(Paragraph(
        f"<i>Generado por Zenic-Flujo · {datetime.now().strftime('%d/%m/%Y %H:%M')}</i>",
        styles["Normal"],
    ))

    doc.build(story)
    return filepath
