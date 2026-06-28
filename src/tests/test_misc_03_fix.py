"""Tests para el fix del bug MISC-03 (Zip Slip, CVE-2018-1002200).

Verifica que ``CertificationEngine._prepare_path`` rechaza ZIPs maliciosos
que intentan escribir archivos fuera del directorio de extracción mediante
paths con ``..`` o rutas absolutas. Antes del fix, ``zf.extractall`` se
invocaba sin sanitización, permitiendo path traversal.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _make_zip(files: dict[str, bytes]) -> bytes:
    """Crea un ZIP en memoria con los archivos indicados.

    Args:
        files: Diccionario {nombre_archivo: contenido_bytes}.

    Returns:
        Bytes del ZIP generado.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestMisc03ZipSlipFix:
    """Verifica el fix del Zip Slip en certification._prepare_path."""

    def test_zip_slip_with_dotdot_rejected(self, tmp_path):
        """ZIP con entrada '../../../etc/passwd' debe levantar ValueError."""
        from src.marketplace.certification import CertificationEngine

        # Crear un ZIP malicioso con path traversal
        malicious_zip = tmp_path / "malicious.zip"
        malicious_content = _make_zip({
            "legit.txt": b"hello",
            "../../../etc/passwd_evil": b"root:x:0:0:root:/root:/bin/bash\n",
            "another.txt": b"world",
        })
        malicious_zip.write_bytes(malicious_content)

        engine = CertificationEngine()
        with pytest.raises(ValueError, match="Zip Slip"):
            engine._prepare_path(str(malicious_zip))

    def test_zip_slip_with_absolute_path_rejected(self, tmp_path):
        """ZIP con entrada '/etc/passwd' (ruta absoluta) debe levantar ValueError."""
        from src.marketplace.certification import CertificationEngine

        malicious_zip = tmp_path / "absolute.zip"
        malicious_content = _make_zip({
            "/etc/passwd_evil": b"root:x:0:0:root:/root:/bin/bash\n",
        })
        malicious_zip.write_bytes(malicious_content)

        engine = CertificationEngine()
        with pytest.raises(ValueError, match="Zip Slip"):
            engine._prepare_path(str(malicious_zip))

    def test_zip_slip_with_deep_dotdot_rejected(self, tmp_path):
        """ZIP con 'a/../../../etc/passwd' debe levantar ValueError."""
        from src.marketplace.certification import CertificationEngine

        malicious_zip = tmp_path / "deep.zip"
        malicious_content = _make_zip({
            "valid_dir/a.txt": b"hello",
            "valid_dir/../../../../tmp/evil.txt": b"evil payload",
        })
        malicious_zip.write_bytes(malicious_content)

        engine = CertificationEngine()
        with pytest.raises(ValueError, match="Zip Slip"):
            engine._prepare_path(str(malicious_zip))

    def test_legit_zip_extracts_normally(self, tmp_path):
        """ZIP sin path traversal se extrae normalmente."""
        from src.marketplace.certification import CertificationEngine

        legit_zip = tmp_path / "legit.zip"
        legit_content = _make_zip({
            "manifest.json": b'{"name": "test-connector"}',
            "src/connector.py": b"class TestConnector: pass\n",
            "tests/test_connector.py": b"def test_ok(): pass\n",
        })
        legit_zip.write_bytes(legit_content)

        engine = CertificationEngine()
        extract_dir = engine._prepare_path(str(legit_zip))

        # Verificar que se extrajeron los archivos esperados
        extract_path = Path(extract_dir)
        assert (extract_path / "manifest.json").exists()
        assert (extract_path / "src" / "connector.py").exists()
        assert (extract_path / "tests" / "test_connector.py").exists()

    def test_zip_slip_does_not_write_outside_extract_dir(self, tmp_path):
        """Tras el rechazo, no se debe haber escrito ningún archivo fuera del dir."""
        from src.marketplace.certification import CertificationEngine

        # Directorio 'target' fuera del dir de extracción esperado
        sentinel = tmp_path / "sentinel_dir"
        sentinel.mkdir()
        sentinel_file = sentinel / "evil.txt"
        assert not sentinel_file.exists()

        malicious_zip = tmp_path / "evil.zip"
        # Path malicioso que intentaría escribir en tmp_path/sentinel_dir/evil.txt
        malicious_content = _make_zip({
            "../sentinel_dir/evil.txt": b"evil payload",
        })
        malicious_zip.write_bytes(malicious_content)

        engine = CertificationEngine()
        with pytest.raises(ValueError, match="Zip Slip"):
            engine._prepare_path(str(malicious_zip))

        # Confirmar defensa: el archivo NO existe (extractall nunca se invocó)
        assert not sentinel_file.exists(), (
            "Zip Slip NO bloqueado: se escribió archivo fuera del directorio destino"
        )

    def test_non_zip_path_returned_unchanged(self, tmp_path):
        """Si connector_path no es .zip, se retorna sin cambios."""
        from src.marketplace.certification import CertificationEngine

        connector_dir = tmp_path / "connector_dir"
        connector_dir.mkdir()
        (connector_dir / "manifest.json").write_text('{"name": "x"}')

        engine = CertificationEngine()
        result = engine._prepare_path(str(connector_dir))
        assert result == str(connector_dir)

    def test_zip_slip_value_error_message_includes_filename(self, tmp_path):
        """El mensaje de error incluye el nombre del miembro malicioso para debugging."""
        from src.marketplace.certification import CertificationEngine

        malicious_zip = tmp_path / "info.zip"
        malicious_content = _make_zip({
            "../../../etc/leaked_secret": b"top-secret",
        })
        malicious_zip.write_bytes(malicious_content)

        engine = CertificationEngine()
        with pytest.raises(ValueError) as exc:
            engine._prepare_path(str(malicious_zip))
        # El mensaje debe mencionar el archivo malicioso
        assert "leaked_secret" in str(exc.value)
