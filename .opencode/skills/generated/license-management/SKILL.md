---
name: license-management
description: License management - validation, activation, key generation, tiers
load: on-demand
tokens: ~120
---

# License Management

## Module: `src/license/` (4 files)
License key management and validation system.

### Key Features
- **License Generation**: Key creation and signing
- **License Validation**: Runtime license checks
- **Tier Management**: Free/Pro/Enterprise tiers
- **Activation Flow**: Online/offline activation
- **Expiry Handling**: Grace periods and expiry

### Key Files
- `src/license/manager.py` - License manager
- `src/license/validator.py` - Validation logic
- `src/license/keys.py` - Key generation
