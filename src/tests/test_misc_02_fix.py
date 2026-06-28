"""
Test de verificacion para bug MISC-02 — Marketplace publish_connector valida api_key solo por longitud.

Antes del fix: ``MarketplaceService.publish_connector`` validaba la api_key del
publicador con ``if not api_key or len(api_key) < 10``. Eso aceptaba cualquier
string aleatorio de >= 10 caracteres (ej: "1234567890") como api_key valida,
permitiendo que cualquiera publicara conectores en el marketplace.

Despues del fix:
- ``_validate_api_key_structure(api_key)`` exige: longitud >= 32, al menos una
  mayuscula, al menos una minuscula, al menos un digito.
- ``_validate_publisher_api_key(api_key)`` ademas consulta la tabla
  ``marketplace_publisher_keys`` y, si hay keys registradas, exige que la
  api_key este en la tabla (comparacion por SHA-256 hash).
- ``register_publisher_api_key(api_key, partner_name)`` permite registrar keys
  validas (para onboarding y tests).
- La tabla ``marketplace_publisher_keys`` se crea en ``sqlite_manager._migrate``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.marketplace.service import (
    MarketplaceService,
    _hash_api_key,
    _validate_api_key_structure,
)


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Crea una DB fresca en tmp_path y la usa como DB_PATH del singleton."""
    db_path = tmp_path / "test_misc_02.db"
    # Forzar el singleton a apuntar a una DB nueva.
    import src.core.db.sqlite_manager as sm_mod

    monkeypatch.setattr(sm_mod, "DB_PATH", str(db_path), raising=False)
    # Resetear la instancia singleton para que se re cree con la nueva DB_PATH.
    sm_mod.DatabaseManager._instance = None
    # Forzar la migracion (crea la tabla marketplace_publisher_keys).
    sm_mod.DatabaseManager()
    yield db_path
    # Cleanup
    sm_mod.DatabaseManager._instance = None


@pytest.fixture
def marketplace_service(fresh_db: Path) -> MarketplaceService:
    """Instancia de MarketplaceService apuntando a la DB fresca."""
    return MarketplaceService()


class TestBugMisc02ValidateApiKeyStructure:
    """La validacion estructural de api_key debe ser estricta."""

    def test_empty_api_key_rejected(self) -> None:
        """API key vacia debe ser rechazada."""
        valido, razon = _validate_api_key_structure("")
        assert valido is False
        assert "vacia" in razon.lower()

    def test_short_api_key_rejected(self) -> None:
        """API key < 32 caracteres debe ser rechazada."""
        # Antes del fix, "1234567890" (10 chars) era aceptado.
        valido, razon = _validate_api_key_structure("1234567890")
        assert valido is False
        assert "corta" in razon.lower()

    def test_api_key_without_uppercase_rejected(self) -> None:
        """API key sin mayusculas debe ser rechazada."""
        valido, razon = _validate_api_key_structure("abcdefghijklmnopqrstuvwxyz123456")
        assert valido is False
        assert "mayuscula" in razon.lower()

    def test_api_key_without_lowercase_rejected(self) -> None:
        """API key sin minusculas debe ser rechazada."""
        valido, razon = _validate_api_key_structure("ABCDEFGHIJKLMNOPQRSTUVWXYZ123456")
        assert valido is False
        assert "minuscula" in razon.lower()

    def test_api_key_without_digit_rejected(self) -> None:
        """API key sin digitos debe ser rechazada."""
        valido, razon = _validate_api_key_structure("abcdefghijklmnopqrstuvwxyzABCDEF")
        assert valido is False
        assert "digito" in razon.lower()

    def test_valid_api_key_accepted(self) -> None:
        """API key con longitud >= 32, mayuscula, minuscula y digito debe ser aceptada."""
        valido, razon = _validate_api_key_structure("Abcdefghijklmnopqrstuvwxyz123456")
        assert valido is True
        assert razon == ""

    def test_strong_api_key_accepted(self) -> None:
        """API key fuerte (estilo Stripe) debe ser aceptada."""
        valido, _ = _validate_api_key_structure("sk-AbcDef123Ghi456Jkl789Mno012Pqr345")
        assert valido is True

    def test_legacy_short_api_key_now_rejected(self) -> None:
        """Regression test: la api_key '1234567890' que antes pasaba ahora debe fallar."""
        # Antes del fix: len("1234567890") == 10 >= 10 → aceptada.
        # Despues del fix: len("1234567890") == 10 < 32 → rechazada.
        valido, _ = _validate_api_key_structure("1234567890")
        assert valido is False, (
            "BUG MISC-02: la api_key '1234567890' (10 chars) sigue siendo aceptada. "
            "El fix debe exigir minimo 32 caracteres."
        )


