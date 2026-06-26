"""
Tests del helper SQL seguro (src/utils/sql.py).

Verifica:
- Identificadores válidos son aceptados.
- Identificadores maliciosos son rechazados (SQL injection attempts).
- build_update_query produce SQL correcto y params correctos.
- safe_drop_table_if_exists solo acepta identificadores seguros.
- build_in_clause genera el número correcto de placeholders.
"""
from __future__ import annotations

import sqlite3

import pytest

from src.core.db import (
    build_in_clause,
    build_update_query,
    quote_identifier,
    safe_drop_table_if_exists,
    validate_identifier,
)


class TestValidateIdentifier:
    """Identificadores válidos e inválidos."""

    @pytest.mark.parametrize("name", [
        "users", "leads", "products", "user_mfa", "api_keys",
        "table_123", "CamelCase", "_private",
    ])
    def test_valid_identifiers(self, name):
        assert validate_identifier(name) == name

    @pytest.mark.parametrize("name,reason", [
        ("", "vacío"),
        ("1table", "empieza con dígito"),
        ("table; DROP users;", "punto y coma"),
        ("table--comment", "comentario SQL"),
        ("table' OR '1'='1", "comilla simple"),
        ('table" OR "1"="1', "comilla doble"),
        ("table` OR `1`=`1", "backtick"),
        ("table OR 1=1", "espacio + OR"),
        ("table/*comment*/", "comentario de bloque"),
        ("table\x00", "null byte"),
        ("a" * 200, "demasiado largo"),
        (None, "None"),
        (123, "int"),
        (["table"], "list"),
    ])
    def test_invalid_identifiers(self, name, reason):
        with pytest.raises(ValueError, match="Identificador"):
            validate_identifier(name)


class TestQuoteIdentifier:
    """Quoting con comillas dobles (estándar SQL)."""

    def test_simple_name(self):
        assert quote_identifier("users") == '"users"'

    def test_reserved_word(self):
        assert quote_identifier("order") == '"order"'

    def test_underscore(self):
        assert quote_identifier("user_mfa") == '"user_mfa"'

    def test_dollar_sign_not_allowed(self):
        """Zenic-Flijo no usa $ en identificadores; el regex lo rechaza por seguridad."""
        with pytest.raises(ValueError):
            quote_identifier("$special")

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            quote_identifier("table; DROP")


class TestBuildUpdateQuery:
    """Construcción de UPDATE con allowlist."""

    def test_basic_update(self):
        sql, params = build_update_query(
            "leads",
            {"name", "email", "stage"},
            {"name": "Juan", "stage": "won"},
        )
        assert sql == 'UPDATE "leads" SET "name" = ?, "stage" = ? WHERE id = ?'
        assert params == ("Juan", "won")

    def test_filters_disallowed_fields(self):
        """Campos fuera del allowlist se ignoran (no se incluyen en SET)."""
        sql, params = build_update_query(
            "users",
            {"name", "email"},
            {"name": "Juan", "is_admin": True, "password_hash": "hacked"},
        )
        # is_admin y password_hash NO están en allowed → ignorados
        assert sql == 'UPDATE "users" SET "name" = ? WHERE id = ?'
        assert params == ("Juan",)

    def test_empty_fields_returns_none(self):
        """Si ningún campo está en allowlist, retorna None."""
        result = build_update_query(
            "users",
            {"name"},
            {"forbidden_col": "value"},
        )
        assert result is None

    def test_all_fields_filtered_returns_none(self):
        result = build_update_query(
            "users",
            {"name"},
            {},  # Sin fields
        )
        assert result is None

    def test_with_extra_set(self):
        from datetime import datetime
        ts = datetime(2026, 6, 18, 10, 0, 0).isoformat()
        sql, params = build_update_query(
            "leads",
            {"name", "email", "updated_at"},
            {"name": "Juan"},
            extra_set={"updated_at": ts},
        )
        assert sql == 'UPDATE "leads" SET "name" = ?, "updated_at" = ? WHERE id = ?'
        assert params == ("Juan", ts)

    def test_extra_set_updated_at_allowed_even_if_not_in_allowlist(self):
        """updated_at es una excepción común — se permite siempre."""
        sql, params = build_update_query(
            "leads",
            {"name"},  # updated_at NO está, pero se permite como extra_set
            {"name": "Juan"},
            extra_set={"updated_at": "2026-06-18"},
        )
        assert "updated_at" in sql
        assert params == ("Juan", "2026-06-18")

    def test_extra_set_other_column_must_be_in_allowlist(self):
        """Columnas extra (no updated_at) deben estar en allowlist explícitamente."""
        with pytest.raises(ValueError, match="Columna extra"):
            build_update_query(
                "leads",
                {"name"},
                {"name": "Juan"},
                extra_set={"created_at": "2026-06-18"},  # No está en allowlist
            )

    def test_invalid_table_raises(self):
        with pytest.raises(ValueError, match="Identificador"):
            build_update_query(
                "leads; DROP TABLE users; --",
                {"name"},
                {"name": "Juan"},
            )

    def test_custom_where_clause(self):
        sql, params = build_update_query(
            "leads",
            {"name"},
            {"name": "Juan"},
            where_clause="tenant_id = ? AND id = ?",
        )
        assert sql == 'UPDATE "leads" SET "name" = ? WHERE tenant_id = ? AND id = ?'
        assert params == ("Juan",)

    def test_where_clause_with_format_raises(self):
        """where_clause no debe usar .format() o %s."""
        with pytest.raises(ValueError, match="where_clause no debe usar"):
            build_update_query(
                "leads",
                {"name"},
                {"name": "Juan"},
                where_clause="id = %s",
            )

    def test_order_preserved(self):
        """El orden de los campos en SET debe preservar el orden de fields."""
        sql, params = build_update_query(
            "leads",
            {"name", "email", "phone", "company"},
            {"phone": "123", "name": "Juan", "company": "ACME", "email": "j@x.com"},
        )
        # Orden en SQL = orden en fields
        assert sql == (
            'UPDATE "leads" SET "phone" = ?, "name" = ?, "company" = ?, "email" = ? WHERE id = ?'
        )
        assert params == ("123", "Juan", "ACME", "j@x.com")


