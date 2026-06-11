"""
Workflow Determinista — Report Generator
Generación de reportes PDF y CSV para workflows, CRM, inventario y facturas.
"""

import csv
import io
import json
from datetime import datetime

from fpdf import FPDF

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class PDF(FPDF):
    """PDF personalizado con theme oscuro para Workflow Determinista."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        """Cabecera con logo y línea."""
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(99, 102, 241)  # primary
        self.cell(0, 8, "Workflow Determinista", align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(42, 42, 42)
        self.line(10, 18, 200, 18)
        self.ln(4)

    def footer(self) -> None:
        """Pie de página con número."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(136, 136, 136)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str) -> None:
        """Título de sección."""
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(224, 224, 224)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def table_header(self, cols: list[str], widths: list[int]) -> None:
        """Fila de encabezado de tabla con fondo oscuro."""
        self.set_fill_color(30, 30, 30)
        self.set_text_color(153, 153, 255)  # primary light
        self.set_font("Helvetica", "B", 8)
        for i, col in enumerate(cols):
            self.cell(widths[i], 7, col, border=1, fill=True, align="C")
        self.ln()

    def table_row(self, cols: list[str], widths: list[int], fill: bool = False) -> None:
        """Fila de datos."""
        if fill:
            self.set_fill_color(26, 26, 26)
        else:
            self.set_fill_color(15, 15, 15)
        self.set_text_color(224, 224, 224)
        self.set_font("Helvetica", "", 8)
        for i, col in enumerate(cols):
            self.cell(widths[i], 6, str(col)[:40], border=1, fill=True, align="C" if i > 0 else "L")
        self.ln()


