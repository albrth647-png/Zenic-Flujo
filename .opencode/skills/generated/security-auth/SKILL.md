---
name: security-auth
description: Security, authentication, authorization, encryption, key management
load: on-demand
tokens: ~160
---

# Security & Auth

## Module: `src/security/` (16 files)
Security infrastructure - authentication, authorization, encryption.

### Key Features
- **JWT Auth**: Token-based authentication
- **RBAC**: Role-based access control
- **Password Hashing**: bcrypt integration
- **2FA/MFA**: pyotp two-factor authentication
- **Encryption**: Data-at-rest encryption
- **Key Management**: API key lifecycle
- **Session Management**: Session tracking and expiry

### Usage
```python
from src.security import AuthManager
auth = AuthManager()
token = auth.authenticate(username="admin", password="***", otp="123456")
```

### Key Files
- `src/security/auth.py` - Authentication
- `src/security/rbac.py` - Access control
- `src/security/encryption.py` - Encryption
