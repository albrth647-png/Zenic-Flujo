"""
SSO Mapping Facade
==================
Re-exporta create_or_link_user y link_existing_user desde
src.core.security.sso.session para mantener compatibilidad con
src.security.sso.routes y src.security.sso (legacy wrappers).

El módulo existe para resolver el gate `no_broken_imports` del rollout
Code-Forge Fase 1. Originalmente era un stub inexistente referenciado
por src/security/sso/__init__.py y src/security/sso.py.
"""
from __future__ import annotations

from src.core.security.sso.session import (
    create_or_link_user,
    link_existing_user,
)

__all__ = ["create_or_link_user", "link_existing_user"]