class TestBugMisc02HashApiKey:
    """El hash de la api_key debe ser determinista y no reversible."""

    def test_hash_is_deterministic(self) -> None:
        """El hash de la misma api_key debe ser siempre el mismo."""
        h1 = _hash_api_key("Abcdefghijklmnopqrstuvwxyz123456")
        h2 = _hash_api_key("Abcdefghijklmnopqrstuvwxyz123456")
        assert h1 == h2

    def test_hash_is_hex_string(self) -> None:
        """El hash debe ser un string hex de 64 chars (SHA-256)."""
        h = _hash_api_key("Abcdefghijklmnopqrstuvwxyz123456")
        assert len(h) == 64
        int(h, 16)  # Levanta ValueError si no es hex valido.

    def test_different_keys_produce_different_hashes(self) -> None:
        """Dos api_keys diferentes deben producir hashes diferentes."""
        h1 = _hash_api_key("Abcdefghijklmnopqrstuvwxyz123456")
        h2 = _hash_api_key("Bbcdefghijklmnopqrstuvwxyz123456")
        assert h1 != h2


class TestBugMisc02PublisherTableCreated:
    """La tabla marketplace_publisher_keys debe existir tras la migracion."""

    def test_publisher_keys_table_exists(self, fresh_db: Path) -> None:
        """La tabla debe existir tras DatabaseManager()._migrate."""
        conn = sqlite3.connect(str(fresh_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='marketplace_publisher_keys'"
        )
        result = cursor.fetchone()
        conn.close()
        assert result is not None, (
            "BUG MISC-02: la tabla marketplace_publisher_keys no fue creada por la migracion."
        )

    def test_publisher_keys_table_has_expected_columns(self, fresh_db: Path) -> None:
        """La tabla debe tener las columnas api_key_hash, partner_name, created_at."""
        conn = sqlite3.connect(str(fresh_db))
        cursor = conn.execute("PRAGMA table_info(marketplace_publisher_keys)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert {"api_key_hash", "partner_name", "created_at"}.issubset(columns)


class TestBugMisc02PublishConnectorRejectsInvalidKeys:
    """publish_connector debe rechazar api_keys invalidas."""

    def test_publish_rejects_empty_api_key(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """API key vacia debe ser rechazada antes de intentar publicar."""
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # ZIP vacio valido
        result = marketplace_service.publish_connector(str(zip_path), "")
        assert result["success"] is False
        assert "api key" in result["error"].lower()

    def test_publish_rejects_short_api_key(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """API key < 32 chars debe ser rechazada."""
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(str(zip_path), "1234567890")
        assert result["success"] is False
        assert "api key" in result["error"].lower()

    def test_publish_rejects_api_key_without_digit(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """API key sin digitos debe ser rechazada."""
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(
            str(zip_path), "abcdefghijklmnopqrstuvwxyzABCDEF"
        )
        assert result["success"] is False

    def test_publish_rejects_api_key_without_uppercase(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """API key sin mayusculas debe ser rechazada."""
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(
            str(zip_path), "abcdefghijklmnopqrstuvwxyz123456"
        )
        assert result["success"] is False

    def test_publish_rejects_unregistered_key_when_strict_mode(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """Si hay keys registradas, una api_key no registrada debe ser rechazada."""
        # Registrar una key valida para activar modo estricto.
        registered_key = "Abcdefghijklmnopqrstuvwxyz123456"
        unregistered_key = "Bbcdefghijklmnopqrstuvwxyz123456"
        reg_result = marketplace_service.register_publisher_api_key(registered_key, "partner_test")
        assert reg_result["success"] is True
        # Intentar publicar con otra key valida estructuralmente pero NO registrada.
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(str(zip_path), unregistered_key)
        assert result["success"] is False
        assert "no registrada" in result["error"].lower()


class TestBugMisc02PublishConnectorAcceptsValidKeys:
    """publish_connector debe aceptar api_keys validas (modo desarrollo y strict)."""

    def test_publish_accepts_valid_unregistered_key_in_dev_mode(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """En modo desarrollo (tabla vacia), una key estructuralmente valida debe pasar."""
        # No registramos ninguna key — la tabla esta vacia, modo desarrollo.
        valid_key = "Abcdefghijklmnopqrstuvwxyz123456"
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(str(zip_path), valid_key)
        # La publicacion puede fallar por la certificacion (ZIP vacio), pero NO
        # por la api_key. Verificamos que el error (si lo hay) no sea de api_key.
        if not result["success"]:
            assert "api_key" not in result.get("error", "").lower(), (
                f"BUG MISC-02: api_key valida fue rechazada en modo desarrollo. Error: {result.get('error')}"
            )

    def test_publish_accepts_registered_key_in_strict_mode(
        self, marketplace_service: MarketplaceService, tmp_path: Path
    ) -> None:
        """En modo estricto, una key registrada debe pasar la validacion."""
        registered_key = "Abcdefghijklmnopqrstuvwxyz123456"
        marketplace_service.register_publisher_api_key(registered_key, "partner_test")
        zip_path = tmp_path / "connector.zip"
        zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        result = marketplace_service.publish_connector(str(zip_path), registered_key)
        # La publicacion puede fallar por la certificacion (ZIP vacio), pero NO
        # por la api_key registrada.
        if not result["success"]:
            assert "api_key" not in result.get("error", "").lower(), (
                f"BUG MISC-02: api_key registrada fue rechazada en modo estricto. Error: {result.get('error')}"
            )


class TestBugMisc02RegisterPublisherApiKey:
    """register_publisher_api_key debe validar la estructura antes de registrar."""

    def test_register_rejects_invalid_key(self, marketplace_service: MarketplaceService) -> None:
        """No debe poder registrar una api_key que no cumple la estructura."""
        result = marketplace_service.register_publisher_api_key("corta", "partner_test")
        assert result["success"] is False

    def test_register_accepts_valid_key(self, marketplace_service: MarketplaceService) -> None:
        """Debe poder registrar una api_key estructuralmente valida."""
        valid_key = "Abcdefghijklmnopqrstuvwxyz123456"
        result = marketplace_service.register_publisher_api_key(valid_key, "partner_test")
        assert result["success"] is True

    def test_registered_key_appears_in_table(self, marketplace_service: MarketplaceService) -> None:
        """Tras registrar, la key (su hash) debe aparecer en la tabla."""
        valid_key = "Abcdefghijklmnopqrstuvwxyz123456"
        marketplace_service.register_publisher_api_key(valid_key, "partner_test")
        row = marketplace_service._db.fetchone(
            "SELECT partner_name FROM marketplace_publisher_keys WHERE api_key_hash = ?",
            (_hash_api_key(valid_key),),
        )
        assert row is not None
        assert row["partner_name"] == "partner_test"

    def test_register_same_key_twice_is_idempotent(
        self, marketplace_service: MarketplaceService
    ) -> None:
        """Registrar la misma key dos veces no debe duplicar ni fallar."""
        valid_key = "Abcdefghijklmnopqrstuvwxyz123456"
        r1 = marketplace_service.register_publisher_api_key(valid_key, "partner_a")
        r2 = marketplace_service.register_publisher_api_key(valid_key, "partner_b")
        assert r1["success"] is True
        assert r2["success"] is True
        # Y la tabla debe tener exactamente una entrada para esa key.
        rows = marketplace_service._db.fetchall(
            "SELECT partner_name FROM marketplace_publisher_keys WHERE api_key_hash = ?",
            (_hash_api_key(valid_key),),
        )
        assert len(rows) == 1
