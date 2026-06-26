"""
Workflow Determinista — CRM Repository
"""

from datetime import datetime

from src.core.db.sql_builder import build_update_query
from src.core.db.sqlite_manager import DatabaseManager


class CRMRepository:
    """Repositorio para operaciones CRUD de CRM."""

    def __init__(self):
        self._db = DatabaseManager()

    def create_lead(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        source: str = "manual",
        notes: str | None = None,
        user_id: int | None = None,
        stage: str = "new",
    ) -> dict:
        cursor = self._db.execute(
            """INSERT INTO leads (name, email, phone, company, source, notes, stage, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, email, phone, company, source, notes, stage, user_id or 1),
        )
        self._db.commit()
        return self.get_lead(cursor.lastrowid)

    def get_lead(self, lead_id: int) -> dict | None:
        return self._db.fetchone("SELECT * FROM leads WHERE id = ?", (lead_id,))

    def list_leads(
        self, stage: str | None = None, limit: int = 50, offset: int = 0, user_id: int | None = None
    ) -> list[dict]:
        if stage and user_id:
            return self._db.fetchall(
                "SELECT * FROM leads WHERE stage = ? AND user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (stage, user_id, limit, offset),
            )
        elif stage:
            return self._db.fetchall(
                "SELECT * FROM leads WHERE stage = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (stage, limit, offset),
            )
        elif user_id:
            return self._db.fetchall(
                "SELECT * FROM leads WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            )
        return self._db.fetchall(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def update_lead(self, lead_id: int, **fields) -> dict | None:
        allowed = {"name", "email", "phone", "company", "stage", "source", "notes", "updated_at"}
        result = build_update_query(
            "leads",
            allowed,
            fields,
            extra_set={"updated_at": datetime.now().isoformat()},
        )
        if result is None:
            return self.get_lead(lead_id)
        sql, params = result
        # Append el valor del WHERE (id = ?) al final de los params
        self._db.execute(sql, (*params, lead_id))
        self._db.commit()
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id: int) -> bool:
        self._db.execute("DELETE FROM lead_activities WHERE lead_id = ?", (lead_id,))
        self._db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        self._db.commit()
        return True

    def add_activity(self, lead_id: int, activity_type: str, description: str | None = None) -> dict:
        cursor = self._db.execute(
            "INSERT INTO lead_activities (lead_id, activity_type, description) VALUES (?, ?, ?)",
            (lead_id, activity_type, description),
        )
        self._db.commit()
        return {"id": cursor.lastrowid, "lead_id": lead_id, "activity_type": activity_type}

    def get_stats(self) -> dict:
        total = self._db.fetchone("SELECT COUNT(*) as count FROM leads")
        by_stage = self._db.fetchall("SELECT stage, COUNT(*) as count FROM leads GROUP BY stage")
        return {
            "total": total["count"] if total else 0,
            "by_stage": {r["stage"]: r["count"] for r in by_stage},
        }

    # ── Foso 3: Clients ──────────────────────────────────────

    def create_client(
        self,
        name: str,
        fiscal_type: str = "",
        fiscal_id: str = "",
        email: str = "",
        phone: str = "",
        address: str = "",
        city: str = "",
        country_code: str = "MX",
        currency: str = "MXN",
        lead_id: int | None = None,
        user_id: int = 1,
    ) -> dict:
        cursor = self._db.execute(
            """INSERT INTO clients (name, fiscal_type, fiscal_id, email, phone,
               address, city, country_code, currency, lead_id, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, fiscal_type, fiscal_id, email, phone,
             address, city, country_code, currency, lead_id, user_id),
        )
        self._db.commit()
        return self.get_client(cursor.lastrowid)

    def get_client(self, client_id: int) -> dict | None:
        return self._db.fetchone("SELECT * FROM clients WHERE id = ?", (client_id,))

    def get_client_by_fiscal_id(self, fiscal_id: str, country_code: str) -> dict | None:
        return self._db.fetchone(
            "SELECT * FROM clients WHERE fiscal_id = ? AND country_code = ?",
            (fiscal_id, country_code),
        )

    def list_clients(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._db.fetchall(
            "SELECT * FROM clients ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def update_client(self, client_id: int, **fields) -> dict | None:
        allowed = {"name", "fiscal_type", "fiscal_id", "email", "phone",
                    "address", "city", "country_code", "currency", "updated_at"}
        result = build_update_query(
            "clients", allowed, fields,
            extra_set={"updated_at": datetime.now().isoformat()},
        )
        if result is None:
            return self.get_client(client_id)
        sql, params = result
        self._db.execute(sql, (*params, client_id))
        self._db.commit()
        return self.get_client(client_id)

    # ── Foso 3: Deals ────────────────────────────────────────

    def create_deal(
        self,
        lead_id: int,
        title: str,
        amount: float,
        currency: str = "MXN",
        probability: float = 0.5,
        expected_close_date: str = "",
        stage: str = "proposal",
        items: list | None = None,
        notes: str = "",
        client_id: int | None = None,
    ) -> dict:
        import json
        cursor = self._db.execute(
            """INSERT INTO deals (lead_id, client_id, title, amount, currency,
               probability, expected_close_date, stage, items, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, client_id, title, amount, currency,
             probability, expected_close_date, stage,
             json.dumps(items or []), notes),
        )
        self._db.commit()
        return self.get_deal(cursor.lastrowid)

    def get_deal(self, deal_id: int) -> dict | None:
        deal = self._db.fetchone("SELECT * FROM deals WHERE id = ?", (deal_id,))
        if deal and isinstance(deal.get("items"), str):
            import json
            deal["items"] = json.loads(deal["items"])
        return deal

    def list_deals(self, lead_id: int | None = None, limit: int = 50) -> list[dict]:
        if lead_id:
            return self._db.fetchall(
                "SELECT * FROM deals WHERE lead_id = ? ORDER BY created_at DESC LIMIT ?",
                (lead_id, limit),
            )
        return self._db.fetchall("SELECT * FROM deals ORDER BY created_at DESC LIMIT ?", (limit,))