class TestSafeDropTableIfExists:
    """DROP TABLE seguro."""

    def test_drops_valid_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.commit()
        # Verificar que existe
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='foo'"
        ).fetchone()[0] == 1

        safe_drop_table_if_exists(conn.cursor(), "foo")
        conn.commit()
        # Verificar que se dropeó
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='foo'"
        ).fetchone()[0] == 0

    def test_drop_nonexistent_table_no_error(self):
        """DROP TABLE IF EXISTS no falla si la tabla no existe."""
        conn = sqlite3.connect(":memory:")
        # No debe levantar error
        safe_drop_table_if_exists(conn.cursor(), "nonexistent")

    def test_malicious_table_name_rejected(self):
        conn = sqlite3.connect(":memory:")
        malicious_names = [
            "foo; DROP TABLE bar; --",
            "foo' OR '1'='1",
            "foo\" OR \"1\"=\"1",
            "foo--",
            "foo/*comment*/",
        ]
        for name in malicious_names:
            with pytest.raises(ValueError, match="Identificador"):
                safe_drop_table_if_exists(conn.cursor(), name)

    def test_sqlite_master_not_droppable_via_validation(self):
        """sqlite_master es identificador válido — la protección es que el caller
        no debería llamar safe_drop_table con nombres que no controla.
        El helper valida caracteres, no semántica."""
        conn = sqlite3.connect(":memory:")
        # sqlite_master pasa la validación (es alfanumérico+underscore)
        # pero SQLite rechaza el DROP con error de runtime:
        with pytest.raises(sqlite3.OperationalError, match="sqlite_master"):
            safe_drop_table_if_exists(conn.cursor(), "sqlite_master")


class TestBuildInClause:
    """Construcción de IN (?, ?, ...) dinámico."""

    def test_one_value(self):
        assert build_in_clause(1) == "(?)"

    def test_three_values(self):
        assert build_in_clause(3) == "(?, ?, ?)"

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            build_in_clause(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            build_in_clause(-1)

    def test_invalid_placeholder_raises(self):
        with pytest.raises(ValueError, match="placeholder"):
            build_in_clause(3, placeholder="%s")


class TestIntegrationWithSQLite:
    """Tests de integración: el SQL generado se ejecuta en SQLite real."""

    def test_update_executes_correctly(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT, stage TEXT, updated_at TEXT)")
        conn.execute("INSERT INTO leads (id, name, stage) VALUES (1, 'Old', 'new')")
        conn.commit()

        from datetime import datetime
        ts = datetime.now().isoformat()
        sql, params = build_update_query(
            "leads",
            {"name", "stage", "updated_at"},
            {"name": "Juan", "stage": "won"},
            extra_set={"updated_at": ts},
        )
        # Append el valor del WHERE (id) a los params
        full_params = (*params, 1)
        conn.execute(sql, full_params)
        conn.commit()

        row = conn.execute("SELECT name, stage, updated_at FROM leads WHERE id = 1").fetchone()
        assert row == ("Juan", "won", ts)

    def test_update_with_in_clause(self):
        """Combinar build_update_query + build_in_clause."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany("INSERT INTO leads (id, name) VALUES (?, ?)",
                         [(1, "A"), (2, "B"), (3, "C")])
        conn.commit()

        in_clause = build_in_clause(3)
        # in_clause proviene de build_in_clause() que solo retorna (?, ?, ?) — seguro.
        sql = f"SELECT name FROM leads WHERE id IN {in_clause}"  # nosec B608 — in_clause es placeholders seguro
        rows = conn.execute(sql, (1, 2, 3)).fetchall()
        assert [r[0] for r in rows] == ["A", "B", "C"]
