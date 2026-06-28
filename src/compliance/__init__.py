"""Enterprise Compliance — SOC 2 Type I/II, GDPR & HIPAA compliance framework.

Implements multi-framework compliance management:
- SOC 2 Type I (Trust Service Criteria — point-in-time design)
- SOC 2 Type II (Operating effectiveness over time with monitoring periods)
- GDPR (Data Protection Regulation)
- HIPAA (Health Insurance Portability and Accountability Act)

Features:
- Multi-framework control catalog with automated testing
- Type II monitoring periods with sample sizing per AICPA guidance
- Trend analysis across test cycles with automated pass rate tracking
- Subservice organization mapping (carve-out / inclusive)
- Bridge letter generation for period transitions
- Evidence collection and SHA-256 integrity verification
- Audit trail with tamper detection
- Policy management with versioning
- Per-framework compliance scoring and reporting

Fix Sprint 3 bug #40: antes ComplianceManager, BAAManager, SOC2TypeIIManager,
y GDPR/HIPAA managers abrían cada uno su propia conexión SQLite al mismo
compliance.db, causando "database locked" errores. Ahora todos usan el
_ComplianceDB singleton compartido (lock global + WAL mode).
"""  # fmt: skip

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

from src.compliance.soc2_type_ii import (
    ControlFrequency,
    ControlTestResult,
    MonitoringPeriod,
    MonitoringPeriodStatus,
    SamplingMethodology,
    SOC2TypeIIManager,
    SubserviceOrganization,
    TestResultStatus,
    recommend_sample_size,
)
from src.core.logging import setup_logging

logger = setup_logging("compliance")


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""
    SOC2 = "soc2"
    GDPR = "gdpr"
    HIPAA = "hipaa"


class TrustServiceCriteria(Enum):
    """SOC 2 Trust Service Criteria categories."""

    SECURITY = "security"
    AVAILABILITY = "availability"
    PROCESSING_INTEGRITY = "processing_integrity"
    CONFIDENTIALITY = "confidentiality"
    PRIVACY = "privacy"


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
    """A single compliance control for any framework (SOC 2, GDPR, HIPAA)."""

    control_id: str = ""
    name: str = ""
    description: str = ""
    framework: ComplianceFramework = ComplianceFramework.SOC2
    criteria: TrustServiceCriteria = TrustServiceCriteria.SECURITY
    ref_code: str = ""
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    owner: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    test_procedure: str = ""
    last_tested: float = 0.0
    last_result: str = ""
    remediation_notes: str = ""
    risk_level: str = "medium"
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
    content: str = ""
    content_hash: str = ""
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
    category: str = ""
    content: str = ""
    approved_by: str = ""
    approved_at: float = 0.0
    effective_date: float = field(default_factory=time.time)
    review_date: float = 0.0
    status: str = "draft"

    def __post_init__(self) -> None:
        if not self.policy_id:
            self.policy_id = f"pol-{uuid.uuid4().hex[:8]}"


# ── Control Catalogs ──────────────────────────────────────

