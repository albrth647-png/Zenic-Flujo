"""Tests para los codemods de migración Any.

Cobertura:
  - Casos positivos (transformación correcta)
  - Casos negativos (no transforma lo que no debe)
  - Idempotencia (aplicar 2x = aplicar 1x)
  - Combo (auto-migrate-bare)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Asegurar import del módulo bajo test
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pytest

from any_codemods import (
    AutoMigrateBareCollections,
    DocumentOptionalAnyAttribute,
    ParametrizeBareList,
    ParametrizeBareDict,
    ParametrizeBareTuple,
    list_codemods,
    transform_module,
)


# ─── ParametrizeBareDict ─────────────────────────────────────────────────────


class TestParametrizeBareDict:
    def test_param_annotation(self) -> None:
        src = "def f(x: dict) -> None:\n    pass\n"
        expected = "def f(x: dict[str, Any]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareDict) == expected

    def test_return_annotation(self) -> None:
        src = "def f() -> dict:\n    return {}\n"
        expected = "def f() -> dict[str, Any]:\n    return {}\n"
        assert transform_module(src, ParametrizeBareDict) == expected

    def test_var_annotation(self) -> None:
        src = "x: dict = {}\n"
        expected = "x: dict[str, Any] = {}\n"
        assert transform_module(src, ParametrizeBareDict) == expected

    def test_capital_dict_legacy_typing(self) -> None:
        src = "def f(x: Dict) -> None:\n    pass\n"
        expected = "def f(x: Dict[str, Any]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareDict) == expected

    def test_already_parametrized_unchanged(self) -> None:
        src = "def f(x: dict[str, int]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareDict) == src

    def test_already_parametrized_with_any_unchanged(self) -> None:
        src = "def f(x: dict[str, Any]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareDict) == src

    def test_idempotent(self) -> None:
        src = "def f(x: dict) -> dict:\n    return {}\n"
        once = transform_module(src, ParametrizeBareDict)
        twice = transform_module(once, ParametrizeBareDict)
        assert once == twice

    def test_does_not_touch_dict_call(self) -> None:
        """`dict()` call (no annotation) no debe tocarse."""
        src = "x = dict()\n"
        assert transform_module(src, ParametrizeBareDict) == src


# ─── ParametrizeBareList ─────────────────────────────────────────────────────


class TestParametrizeBareList:
    def test_param_annotation(self) -> None:
        src = "def f(x: list) -> None:\n    pass\n"
        expected = "def f(x: list[Any]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareList) == expected

    def test_return_annotation(self) -> None:
        src = "def f() -> list:\n    return []\n"
        expected = "def f() -> list[Any]:\n    return []\n"
        assert transform_module(src, ParametrizeBareList) == expected

    def test_capital_list_legacy(self) -> None:
        src = "def f(x: List) -> None:\n    pass\n"
        expected = "def f(x: List[Any]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareList) == expected

    def test_already_parametrized_unchanged(self) -> None:
        src = "def f(x: list[int]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareList) == src

    def test_idempotent(self) -> None:
        src = "def f(x: list) -> list:\n    return []\n"
        once = transform_module(src, ParametrizeBareList)
        twice = transform_module(once, ParametrizeBareList)
        assert once == twice


# ─── ParametrizeBareTuple ────────────────────────────────────────────────────


class TestParametrizeBareTuple:
    def test_param_annotation(self) -> None:
        src = "def f(x: tuple) -> None:\n    pass\n"
        expected = "def f(x: tuple[Any, ...]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareTuple) == expected

    def test_return_annotation(self) -> None:
        src = "def f() -> tuple:\n    return (1, 2)\n"
        expected = "def f() -> tuple[Any, ...]:\n    return (1, 2)\n"
        assert transform_module(src, ParametrizeBareTuple) == expected

    def test_already_parametrized_unchanged(self) -> None:
        src = "def f(x: tuple[int, str]) -> None:\n    pass\n"
        assert transform_module(src, ParametrizeBareTuple) == src

    def test_idempotent(self) -> None:
        src = "def f(x: tuple) -> tuple:\n    return ()\n"
        once = transform_module(src, ParametrizeBareTuple)
        twice = transform_module(once, ParametrizeBareTuple)
        assert once == twice


# ─── DocumentOptionalAnyAttribute ────────────────────────────────────────────


class TestDocumentOptionalAnyAttribute:
    def test_attribute_any_none(self) -> None:
        src = "class S:\n    client: Any = None\n"
        expected = "class S:\n    client: Any | None = None\n"
        assert transform_module(src, DocumentOptionalAnyAttribute) == expected

    def test_attribute_any_with_value_unchanged(self) -> None:
        """`x: Any = "default"` no debe tocarse (no es None)."""
        src = "class S:\n    x: Any = 'default'\n"
        assert transform_module(src, DocumentOptionalAnyAttribute) == src

    def test_attribute_any_no_value_unchanged(self) -> None:
        """`x: Any` sin asignación no debe tocarse."""
        src = "class S:\n    x: Any\n"
        assert transform_module(src, DocumentOptionalAnyAttribute) == src

    def test_attribute_typed_none_unchanged(self) -> None:
        """`x: HTTPClient = None` no debe tocarse (no es Any)."""
        src = "class S:\n    x: HTTPClient = None\n"
        assert transform_module(src, DocumentOptionalAnyAttribute) == src

    def test_already_optional_unchanged(self) -> None:
        """`x: Any | None = None` no debe tocarse."""
        src = "class S:\n    x: Any | None = None\n"
        assert transform_module(src, DocumentOptionalAnyAttribute) == src

    def test_idempotent(self) -> None:
        src = "class S:\n    client: Any = None\n"
        once = transform_module(src, DocumentOptionalAnyAttribute)
        twice = transform_module(once, DocumentOptionalAnyAttribute)
        assert once == twice


# ─── AutoMigrateBareCollections (combo) ──────────────────────────────────────


class TestAutoMigrateBare:
    def test_combo_dict_and_attr(self) -> None:
        src = (
            "class S:\n"
            "    config: dict = None\n"
            "    def f(self, x: dict) -> dict:\n"
            "        return {}\n"
        )
        result = transform_module(src, AutoMigrateBareCollections)
        # El atributo debe tener Any | None, el dict debe quedar parametrizado
        assert "config: dict[str, Any] | None = None" in result
        assert "def f(self, x: dict[str, Any]) -> dict[str, Any]:" in result

    def test_combo_list_and_tuple(self) -> None:
        src = "def f(x: list, y: tuple) -> dict:\n    return {}\n"
        result = transform_module(src, AutoMigrateBareCollections)
        assert "list[Any]" in result
        assert "tuple[Any, ...]" in result
        assert "dict[str, Any]" in result

    def test_combo_idempotent(self) -> None:
        src = (
            "class S:\n"
            "    config: dict = None\n"
            "    items: list = []\n"
            "    def f(self) -> tuple:\n"
            "        return ()\n"
        )
        once = transform_module(src, AutoMigrateBareCollections)
        twice = transform_module(once, AutoMigrateBareCollections)
        assert once == twice

    def test_combo_preserves_already_typed(self) -> None:
        src = (
            "def f(x: dict[str, int], y: list[int]) -> tuple[int, str]:\n"
            "    return (1, 'a')\n"
        )
        assert transform_module(src, AutoMigrateBareCollections) == src


# ─── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_list_codemods_returns_all(self) -> None:
        codemods = list_codemods()
        assert "parametrize-bare-dict" in codemods
        assert "parametrize-bare-list" in codemods
        assert "parametrize-bare-tuple" in codemods
        assert "document-optional-any-attr" in codemods
        assert "auto-migrate-bare" in codemods

    def test_all_codemods_have_description(self) -> None:
        for name, cls in list_codemods().items():
            assert cls.DESCRIPTION, f"{name} no tiene DESCRIPTION"
            assert len(cls.DESCRIPTION) > 10, f"{name} DESCRIPTION demasiado corta"


# ─── Integration: código real ────────────────────────────────────────────────


class TestIntegrationRealCode:
    """Tests con snippets realistas que combinan múltiples antipatrones."""

    def test_connector_signature(self) -> None:
        """Simula la signatura típica de un conector."""
        src = (
            "from typing import Any\n"
            "\n"
            "class MyConnector:\n"
            "    client: Any = None\n"
            "    config: dict = None\n"
            "\n"
            "    def call(self, payload: dict) -> dict:\n"
            "        return {}\n"
            "\n"
            "    def list_items(self) -> list:\n"
            "        return []\n"
        )
        result = transform_module(src, AutoMigrateBareCollections)
        # Verificar transformaciones clave
        assert "client: Any | None = None" in result
        assert "config: dict[str, Any] | None = None" in result
        assert "def call(self, payload: dict[str, Any]) -> dict[str, Any]:" in result
        assert "def list_items(self) -> list[Any]:" in result

    def test_router_endpoint(self) -> None:
        """Simula un endpoint Flask/FastAPI."""
        src = (
            "def get_users() -> dict:\n"
            "    users: list = []\n"
            "    metadata: dict = {}\n"
            "    return {'users': users, 'meta': metadata}\n"
        )
        result = transform_module(src, AutoMigrateBareCollections)
        assert "def get_users() -> dict[str, Any]:" in result
        assert "users: list[Any] = []" in result
        assert "metadata: dict[str, Any] = {}" in result
