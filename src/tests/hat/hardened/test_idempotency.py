"""Tests para idempotency — hash determinista de (tool + action + params).

Cubre:
- Determinismo: mismo input → mismo hash.
- Sensibilidad a tool_name, action_name, params.
- Formato: 16 char hex string (sha256 truncado).
- Orden de params no afecta (sorted keys).
- Tipos no-serializables manejo con default=str.
"""
from __future__ import annotations

from src.hat.level4_workers.base.idempotency import compute_worker_hash


class TestDeterminism:
    """El hash es determinista."""

    def test_same_input_same_hash(self) -> None:
        """Mismo input produce mismo hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        h2 = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        assert h1 == h2

    def test_different_tool_different_hash(self) -> None:
        """Diferente tool_name → diferente hash."""
        h1 = compute_worker_hash("crm", "action", {})
        h2 = compute_worker_hash("invoice", "action", {})
        assert h1 != h2

    def test_different_action_different_hash(self) -> None:
        """Diferente action_name → diferente hash."""
        h1 = compute_worker_hash("crm", "create", {})
        h2 = compute_worker_hash("crm", "list", {})
        assert h1 != h2

    def test_different_params_different_hash(self) -> None:
        """Diferente params → diferente hash."""
        h1 = compute_worker_hash("crm", "action", {"a": 1})
        h2 = compute_worker_hash("crm", "action", {"a": 2})
        assert h1 != h2


class TestFormat:
    """Formato del hash."""

    def test_hash_is_16_char_hex(self) -> None:
        """El hash tiene 16 caracteres hexadecimales."""
        h = compute_worker_hash("tool", "action", {})
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestParamsOrdering:
    """El orden de params no afecta el hash."""

    def test_same_params_different_order_same_hash(self) -> None:
        """Params con keys en distinto orden → mismo hash."""
        h1 = compute_worker_hash("crm", "action", {"a": 1, "b": 2, "c": 3})
        h2 = compute_worker_hash("crm", "action", {"c": 3, "a": 1, "b": 2})
        assert h1 == h2

    def test_empty_params_produces_valid_hash(self) -> None:
        """Params vacío produce hash válido."""
        h = compute_worker_hash("crm", "action", {})
        assert len(h) == 16


class TestNonSerializable:
    """Tipos no-serializables se manejan con default=str."""

    def test_set_in_params_does_not_crash(self) -> None:
        """Set en params no crashea (default=str lo convierte)."""
        h = compute_worker_hash("crm", "action", {"tags": {"a", "b"}})
        assert len(h) == 16

    def test_object_in_params_does_not_crash(self) -> None:
        """Objeto custom en params no crashea."""
        class Custom:
            def __str__(self) -> str:
                return "custom"

        h = compute_worker_hash("crm", "action", {"obj": Custom()})
        assert len(h) == 16

    def test_datetime_in_params_does_not_crash(self) -> None:
        """datetime en params no crashea."""
        from datetime import datetime

        h = compute_worker_hash("crm", "action", {"date": datetime(2024, 1, 1)})
        assert len(h) == 16
