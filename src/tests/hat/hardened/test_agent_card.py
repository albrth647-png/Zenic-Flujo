"""Tests para AgentCard — declaración de capacidades de un agente.

Cubre:
- Atributos requeridos (agent_id, agent_name, domain, tier).
- Atributos opcionales con defaults (capabilities, cost_per_call, etc.).
- to_db_row() — conversión a dict para persistencia.
- to_ovc_metadata() — metadata para variable OVC.
- Frozen dataclass (inmutable).
"""
from __future__ import annotations

import json

import pytest

from src.hat.level3_specialists.base.cards import AgentCard

# ── Tests de construcción ──────────────────────────────────────────────


class TestConstruction:
    """Construcción de AgentCard."""

    def test_minimal_card(self) -> None:
        """Card con solo los campos requeridos."""
        card = AgentCard(
            agent_id="crm",
            agent_name="CRM",
            domain="operaciones",
            tier="specialist",
        )
        assert card.agent_id == "crm"
        assert card.agent_name == "CRM"
        assert card.domain == "operaciones"
        assert card.tier == "specialist"
        assert card.capabilities == []
        assert card.cost_per_call == 0.0
        assert card.avg_latency_ms == 0
        assert card.orbital_keywords == []
        assert card.orbital_amplitude == 1.0
        assert card.orbital_velocity == 0.1

    def test_full_card(self) -> None:
        """Card con todos los campos."""
        card = AgentCard(
            agent_id="crm",
            agent_name="CRM",
            domain="operaciones",
            tier="specialist",
            capabilities=["create_lead", "list_leads"],
            cost_per_call=0.5,
            avg_latency_ms=50,
            orbital_keywords=["cliente", "lead"],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )
        assert card.capabilities == ["create_lead", "list_leads"]
        assert card.cost_per_call == 0.5
        assert card.avg_latency_ms == 50
        assert card.orbital_keywords == ["cliente", "lead"]
        assert card.orbital_amplitude == 1.5
        assert card.orbital_velocity == 0.05


# ── Tests de inmutabilidad ─────────────────────────────────────────────


class TestImmutability:
    """AgentCard es frozen — no se puede mutar."""

    def test_frozen_dataclass(self) -> None:
        """No se pueden modificar atributos después de construcción."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
        )
        with pytest.raises(AttributeError):
            card.agent_id = "other"  # type: ignore[misc]

    def test_frozen_attributes(self) -> None:
        """No se pueden añadir atributos nuevos."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
        )
        with pytest.raises(AttributeError):
            card.new_attr = "value"  # type: ignore[attr-defined]


# ── Tests de to_db_row ─────────────────────────────────────────────────


class TestToDbRow:
    """Conversión a dict para persistencia en DB."""

    def test_to_db_row_has_all_columns(self) -> None:
        """to_db_row retorna dict con las 10 columnas esperadas."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
            capabilities=["create_lead"],
            cost_per_call=0.5,
            avg_latency_ms=50,
            orbital_keywords=["cliente"],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )
        row = card.to_db_row()
        assert row["agent_id"] == "crm"
        assert row["agent_name"] == "CRM"
        assert row["domain"] == "operaciones"
        assert row["tier"] == "specialist"
        assert json.loads(row["capabilities"]) == ["create_lead"]
        assert row["cost_per_call"] == 0.5
        assert row["avg_latency_ms"] == 50
        assert json.loads(row["orbital_keywords"]) == ["cliente"]
        assert row["orbital_amplitude"] == 1.5
        assert row["orbital_velocity"] == 0.05

    def test_to_db_row_capabilities_serialized_as_json(self) -> None:
        """capabilities se serializa como JSON string."""
        card = AgentCard(
            agent_id="x", agent_name="X",
            domain="d", tier="t",
            capabilities=["a", "b", "c"],
        )
        row = card.to_db_row()
        assert isinstance(row["capabilities"], str)
        assert json.loads(row["capabilities"]) == ["a", "b", "c"]

    def test_to_db_row_empty_capabilities(self) -> None:
        """capabilities vacío se serializa como '[]'."""
        card = AgentCard(
            agent_id="x", agent_name="X",
            domain="d", tier="t",
        )
        row = card.to_db_row()
        assert json.loads(row["capabilities"]) == []


# ── Tests de to_ovc_metadata ───────────────────────────────────────────


class TestToOvcMetadata:
    """Metadata para variable OVC."""

    def test_to_ovc_metadata_has_type_agent_card(self) -> None:
        """metadata['type'] = 'agent_card'."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
        )
        meta = card.to_ovc_metadata()
        assert meta["type"] == "agent_card"

    def test_to_ovc_metadata_includes_identity(self) -> None:
        """metadata incluye agent_id, agent_name, domain, tier."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
        )
        meta = card.to_ovc_metadata()
        assert meta["agent_id"] == "crm"
        assert meta["agent_name"] == "CRM"
        assert meta["domain"] == "operaciones"
        assert meta["tier"] == "specialist"

    def test_to_ovc_metadata_capabilities_as_list(self) -> None:
        """capabilities se mantiene como list (no JSON) en metadata."""
        card = AgentCard(
            agent_id="x", agent_name="X",
            domain="d", tier="t",
            capabilities=["a", "b"],
        )
        meta = card.to_ovc_metadata()
        assert meta["capabilities"] == ["a", "b"]
        assert isinstance(meta["capabilities"], list)


# ── Tests de __repr__ ─────────────────────────────────────────────────


class TestRepr:
    """Representación string compacta."""

    def test_repr_compact(self) -> None:
        """__repr__ no incluye capabilities completas (puede ser largo)."""
        card = AgentCard(
            agent_id="crm", agent_name="CRM",
            domain="operaciones", tier="specialist",
            capabilities=["a"] * 100,
            orbital_keywords=["k1", "k2"],
        )
        r = repr(card)
        assert "AgentCard" in r
        assert "crm" in r
        assert "operaciones" in r
        assert "specialist" in r
        # No debe incluir las 100 capabilities
        assert "a" * 50 not in r
