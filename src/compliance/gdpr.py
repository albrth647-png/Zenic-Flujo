"""GDPR Compliance — Data Protection Controls and Consent Management.

Implements key GDPR requirements:
- Lawful basis for processing (Art. 6)
- Data Subject Rights (Art. 15-22): Access, Rectification, Erasure, Portability, Restriction
- Consent management (Art. 7)
- Data Protection Impact Assessment (Art. 35)
- Data breach notification (Art. 33-34)
- Data Protection Officer designation (Art. 37)
- Records of processing activities (Art. 30)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.logging import get_logger

logger = get_logger("gdpr")


class ConsentStatus(Enum):
    """Status of data subject consent."""
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    NOT_GIVEN = "not_given"


class DataSubjectRight(Enum):
    """GDPR Data Subject Rights."""
    ACCESS = "right_of_access"          # Art. 15
    RECTIFICATION = "right_of_rectification"  # Art. 16
    ERASURE = "right_to_be_forgotten"   # Art. 17
    PORTABILITY = "right_to_portability"  # Art. 20
    RESTRICTION = "right_to_restriction"  # Art. 18
    OBJECTION = "right_to_object"       # Art. 21


@dataclass
class ConsentRecord:
    """Record of data subject consent."""
    consent_id: str = ""
    subject_id: str = ""  # ID of the data subject
    purpose: str = ""  # Processing purpose
    status: ConsentStatus = ConsentStatus.NOT_GIVEN
    granted_at: float = 0.0
    revoked_at: float = 0.0
    expires_at: float = 0.0
    ip_address: str = ""
    user_agent: str = ""
    proof_hash: str = ""  # SHA-256 of consent artifact

    def __post_init__(self) -> None:
        if not self.consent_id:
            self.consent_id = f"consent-{uuid.uuid4().hex[:12]}"


@dataclass
class DSARRequest:
    """Data Subject Access Request."""
    dsar_id: str = ""
    subject_email: str = ""
    subject_name: str = ""
    right_type: DataSubjectRight = DataSubjectRight.ACCESS
    status: str = "pending"  # pending, processing, completed, rejected
    description: str = ""
    submitted_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    response_data: dict[str, Any] = field(default_factory=dict)
    verified_identity: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.dsar_id:
            self.dsar_id = f"dsar-{uuid.uuid4().hex[:12]}"


@dataclass
class DataBreachRecord:
    """Personal data breach record (Art. 33-34)."""
    breach_id: str = ""
    discovered_at: float = field(default_factory=time.time)
    notified_supervisory_at: float = 0.0  # Within 72h
    notified_subjects_at: float = 0.0
    affected_subjects: int = 0
    data_categories: list[str] = field(default_factory=list)
    description: str = ""
    root_cause: str = ""
    remediation: str = ""
    risk_level: str = "low"  # low, medium, high
    notified_dpa: bool = False

    def __post_init__(self) -> None:
        if not self.breach_id:
            self.breach_id = f"breach-{uuid.uuid4().hex[:12]}"


# ── GDPR Control Catalog (8 controls) ─────────────────────

GDPR_CONTROLS: list[dict[str, Any]] = [
    # ── Lawful Basis & Rights ──
    {
        "name": "Lawful Basis for Processing",
        "description": "All processing of personal data is conducted under a lawful basis as defined in Art. 6 (consent, contract, legal obligation, vital interests, public task, legitimate interests).",
        "ref_code": "GDPR-Art6",
        "risk_level": "critical",
        "test_procedure": "Verify all data processing activities have documented lawful basis. Check consent records.",
        "implementation_guidance": "Maintain Register of Processing Activities (ROPA) with lawful basis for each activity.",
    },
    {
        "name": "Data Subject Access Request (DSAR)",
        "description": "Data subjects can exercise their right of access (Art. 15) within 30 days, free of charge.",
        "ref_code": "GDPR-Art15",
        "risk_level": "critical",
        "test_procedure": "Submit test DSAR and verify response within 30-day SLA. Check identity verification process.",
        "implementation_guidance": "Implement DSAR portal with automated data discovery and response workflow.",
    },
    {
        "name": "Right to Erasure (Right to be Forgotten)",
        "description": "Data subjects can request erasure of their personal data under conditions defined in Art. 17.",
        "ref_code": "GDPR-Art17",
        "risk_level": "high",
        "test_procedure": "Verify erasure workflow: identify, confirm, delete across all systems, confirm completion.",
        "implementation_guidance": "Implement data erasure pipeline with cascade deletion across all data stores.",
    },
    {
        "name": "Data Portability",
        "description": "Data subjects can receive their personal data in a structured, commonly used, machine-readable format (Art. 20).",
        "ref_code": "GDPR-Art20",
        "risk_level": "high",
        "test_procedure": "Verify export produces JSON/CSV with complete data schema. Test import into another system.",
        "implementation_guidance": "Support data export in JSON and CSV formats via self-service portal.",
    },
    {
        "name": "Consent Management",
        "description": "Consent for processing is freely given, specific, informed, and unambiguous (Art. 7). Consent can be withdrawn at any time.",
        "ref_code": "GDPR-Art7",
        "risk_level": "critical",
        "test_procedure": "Verify consent collection UI, withdrawal mechanism, and audit trail for consent changes.",
        "implementation_guidance": "Use ConsentManager with granular purpose-based consent and withdrawal tracking.",
    },
    {
        "name": "Data Breach Notification",
        "description": "Personal data breaches are notified to supervisory authority within 72 hours (Art. 33) and to affected data subjects without undue delay (Art. 34).",
        "ref_code": "GDPR-Art33",
        "risk_level": "critical",
        "test_procedure": "Verify breach detection, 72h notification timeline, and subject notification workflow.",
        "implementation_guidance": "Implement automated breach detection, notification templates, and escalation workflow.",
    },
    {
        "name": "Data Protection Impact Assessment (DPIA)",
        "description": "DPIAs are conducted for processing that presents high risk to data subjects' rights and freedoms (Art. 35).",
        "ref_code": "GDPR-Art35",
        "risk_level": "high",
        "test_procedure": "Verify DPIA process: screening, assessment, risk mitigation, DPO review, sign-off.",
        "implementation_guidance": "Implement DPIA template with automated risk scoring and approval workflow.",
    },
    {
        "name": "Records of Processing Activities (ROPA)",
        "description": "The controller maintains records of all processing activities (Art. 30), including purposes, categories, and retention schedules.",
        "ref_code": "GDPR-Art30",
        "risk_level": "high",
        "test_procedure": "Verify ROPA is complete: data categories, purposes, lawful basis, retention, technical measures.",
        "implementation_guidance": "Maintain automated ROPA with data flow mapping and retention schedules.",
    },
]


class ConsentManager:
    """Manages GDPR consent records.

    Provides:
    - Consent collection with proof (timestamp, IP, user agent)
    - Consent withdrawal
    - Consent audit trail
    - Expiration management
    """

    _instance: ConsentManager | None = None
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
    def get_instance(cls, **kwargs: Any) -> ConsentManager:
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
            CREATE TABLE IF NOT EXISTS gdpr_consents (
                consent_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'not_given',
                granted_at REAL,
                revoked_at REAL,
                expires_at REAL,
                ip_address TEXT,
                user_agent TEXT,
                proof_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS gdpr_dsar_requests (
                dsar_id TEXT PRIMARY KEY,
                subject_email TEXT NOT NULL,
                subject_name TEXT,
                right_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                description TEXT,
                submitted_at REAL,
                completed_at REAL,
                response_data TEXT,
                verified_identity INTEGER DEFAULT 0,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS gdpr_breaches (
                breach_id TEXT PRIMARY KEY,
                discovered_at REAL,
                notified_supervisory_at REAL,
                notified_subjects_at REAL,
                affected_subjects INTEGER DEFAULT 0,
                data_categories TEXT,
                description TEXT,
                root_cause TEXT,
                remediation TEXT,
                risk_level TEXT DEFAULT 'low',
                notified_dpa INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_gdpr_consent_subject ON gdpr_consents(subject_id);
            CREATE INDEX IF NOT EXISTS idx_gdpr_dsar_status ON gdpr_dsar_requests(status);
            CREATE INDEX IF NOT EXISTS idx_gdpr_dsar_email ON gdpr_dsar_requests(subject_email);
        """)
        self._conn.commit()
        logger.info("GDPR ConsentManager: Database initialized")

    # ── Consent Management ─────────────────────────────────

    def grant_consent(
        self,
        subject_id: str,
        purpose: str,
        ip_address: str = "",
        user_agent: str = "",
        expires_in_days: int = 365,
    ) -> ConsentRecord:
        """Record consent granted by a data subject."""
        record = ConsentRecord(
            subject_id=subject_id,
            purpose=purpose,
            status=ConsentStatus.GRANTED,
            granted_at=time.time(),
            expires_at=time.time() + (expires_in_days * 86400),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Create proof hash
        proof_data = f"{record.consent_id}:{subject_id}:{purpose}:{record.granted_at}:{ip_address}"
        import hashlib
        record.proof_hash = hashlib.sha256(proof_data.encode()).hexdigest()

        self._persist_consent(record)
        logger.info(f"GDPR: Consent granted for subject '{subject_id}', purpose='{purpose}'")
        return record

    def revoke_consent(self, consent_id: str) -> bool:
        """Revoke a previously granted consent."""
        existing = self._fetch_consent(consent_id)
        if not existing:
            return False
        if existing.get("status") != ConsentStatus.GRANTED.value:
            return False

        self._conn.execute(
            "UPDATE gdpr_consents SET status = ?, revoked_at = ? WHERE consent_id = ?",
            (ConsentStatus.REVOKED.value, time.time(), consent_id),
        )
        self._conn.commit()
        logger.info(f"GDPR: Consent '{consent_id}' revoked")
        return True

    def get_consents(self, subject_id: str | None = None) -> list[dict[str, Any]]:
        """Get consent records with optional subject filter."""
        if subject_id:
            rows = self._conn.execute(
                "SELECT * FROM gdpr_consents WHERE subject_id = ? ORDER BY granted_at DESC",
                (subject_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gdpr_consents ORDER BY granted_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def has_valid_consent(self, subject_id: str, purpose: str) -> bool:
        """Check if a subject has valid (granted, non-expired) consent for a purpose."""
        now = time.time()
        row = self._conn.execute(
            "SELECT status, expires_at FROM gdpr_consents WHERE subject_id = ? AND purpose = ? ORDER BY granted_at DESC LIMIT 1",
            (subject_id, purpose),
        ).fetchone()
        if not row:
            return False
        return row["status"] == ConsentStatus.GRANTED.value and (row["expires_at"] == 0 or row["expires_at"] > now)

    # ── DSAR Management ────────────────────────────────────

    def create_dsar(
        self,
        subject_email: str,
        right_type: DataSubjectRight,
        subject_name: str = "",
        description: str = "",
    ) -> DSARRequest:
        """Create a new Data Subject Access Request."""
        dsar = DSARRequest(
            subject_email=subject_email,
            subject_name=subject_name,
            right_type=right_type,
            description=description,
        )
        self._persist_dsar(dsar)
        logger.info(f"GDPR: DSAR '{dsar.dsar_id}' created ({right_type.value}) for {subject_email}")
        return dsar

    def update_dsar_status(self, dsar_id: str, status: str, notes: str = "") -> bool:
        """Update DSAR status."""
        row = self._conn.execute(
            "SELECT status FROM gdpr_dsar_requests WHERE dsar_id = ?", (dsar_id,)
        ).fetchone()
        if not row:
            return False

        updates: dict[str, Any] = {"status": status}
        if status == "completed":
            updates["completed_at"] = time.time()
        if notes:
            updates["notes"] = notes

        self._conn.execute(
            "UPDATE gdpr_dsar_requests SET status = ?, completed_at = COALESCE(?, completed_at), notes = ? WHERE dsar_id = ?",
            (status, updates.get("completed_at"), notes, dsar_id),
        )
        self._conn.commit()
        return True

    def verify_dsar_identity(self, dsar_id: str) -> bool:
        """Mark DSAR identity as verified."""
        self._conn.execute(
            "UPDATE gdpr_dsar_requests SET verified_identity = 1 WHERE dsar_id = ?",
            (dsar_id,),
        )
        self._conn.commit()
        return True

    def get_dsar(self, dsar_id: str) -> dict[str, Any] | None:
        """Get a DSAR by ID."""
        row = self._conn.execute(
            "SELECT * FROM gdpr_dsar_requests WHERE dsar_id = ?", (dsar_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_dsars(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List DSAR requests with optional filter."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM gdpr_dsar_requests WHERE status = ? ORDER BY submitted_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM gdpr_dsar_requests ORDER BY submitted_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_dsars_count(self) -> int:
        """Get count of pending DSARs (for SLA monitoring)."""
        row = self._conn.execute(
            "SELECT COUNT(*) as c FROM gdpr_dsar_requests WHERE status = 'pending'"
        ).fetchone()
        return row["c"] if row else 0

    def get_overdue_dsars(self) -> list[dict[str, Any]]:
        """Get DSARs that are overdue (>30 days pending)."""
        cutoff = time.time() - (30 * 86400)
        rows = self._conn.execute(
            "SELECT * FROM gdpr_dsar_requests WHERE status IN ('pending', 'processing') AND submitted_at < ? ORDER BY submitted_at",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Breach Management ──────────────────────────────────

    def record_breach(
        self,
        description: str,
        affected_subjects: int,
        data_categories: list[str],
        risk_level: str = "medium",
    ) -> DataBreachRecord:
        """Record a personal data breach."""
        breach = DataBreachRecord(
            description=description,
            affected_subjects=affected_subjects,
            data_categories=data_categories,
            risk_level=risk_level,
        )
        self._persist_breach(breach)
        logger.warning(f"GDPR: Data breach '{breach.breach_id}' recorded ({affected_subjects} subjects)")
        return breach

    def notify_breach(self, breach_id: str) -> bool:
        """Mark breach as notified to supervisory authority."""
        self._conn.execute(
            "UPDATE gdpr_breaches SET notified_supervisory_at = ?, notified_dpa = 1 WHERE breach_id = ?",
            (time.time(), breach_id),
        )
        self._conn.commit()
        return True

    def list_breaches(self, limit: int = 50) -> list[dict[str, Any]]:
        """List data breaches."""
        rows = self._conn.execute(
            "SELECT * FROM gdpr_breaches ORDER BY discovered_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ──────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get GDPR compliance statistics."""
        total_consents = self._conn.execute("SELECT COUNT(*) as c FROM gdpr_consents").fetchone()
        active_consents = self._conn.execute(
            "SELECT COUNT(*) as c FROM gdpr_consents WHERE status = 'granted'"
        ).fetchone()
        total_dsars = self._conn.execute("SELECT COUNT(*) as c FROM gdpr_dsar_requests").fetchone()
        pending_dsars = self.get_pending_dsars_count()
        overdue_dsars = len(self.get_overdue_dsars())
        total_breaches = self._conn.execute("SELECT COUNT(*) as c FROM gdpr_breaches").fetchone()

        return {
            "total_consents": total_consents["c"] if total_consents else 0,
            "active_consents": active_consents["c"] if active_consents else 0,
            "total_dsars": total_dsars["c"] if total_dsars else 0,
            "pending_dsars": pending_dsars,
            "overdue_dsars": overdue_dsars,
            "total_breaches": total_breaches["c"] if total_breaches else 0,
            "dsar_compliance_pct": max(
                0,
                100 - (overdue_dsars / max(total_dsars["c"], 1)) * 100
            ) if total_dsars else 100,
        }

    # ── Persistence ────────────────────────────────────────

    def _persist_consent(self, record: ConsentRecord) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT OR REPLACE INTO gdpr_consents
               (consent_id, subject_id, purpose, status, granted_at, revoked_at,
                expires_at, ip_address, user_agent, proof_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.consent_id, record.subject_id, record.purpose, record.status.value,
             record.granted_at, record.revoked_at, record.expires_at,
             record.ip_address, record.user_agent, record.proof_hash),
        )
        self._conn.commit()

    def _persist_dsar(self, dsar: DSARRequest) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT INTO gdpr_dsar_requests
               (dsar_id, subject_email, subject_name, right_type, status, description,
                submitted_at, completed_at, response_data, verified_identity, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dsar.dsar_id, dsar.subject_email, dsar.subject_name, dsar.right_type.value,
             dsar.status, dsar.description, dsar.submitted_at, dsar.completed_at,
             json.dumps(dsar.response_data), int(dsar.verified_identity), dsar.notes),
        )
        self._conn.commit()

    def _persist_breach(self, breach: DataBreachRecord) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT INTO gdpr_breaches
               (breach_id, discovered_at, notified_supervisory_at, notified_subjects_at,
                affected_subjects, data_categories, description, root_cause, remediation,
                risk_level, notified_dpa)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (breach.breach_id, breach.discovered_at, breach.notified_supervisory_at,
             breach.notified_subjects_at, breach.affected_subjects,
             json.dumps(breach.data_categories), breach.description, breach.root_cause,
             breach.remediation, breach.risk_level, int(breach.notified_dpa)),
        )
        self._conn.commit()

    def _fetch_consent(self, consent_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM gdpr_consents WHERE consent_id = ?", (consent_id,)
        ).fetchone()
        return dict(row) if row else None

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