SOC2_CONTROLS: list[dict[str, Any]] = [
    {"name": "Access Control Policy", "description": "Logical access controls are implemented to restrict access to systems and data based on need and least privilege.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.1", "risk_level": "critical", "test_procedure": "Verify RBAC is configured with least-privilege roles. Check user access reviews.", "implementation_guidance": "Implement RBAC via RBACManager with periodic access reviews."},
    {"name": "User Authentication", "description": "Users are authenticated before accessing system resources using secure mechanisms.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.1", "risk_level": "critical", "test_procedure": "Verify MFA enforcement and password policies. Check bcrypt hashing.", "implementation_guidance": "Use MFAService with TOTP and bcrypt password hashing."},
    {"name": "Encryption at Rest", "description": "Sensitive data is encrypted at rest using strong cryptographic algorithms.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.1", "risk_level": "critical", "test_procedure": "Verify EncryptionService with BYOK support is active. Check key rotation.", "implementation_guidance": "Use EncryptionService with AES-256 and BYOK key management."},
    {"name": "Encryption in Transit", "description": "Data in transit is protected using TLS/SSL encryption.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.7", "risk_level": "high", "test_procedure": "Verify TLS configuration on all endpoints. Check certificate validity.", "implementation_guidance": "Enforce HTTPS on all API endpoints with valid TLS certificates."},
    {"name": "Network Security", "description": "Network access is restricted using firewalls, VPNs, and network segmentation.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.6", "risk_level": "high", "test_procedure": "Verify firewall rules, network segmentation, and VPN access controls.", "implementation_guidance": "Implement network policies via Docker/K8s network policies."},
    {"name": "Vulnerability Management", "description": "Vulnerabilities are identified and remediated on a timely basis.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC7.1", "risk_level": "high", "test_procedure": "Review vulnerability scan results and remediation timelines.", "implementation_guidance": "Integrate Snyk/Trivy in CI/CD pipeline. Monthly scans."},
    {"name": "Incident Response", "description": "Security incidents are detected, reported, and responded to in a timely manner.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC7.2", "risk_level": "high", "test_procedure": "Verify incident response plan exists. Test alerting mechanisms.", "implementation_guidance": "Implement audit trail, anomaly detection, and alerting."},
    {"name": "Change Management", "description": "Changes to systems are authorized, documented, and tested before deployment.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC8.1", "risk_level": "medium", "test_procedure": "Review change management process, PR approvals, CI/CD gates.", "implementation_guidance": "Enforce PR reviews, branch protection, and CI/CD quality gates."},
    {"name": "Audit Logging", "description": "System activities are logged and retained for audit purposes.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC7.2", "risk_level": "critical", "test_procedure": "Verify audit logs are generated for all sensitive operations. Check retention.", "implementation_guidance": "Use AuditLogger with 90-day retention and tamper detection."},
    {"name": "SSO & Identity Federation", "description": "Single sign-on and identity federation are implemented for enterprise access.", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "CC6.1", "risk_level": "high", "test_procedure": "Verify SAML/OIDC configuration. Test SSO login flow.", "implementation_guidance": "Use SSOService with SAML and OAuth2/OIDC providers."},
    {"name": "System Monitoring", "description": "System health and performance are continuously monitored with alerting.", "criteria": TrustServiceCriteria.AVAILABILITY, "ref_code": "A1.2", "risk_level": "high", "test_procedure": "Verify OpenTelemetry integration. Check alerting thresholds.", "implementation_guidance": "Use Observability module with Prometheus metrics and alerts."},
    {"name": "Backup & Recovery", "description": "Data is backed up regularly and recovery procedures are tested.", "criteria": TrustServiceCriteria.AVAILABILITY, "ref_code": "A1.3", "risk_level": "critical", "test_procedure": "Verify backup schedule, test restoration, check RTO/RPO targets.", "implementation_guidance": "Use BackupEngine with daily full + incremental backups."},
    {"name": "Disaster Recovery Plan", "description": "A documented disaster recovery plan is maintained and tested.", "criteria": TrustServiceCriteria.AVAILABILITY, "ref_code": "A1.3", "risk_level": "high", "test_procedure": "Verify DR plan documentation. Check test results.", "implementation_guidance": "Document RTO/RPO targets. Quarterly DR drills."},
    {"name": "Data Validation", "description": "Input data is validated to ensure completeness, accuracy, and authorization.", "criteria": TrustServiceCriteria.PROCESSING_INTEGRITY, "ref_code": "PI1.2", "risk_level": "high", "test_procedure": "Verify input validation on API endpoints. Check Pydantic models.", "implementation_guidance": "Use Pydantic models for all API inputs. Schema validation."},
    {"name": "Workflow Determinism", "description": "Workflow execution produces consistent, deterministic results.", "criteria": TrustServiceCriteria.PROCESSING_INTEGRITY, "ref_code": "PI1.3", "risk_level": "high", "test_procedure": "Run workflow benchmarks. Verify deterministic convergence via COD.", "implementation_guidance": "Orbital Engine ensures deterministic convergence."},
    {"name": "Data Classification", "description": "Data is classified based on sensitivity and handled according to classification.", "criteria": TrustServiceCriteria.CONFIDENTIALITY, "ref_code": "C1.2", "risk_level": "high", "test_procedure": "Verify data classification labels and handling procedures.", "implementation_guidance": "Implement data classification tags in metadata."},
    {"name": "Tenant Data Isolation", "description": "Multi-tenant data is properly isolated to prevent cross-tenant access.", "criteria": TrustServiceCriteria.CONFIDENTIALITY, "ref_code": "C1.2", "risk_level": "critical", "test_procedure": "Verify tenant isolation in database. Test cross-tenant access denial.", "implementation_guidance": "Use TenantService with schema-per-tenant isolation."},
    {"name": "Privacy Policy", "description": "A privacy policy is published describing data collection, use, and retention practices.", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "P1.1", "risk_level": "high", "test_procedure": "Verify privacy policy exists and is accessible.", "implementation_guidance": "Publish privacy policy. Implement consent management."},
    {"name": "Data Retention & Disposal", "description": "Personal data is retained only as long as necessary and properly disposed of.", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "P1.3", "risk_level": "high", "test_procedure": "Verify retention policies are enforced. Check disposal procedures.", "implementation_guidance": "Implement automated retention policies with secure deletion."},
]

