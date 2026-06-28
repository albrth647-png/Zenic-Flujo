"""
Blueprints — Reportes (CSV/PDF)
"""

from flask import Blueprint, current_app, jsonify

from src.web.helpers import login_required

bp = Blueprint("reports", __name__)


@bp.route("/api/reports/workflows/<fmt>")
@login_required
def api_report_workflows(fmt):
    from src.web.reports import ReportGenerator
    gen = ReportGenerator()
    if fmt == "csv":
        content = gen.workflows_csv()
        mimetype = "text/csv"
    elif fmt == "pdf":
        content = gen.workflows_pdf()
        mimetype = "application/pdf"
    else:
        return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
    response = current_app.response_class(response=content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("workflows", fmt)}"'
    return response


@bp.route("/api/reports/crm/<fmt>")
@login_required
def api_report_crm(fmt):
    from src.web.reports import ReportGenerator
    gen = ReportGenerator()
    if fmt == "csv":
        content = gen.crm_leads_csv()
        mimetype = "text/csv"
    elif fmt == "pdf":
        content = gen.crm_leads_pdf()
        mimetype = "application/pdf"
    else:
        return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
    response = current_app.response_class(response=content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("crm_leads", fmt)}"'
    return response


@bp.route("/api/reports/inventory/<fmt>")
@login_required
def api_report_inventory(fmt):
    from src.web.reports import ReportGenerator
    gen = ReportGenerator()
    if fmt == "csv":
        content = gen.inventory_csv()
        mimetype = "text/csv"
    elif fmt == "pdf":
        content = gen.inventory_pdf()
        mimetype = "application/pdf"
    else:
        return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
    response = current_app.response_class(response=content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("inventory", fmt)}"'
    return response


@bp.route("/api/reports/invoices/<fmt>")
@login_required
def api_report_invoices(fmt):
    from src.web.reports import ReportGenerator
    gen = ReportGenerator()
    if fmt == "csv":
        content = gen.invoices_csv()
        mimetype = "text/csv"
    elif fmt == "pdf":
        content = gen.invoices_pdf()
        mimetype = "application/pdf"
    else:
        return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
    response = current_app.response_class(response=content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("invoices", fmt)}"'
    return response


@bp.route("/api/reports/audit/<fmt>")
@login_required
def api_report_audit(fmt):
    """Genera reporte del audit log en CSV o PDF.
    Necesario para compliance SOC 2 / GDPR."""
    import io

    from src.core.repositories import AuditRepository
    from src.web.helpers import db

    audit_repo = AuditRepository(db)
    entries = audit_repo.get_recent(limit=10000)

    if fmt == "csv":
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "event", "details", "ip_address", "user_id", "created_at"])
        for e in entries:
            writer.writerow([
                e.get("id", ""),
                e.get("event", ""),
                e.get("details", ""),
                e.get("ip_address", ""),
                e.get("user_id", ""),
                e.get("created_at", ""),
            ])
        content = output.getvalue().encode("utf-8")
        mimetype = "text/csv"
    elif fmt == "pdf":
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=8)
        pdf.cell(0, 6, "Audit Log Report", ln=True, style="B")
        pdf.ln(3)
        for e in entries:
            line = f'{e.get("created_at", "")} | {e.get("event", "")} | {e.get("details", "")[:80]} | IP: {e.get("ip_address", "")}'
            pdf.cell(0, 4, line[:180], ln=True)
        content = pdf.output(dest="S").encode("latin-1") if isinstance(pdf.output(dest="S"), str) else pdf.output(dest="S")
        mimetype = "application/pdf"
    else:
        return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400

    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    response = current_app.response_class(response=content, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="audit_log_{timestamp}.{fmt}"'
    return response
