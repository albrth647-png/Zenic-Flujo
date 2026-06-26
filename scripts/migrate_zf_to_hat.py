#!/usr/bin/env python3
"""
Migration script: Zenic-Flujo → HAT-ORBITAL.

Crea las 7 tablas HAT en la DB SQLite existente de ZF.
No modifica tablas existentes — HAT convive con ZF.

Uso:
    python scripts/migrate_zf_to_hat.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.hat.ledger.repository import LedgerRepository


def migrate() -> dict[str, str]:
    """Ejecuta la migración ZF → HAT.

    Returns:
        Dict con estado de cada tabla: 'created' o 'exists'.
    """
    repo = LedgerRepository()
    db = repo._db
    expected_tables = [
        "hat_facts", "hat_hypotheses", "hat_plan", "hat_progress",
        "hat_dispatch_registry", "hat_agent_cards", "hat_sessions",
    ]
    result: dict[str, str] = {}
    for table in expected_tables:
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        result[table] = "exists" if row else "missing"
    return result


def main() -> int:
    print("=== Migration: Zenic-Flujo → HAT-ORBITAL ===\n")
    result = migrate()
    all_ok = True
    for table, status in result.items():
        icon = "✅" if status == "exists" else "❌"
        print(f"  {icon} {table}: {status}")
        if status != "exists":
            all_ok = False

    if all_ok:
        print("\n✅ Migration successful — all 7 HAT tables ready.")
        print("\nNext steps:")
        print("  1. curl http://localhost:8000/api/hat/health")
        print("  2. python scripts/benchmark_hat.py --n 20")
        return 0
    print("\n❌ Migration incomplete — some tables missing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
