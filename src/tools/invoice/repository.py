"""
Workflow Determinista — Invoice Repository
"""
import json
from datetime import datetime, timedelta

from src.data.database_manager import DatabaseManager


class InvoiceRepository:
    def __init__(self):
        self._db = DatabaseManager()

    def create(self, number: str, client_name: str, client_email: str | None,
               items: list, subtotal: float, tax_rate: float, tax_amount: float,
               discount: float, total: float, due_date: str | None = None,
               notes: str | None = None,
               user_id: int | None = None) -> dict:
        if not due_date:
            due_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        cursor = self._db.execute(
            """INSERT INTO invoices (number, client_name, client_email, items, subtotal,
               tax_rate, tax_amount, discount, total, due_date, notes, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (number, client_name, client_email, json.dumps(items),
             subtotal, tax_rate, tax_amount, discount, total, due_date, notes,
             user_id or 1),
        )
        self._db.commit()
        return self.get(cursor.lastrowid)

    def get(self, invoice_id: int) -> dict | None:
        row = self._db.fetchone("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        if row:
            if isinstance(row.get("items"), str):
                row["items"] = json.loads(row["items"])
        return row

    def list_invoices(self, status: str | None = None, limit: int = 50,
                       user_id: int | None = None) -> list[dict]:
        if status and user_id:
            rows = self._db.fetchall(
                "SELECT * FROM invoices WHERE status = ? AND user_id = ? ORDER BY issued_at DESC LIMIT ?",
                (status, user_id, limit),
            )
        elif status:
            rows = self._db.fetchall(
                "SELECT * FROM invoices WHERE status = ? ORDER BY issued_at DESC LIMIT ?",
                (status, limit),
            )
        elif user_id:
            rows = self._db.fetchall(
                "SELECT * FROM invoices WHERE user_id = ? ORDER BY issued_at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM invoices ORDER BY issued_at DESC LIMIT ?", (limit,)
            )
        for row in rows:
            if isinstance(row.get("items"), str):
                row["items"] = json.loads(row["items"])
        return rows

    def update_status(self, invoice_id: int, status: str) -> dict | None:
        self._db.execute(
            "UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id)
        )
        self._db.commit()
        return self.get(invoice_id)

    def mark_paid(self, invoice_id: int) -> dict | None:
        self._db.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ? WHERE id = ?",
            (datetime.now().isoformat(), invoice_id),
        )
        self._db.commit()
        return self.get(invoice_id)

    def get_overdue(self) -> list[dict]:
        return self._db.fetchall(
            "SELECT * FROM invoices WHERE status = 'pending' AND due_date < date('now')"
        )

    def get_stats(self) -> dict:
        stats = self._db.fetchone(
            """SELECT COUNT(*) as total,
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
               SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) as paid,
               SUM(CASE WHEN status='overdue' THEN 1 ELSE 0 END) as overdue,
               SUM(CASE WHEN status='paid' THEN total ELSE 0 END) as total_revenue
               FROM invoices"""
        )
        return dict(stats) if stats else {}
