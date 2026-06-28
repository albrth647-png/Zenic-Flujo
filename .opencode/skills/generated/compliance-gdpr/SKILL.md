---
name: compliance-gdpr
description: GDPR, HIPAA, SOC2 Type II compliance - data privacy, audit trails, retention
load: on-demand
tokens: ~160
---

# Compliance & GDPR

## Module: `src/compliance/` (6 files)
Regulatory compliance framework covering GDPR, HIPAA, and SOC2 Type II.

### Key Components
- **GDPR**: Data privacy, right to deletion, consent management
- **HIPAA**: Healthcare data protection
- **SOC2 Type II**: Audit controls and evidence collection
- **Retention Policy**: Data lifecycle management
- **Reproducibility Reporter**: Action audit logging

### Usage
```python
from src.compliance import ComplianceManager
cm = ComplianceManager()
cm.audit_action(user_id=123, action="data_export", resource="invoices")
```

### Key Files
- `src/compliance/gdpr.py` - GDPR implementation
- `src/compliance/hipaa.py` - HIPAA controls
- `src/compliance/soc2_type_ii.py` - SOC2 audit
- `src/compliance/retention_policy.py` - Data retention
