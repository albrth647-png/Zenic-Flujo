"""E2E Encrypted Cloud Sync — Sync engine for workflows between instances.

Features:
- End-to-end encryption (AES-256-GCM) with dedicated sync keys
- Push/pull workflow definitions between instances
- Conflict resolution with version vectors
- Incremental sync (only changes since last sync)
- Export/import packages with metadata
- Optional, opt-in per-tenant
"""
