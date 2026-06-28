"""HIPAA Compliance — PHI Controls, BAAs, and Administrative Safeguards.

Implements key HIPAA (Health Insurance Portability and Accountability Act) requirements:
- Privacy Rule (45 CFR §164.500-534): Protected Health Information (PHI) controls
- Security Rule (45 CFR §164.302-318): Administrative, physical, technical safeguards
- Breach Notification Rule (45 CFR §164.400-414)
- Business Associate Agreements (BAA)
- Omnibus Rule (2013): Extended BAA liability
- HITECH Act: Enhanced enforcement and breach notification
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.logging import get_logger

logger = get_logger("hipaa")


class BAAType(Enum):
    """Types of Business Associate Agreements."""
    STANDARD = "standard"
    CLOUD_SERVICE = "cloud_service"
    SUBPROCESSOR = "subprocessor"
    CONSULTING = "consulting"


class BAStatus(Enum):
    """BAA lifecycle status."""
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    EXECUTED = "executed"
    EXPIRED = "expired"
    TERMINATED = "terminated"


@dataclass
class BusinessAssociateAgreement:
    """A Business Associate Agreement (BAA) for HIPAA compliance."""
    baa_id: str = ""
    company_name: str = ""
    baa_type: BAAType = BAAType.STANDARD
    status: BAStatus = BAStatus.DRAFT
    effective_date: float = field(default_factory=time.time)
    expiration_date: float = 0.0
    signed_by_covered_entity: str = ""
    signed_by_business_associate: str = ""
    signed_at: float = 0.0
    scope_of_services: str = ""
    phi_access_description: str = ""
    security_measures: str = ""
    breach_notification_sla_hours: int = 24
    document_url: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.baa_id:
            self.baa_id = f"baa-{uuid.uuid4().hex[:12]}"


@dataclass
class PHIInventoryItem:
    """An item in the Protected Health Information (PHI) inventory."""
    item_id: str = ""
    data_type: str = ""  # e.g., medical_record, diagnosis, lab_result, insurance
    description: str = ""
    storage_location: str = ""
    format: str = "electronic"  # electronic, paper, oral
    retention_days: int = 365
    access_controls: str = ""
    encryption_status: str = "aes256"
    backup_procedure: str = ""
    disposal_method: str = "secure_deletion"

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = f"phi-{uuid.uuid4().hex[:8]}"


# ── HIPAA Control Catalog (10 controls) ──────────────────

HIPAA_CONTROLS: list[dict[str, Any]] = [
    {
        "name": "Privacy Rule — PHI Identification & Classification",
        "description": "All Protected Health Information (PHI) is identified, classified, and handled according to the Privacy Rule (45 CFR §164.506). Minimum necessary standard is enforced.",
        "ref_code": "HIPAA-164.506",
        "risk_level": "critical",
        "test_procedure": "Verify PHI inventory is complete and up-to-date. Check minimum necessary configuration.",
        "implementation_guidance": "Maintain PHI inventory with automated discovery and classification.",
    },
    {
        "name": "Security Rule — Access Control (Technical Safeguard)",
        "description": "Unique user identification, emergency access procedures, automatic logoff, and encryption/decryption are implemented (45 CFR §164.312(a)).",
        "ref_code": "HIPAA-164.312(a)",
        "risk_level": "critical",
        "test_procedure": "Verify unique user IDs, automatic logoff timer, encryption at rest/transit, emergency access procedure.",
        "implementation_guidance": "RBAC with unique user IDs. AES-256 encryption. Automatic session timeout.",
    },
    {
        "name": "Security Rule — Audit Controls (Technical Safeguard)",
        "description": "Hardware, software, and procedural mechanisms that record and examine access and other activity in information systems (45 CFR §164.312(b)).",
        "ref_code": "HIPAA-164.312(b)",
        "risk_level": "critical",
        "test_procedure": "Verify audit logs capture all PHI access: who, what, when. Check log retention (min 6 years).",
        "implementation_guidance": "Comprehensive audit logging of all PHI access with 6-year retention.",
    },
    {
        "name": "Security Rule — Integrity Controls (Technical Safeguard)",
        "description": "Mechanisms to ensure that electronic PHI is not improperly altered or destroyed (45 CFR §164.312(c)).",
        "ref_code": "HIPAA-164.312(c)",
        "risk_level": "high",
        "test_procedure": "Verify data integrity checks (SHA-256 hashing), checksums, and electronic signatures.",
        "implementation_guidance": "Implement integrity verification with hash chains and electronic signatures.",
    },
    {
        "name": "Security Rule — Person/Authentication (Technical Safeguard)",
        "description": "Procedures to verify that a person or entity seeking access to ePHI is the one claimed (45 CFR §164.312(d)).",
        "ref_code": "HIPAA-164.312(d)",
        "risk_level": "high",
        "test_procedure": "Verify MFA enforcement for PHI access. Check password complexity requirements.",
        "implementation_guidance": "MFA with TOTP for all PHI access. Strong password policy (12+ chars, complex).",
    },
    {
        "name": "Security Rule — Transmission Security (Technical Safeguard)",
        "description": "Implement technical security measures to guard against unauthorized access to ePHI transmitted over electronic networks (45 CFR §164.312(e)).",
        "ref_code": "HIPAA-164.312(e)",
        "risk_level": "high",
        "test_procedure": "Verify TLS 1.2+ for all data in transit. Check integrity controls.",
        "implementation_guidance": "Enforce TLS 1.2+ minimum. Implement HSTS and certificate pinning.",
    },
    {
        "name": "Business Associate Agreements (BAA)",
        "description": "Written BAAs are in place with all business associates who create, receive, maintain, or transmit PHI (45 CFR §164.504(e)).",
        "ref_code": "HIPAA-164.504(e)",
        "risk_level": "critical",
        "test_procedure": "Verify BAA inventory is complete. Check each BAA contains required elements: permitted uses, safeguards, breach notification, termination.",
        "implementation_guidance": "Maintain BAA inventory with automated renewal tracking and compliance checks.",
    },
    {
        "name": "Breach Notification Rule",
        "description": "Breaches of unsecured PHI are notified to affected individuals, HHS, and media (when applicable) within 60 days (45 CFR §164.400-414).",
        "ref_code": "HIPAA-164.400",
        "risk_level": "critical",
        "test_procedure": "Verify breach detection, risk assessment (4-factor), notification workflow, and documentation.",
        "implementation_guidance": "Automated breach detection with 4-factor risk assessment and notification templates.",
    },
    {
        "name": "Administrative Safeguards — Security Management",
        "description": "Implement policies and procedures to prevent, detect, contain, and correct security violations (45 CFR §164.308(a)). Includes risk analysis, risk management, sanction policy, and information system activity review.",
        "ref_code": "HIPAA-164.308(a)",
        "risk_level": "critical",
        "test_procedure": "Verify risk analysis document, risk management plan, sanction policy, and regular system activity reviews.",
        "implementation_guidance": "Annual risk analysis. Documented risk management plan. Regular security reviews.",
    },
    {
        "name": "Administrative Safeguards — Workforce Security",
        "description": "Implement policies to ensure that workforce members have appropriate access to ePHI (45 CFR §164.308(a)(3)). Includes authorization, supervision, and termination procedures.",
        "ref_code": "HIPAA-164.308(a)(3)",
        "risk_level": "high",
        "test_procedure": "Verify authorization/supervision policies, termination procedures (immediate access revocation), and sanctions.",
        "implementation_guidance": "Automated access provisioning and immediate deprovisioning on termination.",
    },
]


class BAAManager:
    """Manages Business Associate Agreements (BAAs) for HIPAA compliance."""

    _instance: BAAManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from src.core.config import COMPLIANCE_DB_PATH
            db_path = str(COMPLIANCE_DB_PATH)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> BAAManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        # Fix NEW-BUG-6: PRAGMA WAL + busy_timeout (mismo fix que compliance/__init__.py bug #40)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS hipaa_baas (
                baa_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                baa_type TEXT NOT NULL DEFAULT 'standard',
                status TEXT NOT NULL DEFAULT 'draft',
                effective_date REAL,
                expiration_date REAL,
                signed_by_covered_entity TEXT,
                signed_by_business_associate TEXT,
                signed_at REAL,
                scope_of_services TEXT,
                phi_access_description TEXT,
                security_measures TEXT,
                breach_notification_sla_hours INTEGER DEFAULT 24,
                document_url TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS hipaa_phi_inventory (
                item_id TEXT PRIMARY KEY,
                data_type TEXT NOT NULL,
                description TEXT,
                storage_location TEXT,
                format TEXT DEFAULT 'electronic',
                retention_days INTEGER DEFAULT 365,
                access_controls TEXT,
                encryption_status TEXT DEFAULT 'aes256',
                backup_procedure TEXT,
                disposal_method TEXT DEFAULT 'secure_deletion'
            );
            CREATE INDEX IF NOT EXISTS idx_hipaa_baas_status ON hipaa_baas(status);
            CREATE INDEX IF NOT EXISTS idx_hipaa_phi_type ON hipaa_phi_inventory(data_type);
        """)
        self._conn.commit()
        logger.info("HIPAA BAAManager: Database initialized")

    # ── BAA Management ─────────────────────────────────────

    def create_baa(self, baa: BusinessAssociateAgreement) -> str:
        """Create a new BAA."""
        self._conn.execute(
            """INSERT INTO hipaa_baas
               (baa_id, company_name, baa_type, status, effective_date, expiration_date,
                signed_by_covered_entity, signed_by_business_associate, signed_at,
                scope_of_services, phi_access_description, security_measures,
                breach_notification_sla_hours, document_url, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (baa.baa_id, baa.company_name, baa.baa_type.value, baa.status.value,
             baa.effective_date, baa.expiration_date, baa.signed_by_covered_entity,
             baa.signed_by_business_associate, baa.signed_at, baa.scope_of_services,
             baa.phi_access_description, baa.security_measures,
             baa.breach_notification_sla_hours, baa.document_url, baa.notes),
        )
        self._conn.commit()
        logger.info(f"HIPAA: BAA '{baa.baa_id}' created for {baa.company_name}")
        return baa.baa_id

    def execute_baa(self, baa_id: str, signed_by_covered: str, signed_by_ba: str) -> bool:
        """Execute/sign a BAA."""
        self._conn.execute(
            """UPDATE hipaa_baas SET
               status = ?, signed_by_covered_entity = ?, signed_by_business_associate = ?,
               signed_at = ?
               WHERE baa_id = ?""",
            (BAStatus.EXECUTED.value, signed_by_covered, signed_by_ba, time.time(), baa_id),
        )
        self._conn.commit()
        return True

    def list_baas(self, status: str | None = None) -> list[dict[str, Any]]:
        """List BAAs with optional status filter."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM hipaa_baas WHERE status = ? ORDER BY effective_date DESC", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM hipaa_baas ORDER BY effective_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_expiring_baas(self, days: int = 90) -> list[dict[str, Any]]:
        """Get BAAs expiring within the specified number of days."""
        cutoff = time.time() + (days * 86400)
        rows = self._conn.execute(
            "SELECT * FROM hipaa_baas WHERE status = 'executed' AND expiration_date > 0 AND expiration_date < ? ORDER BY expiration_date",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── PHI Inventory ──────────────────────────────────────

    def add_phi_item(self, item: PHIInventoryItem) -> str:
        """Add an item to the PHI inventory."""
        self._conn.execute(
            """INSERT INTO hipaa_phi_inventory
               (item_id, data_type, description, storage_location, format,
                retention_days, access_controls, encryption_status,
                backup_procedure, disposal_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.item_id, item.data_type, item.description, item.storage_location,
             item.format, item.retention_days, item.access_controls,
             item.encryption_status, item.backup_procedure, item.disposal_method),
        )
        self._conn.commit()
        return item.item_id

    def list_phi_inventory(self) -> list[dict[str, Any]]:
        """List all PHI inventory items."""
        rows = self._conn.execute(
            "SELECT * FROM hipaa_phi_inventory ORDER BY data_type"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ──────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get HIPAA compliance statistics."""
        total_baas = self._conn.execute("SELECT COUNT(*) as c FROM hipaa_baas").fetchone()
        executed_baas = self._conn.execute(
            "SELECT COUNT(*) as c FROM hipaa_baas WHERE status = 'executed'"
        ).fetchone()
        expiring_baas = len(self.get_expiring_baas())
        phi_count = self._conn.execute("SELECT COUNT(*) as c FROM hipaa_phi_inventory").fetchone()
        expired_baas = self._conn.execute(
            "SELECT COUNT(*) as c FROM hipaa_baas WHERE status IN ('expired', 'terminated')"
        ).fetchone()

        return {
            "total_baas": total_baas["c"] if total_baas else 0,
            "executed_baas": executed_baas["c"] if executed_baas else 0,
            "expiring_baas": expiring_baas,
            "total_phi_items": phi_count["c"] if phi_count else 0,
            "expired_baas": expired_baas["c"] if expired_baas else 0,
            "baa_compliance_pct": (
                (executed_baas["c"] / max(total_baas["c"], 1)) * 100
            ) if total_baas else 100,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None
