"""
Workflow Determinista — Test Fixtures Compartidas
Fixtures de pytest compartidas por todos los tests.
"""
import sys
import pytest
from pathlib import Path

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
    from src.events.bus import EventBus
    from src.workflow.engine import WorkflowEngine

    # Also patch the imported DB_PATH in database_manager module
    # (it uses 'from src.config import DB_PATH' which creates a local binding)
    monkeypatch.setattr(database_manager, "DB_PATH", db_path)

    # Reset singletons para usar nueva DB
    EventBus._instance = None
    DatabaseManager._instance = None
    WorkflowEngine._reset()
    from src.orbital.context import OrbitalContext
    OrbitalContext._reset()
    dm = DatabaseManager()
    yield dm
    dm.close_all()
    DatabaseManager._instance = None
    EventBus._instance = None
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
            {"id": 1, "tool": "crm", "action": "create_lead",
             "params": {"name": "$input.nombre", "email": "$input.email"}},
            {"id": 2, "tool": "notification", "action": "send_email",
             "params": {"to": "$input.email", "subject": "Test", "body": "Hola"}},
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
