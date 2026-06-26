"""src.core — Core infrastructure for Zenic-Flujo HAT v2.

This package hosts the foundational, framework-agnostic building blocks of the
platform: configuration, logging, database helpers, utils, schemas, security,
observability, i18n and repositories.

Submodules:
    config         — application configuration & env-driven settings
    logging        — centralized structured logging (merged from src/utils)
    db             — database helpers (sql_builder, repositories)
    utils          — general-purpose helpers (split from src/utils/helpers.py)
    schemas        — shared Pydantic / dataclass schemas
    security       — RBAC, MFA, BYOK encryption, SSO, vault
    observability  — telemetry, tracing, metrics
    i18n           — internationalization
    repositories   — persistence abstractions
"""
