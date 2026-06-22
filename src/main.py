"""
Workflow Determinista — Entry Point
Inicia el servidor web Flask y todos los workers en segundo plano.
"""

import contextlib
import os
import webbrowser

from src.core.config import WEB_HOST, WEB_PORT, WEBHOOK_PORT
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging

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
    from src.core.db.backup_engine import BackupEngine

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
    """Registra todas las herramientas de negocio en el WorkflowEngine.

    Usa ToolsRegistry (Nivel 5) como punto único de registro.
    Añadir tool nueva = 1 entrada en src/hat/level5_tools/registry.py
    """
    from src.hat.level5_tools.registry import get_tools_registry
    from src.workflow.engine import WorkflowEngine

    engine = WorkflowEngine()

    # ToolsRegistry.register_all() instancia las 19 tools automáticamente
    tools = get_tools_registry().register_all(event_bus=event_bus)

    # Registrar cada tool en el WorkflowEngine
    for name, tool_instance in tools.items():
        engine.register_tool(name, tool_instance)

    logger.info(f"Herramientas registradas: {list(engine._tools.keys())}")
    logger.info(f"Total tools: {len(tools)} (vía ToolsRegistry)")
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
    # Fix Sprint 2 bug #24: antes hardcodeaba admin/admin123 incluso en prod.
    # Ahora: en producción REQUIERE WFD_ADMIN_PASSWORD env var (≥12 chars);
    # en dev usa default con warning loud + force password change en primer login.
    try:
        existing_users = db.fetchall("SELECT COUNT(*) as count FROM users")
        if existing_users and existing_users[0]["count"] == 0:
            import hashlib
            import secrets as _secrets

            from src.core.config import PRODUCTION

            # En producción, REQUIRE env var WFD_ADMIN_PASSWORD (≥12 chars).
            # En dev, default con warning loud.
            admin_password = os.environ.get("WFD_ADMIN_PASSWORD", "")
            if PRODUCTION:
                if not admin_password:
                    logger.error(
                        "Seed: WFD_ADMIN_PASSWORD env var OBLIGATORIA en producción "
                        "(≥12 caracteres). Abortando arranque por seguridad."
                    )
                    raise RuntimeError(
                        "WFD_ADMIN_PASSWORD env var required in production (min 12 chars)"
                    )
                if len(admin_password) < 12:
                    logger.error(
                        "Seed: WFD_ADMIN_PASSWORD debe tener ≥12 caracteres en producción."
                    )
                    raise RuntimeError(
                        "WFD_ADMIN_PASSWORD must be at least 12 characters in production"
                    )
            else:
                if not admin_password:
                    admin_password = "admin123"
                    logger.warning(
                        "⚠️  Seed: usando password admin por defecto 'admin123' (modo dev). "
                        "Setea WFD_ADMIN_PASSWORD para override. "
                        "NUNCA usar este default en producción."
                    )

            _pbkdf2_iterations = 600000
            salt = _secrets.token_hex(16)
            hashed = hashlib.pbkdf2_hmac(
                "sha256", admin_password.encode(), salt.encode(), iterations=_pbkdf2_iterations
            ).hex()
            stored_hash = f"pbkdf2:sha256:{_pbkdf2_iterations}:{salt}:{hashed}"

            legacy_hash = db.get_setting("admin_password_hash")
            if not legacy_hash:
                db.set_setting("admin_password_hash", stored_hash)

            try:
                db.create_user(
                    username="admin",
                    password=admin_password,
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

            # No loggear el password en claro (fix BUG-LOG-01 previo).
            logger.info("Seed: usuario admin creado (username: admin)")
            if not PRODUCTION:
                logger.info("⚠️  CAMBIA LA CONTRASEÑA en Settings > Cambiar contraseña después del primer ingreso.")
    except RuntimeError:
        # Re-raise production errors (WFD_ADMIN_PASSWORD missing)
        raise
    except Exception as seed_err:
        logger.warning(f"Seed: no se pudo crear usuario por defecto ({seed_err}). Puedes crear uno manualmente.")

    # 2. Registrar herramientas de negocio (con event_bus inyectado)
    register_tools(event_bus)

    # 2a. Seed: crear datos de demostración si la DB está vacía
    try:
        existing_leads = db.fetchall("SELECT COUNT(*) as count FROM leads")
        if existing_leads and existing_leads[0]["count"] == 0:
            demo_leads = [
                ("Juan Pérez", "juan.perez@email.com", "555-0101", "TechCorp", "new"),
                ("María García", "maria.garcia@email.com", "555-0102", "InnovateLLC", "contacted"),
                ("Carlos López", "carlos.lopez@email.com", "555-0103", "BuildInc", "qualified"),
                ("Ana Martínez", "ana.martinez@email.com", "555-0104", "DataSoft", "new"),
                ("Pedro Sánchez", "pedro.sanchez@email.com", "555-0105", "CloudOps", "contacted"),
            ]
            for name, email, phone, company, stage in demo_leads:
                db.execute(
                    "INSERT INTO leads (name, email, phone, company, stage, source, user_id) "
                    "VALUES (?, ?, ?, ?, ?, 'manual', 1)",
                    (name, email, phone, company, stage),
                )
            db.commit()
            logger.info(f"Seed: {len(demo_leads)} leads de demostración creados")

            # Demo products
            demo_products = [
                ("W001", "Widget Premium", "Widget de alta calidad", "General", 50, 10, 29.99),
                ("G001", "Gadget Pro", "Gadget profesional", "Electrónica", 25, 5, 49.99),
                ("T001", "ToolKit Basic", "Kit de herramientas básico", "Herramientas", 100, 20, 99.99),
            ]
            for sku, name, desc, cat, stock, min_stock, price in demo_products:
                db.execute(
                    "INSERT INTO products (sku, name, description, category, stock, min_stock, price, user_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (sku, name, desc, cat, stock, min_stock, price),
                )
            db.commit()
            logger.info(f"Seed: {len(demo_products)} productos de demostración creados")
    except Exception as seed_data_err:
        logger.warning(f"Seed datos demo: {seed_data_err}")

    # 2b. Inicializar HAT (5 niveles de orquestación con ORBITAL como cerebro central)
    # get_hat_router() inicializa: Tools → Workers → Specialists → Supervisors → HATRouter
    # Y guarda el singleton en _cached_router para que Flask y FastAPI lo reutilicen.
    # ORBITAL ejecuta el ciclo completo (OVC→TOR→RCC→COD→Espectro→Retro) por cada request.
    try:
        from src.hat import get_hat_router
        _hat_router = get_hat_router(event_bus=event_bus)
        logger.info(
            "HAT inicializado: 1 HATRouter + 3 Supervisores + 9 Specialists "
            "+ ~59 Workers + 80 Tools (19 nativas + 61 conectores)"
        )
        logger.info("ORBITAL: cerebro central activo (OVC→TOR→RCC→COD→Espectro→Retro)")
    except Exception as hat_err:
        logger.warning(
            "HAT no se pudo inicializar (%s). "
            "El sistema funcionará con WorkflowEngine legacy. "
            "HAT se activará cuando se resuelva el error.",
            hat_err,
        )

    # 3. Iniciar workers con dependencias inyectadas
    workers = start_workers(event_bus, event_queue, workflow_subscriber)

    # 3b. Foso 3: PYME orchestrator subscribers
    try:
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import register_subscribers
        register_subscribers(event_bus)
        logger.info("PYME orchestrator subscribers registrados")
    except Exception as e:
        logger.warning(f"No se pudieron registrar subscribers PYME: {e}")

    # 4. Crear y ejecutar app Flask
    app = create_web_app()

    # 5. Abrir navegador
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    with contextlib.suppress(OSError):
        webbrowser.open(url)

    logger.info(f"Servidor iniciado en {url}")
    logger.info("Presiona Ctrl+C para detener el sistema")

    # M10.2: Lanzar FastAPI v2 en un hilo en background (port 8000).
    # Flask sigue en el hilo principal (port 8080). Ambos comparten el mismo
    # proceso Python (sqlite_manager es thread-safe; los workers ya corren
    # en hilos propios). Si uvicorn no está instalado, se loggea warning y
    # el sistema sigue funcionando solo con Flask.
    import threading

    def run_fastapi():
        """Run FastAPI v2 in background thread.

        Imports are lazy: uvicorn y api_v2.app pueden no estar instalados
        en entornos mínimos (CI, dev sin extras). En ese caso, se loggea
        un warning y el sistema sigue operativo con Flask solamente.
        """
        try:
            import uvicorn

            from src.api_v2.app import app as fastapi_app

            uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
        except ImportError:
            logger.warning(
                "uvicorn no instalado — FastAPI v2 no iniciado. "
                "Instalar con: pip install uvicorn fastapi"
            )
        except Exception as exc:
            logger.error("FastAPI v2 no pudo iniciar: %s", exc)

    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True, name="fastapi-v2")
    fastapi_thread.start()
    logger.info("FastAPI v2 iniciado en puerto 8000 (background thread)")

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
