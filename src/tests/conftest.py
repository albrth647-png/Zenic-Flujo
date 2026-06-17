"""
Workflow Determinista — Test Fixtures Compartidas
Fixtures de pytest compartidas por todos los tests.
"""

import sys
from pathlib import Path

import pytest

# Asegurar que src/ está en el path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def db_path(tmp_path):
    """Retorna un path temporal para la base de datos de prueba."""
    return tmp_path / "test_workflow_determinista.db"


@pytest.fixture
def db_manager(db_path, monkeypatch):
    """
    Provee un DatabaseManager configurado con base de datos temporal.
    Usa monkeypatch para redirigir DB_PATH al archivo temporal.
    """
    from src import config

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "DATA_DIR", db_path.parent)

    from src.data import database_manager
    from src.data.database_manager import DatabaseManager
    from src.workflow.engine import WorkflowEngine

    # Also patch the imported DB_PATH in database_manager module
    # (it uses 'from src.config import DB_PATH' which creates a local binding)
    monkeypatch.setattr(database_manager, "DB_PATH", db_path)

    # Reset singletons para usar nueva DB
    DatabaseManager._instance = None
    WorkflowEngine._reset()
    from src.orbital.context import OrbitalContext

    OrbitalContext._reset()
    dm = DatabaseManager()
    yield dm
    dm.close_all()
    DatabaseManager._instance = None
    WorkflowEngine._reset()
    OrbitalContext._reset()


@pytest.fixture
def sample_workflow():
    """Retorna una definición de workflow de prueba."""
    return {
        "name": "Test Workflow",
        "description": "Workflow de prueba para tests",
        "trigger_type": "event",
        "trigger_config": {"event": "test.trigger"},
        "steps": [
            {
                "id": 1,
                "tool": "crm",
                "action": "create_lead",
                "params": {"name": "$input.nombre", "email": "$input.email"},
            },
            {
                "id": 2,
                "tool": "notification",
                "action": "send_email",
                "params": {"to": "$input.email", "subject": "Test", "body": "Hola"},
            },
        ],
    }


@pytest.fixture
def sample_context():
    """Retorna un contexto de ejecución de prueba."""
    return {
        "input": {"nombre": "Juan", "email": "juan@test.com"},
        "output": {},
        "settings": {"admin_email": "admin@test.com"},
    }


@pytest.fixture
def crm_service(db_manager):
    """Provee un CRMService con base de datos temporal."""
    from src.tools.crm.service import CRMService

    return CRMService()


@pytest.fixture
def invoice_service(db_manager):
    """Provee un InvoiceService con base de datos temporal."""
    from src.tools.invoice.service import InvoiceService

    return InvoiceService()


@pytest.fixture
def inventory_service(db_manager):
    """Provee un InventoryService con base de datos temporal."""
    from src.tools.inventory.service import InventoryService

    return InventoryService()


@pytest.fixture
def notification_service(db_manager):
    """Provee un NotificationService con base de datos temporal."""
    from src.tools.notification.service import NotificationService

    return NotificationService()


@pytest.fixture(autouse=True)
def _ensure_test_license_keys(monkeypatch, db_path):
    """Genera claves Ed25519 para tests en el directorio temporal de la BD.

    Parchea las rutas de keys.py (ya vinculadas a nivel de módulo)
    para que apunten al directorio temporal de la BD de test.
    """

    from src.license import keys as license_keys

    # Parchear las constantes de keys.py (ya vinculadas a nivel de módulo)
    test_keys_dir = db_path.parent / "license_keys"
    test_keys_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(license_keys, "KEYS_DIR", test_keys_dir)
    monkeypatch.setattr(license_keys, "PRIVATE_KEY_FILE", test_keys_dir / "private_key.enc")
    monkeypatch.setattr(license_keys, "PUBLIC_KEY_FILE", test_keys_dir / "public_key.pem")
    monkeypatch.setattr(license_keys, "SALT_FILE", test_keys_dir / "key_salt.bin")
    monkeypatch.setattr(license_keys, "METADATA_FILE", test_keys_dir / "metadata.json")

    # Generar keys si no existen en el path de test
    if not (test_keys_dir / "private_key.enc").exists():
        try:
            license_keys.generate_keypair("test-admin-pw")
        except Exception as e:
            import warnings
            warnings.warn(f"No se pudieron generar keys Ed25519 para tests: {e}", stacklevel=2)


@pytest.fixture
def license_generator():
    """Provee un LicenseGenerator."""
    from src.license.generator import LicenseGenerator

    return LicenseGenerator()


@pytest.fixture
def license_validator(db_manager):
    """Provee un LicenseValidator con base de datos temporal."""
    from src.license.validator import LicenseValidator

    return LicenseValidator()


@pytest.fixture
def condition_evaluator():
    """Provee un ConditionEvaluator."""
    from src.workflow.condition_evaluator import ConditionEvaluator

    return ConditionEvaluator()


@pytest.fixture
def branch_handler():
    """Provee un BranchHandler."""
    from src.workflow.branch_handler import BranchHandler

    return BranchHandler()


@pytest.fixture
def loop_handler():
    """Provee un LoopHandler."""
    from src.workflow.loop_handler import LoopHandler

    return LoopHandler()


@pytest.fixture
def error_handler():
    """Provee un ErrorHandler."""
    from src.workflow.error_handler import ErrorHandler

    return ErrorHandler()