GDPR_CONTROLS: list[dict[str, Any]] = [
    {"name": "Lawful Basis for Processing", "description": "All processing of personal data is conducted under a lawful basis as defined in Art. 6.", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art6", "risk_level": "critical", "test_procedure": "Verify all data processing activities have documented lawful basis.", "implementation_guidance": "Maintain ROPA with lawful basis for each processing activity."},
    {"name": "Data Subject Access Request (DSAR)", "description": "Data subjects can exercise right of access (Art. 15) within 30 days, free of charge.", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art15", "risk_level": "critical", "test_procedure": "Submit test DSAR and verify response within 30-day SLA.", "implementation_guidance": "Implement DSAR portal with automated discovery and response."},
    {"name": "Right to Erasure", "description": "Data subjects can request erasure of personal data under Art. 17.", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art17", "risk_level": "high", "test_procedure": "Verify erasure workflow: identify, confirm, cascade delete, confirm completion.", "implementation_guidance": "Implement data erasure pipeline with cascade deletion across all stores."},
    {"name": "Data Portability", "description": "Data subjects can receive data in structured, machine-readable format (Art. 20).", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art20", "risk_level": "high", "test_procedure": "Verify export produces JSON/CSV with complete data schema.", "implementation_guidance": "Support data export in JSON and CSV via self-service portal."},
    {"name": "Consent Management", "description": "Consent is freely given, specific, informed, and unambiguous (Art. 7).", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art7", "risk_level": "critical", "test_procedure": "Verify consent collection UI, withdrawal mechanism, and audit trail.", "implementation_guidance": "Use ConsentManager with granular purpose-based consent and withdrawal tracking."},
    {"name": "Data Breach Notification", "description": "Breaches notified to authority within 72h (Art. 33) and to subjects without delay (Art. 34).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "GDPR-Art33", "risk_level": "critical", "test_procedure": "Verify breach detection, 72h notification timeline, subject notification workflow.", "implementation_guidance": "Automated breach detection with notification templates and escalation workflow."},
    {"name": "Data Protection Impact Assessment (DPIA)", "description": "DPIAs conducted for high-risk processing (Art. 35).", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art35", "risk_level": "high", "test_procedure": "Verify DPIA process: screening, assessment, risk mitigation, DPO review.", "implementation_guidance": "DPIA template with automated risk scoring and approval workflow."},
    {"name": "Records of Processing Activities (ROPA)", "description": "Controller maintains records of all processing activities (Art. 30).", "criteria": TrustServiceCriteria.PRIVACY, "ref_code": "GDPR-Art30", "risk_level": "high", "test_procedure": "Verify ROPA is complete: data categories, purposes, lawful basis, retention.", "implementation_guidance": "Maintain automated ROPA with data flow mapping and retention schedules."},
]

HIPAA_CONTROLS: list[dict[str, Any]] = [
    {"name": "PHI Identification & Classification", "description": "All PHI is identified, classified, and handled per Privacy Rule (45 CFR §164.506).", "criteria": TrustServiceCriteria.CONFIDENTIALITY, "ref_code": "HIPAA-164.506", "risk_level": "critical", "test_procedure": "Verify PHI inventory completeness. Check minimum necessary configuration.", "implementation_guidance": "Maintain PHI inventory with automated discovery and classification."},
    {"name": "Access Control (Technical Safeguard)", "description": "Unique user IDs, emergency access, auto-logoff, encryption (45 CFR §164.312(a)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.312(a)", "risk_level": "critical", "test_procedure": "Verify unique user IDs, auto-logoff, encryption, emergency access procedure.", "implementation_guidance": "RBAC with unique IDs. AES-256 encryption. Automatic session timeout."},
    {"name": "Audit Controls (Technical Safeguard)", "description": "Record and examine access and activity in information systems (45 CFR §164.312(b)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.312(b)", "risk_level": "critical", "test_procedure": "Verify audit logs capture all PHI access. Check 6-year retention.", "implementation_guidance": "Comprehensive audit logging of all PHI access with 6-year retention."},
    {"name": "Integrity Controls (Technical Safeguard)", "description": "Ensure ePHI is not improperly altered or destroyed (45 CFR §164.312(c)).", "criteria": TrustServiceCriteria.PROCESSING_INTEGRITY, "ref_code": "HIPAA-164.312(c)", "risk_level": "high", "test_procedure": "Verify integrity checks (SHA-256), checksums, electronic signatures.", "implementation_guidance": "Integrity verification with hash chains and electronic signatures."},
    {"name": "Person/Authentication (Technical Safeguard)", "description": "Verify person/entity seeking access is the one claimed (45 CFR §164.312(d)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.312(d)", "risk_level": "high", "test_procedure": "Verify MFA enforcement for PHI access. Check password complexity.", "implementation_guidance": "MFA with TOTP for all PHI access. Strong password policy."},
    {"name": "Transmission Security (Technical Safeguard)", "description": "Guard against unauthorized access to ePHI over networks (45 CFR §164.312(e)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.312(e)", "risk_level": "high", "test_procedure": "Verify TLS 1.2+ for data in transit. Check integrity controls.", "implementation_guidance": "Enforce TLS 1.2+ minimum. HSTS and certificate pinning."},
    {"name": "Business Associate Agreements (BAA)", "description": "Written BAAs with all business associates handling PHI (45 CFR §164.504(e)).", "criteria": TrustServiceCriteria.CONFIDENTIALITY, "ref_code": "HIPAA-164.504(e)", "risk_level": "critical", "test_procedure": "Verify BAA inventory completeness. Check required elements in each BAA.", "implementation_guidance": "Maintain BAA inventory with renewal tracking and compliance checks."},
    {"name": "Breach Notification Rule", "description": "Breaches of unsecured PHI notified within 60 days (45 CFR §164.400-414).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.400", "risk_level": "critical", "test_procedure": "Verify breach detection, 4-factor risk assessment, notification workflow.", "implementation_guidance": "Automated breach detection with 4-factor risk assessment and notification."},
    {"name": "Security Management (Admin Safeguard)", "description": "Policies to prevent, detect, contain, and correct violations (45 CFR §164.308(a)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.308(a)", "risk_level": "critical", "test_procedure": "Verify risk analysis, risk management plan, sanction policy, activity reviews.", "implementation_guidance": "Annual risk analysis. Documented risk management plan. Regular reviews."},
    {"name": "Workforce Security (Admin Safeguard)", "description": "Workforce has appropriate ePHI access (45 CFR §164.308(a)(3)).", "criteria": TrustServiceCriteria.SECURITY, "ref_code": "HIPAA-164.308(a)(3)", "risk_level": "high", "test_procedure": "Verify auth/supervision policies, termination procedures, and sanctions.", "implementation_guidance": "Automated access provisioning and immediate deprovisioning on termination."},
]


class ComplianceManager:
    """Central manager for enterprise compliance (SOC 2 Type I/II, GDPR, HIPAA).

    Usage:
        manager = ComplianceManager.get_instance()
        score = manager.calculate_compliance_score()
        report = manager.calculate_framework_scores()

        # SOC 2 Type II:
        type_ii = SOC2TypeIIManager.get_instance()
        period = type_ii.create_monitoring_period(...)
    """

    _instance: ComplianceManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from src.core.config import COMPLIANCE_DB_PATH
            db_path = str(COMPLIANCE_DB_PATH)
        self._db_path = db_path
        self._controls: dict[str, ComplianceControl] = {}
        self._evidence: dict[str, ComplianceEvidence] = {}
        self._policies: dict[str, PolicyDocument] = {}
        self._audit_trail: list[AuditEntry] = []
        self._lock_local = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        # Fix Sprint 3 bug #40: abrir con check_same_thread=False + WAL + busy_timeout
        # para evitar "database locked" cuando ComplianceManager, BAAManager,
        # SOC2TypeIIManager y GDPR/HIPAA managers acceden concurrentemente.
        self._init_db()
        self._load_default_controls()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> ComplianceManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        # Fix Sprint 3 bug #40: PRAGMA WAL + busy_timeout para permitir múltiples
        # readers concurrentes y writers sin "database locked".
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")  # 5s
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS compliance_controls (
                control_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                framework TEXT NOT NULL DEFAULT 'soc2', criteria TEXT NOT NULL,
                ref_code TEXT, status TEXT NOT NULL DEFAULT 'not_implemented',
                owner TEXT, evidence_ids TEXT, test_procedure TEXT,
                last_tested REAL, last_result TEXT, remediation_notes TEXT,
                risk_level TEXT, implementation_guidance TEXT
            );
            CREATE TABLE IF NOT EXISTS compliance_evidence (
                evidence_id TEXT PRIMARY KEY, control_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL, description TEXT, content_hash TEXT,
                collected_at REAL, collected_by TEXT, verified INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS compliance_audit (
                entry_id TEXT PRIMARY KEY, timestamp REAL NOT NULL, actor TEXT,
                action TEXT, resource_type TEXT, resource_id TEXT, details TEXT,
                source_ip TEXT, session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS compliance_policies (
                policy_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT,
                category TEXT, content TEXT, approved_by TEXT, approved_at REAL,
                effective_date REAL, review_date REAL, status TEXT
            );
        """)
        self._conn.commit()

    def _load_default_controls(self) -> None:
        """Load all framework control catalogs."""
        for framework, controls_list, criteria_field in [
            (ComplianceFramework.SOC2, SOC2_CONTROLS, "criteria"),
            (ComplianceFramework.GDPR, GDPR_CONTROLS, "criteria"),
            (ComplianceFramework.HIPAA, HIPAA_CONTROLS, "criteria"),
        ]:
            for ctrl_data in controls_list:
                ctrl = ComplianceControl(
                    name=ctrl_data["name"],
                    description=ctrl_data["description"],
                    framework=framework,
                    criteria=ctrl_data.get(criteria_field, TrustServiceCriteria.SECURITY),
                    ref_code=ctrl_data.get("ref_code", ""),
                    risk_level=ctrl_data.get("risk_level", "medium"),
                    test_procedure=ctrl_data.get("test_procedure", ""),
                    implementation_guidance=ctrl_data.get("implementation_guidance", ""),
                )
                self._controls[ctrl.control_id] = ctrl
                self._persist_control(ctrl)

    # ── Control Management ──────────────────────────────────

    def add_control(self, control: ComplianceControl) -> str:
        with self._lock_local:
            self._controls[control.control_id] = control
            self._persist_control(control)
        return control.control_id

    def update_control_status(self, control_id: str, status: ControlStatus, notes: str = "") -> bool:
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
                actor="system", action="update_control_status",
                resource_type="control", resource_id=control_id,
                details={"new_status": status.value, "notes": notes},
            )
        return True

    def get_control(self, control_id: str) -> ComplianceControl | None:
        return self._controls.get(control_id)

    def list_controls(
        self,
        framework: ComplianceFramework | None = None,
        criteria: TrustServiceCriteria | None = None,
        status: ControlStatus | None = None,
        risk_level: str | None = None,
    ) -> list[ComplianceControl]:
        controls = list(self._controls.values())
        if framework:
            controls = [c for c in controls if c.framework == framework]
        if criteria:
            controls = [c for c in controls if c.criteria == criteria]
        if status:
            controls = [c for c in controls if c.status == status]
        if risk_level:
            controls = [c for c in controls if c.risk_level == risk_level]
        return controls

    # ── Evidence ────────────────────────────────────────────

    def collect_evidence(self, control_id: str, evidence_type: EvidenceType, description: str, content: str, collected_by: str = "system") -> ComplianceEvidence:
        evidence = ComplianceEvidence(control_id=control_id, evidence_type=evidence_type, description=description, content=content, collected_by=collected_by)
        with self._lock_local:
            self._evidence[evidence.evidence_id] = evidence
            ctrl = self._controls.get(control_id)
            if ctrl:
                ctrl.evidence_ids.append(evidence.evidence_id)
            self._persist_evidence(evidence)
            self._add_audit_entry(actor=collected_by, action="collect_evidence", resource_type="evidence", resource_id=evidence.evidence_id, details={"control_id": control_id, "type": evidence_type.value})
        return evidence

    def verify_evidence(self, evidence_id: str) -> bool:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            return False
        current_hash = hashlib.sha256(evidence.content.encode()).hexdigest()
        if current_hash != evidence.content_hash:
            logger.warning("Evidence integrity check failed: %s", evidence_id)
            return False
        evidence.verified = True
        return True

    # ── Audit Trail ─────────────────────────────────────────

    def _add_audit_entry(self, actor: str, action: str, resource_type: str, resource_id: str, details: dict[str, Any] | None = None, source_ip: str = "", session_id: str = "") -> None:
        entry = AuditEntry(actor=actor, action=action, resource_type=resource_type, resource_id=resource_id, details=details or {}, source_ip=source_ip, session_id=session_id)
        self._audit_trail.append(entry)
        self._persist_audit_entry(entry)

    def get_audit_trail(self, actor: str | None = None, action: str | None = None, resource_type: str | None = None, start_time: float | None = None, end_time: float | None = None, limit: int = 100) -> list[AuditEntry]:
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
        with self._lock_local:
            self._policies[policy.policy_id] = policy
            self._persist_policy(policy)
        return policy.policy_id

    def approve_policy(self, policy_id: str, approved_by: str) -> bool:
        with self._lock_local:
            policy = self._policies.get(policy_id)
            if policy is None:
                return False
            policy.status = "approved"
            policy.approved_by = approved_by
            policy.approved_at = time.time()
            self._persist_policy(policy)
            self._add_audit_entry(actor=approved_by, action="approve_policy", resource_type="policy", resource_id=policy_id)
        return True

    def list_policies(self, category: str | None = None, status: str | None = None) -> list[PolicyDocument]:
        policies = list(self._policies.values())
        if category:
            policies = [p for p in policies if p.category == category]
        if status:
            policies = [p for p in policies if p.status == status]
        return policies

    # ── Scoring & Reporting ─────────────────────────────────

    def calculate_framework_scores(self) -> dict[str, Any]:
        """Calculate compliance scores per framework."""
        status_scores = {
            ControlStatus.NOT_IMPLEMENTED: 0.0,
            ControlStatus.PARTIAL: 0.4,
            ControlStatus.IMPLEMENTED: 0.7,
            ControlStatus.VERIFIED: 1.0,
            ControlStatus.FAILED: 0.0,
        }

        results: dict[str, Any] = {}
        overall_total = 0.0
        all_controls = list(self._controls.values())

        for framework in ComplianceFramework:
            controls = [c for c in all_controls if c.framework == framework]
            if not controls:
                results[framework.value] = {"score": 0.0, "total": 0, "not_implemented": 0, "by_status": {}}
                continue
            total = sum(status_scores[c.status] for c in controls)
            score = round((total / len(controls)) * 100, 1)
            results[framework.value] = {
                "score": score,
                "total": len(controls),
                "implemented": sum(1 for c in controls if c.status in {ControlStatus.IMPLEMENTED, ControlStatus.VERIFIED}),
                "verified": sum(1 for c in controls if c.status == ControlStatus.VERIFIED),
                "failed": sum(1 for c in controls if c.status == ControlStatus.FAILED),
                "not_implemented": sum(1 for c in controls if c.status == ControlStatus.NOT_IMPLEMENTED),
                "by_status": {s.value: sum(1 for c in controls if c.status == s) for s in ControlStatus},
            }
            overall_total += total * len(controls)

        overall = round(
            (sum(status_scores[c.status] for c in all_controls) / max(len(all_controls), 1)) * 100, 1
        ) if all_controls else 0.0

        return {
            "overall_score": overall,
            "frameworks": results,
            "total_controls": len(all_controls),
        }

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive multi-framework compliance report."""
        framework_scores = self.calculate_framework_scores()
        controls = list(self._controls.values())

        return {
            "report_type": "Enterprise Compliance",
            "generated_at": time.time(),
            "supported_frameworks": ["SOC 2 Type I", "SOC 2 Type II", "GDPR", "HIPAA"],
            "summary": framework_scores,
            "controls": [
                {
                    "control_id": c.control_id,
                    "name": c.name,
                    "ref_code": c.ref_code,
                    "framework": c.framework.value,
                    "status": c.status.value,
                    "risk_level": c.risk_level,
                    "evidence_count": len(c.evidence_ids),
                    "last_tested": c.last_tested,
                    "remediation_notes": c.remediation_notes,
                }
                for c in controls
            ],
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> list[str]:
        recommendations = []
        critical_gaps = [c for c in self._controls.values() if c.risk_level == "critical" and c.status in {ControlStatus.NOT_IMPLEMENTED, ControlStatus.FAILED}]
        for ctrl in critical_gaps:
            recommendations.append(f"[{ctrl.framework.value.upper()}] CRITICAL: Implement {ctrl.name} ({ctrl.ref_code}) — {ctrl.implementation_guidance}")
        high_partial = [c for c in self._controls.values() if c.risk_level == "high" and c.status == ControlStatus.PARTIAL]
        for ctrl in high_partial:
            recommendations.append(f"[{ctrl.framework.value.upper()}] HIGH: Complete {ctrl.name} ({ctrl.ref_code}) — {ctrl.implementation_guidance}")
        no_evidence = [c for c in self._controls if not self._controls[c].evidence_ids]
        for ctrl_id in no_evidence[:5]:
            ctrl = self._controls[ctrl_id]
            recommendations.append(f"[{ctrl.framework.value.upper()}] EVIDENCE: Collect evidence for {ctrl.name} ({ctrl.ref_code})")
        return recommendations

    # ── Persistence ─────────────────────────────────────────

    def _persist_control(self, ctrl: ComplianceControl) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_controls
                   (control_id, name, description, framework, criteria, ref_code, status,
                    owner, evidence_ids, test_procedure, last_tested, last_result,
                    remediation_notes, risk_level, implementation_guidance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ctrl.control_id, ctrl.name, ctrl.description, ctrl.framework.value,
                 ctrl.criteria.value, ctrl.ref_code, ctrl.status.value, ctrl.owner,
                 json.dumps(ctrl.evidence_ids), ctrl.test_procedure, ctrl.last_tested,
                 ctrl.last_result, ctrl.remediation_notes, ctrl.risk_level, ctrl.implementation_guidance),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist control: %s", exc)

    def _persist_evidence(self, evidence: ComplianceEvidence) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_evidence
                   (evidence_id, control_id, evidence_type, description, content_hash,
                    collected_at, collected_by, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (evidence.evidence_id, evidence.control_id, evidence.evidence_type.value,
                 evidence.description, evidence.content_hash, evidence.collected_at,
                 evidence.collected_by, int(evidence.verified)),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist evidence: %s", exc)

    def _persist_audit_entry(self, entry: AuditEntry) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO compliance_audit
                   (entry_id, timestamp, actor, action, resource_type, resource_id, details, source_ip, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.entry_id, entry.timestamp, entry.actor, entry.action,
                 entry.resource_type, entry.resource_id, json.dumps(entry.details),
                 entry.source_ip, entry.session_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist audit entry: %s", exc)

    def _persist_policy(self, policy: PolicyDocument) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO compliance_policies
                   (policy_id, name, version, category, content, approved_by,
                    approved_at, effective_date, review_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (policy.policy_id, policy.name, policy.version, policy.category,
                 policy.content, policy.approved_by, policy.approved_at,
                 policy.effective_date, policy.review_date, policy.status),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist policy: %s", exc)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_controls": len(self._controls),
            "total_evidence": len(self._evidence),
            "total_policies": len(self._policies),
            "audit_entries": len(self._audit_trail),
            "framework_scores": self.calculate_framework_scores(),
        }


__all__ = [
    "AuditEntry",
    "ComplianceControl",
    "ComplianceEvidence",
    "ComplianceFramework",
    "ComplianceManager",
    "ControlFrequency",
    "ControlStatus",
    "ControlTestResult",
    "EvidenceType",
    "MonitoringPeriod",
    "MonitoringPeriodStatus",
    "PolicyDocument",
    "SOC2TypeIIManager",
    "SamplingMethodology",
    "SubserviceOrganization",
    "TestResultStatus",
    "TrustServiceCriteria",
    "recommend_sample_size",
]
