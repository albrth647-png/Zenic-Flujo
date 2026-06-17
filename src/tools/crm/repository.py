"""
Workflow Determinista — CRM Repository
"""

from datetime import datetime

from src.data.database_manager import DatabaseManager
from src.utils.sql import build_update_query


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
    ) -> dict:
        cursor = self._db.execute(
            """INSERT INTO leads (name, email, phone, company, source, notes, stage, user_id)
               VALUES (?, ?, ?, ?, ?, ?, 'new', ?)""",
            (name, email, phone, company, source, notes, user_id or 1),
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