class ReportGenerator:
    """Genera reportes en formato CSV y PDF."""

    def __init__(self) -> None:
        self._db = DatabaseManager()

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def filename(report_type: str, fmt: str) -> str:
        """Genera nombre de archivo con timestamp."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"wfd_{report_type}_{ts}.{fmt}"

    # ── Workflows CSV ────────────────────────────────────────

    def workflows_csv(self) -> str:
        rows = self._db.fetchall(
            "SELECT id, name, description, trigger_type, status, "
            "created_at, updated_at FROM workflow_definitions "
            "ORDER BY updated_at DESC"
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Nombre", "Descripción", "Disparador", "Estado", "Creado", "Actualizado"])
        for r in rows:
            writer.writerow(
                [
                    r["id"],
                    r["name"],
                    r.get("description", ""),
                    r["trigger_type"],
                    r["status"],
                    r.get("created_at", ""),
                    r.get("updated_at", ""),
                ]
            )
        return output.getvalue()

    # ── Workflows PDF ────────────────────────────────────────

    def workflows_pdf(self) -> bytes:
        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.section_title("Reporte de Workflows")

        rows = self._db.fetchall(
            "SELECT id, name, description, trigger_type, status, "
            "steps, created_at FROM workflow_definitions ORDER BY updated_at DESC"
        )
        if not rows:
            pdf.set_text_color(136, 136, 136)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 10, "No hay workflows registrados.", new_x="LMARGIN", new_y="NEXT")
            return bytes(pdf.output())

        widths = [10, 50, 35, 25, 20, 40]
        pdf.table_header(["ID", "Nombre", "Disparador", "Estado", "Pasos", "Creado"], widths)
        for i, r in enumerate(rows):
            raw_steps = r.get("steps", "[]")
            if isinstance(raw_steps, str):
                try:
                    step_count = len(json.loads(raw_steps))
                except (json.JSONDecodeError, TypeError):
                    step_count = 0
            elif isinstance(raw_steps, (list, tuple)):
                step_count = len(raw_steps)
            else:
                step_count = 0
            pdf.table_row(
                [
                    str(r["id"]),
                    r["name"][:30],
                    r["trigger_type"],
                    r["status"],
                    str(step_count),
                    (r.get("created_at") or "")[:10],
                ],
                widths,
                fill=(i % 2 == 0),
            )

        return bytes(pdf.output())

    # ── CRM Leads CSV ────────────────────────────────────────

    def crm_leads_csv(self) -> str:
        rows = self._db.fetchall(
            "SELECT id, name, email, phone, company, stage, source, "
            "notes, created_at FROM leads ORDER BY created_at DESC"
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Nombre", "Email", "Teléfono", "Empresa", "Etapa", "Origen", "Notas", "Creado"])
        for r in rows:
            writer.writerow(
                [
                    r["id"],
                    r["name"],
                    r.get("email", ""),
                    r.get("phone", ""),
                    r.get("company", ""),
                    r.get("stage", ""),
                    r.get("source", ""),
                    r.get("notes", ""),
                    r.get("created_at", ""),
                ]
            )
        return output.getvalue()

    # ── CRM Leads PDF ────────────────────────────────────────

    def crm_leads_pdf(self) -> bytes:
        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.section_title("Reporte de Leads CRM")

        rows = self._db.fetchall(
            "SELECT id, name, email, phone, company, stage, source, created_at FROM leads ORDER BY created_at DESC"
        )
        if not rows:
            pdf.set_text_color(136, 136, 136)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 10, "No hay leads registrados.", new_x="LMARGIN", new_y="NEXT")
            return bytes(pdf.output())

        widths = [8, 35, 40, 25, 30, 20, 20, 22]
        pdf.table_header(["ID", "Nombre", "Email", "Teléfono", "Empresa", "Etapa", "Origen", "Creado"], widths)
        for i, r in enumerate(rows):
            pdf.table_row(
                [
                    str(r["id"]),
                    r["name"][:25],
                    (r.get("email") or "")[:30],
                    r.get("phone") or "",
                    (r.get("company") or "")[:20],
                    r.get("stage") or "",
                    r.get("source") or "",
                    (r.get("created_at") or "")[:10],
                ],
                widths,
                fill=(i % 2 == 0),
            )

        return bytes(pdf.output())

    # ── Inventory CSV ────────────────────────────────────────

    def inventory_csv(self) -> str:
        rows = self._db.fetchall(
            "SELECT id, sku, name, description, category, stock, min_stock, price FROM products ORDER BY name ASC"
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "SKU", "Nombre", "Categoría", "Stock", "Stock Mínimo", "Precio", "Estado"])
        for r in rows:
            stock = r["stock"]
            min_stock = r["min_stock"]
            estado = "Bajo stock" if stock <= min_stock else "Normal"
            writer.writerow(
                [
                    r["id"],
                    r["sku"],
                    r["name"],
                    r.get("category", ""),
                    stock,
                    min_stock,
                    r.get("price", 0),
                    estado,
                ]
            )
        return output.getvalue()

    # ── Inventory PDF ────────────────────────────────────────

    def inventory_pdf(self) -> bytes:
        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.section_title("Reporte de Inventario")

        rows = self._db.fetchall(
            "SELECT id, sku, name, category, stock, min_stock, price FROM products ORDER BY name ASC"
        )
        if not rows:
            pdf.set_text_color(136, 136, 136)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 10, "No hay productos registrados.", new_x="LMARGIN", new_y="NEXT")
            return bytes(pdf.output())

        widths = [8, 25, 45, 25, 15, 20, 22, 30]
        pdf.table_header(["ID", "SKU", "Nombre", "Categoría", "Stock", "St. Mín", "Precio", "Estado"], widths)
        for i, r in enumerate(rows):
            stock = r["stock"]
            min_stock = r["min_stock"]
            estado = "Bajo stock" if stock <= min_stock else "Ok"
            pdf.table_row(
                [
                    str(r["id"]),
                    r["sku"],
                    r["name"][:30],
                    (r.get("category") or "")[:15],
                    str(stock),
                    str(min_stock),
                    f"${r.get('price', 0):.2f}",
                    estado,
                ],
                widths,
                fill=(i % 2 == 0),
            )

        return bytes(pdf.output())

    # ── Invoices CSV ─────────────────────────────────────────

    def invoices_csv(self) -> str:
        rows = self._db.fetchall(
            "SELECT id, number, client_name, client_email, status, "
            "subtotal, tax_amount, discount, total, due_date, "
            "issued_at, paid_at FROM invoices ORDER BY issued_at DESC"
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Número",
                "Cliente",
                "Email Cliente",
                "Estado",
                "Subtotal",
                "IVA",
                "Descuento",
                "Total",
                "Vencimiento",
                "Emitida",
                "Pagada",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["id"],
                    r.get("number", ""),
                    r["client_name"],
                    r.get("client_email", ""),
                    r["status"],
                    r.get("subtotal", 0),
                    r.get("tax_amount", 0),
                    r.get("discount", 0),
                    r.get("total", 0),
                    r.get("due_date", ""),
                    r.get("issued_at", ""),
                    r.get("paid_at", ""),
                ]
            )
        return output.getvalue()

    # ── Invoices PDF ─────────────────────────────────────────

    def invoices_pdf(self) -> bytes:
        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.section_title("Reporte de Facturas")

        rows = self._db.fetchall(
            "SELECT id, number, client_name, status, subtotal, "
            "tax_amount, discount, total, due_date, issued_at "
            "FROM invoices ORDER BY issued_at DESC"
        )
        if not rows:
            pdf.set_text_color(136, 136, 136)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 10, "No hay facturas registradas.", new_x="LMARGIN", new_y="NEXT")
            return bytes(pdf.output())

        widths = [8, 25, 35, 18, 20, 18, 18, 22, 18, 18]
        pdf.table_header(
            ["ID", "Número", "Cliente", "Estado", "Subtotal", "IVA", "Desc.", "Total", "Venc.", "Emitida"], widths
        )
        for i, r in enumerate(rows):
            pdf.table_row(
                [
                    str(r["id"]),
                    r.get("number", "")[:10],
                    r["client_name"][:20],
                    r["status"],
                    f"${r.get('subtotal', 0):.2f}",
                    f"${r.get('tax_amount', 0):.2f}",
                    f"${r.get('discount', 0):.2f}",
                    f"${r.get('total', 0):.2f}",
                    (r.get("due_date") or "")[:10],
                    (r.get("issued_at") or "")[:10],
                ],
                widths,
                fill=(i % 2 == 0),
            )

        return bytes(pdf.output())
