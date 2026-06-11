"""
Tests para Reportes PDF/CSV (Mejora #5).
"""

import csv
import io


class TestCSVReports:
    """Tests para generación de reportes CSV."""

    def test_generate_workflows_csv(self, db_manager, sample_workflow):
        """Genera CSV de workflows."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        repo.create(WorkflowDefinition(**sample_workflow))
        import time

        time.sleep(0.05)  # Asegurar timestamp distinto
        repo.create(
            WorkflowDefinition(
                name="Workflow 2",
                trigger_type="manual",
                steps=[],
            )
        )

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        csv_content = gen.workflows_csv()
        assert csv_content is not None
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 2
        names = [r["Nombre"] for r in rows]
        assert "Test Workflow" in names
        assert "Workflow 2" in names

    def test_generate_crm_csv(self, db_manager):
        """Genera CSV de leads CRM."""
        from src.tools.crm.service import CRMService

        crm = CRMService()
        crm.create_lead("Juan", email="juan@test.com", phone="555-0100", company="ACME", source="web")
        crm.create_lead("María", email="maria@test.com", phone="555-0200", company="XYZ", source="referral")

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        csv_content = gen.crm_leads_csv()
        assert csv_content is not None
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 2
        names = [r["Nombre"] for r in rows]
        assert "Juan" in names
        assert "María" in names

    def test_generate_inventory_csv(self, db_manager):
        """Genera CSV de inventario."""
        from src.tools.inventory.service import InventoryService

        inv = InventoryService()
        inv.add_product("SKU-001", "Laptop", stock=10, min_stock=3, price=999.99)
        inv.add_product("SKU-002", "Mouse", stock=2, min_stock=5, price=29.99)

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        csv_content = gen.inventory_csv()
        rows = list(csv.DictReader(io.StringIO(csv_content)))
        assert len(rows) == 2

    def test_generate_invoices_csv(self, db_manager):
        """Genera CSV de facturas."""
        from src.tools.invoice.service import InvoiceService

        inv = InvoiceService()
        inv.create_invoice("Cliente A", items=[{"desc": "Item 1", "qty": 1, "price": 100}])

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        csv_content = gen.invoices_csv()
        rows = list(csv.DictReader(io.StringIO(csv_content)))
        assert len(rows) == 1
        assert rows[0]["Cliente"] == "Cliente A"

    def test_csv_empty_data(self, db_manager):
        """CSV con datos vacíos retorna solo headers."""
        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        csv_content = gen.crm_leads_csv()
        rows = list(csv.DictReader(io.StringIO(csv_content)))
        assert len(rows) == 0  # Solo headers, sin datos


class TestPDFReports:
    """Tests para generación de reportes PDF."""

    def test_generate_workflows_pdf(self, db_manager, sample_workflow):
        """Genera PDF de workflows."""
        from src.workflow.repository import WorkflowDefinition, WorkflowRepository

        repo = WorkflowRepository()
        repo.create(WorkflowDefinition(**sample_workflow))

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        pdf_bytes = gen.workflows_pdf()
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 100  # Debe tener contenido
        assert pdf_bytes.startswith(b"%PDF")  # Debe ser PDF válido

    def test_generate_crm_pdf(self, db_manager):
        """Genera PDF de leads."""
        from src.tools.crm.service import CRMService

        crm = CRMService()
        crm.create_lead("Juan", email="juan@test.com")

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        pdf_bytes = gen.crm_leads_pdf()
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")

    def test_generate_inventory_pdf(self, db_manager):
        """Genera PDF de inventario."""
        from src.tools.inventory.service import InventoryService

        inv = InventoryService()
        inv.add_product("SKU-TEST", "Test Product", stock=5, min_stock=2, price=99.99)

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        pdf_bytes = gen.inventory_pdf()
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")

    def test_generate_invoices_pdf(self, db_manager):
        """Genera PDF de facturas."""
        from src.tools.invoice.service import InvoiceService

        inv = InvoiceService()
        inv.create_invoice("Cliente Test", items=[{"desc": "Item", "qty": 2, "price": 50}])

        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        pdf_bytes = gen.invoices_pdf()
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")

    def test_pdf_empty_data(self, db_manager):
        """PDF con datos vacíos debe generar página con mensaje."""
        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        pdf_bytes = gen.crm_leads_pdf()
        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 200  # Al menos portada + mensaje

    def test_pdf_filename_format(self):
        """Verificar formato de nombres de archivo."""
        from src.web.reports import ReportGenerator

        gen = ReportGenerator()
        name = gen.filename("workflows", "pdf")
        assert name.endswith(".pdf")
        assert "workflows" in name
        name2 = gen.filename("crm_leads", "csv")
        assert name2.endswith(".csv")
        assert "crm_leads" in name2
