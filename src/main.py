"""
Workflow Determinista — Entry Point
Inicia el servidor web Flask y todos los workers en segundo plano.
"""

import contextlib
import webbrowser
from datetime import datetime

from src.config import WEB_HOST, WEB_PORT, WEBHOOK_PORT
from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


def start_workers():
    """Inicia todos los workers en segundo plano."""
    workers = []

    # ScheduleWorker
    from src.events.schedule_worker import ScheduleWorker

    sw = ScheduleWorker()
    sw.start()
    workers.append(("ScheduleWorker", sw))

    # WebhookServer
    from src.events.webhook_server import WebhookServer

    ws = WebhookServer()
    ws.start(WEBHOOK_PORT)
    workers.append(("WebhookServer", ws))

    # BackupEngine
    from src.data.backup_engine import BackupEngine

    be = BackupEngine()
    be.start_auto_backup(interval_hours=24)
    workers.append(("BackupEngine", be))

    # DatabaseTrigger — instala triggers SQL para eventos de DB
    from src.events.db_trigger import DatabaseTrigger

    dt = DatabaseTrigger()
    dt.install_triggers()
    logger.info("DatabaseTrigger: triggers SQL instalados")

    # EmailWatcher — monitoreo IMAP (solo si configurado)
    from src.events.email_watcher import EmailWatcher

    ew = EmailWatcher(callback=lambda event_type, data: eb.publish(event_type, data))
    ew.start()
    workers.append(("EmailWatcher", ew))

    # FileWatcher — monitoreo de archivos (solo si se configuran directorios)
    from src.events.file_watcher import FileWatcher

    fw = FileWatcher(callback=lambda event_type, data: eb.publish(event_type, data), interval=10.0)
    fw.start()
    workers.append(("FileWatcher", fw))

    # EventBus — reprocesar eventos pendientes
    from src.events.bus import EventBus

    eb = EventBus()
    reprocessed = eb.reprocess_pending()
    if reprocessed > 0:
        logger.info(f"{reprocessed} eventos pendientes reprocesados")

    # WorkerManager (Sprint 7-8): workers de cola de ejecución
    from src.events.worker_manager import WorkerManager

    wm = WorkerManager(num_workers=4)
    wm.start()
    workers.append(("WorkerManager", wm))

    logger.info(f"WorkerManager: {4} workers de cola iniciados")

    # Emitir evento de inicio
    eb.publish("system.started", {"timestamp": datetime.now().isoformat()})

    logger.info(f"Workers iniciados: {[w[0] for w in workers]}")
    return workers


def register_tools():
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

    # Registrar cada tool con su servicio
    engine.register_tool("crm", CRMService())
    engine.register_tool("invoice", InvoiceService())
    engine.register_tool("inventory", InventoryService())
    engine.register_tool("notification", NotificationService())
    engine.register_tool("autopilot", AutoPilotService())
    engine.register_tool("logic_gate", LogicGateService())
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
    """Punto de entrada principal."""
    logger.info("=" * 50)
    logger.info("Workflow Determinista — Iniciando...")
    logger.info("=" * 50)

    # 1. Inicializar base de datos
    db = DatabaseManager()
    logger.info(f"Base de datos: {db._db_path}")

    # 2. Registrar herramientas de negocio
    register_tools()

    # 3. Iniciar workers
    workers = start_workers()

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
        # Detener workers
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
