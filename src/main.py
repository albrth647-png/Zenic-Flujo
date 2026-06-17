"""
Workflow Determinista — Entry Point
Inicia el servidor web Flask y todos los workers en segundo plano.
"""

import contextlib
import webbrowser

from src.config import WEB_HOST, WEB_PORT, WEBHOOK_PORT
from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


def start_workers(event_bus, event_queue, workflow_subscriber):
    """Inicia todos los workers en segundo plano con dependencias inyectadas."""
    workers = []

    # ScheduleWorker
    from src.events.schedule_worker import ScheduleWorker

    sw = ScheduleWorker(event_bus=event_bus)
    sw.start()
    workers.append(("ScheduleWorker", sw))

    # WebhookServer
    from src.events.webhook_server import WebhookServer

    ws = WebhookServer(event_bus=event_bus, workflow_subscriber=workflow_subscriber)
    ws.start(WEBHOOK_PORT)
    workers.append(("WebhookServer", ws))

    # BackupEngine
    from src.data.backup_engine import BackupEngine

    be = BackupEngine()
    be.start_auto_backup(interval_hours=24)
    workers.append(("BackupEngine", be))

    # DatabaseTrigger — instala triggers SQL para eventos de DB
    from src.events.db_trigger import DatabaseTrigger

    dt = DatabaseTrigger(event_bus=event_bus)
    dt.install_triggers()
    logger.info("DatabaseTrigger: triggers SQL instalados")

    # EmailWatcher — monitoreo IMAP (solo si configurado)
    from src.events.email_watcher import EmailWatcher

    ew = EmailWatcher(callback=lambda event_type, data: event_bus.publish(event_type, data))
    ew.start()
    workers.append(("EmailWatcher", ew))

    # FileWatcher — monitoreo de archivos (solo si se configuran directorios)
    from src.events.file_watcher import FileWatcher

    fw = FileWatcher(callback=lambda event_type, data: event_bus.publish(event_type, data), interval=10.0)
    fw.start()
    workers.append(("FileWatcher", fw))

    # WorkerManager (Sprint 7-8): workers de cola de ejecución
    from src.events.worker_manager import WorkerManager

    wm = WorkerManager(num_workers=4)
    wm.start()
    workers.append(("WorkerManager", wm))

    logger.info(f"Workers iniciados: {[w[0] for w in workers]}")
    return workers


def register_tools(event_bus):
    """Registra todas las herramientas de negocio en el WorkflowEngine."""
    from src.tools.api_connector.service import APIConnectorService
    from src.tools.autopilot.service import AutoPilotService
    from src.tools.code_runner.service import CodeRunnerTool
    from src.tools.crm.service import CRMService
    from src.tools.data_keeper.service import DataKeeperService
    from src.tools.integrations.drive_service import DriveService
    from src.tools.integrations.gmail_service import GmailService
    from src.tools.integrations.mercadopago_service import MercadoPagoService
    from src.tools.integrations.ollama_service import OllamaService
    from src.tools.integrations.openai_service import OpenAIService
    from src.tools.integrations.postgresql_service import PostgreSQLService
    from src.tools.integrations.sheets_service import SheetsService
    from src.tools.integrations.slack_service import SlackService
    from src.tools.integrations.stripe_service import StripeService
    from src.tools.integrations.telegram_service import TelegramService
    from src.tools.inventory.service import InventoryService
    from src.tools.invoice.service import InvoiceService
    from src.tools.logic_gate.service import LogicGateService
    from src.tools.notification.service import NotificationService
    from src.workflow.engine import WorkflowEngine

    engine = WorkflowEngine()

    # Registrar cada tool con su servicio (inyectar event_bus)
    engine.register_tool("crm", CRMService(event_bus=event_bus))
    engine.register_tool("invoice", InvoiceService(event_bus=event_bus))
    engine.register_tool("inventory", InventoryService(event_bus=event_bus))
    engine.register_tool("notification", NotificationService())
    engine.register_tool("autopilot", AutoPilotService())
    engine.register_tool("logic_gate", LogicGateService(event_bus=event_bus))
    engine.register_tool("api_connector", APIConnectorService())
    engine.register_tool("data_keeper", DataKeeperService())
    engine.register_tool("code_runner", CodeRunnerTool())

    # Integraciones (se activan cuando el usuario configura credenciales)
    engine.register_tool("gmail", GmailService())
    engine.register_tool("sheets", SheetsService())
    engine.register_tool("telegram", TelegramService())
    engine.register_tool("slack", SlackService())
    # Sprint 6: Nuevos conectores
    engine.register_tool("openai", OpenAIService())
    engine.register_tool("ollama", OllamaService())
    engine.register_tool("postgresql", PostgreSQLService())
    engine.register_tool("drive", DriveService())
    engine.register_tool("stripe", StripeService())
    engine.register_tool("mercadopago", MercadoPagoService())

    logger.info(f"Herramientas registradas: {list(engine._tools.keys())}")
    return engine


