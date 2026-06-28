"""
conftest para property-based testing del Orbital Engine.

Define:
  - Perfiles Hypothesis: orbital_ci (200 ejemplos), orbital_stress (2000 ejemplos)
  - Settings globales: deadline=None, suppress_health_check para floats
  - Fixtures compartidas: engine limpio, engine con variables

Referencias:
  - Skill: .opencode/skills/any-best-practices/SKILL.md §10
  - Investigación: docs/research/property-based-testing-orbital.md (si existe)
"""
from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, settings


# ─── Perfiles Hypothesis ─────────────────────────────────────────────────────


def _register_profiles() -> None:
    """Registra perfiles para CI (rápido) y stress (profundo, nightly)."""
    # Perfil CI: 200 ejemplos (default), sin deadline (COD puede ser lento)
    settings.register_profile(
        "orbital_ci",
        max_examples=200,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.data_too_large,
            HealthCheck.function_scoped_fixture,
        ],
    )

    # Perfil stress: 2000 ejemplos para nightly / pre-release
    settings.register_profile(
        "orbital_stress",
        max_examples=2000,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.data_too_large,
            HealthCheck.function_scoped_fixture,
        ],
    )

    # Perfil default = CI si no se especifica
    settings.register_profile("default", parent="orbital_ci")


_register_profiles()

# Cargar perfil según env var ORBITAL_PROFILE (default: ci)
_profile = os.environ.get("ORBITAL_PROFILE", "ci")
settings.load_profile(f"orbital_{_profile}")


# ─── Fixtures compartidas ────────────────────────────────────────────────────


@pytest.fixture
def clean_engine():
    """OrbitalEngine fresco sin variables ni ciclos."""
    from src.orbital.engine import OrbitalEngine

    return OrbitalEngine()


@pytest.fixture
def engine_with_variables(clean_engine):
    """OrbitalEngine con 3 variables orbitales básicas."""
    from src.orbital.engine import OrbitalEngine

    eng = clean_engine
    eng.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    eng.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    eng.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    return eng
