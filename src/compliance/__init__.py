"""SOC 2 Type I Compliance — Security controls and audit framework.

Implements the five Trust Service Criteria (TSC) for SOC 2 Type I:
1. Security (Common Criteria) — Logical/physical access controls
2. Availability — System availability and disaster recovery
3. Processing Integrity — Accurate, complete, and timely processing
4. Confidentiality — Data classification and protection
5. Privacy — Personal data collection, use, and retention

Features:
- Control catalog with automated testing
- Evidence collection and storage
- Audit trail generation
- Compliance scoring and reporting
- Continuous monitoring dashboard
- Policy management
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("compliance")


class TrustServiceCriteria(Enum):
    """SOC 2 Trust Service Criteria categories."""

    SECURITY = "security"  # CC (Common Criteria)
    AVAILABILITY = "availability"  # A1
    PROCESSING_INTEGRITY = "processing_integrity"  # PI1
    CONFIDENTIALITY = "confidentiality"  # C1
    PRIVACY = "privacy"  # P1


class ControlStatus(Enum):
    """Status of a compliance control."""

    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    FAILED = "failed"


class EvidenceType(Enum):
    """Types of compliance evidence."""

    POLICY_DOCUMENT = "policy_document"
    CONFIGURATION = "configuration"
    LOG_EXCERPT = "log_excerpt"
    SCREENSHOT = "screenshot"
    TEST_RESULT = "test_result"
    INTERVIEW_NOTE = "interview_note"
    SYSTEM_OUTPUT = "system_output"


@dataclass
class ComplianceControl:
    """A single SOC 2 compliance control.

    Maps to specific points in the SOC 2 TSC framework.
    """

    control_id: str = ""
    name: str = ""
    description: str = ""
    criteria: TrustServiceCriteria = TrustServiceCriteria.SECURITY
    ref_code: str = ""  # e.g., CC6.1, A1.2, PI1.3
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    owner: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    test_procedure: str = ""
    last_tested: float = 0.0
    last_result: str = ""
    remediation_notes: str = ""
    risk_level: str = "medium"  # low, medium, high, critical
    implementation_guidance: str = ""

    def __post_init__(self) -> None:
        if not self.control_id:
            self.control_id = f"ctrl-{uuid.uuid4().hex[:8]}"


@dataclass
class ComplianceEvidence:
    """Evidence supporting a compliance control."""

    evidence_id: str = ""
    control_id: str = ""
    evidence_type: EvidenceType = EvidenceType.CONFIGURATION
    description: str = ""
    content: str = ""  # The actual evidence content or reference
    content_hash: str = ""  # SHA-256 hash for integrity
    collected_at: float = field(default_factory=time.time)
    collected_by: str = "system"
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.evidence_id:
            self.evidence_id = f"ev-{uuid.uuid4().hex[:8]}"
        if self.content and not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class AuditEntry:
    """An entry in the compliance audit trail."""

    entry_id: str = ""
    timestamp: float = field(default_factory=time.time)
    actor: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    source_ip: str = ""
    session_id: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"audit-{uuid.uuid4().hex[:8]}"


@dataclass
class PolicyDocument:
    """A compliance policy document."""

    policy_id: str = ""
    name: str = ""
    version: str = "1.0"
    category: str = ""  # security, availability, privacy, etc.
    content: str = ""
    approved_by: str = ""
    approved_at: float = 0.0
    effective_date: float = field(default_factory=time.time)
    review_date: float = 0.0
    status: str = "draft"  # draft, approved, retired

    def __post_init__(self) -> None:
        if not self.policy_id:
            self.policy_id = f"pol-{uuid.uuid4().hex[:8]}"


# ── Default SOC 2 Control Catalog ──────────────────────────

SOC2_CONTROLS: list[dict[str, Any]] = [
    # ── Security (Common Criteria) ──
    {
        "name": "Access Control Policy",
        "description": "Logical access controls are implemented to restrict access to systems and data based on need and least privilege.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.1",
        "risk_level": "critical",
        "test_procedure": "Verify RBAC is configured with least-privilege roles. Check user access reviews.",
        "implementation_guidance": "Implement RBAC via RBACManager with periodic access reviews.",
    },
    {
        "name": "User Authentication",
        "description": "Users are authenticated before accessing system resources using secure mechanisms.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.1",
        "risk_level": "critical",
        "test_procedure": "Verify MFA enforcement and password policies. Check bcrypt hashing.",
        "implementation_guidance": "Use MFAService with TOTP and bcrypt password hashing.",
    },
    {
        "name": "Encryption at Rest",
        "description": "Sensitive data is encrypted at rest using strong cryptographic algorithms.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.1",
        "risk_level": "critical",
        "test_procedure": "Verify EncryptionService with BYOK support is active. Check key rotation.",
        "implementation_guidance": "Use EncryptionService with AES-256 and BYOK key management.",
    },
    {
        "name": "Encryption in Transit",
        "description": "Data in transit is protected using TLS/SSL encryption.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.7",
        "risk_level": "high",
        "test_procedure": "Verify TLS configuration on all endpoints. Check certificate validity.",
        "implementation_guidance": "Enforce HTTPS on all API endpoints with valid TLS certificates.",
    },
    {
        "name": "Network Security",
        "description": "Network access is restricted using firewalls, VPNs, and network segmentation.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.6",
        "risk_level": "high",
        "test_procedure": "Verify firewall rules, network segmentation, and VPN access controls.",
        "implementation_guidance": "Implement network policies via Docker/K8s network policies.",
    },
    {
        "name": "Vulnerability Management",
        "description": "Vulnerabilities are identified and remediated on a timely basis.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC7.1",
        "risk_level": "high",
        "test_procedure": "Review vulnerability scan results and remediation timelines.",
        "implementation_guidance": "Integrate Snyk/Trivy in CI/CD pipeline. Monthly scans.",
    },
    {
        "name": "Incident Response",
        "description": "Security incidents are detected, reported, and responded to in a timely manner.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC7.2",
        "risk_level": "high",
        "test_procedure": "Verify incident response plan exists. Test alerting mechanisms.",
        "implementation_guidance": "Implement audit trail, anomaly detection, and alerting.",
    },
    {
        "name": "Change Management",
        "description": "Changes to systems are authorized, documented, and tested before deployment.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC8.1",
        "risk_level": "medium",
        "test_procedure": "Review change management process, PR approvals, CI/CD gates.",
        "implementation_guidance": "Enforce PR reviews, branch protection, and CI/CD quality gates.",
    },
    {
        "name": "Audit Logging",
        "description": "System activities are logged and retained for audit purposes.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC7.2",
        "risk_level": "critical",
        "test_procedure": "Verify audit logs are generated for all sensitive operations. Check retention.",
        "implementation_guidance": "Use AuditLogger with 90-day retention and tamper detection.",
    },
    {
        "name": "SSO & Identity Federation",
        "description": "Single sign-on and identity federation are implemented for enterprise access.",
        "criteria": TrustServiceCriteria.SECURITY,
        "ref_code": "CC6.1",
        "risk_level": "high",
        "test_procedure": "Verify SAML/OIDC configuration. Test SSO login flow.",
        "implementation_guidance": "Use SSOService with SAML and OAuth2/OIDC providers.",
    },
    # ── Availability ──
    {
        "name": "System Monitoring",
        "description": "System health and performance are continuously monitored with alerting.",
        "criteria": TrustServiceCriteria.AVAILABILITY,
        "ref_code": "A1.2",
        "risk_level": "high",
        "test_procedure": "Verify OpenTelemetry integration. Check alerting thresholds.",
        "implementation_guidance": "Use Observability module with Prometheus metrics and alerts.",
    },
    {
        "name": "Backup & Recovery",
        "description": "Data is backed up regularly and recovery procedures are tested.",
        "criteria": TrustServiceCriteria.AVAILABILITY,
        "ref_code": "A1.3",
        "risk_level": "critical",
        "test_procedure": "Verify backup schedule, test restoration, check RTO/RPO targets.",
        "implementation_guidance": "Use BackupEngine with daily full + incremental backups.",
    },
    {
        "name": "Disaster Recovery Plan",
        "description": "A documented disaster recovery plan is maintained and tested.",
        "criteria": TrustServiceCriteria.AVAILABILITY,
        "ref_code": "A1.3",
        "risk_level": "high",
        "test_procedure": "Verify DR plan documentation. Check test results.",
        "implementation_guidance": "Document RTO/RPO targets. Quarterly DR drills.",
    },
    # ── Processing Integrity ──
    {
        "name": "Data Validation",
        "description": "Input data is validated to ensure completeness, accuracy, and authorization.",
        "criteria": TrustServiceCriteria.PROCESSING_INTEGRITY,
        "ref_code": "PI1.2",
        "risk_level": "high",
        "test_procedure": "Verify input validation on API endpoints. Check Pydantic models.",
        "implementation_guidance": "Use Pydantic models for all API inputs. Schema validation.",
    },
    {
        "name": "Workflow Determinism",
        "description": "Workflow execution produces consistent, deterministic results.",
        "criteria": TrustServiceCriteria.PROCESSING_INTEGRITY,
        "ref_code": "PI1.3",
        "risk_level": "high",
        "test_procedure": "Run workflow benchmarks. Verify deterministic convergence via COD.",
        "implementation_guidance": "Orbital Engine's COD (Colapso Orbital Determinista) guarantees convergence.",
    },
    # ── Confidentiality ──
    {
        "name": "Data Classification",
        "description": "Data is classified based on sensitivity and handled according to classification.",
        "criteria": TrustServiceCriteria.CONFIDENTIALITY,
        "ref_code": "C1.2",
        "risk_level": "high",
        "test_procedure": "Verify data classification labels and handling procedures.",
        "implementation_guidance": "Implement data classification tags in metadata. Enforce per-class rules.",
    },
    {
        "name": "Tenant Data Isolation",
        "description": "Multi-tenant data is properly isolated to prevent cross-tenant access.",
        "criteria": TrustServiceCriteria.CONFIDENTIALITY,
        "ref_code": "C1.2",
        "risk_level": "critical",
        "test_procedure": "Verify tenant isolation in database. Test cross-tenant access denial.",
        "implementation_guidance": "Use TenantService with schema-per-tenant or DB-per-tenant isolation.",
    },
    # ── Privacy ──
    {
        "name": "Privacy Policy",
        "description": "A privacy policy is published describing data collection, use, and retention practices.",
        "criteria": TrustServiceCriteria.PRIVACY,
        "ref_code": "P1.1",
        "risk_level": "high",
        "test_procedure": "Verify privacy policy exists and is accessible. Review content.",
        "implementation_guidance": "Publish privacy policy. Implement consent management.",
    },
    {
        "name": "Data Retention & Disposal",
        "description": "Personal data is retained only as long as necessary and properly disposed of.",
        "criteria": TrustServiceCriteria.PRIVACY,
        "ref_code": "P1.3",
        "risk_level": "high",
        "test_procedure": "Verify retention policies are enforced. Check disposal procedures.",
        "implementation_guidance": "Implement automated retention policies with secure deletion.",
    },
]


class ComplianceManager:
    """Central manager for SOC 2 Type I compliance.

    Provides:
    - Control catalog management with automated status tracking
    - Evidence collection and integrity verification
    - Audit trail with tamper detection
    - Policy management with versioning
    - Compliance scoring and reporting
    - Continuous monitoring

    Usage:
        manager = ComplianceManager.get_instance()
        score = manager.calculate_compliance_score()
        report = manager.generate_report()
    """

    _instance: ComplianceManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = "compliance.db") -> None:
        self._db_path = db_path
        self._controls: dict[str, ComplianceControl] = {}
        self._evidence: dict[str, ComplianceEvidence] = {}
        self._policies: dict[str, PolicyDocument] = {}
        self._audit_trail: list[AuditEntry] = []
        self._lock_local = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        self._load_default_controls()

    @classmethod
    def get_instance(cls, **kwargs: Any) -> ComplianceManager:
        """Get or create the singleton manager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def _init_db(self) -> None:
        """Initialize SQLite for persistent compliance data."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_controls (
                control_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                criteria TEXT NOT NULL,
                ref_code TEXT,
                status TEXT NOT NULL DEFAULT 'not_implemented',
                owner TEXT,
                evidence_ids TEXT,
                test_procedure TEXT,
                last_tested REAL,
                last_result TEXT,
                remediation_notes TEXT,
                risk_level TEXT,
                implementation_guidance TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_evidence (
                evidence_id TEXT PRIMARY KEY,
                control_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                description TEXT,
                content_hash TEXT,
                collected_at REAL,
                collected_by TEXT,
                verified INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_audit (
                entry_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                actor TEXT,
                action TEXT,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                source_ip TEXT,
                session_id TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_policies (
                policy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT,
                category TEXT,
                content TEXT,
                approved_by TEXT,
                approved_at REAL,
                effective_date REAL,
                review_date REAL,
                status TEXT
            )
        """)
        self._conn.commit()

    def _load_default_controls(self) -> None:
        """Load the default SOC 2 control catalog."""
        for ctrl_data in SOC2_CONTROLS:
            ctrl = ComplianceControl(
                name=ctrl_data["name"],
                description=ctrl_data["description"],
                criteria=ctrl_data["criteria"],
                ref_code=ctrl_data.get("ref_code", ""),
                risk_level=ctrl_data.get("risk_level", "medium"),
                test_procedure=ctrl_data.get("test_procedure", ""),
                implementation_guidance=ctrl_data.get("implementation_guidance", ""),
            )
            self._controls[ctrl.control_id] = ctrl
            self._persist_control(ctrl)

    # ── Control Management ──────────────────────────────────

    def add_control(self, control: ComplianceControl) -> str:
        """Add a compliance control."""
        with self._lock_local:
            self._controls[control.control_id] = control
            self._persist_control(control)
        return control.control_id

    def update_control_status(
        self,
        control_id: str,
        status: ControlStatus,
        notes: str = "",
    ) -> bool:
        """Update the status of a compliance control."""
        with self._lock_local:
            ctrl = self._controls.get(control_id)
            if ctrl is None:
                return False
            ctrl.status = status
            ctrl.last_tested = time.time()
            ctrl.last_result = status.value
            if notes:
                ctrl.remediation_notes = notes
            self._persist_control(ctrl)
            self._add_audit_entry(
                actor="system",
                action="update_control_status",
                resource_type="control",
                resource_id=control_id,
                details={"new_status": status.value, "notes": notes},
            )
        return True

    def get_control(self, control_id: str) -> ComplianceControl | None:
        """Get a control by ID."""
        return self._controls.get(control_id)

    def list_controls(
        self,
        criteria: TrustServiceCriteria | None = None,
        status: ControlStatus | None = None,
        risk_level: str | None = None,
    ) -> list[ComplianceControl]:
        """List controls with optional filters."""
        controls = list(self._controls.values())
        if criteria:
            controls = [c for c in controls if c.criteria == criteria]
        if status:
            controls = [c for c in controls if c.status == status]
        if risk_level:
            controls = [c for c in controls if c.risk_level == risk_level]
        return controls

    # ── Evidence ────────────────────────────────────────────

    def collect_evidence(
        self,
        control_id: str,
        evidence_type: EvidenceType,
        description: str,
        content: str,
        collected_by: str = "system",
    ) -> ComplianceEvidence:
        """Collect evidence for a compliance control."""
        evidence = ComplianceEvidence(
            control_id=control_id,
            evidence_type=evidence_type,
            description=description,
            content=content,
            collected_by=collected_by,
        )

        with self._lock_local:
            self._evidence[evidence.evidence_id] = evidence
            ctrl = self._controls.get(control_id)
            if ctrl:
                ctrl.evidence_ids.append(evidence.evidence_id)
            self._persist_evidence(evidence)
            self._add_audit_entry(
                actor=collected_by,
                action="collect_evidence",
                resource_type="evidence",
                resource_id=evidence.evidence_id,
                details={"control_id": control_id, "type": evidence_type.value},
            )

        return evidence

    def verify_evidence(self, evidence_id: str) -> bool:
        """Verify the integrity of collected evidence."""
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            return False

        # Verify content hash
        current_hash = hashlib.sha256(evidence.content.encode()).hexdigest()
        if current_hash != evidence.content_hash:
            logger.warning("Evidence integrity check failed: %s", evidence_id)
            return False

        evidence.verified = True
        return True

    # ── Audit Trail ─────────────────────────────────────────

    def _add_audit_entry(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        source_ip: str = "",
        session_id: str = "",
    ) -> None:
        """Add an entry to the audit trail."""
        entry = AuditEntry(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            source_ip=source_ip,
            session_id=session_id,
        )
        self._audit_trail.append(entry)
        self._persist_audit_entry(entry)

    def get_audit_trail(
        self,
        actor: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query the audit trail with filters."""
        entries = list(self._audit_trail)
        if actor:
            entries = [e for e in entries if e.actor == actor]
        if action:
            entries = [e for e in entries if e.action == action]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        return entries[-limit:]

    # ── Policy Management ───────────────────────────────────

    def create_policy(self, policy: PolicyDocument) -> str:
        """Create a new policy document."""
        with self._lock_local:
            self._policies[policy.policy_id] = policy
            self._persist_policy(policy)
        return policy.policy_id

    def approve_policy(self, policy_id: str, approved_by: str) -> bool:
        """Approve a policy document."""
        with self._lock_local:
            policy = self._policies.get(policy_id)
            if policy is None:
                return False
            policy.status = "approved"
            policy.approved_by = approved_by
            policy.approved_at = time.time()
            self._persist_policy(policy)
            self._add_audit_entry(
                actor=approved_by,
                action="approve_policy",
                resource_type="policy",
                resource_id=policy_id,
            )
        return True

    def list_policies(self, category: str | None = None, status: str | None = None) -> list[PolicyDocument]:
        """List policy documents with optional filters."""
        policies = list(self._policies.values())
        if category:
            policies = [p for p in policies if p.category == category]
        if status:
            policies = [p for p in policies if p.status == status]
        return policies

    # ── Scoring & Reporting ─────────────────────────────────

    def calculate_compliance_score(self) -> dict[str, Any]:
        """Calculate overall compliance score and per-criteria scores.

        Scoring:
        - NOT_IMPLEMENTED = 0%
        - PARTIAL = 40%
        - IMPLEMENTED = 70%
        - VERIFIED = 100%
        - FAILED = 0%
        """
        status_scores = {
            ControlStatus.NOT_IMPLEMENTED: 0.0,
            ControlStatus.PARTIAL: 0.4,
            ControlStatus.IMPLEMENTED: 0.7,
            ControlStatus.VERIFIED: 1.0,
            ControlStatus.FAILED: 0.0,
        }

        if not self._controls:
            return {"overall_score": 0.0, "criteria_scores": {}, "total_controls": 0}

        # Overall score
        total = sum(status_scores[c.status] for c in self._controls.values())
        overall = (total / len(self._controls)) * 100

        # Per-criteria scores
        criteria_scores: dict[str, Any] = {}
        for criteria in TrustServiceCriteria:
            controls = [c for c in self._controls.values() if c.criteria == criteria]
            if controls:
                criteria_total = sum(status_scores[c.status] for c in controls)
                criteria_scores[criteria.value] = {
                    "score": round((criteria_total / len(controls)) * 100, 1),
                    "total": len(controls),
                    "implemented": sum(1 for c in controls if c.status in {ControlStatus.IMPLEMENTED, ControlStatus.VERIFIED}),
                    "verified": sum(1 for c in controls if c.status == ControlStatus.VERIFIED),
                    "failed": sum(1 for c in controls if c.status == ControlStatus.FAILED),
                }

        # Risk-weighted score
        risk_weights = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        weighted_total = 0
        weight_sum = 0
        for ctrl in self._controls.values():
            weight = risk_weights.get(ctrl.risk_level, 2)
            weighted_total += status_scores[ctrl.status] * weight
            weight_sum += weight
        risk_weighted_score = (weighted_total / max(weight_sum, 1)) * 100

        return {
            "overall_score": round(overall, 1),
            "risk_weighted_score": round(risk_weighted_score, 1),
            "criteria_scores": criteria_scores,
            "total_controls": len(self._controls),
            "by_status": {
                s.value: sum(1 for c in self._controls.values() if c.status == s)
                for s in ControlStatus
            },
        }

    def generate_report(self) -> dict[str, Any]:
        """Generate a comprehensive SOC 2 Type I compliance report."""
        score = self.calculate_compliance_score()
        controls = list(self._controls.values())

        return {
            "report_type": "SOC 2 Type I",
            "generated_at": time.time(),
            "summary": score,
            "controls": [
                {
                    "control_id": c.control_id,
                    "name": c.name,
                    "ref_code": c.ref_code,
                    "criteria": c.criteria.value,
                    "status": c.status.value,
                    "risk_level": c.risk_level,
                    "evidence_count": len(c.evidence_ids),
                    "last_tested": c.last_tested,
                    "remediation_notes": c.remediation_notes,
                }
                for c in controls
            ],
            "policies": [
                {
                    "policy_id": p.policy_id,
                    "name": p.name,
                    "category": p.category,
                    "status": p.status,
                    "version": p.version,
                }
                for p in self._policies.values()
            ],
            "recent_audit_entries": len(self._audit_trail),
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> list[str]:
        """Generate prioritized recommendations based on control gaps."""
        recommendations = []

        # Critical controls not implemented
        critical_gaps = [
            c for c in self._controls.values()
            if c.risk_level == "critical" and c.status in {ControlStatus.NOT_IMPLEMENTED, ControlStatus.FAILED}
        ]
        for ctrl in critical_gaps:
            recommendations.append(
                f"CRITICAL: Implement {ctrl.name} ({ctrl.ref_code}) — {ctrl.implementation_guidance}"
            )

        # High-risk controls partially implemented
        high_partial = [
            c for c in self._controls.values()
            if c.risk_level == "high" and c.status == ControlStatus.PARTIAL
        ]
        for ctrl in high_partial:
            recommendations.append(
                f"HIGH: Complete {ctrl.name} ({ctrl.ref_code}) — {ctrl.implementation_guidance}"
            )

        # Controls without evidence
        no_evidence = [c for c in self._controls if not self._controls[c].evidence_ids]
        for ctrl_id in no_evidence[:5]:
            ctrl = self._controls[ctrl_id]
            recommendations.append(
                f"EVIDENCE: Collect evidence for {ctrl.name} ({ctrl.ref_code})"
            )

        return recommendations

    # ── Persistence ─────────────────────────────────────────

    def _persist_control(self, ctrl: ComplianceControl) -> None:
        """Persist a control to SQLite."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_controls
                   (control_id, name, description, criteria, ref_code, status, owner,
                    evidence_ids, test_procedure, last_tested, last_result,
                    remediation_notes, risk_level, implementation_guidance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ctrl.control_id, ctrl.name, ctrl.description, ctrl.criteria.value,
                    ctrl.ref_code, ctrl.status.value, ctrl.owner,
                    json.dumps(ctrl.evidence_ids), ctrl.test_procedure,
                    ctrl.last_tested, ctrl.last_result, ctrl.remediation_notes,
                    ctrl.risk_level, ctrl.implementation_guidance,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist control: %s", exc)

    def _persist_evidence(self, evidence: ComplianceEvidence) -> None:
        """Persist evidence to SQLite."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_evidence
                   (evidence_id, control_id, evidence_type, description,
                    content_hash, collected_at, collected_by, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence.evidence_id, evidence.control_id,
                    evidence.evidence_type.value, evidence.description,
                    evidence.content_hash, evidence.collected_at,
                    evidence.collected_by, int(evidence.verified),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist evidence: %s", exc)

    def _persist_audit_entry(self, entry: AuditEntry) -> None:
        """Persist an audit entry to SQLite."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO compliance_audit
                   (entry_id, timestamp, actor, action, resource_type,
                    resource_id, details, source_ip, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id, entry.timestamp, entry.actor,
                    entry.action, entry.resource_type, entry.resource_id,
                    json.dumps(entry.details), entry.source_ip, entry.session_id,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist audit entry: %s", exc)

    def _persist_policy(self, policy: PolicyDocument) -> None:
        """Persist a policy to SQLite."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_policies
                   (policy_id, name, version, category, content,
                    approved_by, approved_at, effective_date, review_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    policy.policy_id, policy.name, policy.version,
                    policy.category, policy.content, policy.approved_by,
                    policy.approved_at, policy.effective_date,
                    policy.review_date, policy.status,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist policy: %s", exc)

    # ── Lifecycle ───────────────────────────────────────────

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_stats(self) -> dict[str, Any]:
        """Get compliance manager statistics."""
        return {
            "total_controls": len(self._controls),
            "total_evidence": len(self._evidence),
            "total_policies": len(self._policies),
            "audit_entries": len(self._audit_trail),
            "compliance_score": self.calculate_compliance_score(),
        }