def create_web_app():
    """Crea y configura la aplicación Flask."""
    from src.web.app import create_app

    return create_app()


def main():
    """Punto de entrada principal con inyección de dependencias."""
    logger.info("=" * 50)
    logger.info("Workflow Determinista — Iniciando...")
    logger.info("=" * 50)

    # 0. Crear dependencias compartidas
    from src.events.bus import EventBus
    from src.events.queue_service import EventQueueService
    from src.events.workflow_subscriber import WorkflowSubscriber
    from src.workflow.engine import WorkflowEngine

    event_bus = EventBus()
    event_queue = EventQueueService()
    workflow_engine = WorkflowEngine()
    workflow_subscriber = WorkflowSubscriber(event_bus, event_queue, workflow_engine)
    # Registrar suscripciones DB existentes en EventBus
    workflow_subscriber.register_all_db_subscriptions()

    # Inicializar web helpers con event_bus y subscriber inyectados
    from src.web import helpers as web_helpers
    web_helpers.init(event_bus_instance=event_bus, subscriber=workflow_subscriber)

    # 1. Inicializar base de datos
    db = DatabaseManager()
    logger.info(f"Base de datos: {db._db_path}")

    # 1b. Seed: crear usuario admin por defecto si no existe ningún usuario
    try:
        existing_users = db.fetchall("SELECT COUNT(*) as count FROM users")
        if existing_users and existing_users[0]["count"] == 0:
            import hashlib
            import secrets
            default_password = "admin123"
            _pbkdf2_iterations = 600000
            salt = secrets.token_hex(16)
            hashed = hashlib.pbkdf2_hmac("sha256", default_password.encode(), salt.encode(), iterations=_pbkdf2_iterations).hex()
            stored_hash = f"pbkdf2:sha256:{_pbkdf2_iterations}:{salt}:{hashed}"

            legacy_hash = db.get_setting("admin_password_hash")
            if not legacy_hash:
                db.set_setting("admin_password_hash", stored_hash)

            try:
                db.create_user(
                    username="admin",
                    password="admin123",
                    role="admin",
                    display_name="Administrador",
                    email="admin@localhost",
                )
            except Exception as create_err:
                logger.warning(f"Seed: create_user con bcrypt falló ({create_err}), insert manual")
                db.execute(
                    "INSERT INTO users (username, password_hash, role, display_name, email) VALUES (?, ?, ?, ?, ?)",
                    ("admin", stored_hash, "admin", "Administrador", "admin@localhost"),
                )
                db.commit()

            logger.info("Seed: usuario admin creado (username: admin / password: admin123)")
            logger.info("⚠️  CAMBIA LA CONTRASEÑA en Settings > Cambiar contraseña después del primer ingreso.")
    except Exception as seed_err:
        logger.warning(f"Seed: no se pudo crear usuario por defecto ({seed_err}). Puedes crear uno manualmente.")

    # 2. Registrar herramientas de negocio (con event_bus inyectado)
    register_tools(event_bus)

    # 3. Iniciar workers con dependencias inyectadas
    workers = start_workers(event_bus, event_queue, workflow_subscriber)

    # 4. Crear y ejecutar app Flask
    app = create_web_app()

    # 5. Abrir navegador
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    with contextlib.suppress(OSError):
        webbrowser.open(url)

    logger.info(f"Servidor iniciado en {url}")
    logger.info("Presiona Ctrl+C para detener el sistema")

    # 6. Iniciar servidor Flask
    try:
        app.run(
            host=WEB_HOST,
            port=WEB_PORT,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        logger.info("Deteniendo el sistema...")
    finally:
        for name, worker in workers:
            if hasattr(worker, "stop"):
                try:
                    worker.stop()
                    logger.info(f"{name} detenido")
                except Exception as e:
                    logger.warning(f"Error deteniendo {name}: {e}")
        logger.info("Sistema detenido")


if __name__ == "__main__":
    main()
