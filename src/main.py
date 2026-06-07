"""
Workflow Determinista — Entry Point
Inicia el servidor web Flask y todos los workers en segundo plano.
"""
import sys
import threading
import webbrowser

from src.config import WEB_HOST, WEB_PORT, WEBHOOK_PORT
from src.utils.logger import setup_logging
from src.data.database_manager import DatabaseManager

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

    # EventBus — reprocesar eventos pendientes
    from src.events.bus import EventBus
    eb = EventBus()
    reprocessed = eb.reprocess_pending()
    if reprocessed > 0:
        logger.info(f"{reprocessed} eventos pendientes reprocesados")

    # Emitir evento de inicio
    eb.publish("system.started", {"timestamp": __import__("datetime").datetime.now().isoformat()})

    logger.info(f"Workers iniciados: {[w[0] for w in workers]}")
    return workers


def register_tools():
    """Registra todas las herramientas de negocio en el WorkflowEngine."""
    from src.workflow.engine import WorkflowEngine
    from src.tools.crm.service import CRMService
    from src.tools.invoice.service import InvoiceService
    from src.tools.inventory.service import InventoryService
    from src.tools.notification.service import NotificationService
    from src.tools.autopilot.service import AutoPilotService
    from src.tools.logic_gate.service import LogicGateService

    engine = WorkflowEngine()

    # Registrar cada tool con su servicio
    engine.register_tool("crm", CRMService())
    engine.register_tool("invoice", InvoiceService())
    engine.register_tool("inventory", InventoryService())
    engine.register_tool("notification", NotificationService())
    engine.register_tool("autopilot", AutoPilotService())
    engine.register_tool("logic_gate", LogicGateService())

    logger.info(f"Herramientas registradas: {list(engine._tools.keys())}")
    return engine


def create_web_app():
    """Crea y configura la aplicación Flask."""
    from src.web.app import create_app
    return create_app()


def main():
    """Punto de entrada principal."""
    import time
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
    try:
        webbrowser.open(url)
    except Exception:
        pass

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
