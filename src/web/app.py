"""
Workflow Determinista — Web App (Flask)
Servidor web con todas las rutas de la API REST.
"""
import html as _html
import re as _re
import urllib.parse as _urlparse
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for,
)

from src.config import (
    SESSION_SECRET, SESSION_EXPIRY_HOURS,
    LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MINUTES,
    FREE_TIER_MAX_WORKFLOWS, FREE_TIER_ALLOWED_TOOLS,
    SESSION_COOKIE_SECURE,
)
from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging
from src.license.validator import LicenseValidator
from src.workflow.repository import WorkflowRepository, WorkflowDefinition
from src.events.bus import EventBus

logger = setup_logging(__name__)

# ── Helpers ────────────────────────────────────────────────

db = DatabaseManager()
repo = WorkflowRepository()
event_bus = EventBus()

# Rate limiting state
_login_attempts: dict[str, list[float]] = {}


def _sanitize(s: str) -> str:
    """Limpia inputs de texto contra XSS.

    Preserva texto plano, elimina tags HTML, entidades codificadas,
    y URI schemes maliciosos (javascript:, data:, vbscript:).
    """
    # 1. Decodificar URL encoding (%3C → <)
    unquoted = _urlparse.unquote(s)
    # 2. Unescape entidades HTML (&lt; → <)
    unescaped = _html.unescape(unquoted)
    # 3. Eliminar tags HTML completos
    cleaned = _re.sub(r"<[^>]*>", "", unescaped)
    # 4. Eliminar tags sin cerrar al final del string
    cleaned = _re.sub(r"<[^>]+$", "", cleaned)
    # 4. Eliminar URI schemes maliciosos
    cleaned = _re.sub(r"(javascript|vbscript|data):", "", cleaned, flags=_re.IGNORECASE)
    return cleaned.strip()


def _check_rate_limit(ip: str) -> bool:
    """Verifica rate limiting: 10 intentos cada 15 minutos por IP."""
    import time
    now = time.time()
    window = LOGIN_WINDOW_MINUTES * 60
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]
    if len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS:
        return False
    _login_attempts[ip].append(now)
    return True


def login_required(f):
    """Decorador: requiere sesión iniciada."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def check_trial():
    """Verifica si el trial ha expirado."""
    validator = LicenseValidator()
    status = validator.get_trial_status()
    return status["status"] == "expired" and status.get("is_trial", False)


def check_free_tier():
    """Decorador: verifica límites del Free Tier antes de crear workflows.

    Si la licencia es trial o free, impone:
    - Máximo FREE_TIER_MAX_WORKFLOWS workflows
    - Solo herramientas en FREE_TIER_ALLOWED_TOOLS en los pasos del workflow
    Retorna 403 con mensaje descriptivo si se viola algún límite.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            validator = LicenseValidator()
            license_info = validator.get_license_info()
            is_restricted = license_info.get("is_trial", False) or license_info.get("type") == "free"

            if is_restricted:
                # ── Límite de workflows ─────────────────────────
                current_count = len(repo.list_all())
                if current_count >= FREE_TIER_MAX_WORKFLOWS:
                    return jsonify({
                        "error": "Free tier limitado a 3 workflows. "
                                 "Activa tu licencia para workflows ilimitados."
                    }), 403

                # ── Solo herramientas permitidas ─────────────────
                data = request.get_json() or {}
                steps = data.get("steps", [])
                for step in steps:
                    tool = step.get("tool", "")
                    if tool and tool not in FREE_TIER_ALLOWED_TOOLS:
                        return jsonify({
                            "error": "Free tier solo permite CRM. "
                                     "Activa tu licencia para usar todas las herramientas."
                        }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def create_app() -> Flask:
    """Crea y configura la aplicación Flask."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = SESSION_SECRET
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = SESSION_EXPIRY_HOURS * 3600

    def require_role(role: str):
        """Decorador: requiere un rol específico para acceder a la ruta."""
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if "user" not in session:
                    return jsonify({"error": "No autenticado"}), 401
                user_role = session.get("role", "")
                roles_hierarchy = {"admin": 3, "editor": 2, "viewer": 1}
                if roles_hierarchy.get(user_role, 0) < roles_hierarchy.get(role, 0):
                    return jsonify({"error": f"Se requiere rol '{role}'"}), 403
                return f(*args, **kwargs)
            return decorated
        return decorator

    # ── Rutas de páginas ──────────────────────────────────

    @app.route("/")
    @login_required
    def index():
        return redirect(url_for("dashboard_page"))

    @app.route("/login")
    def login_page():
        if "user" in session:
            return redirect(url_for("dashboard_page"))
        trial = LicenseValidator().get_trial_status()
        return render_template("login.html", trial=trial)

    @app.route("/dashboard")
    @login_required
    def dashboard_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("dashboard.html")

    @app.route("/chat")
    @login_required
    def chat_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("chat.html")

    @app.route("/editor")
    @login_required
    def editor_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("editor.html")

    @app.route("/workflows")
    @login_required
    def workflow_list_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("workflow_list.html")

    @app.route("/workflows/<int:workflow_id>")
    @login_required
    def workflow_detail_page(workflow_id):
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("workflow_detail.html", workflow_id=workflow_id)

    @app.route("/settings")
    @login_required
    def settings_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("settings.html")

    @app.route("/dead-letter")
    @login_required
    def dead_letter_page():
        if check_trial():
            return render_template("login.html", trial={"status": "expired"})
        return render_template("dead_letter.html")

    # ── API: Auth (multi-user) ──────────────────────────────

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        ip = request.remote_addr or "unknown"
        if not _check_rate_limit(ip):
            return jsonify({"error": "Demasiados intentos. Espera 15 minutos."}), 429
        data = request.get_json() or {}
        username = data.get("username", "")
        password = data.get("password", "")

        import bcrypt

        # Buscar usuario en tabla users
        user = db.get_user_by_username(username)
        if not user:
            # Fallback al admin_password_hash legacy
            stored_hash = db.get_setting("admin_password_hash")
            if stored_hash and isinstance(stored_hash, str):
                try:
                    if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                        session["user"] = username
                        session["user_id"] = 1
                        session["role"] = "admin"
                        session.permanent = True
                        db.audit("login.success", f"Login legacy: {username}", ip, 1)
                        return jsonify({"status": "ok", "user": username})
                except (ValueError, TypeError):
                    pass
            db.audit("login.failed", f"Intento fallido para {username}", ip)
            return jsonify({"error": "Credenciales inválidas"}), 401

        if not user.get("is_active", 1):
            return jsonify({"error": "Usuario desactivado"}), 403

        try:
            valid = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
        except (ValueError, TypeError):
            valid = False

        if not valid:
            db.audit("login.failed", f"Intento fallido para {username}", ip, user["id"])
            return jsonify({"error": "Credenciales inválidas"}), 401

        session["user"] = username
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session.permanent = True
        db.audit("login.success", f"Login exitoso: {username}", ip, user["id"])
        # Actualizar last_login
        db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        db.commit()
        return jsonify({"status": "ok", "user": username, "role": user["role"]})

    @app.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        session.pop("user", None)
        return jsonify({"status": "ok"})

    @app.route("/api/auth/status")
    def api_auth_status():
        return jsonify({"authenticated": "user" in session})

    # ── API: Dashboard ─────────────────────────────────────

    @app.route("/api/dashboard/stats")
    @login_required
    def api_dashboard_stats():
        stats = repo.get_stats()
        trial = LicenseValidator().get_trial_status()
        return jsonify({"stats": stats, "trial": trial})

    @app.route("/api/dashboard/timeline")
    @login_required
    def api_dashboard_timeline():
        """Retorna ejecuciones agrupadas por día para gráficos."""
        days = int(request.args.get("days", 14))
        raw = db.fetchall(
            """SELECT DATE(started_at) as day, status, COUNT(*) as count
               FROM workflow_executions
               WHERE started_at >= datetime('now', ? || ' days')
               GROUP BY day, status
               ORDER BY day ASC""",
            (f"-{days}",),
        )
        # Tools más usadas
        tools_raw = db.fetchall(
            """SELECT tool, COUNT(*) as count
               FROM workflow_step_logs
               GROUP BY tool
               ORDER BY count DESC LIMIT 10"""
        )
        # Tasa de éxito por día
        daily: dict[str, dict] = {}
        for r in raw:
            day = r["day"]
            if day not in daily:
                daily[day] = {"day": day, "completed": 0, "failed": 0, "total": 0}
            status = r["status"]
            count = r["count"]
            if status == "completed":
                daily[day]["completed"] += count
            elif status == "failed":
                daily[day]["failed"] += count
            daily[day]["total"] += count

        return jsonify({
            "daily": sorted(daily.values(), key=lambda x: x["day"]),
            "tools": tools_raw,
        })

    # ── API: Workflows ─────────────────────────────────────

    @app.route("/api/workflows", methods=["GET"])
    @login_required
    def api_list_workflows():
        status = request.args.get("status")
        workflows = repo.list_all(status)
        return jsonify([w.to_dict() for w in workflows])

    @app.route("/api/workflows", methods=["POST"])
    @login_required
    @require_role("editor")
    @check_free_tier()
    def api_create_workflow():
        data = request.get_json() or {}
        try:
            wf = WorkflowDefinition(
                name=_sanitize(data.get("name", "")),
                description=_sanitize(data.get("description", "")),
                trigger_type=data.get("trigger_type", "manual"),
                trigger_config=data.get("trigger_config", {}),
                steps=data.get("steps", []),
            )
            created = repo.create(wf, user_id=session.get("user_id"))

            # Suscribir a eventos según trigger_type
            if created.trigger_type == "event":
                event_config = created.trigger_config
                event_type = event_config.get("event", "")
                if event_type:
                    event_bus.subscribe(event_type, created.id)
            elif created.trigger_type == "webhook":
                # Los webhooks se suscriben automáticamente al evento webhook.received
                event_bus.subscribe("webhook.received", created.id)

            return jsonify(created.to_dict()), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/workflows/<int:wf_id>", methods=["GET"])
    @login_required
    def api_get_workflow(wf_id):
        wf = repo.get(wf_id)
        if not wf:
            return jsonify({"error": "Workflow no encontrado"}), 404
        return jsonify(wf.to_dict())

    @app.route("/api/workflows/<int:wf_id>", methods=["PUT"])
    @login_required
    @require_role("editor")
    def api_update_workflow(wf_id):
        data = request.get_json() or {}
        updated = repo.update(wf_id, data)
        if not updated:
            return jsonify({"error": "Workflow no encontrado"}), 404
        return jsonify(updated.to_dict())

    @app.route("/api/workflows/<int:wf_id>", methods=["DELETE"])
    @login_required
    @require_role("editor")
    def api_delete_workflow(wf_id):
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        engine.pause(wf_id)
        repo.delete(wf_id)
        return jsonify({"status": "deleted"})

    @app.route("/api/workflows/<int:wf_id>/activate", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_activate_workflow(wf_id):
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        result = engine.resume(wf_id)
        return jsonify({"status": "active" if result else "error"})

    @app.route("/api/workflows/<int:wf_id>/pause", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_pause_workflow(wf_id):
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        result = engine.pause(wf_id)
        return jsonify({"status": "paused" if result else "error"})

    @app.route("/api/workflows/<int:wf_id>/history", methods=["GET"])
    @login_required
    def api_workflow_history(wf_id):
        limit = int(request.args.get("limit", 50))
        executions = repo.list_executions(wf_id, limit)
        return jsonify([e.to_dict() for e in executions])

    @app.route("/api/workflows/<int:wf_id>/history/<int:exec_id>", methods=["GET"])
    @login_required
    def api_execution_detail(wf_id, exec_id):
        execution = repo.get_execution(exec_id)
        if not execution or execution.workflow_id != wf_id:
            return jsonify({"error": "Ejecución no encontrada"}), 404
        logs = repo.get_step_logs(exec_id)
        return jsonify({"execution": execution.to_dict(), "logs": logs})

    @app.route("/api/workflows/<int:wf_id>/export", methods=["GET"])
    @login_required
    def api_export_workflow(wf_id):
        exported = repo.export_workflow(wf_id)
        if not exported:
            return jsonify({"error": "Workflow no encontrado"}), 404
        return jsonify(exported)

    @app.route("/api/workflows/import", methods=["POST"])
    @login_required
    def api_import_workflow():
        data = request.get_json() or {}
        try:
            imported = repo.import_workflow(data)
            return jsonify(imported.to_dict()), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/workflows/<int:wf_id>/retry", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_retry_workflow(wf_id):
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        try:
            result = engine.execute(wf_id)
            return jsonify(result.to_dict())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # ── API: NLP Chat ───────────────────────────────────────

    @app.route("/api/nlu/understand", methods=["POST"])
    @login_required
    def api_nlu_understand():
        """Endpoint NLU completo: análisis + compilación + simulación."""
        data = request.get_json() or {}
        text = data.get("text", "")
        mode = data.get("mode", "compile")  # 'analyze' | 'compile' | 'simulate'
        lang = data.get("lang")
        context = data.get("context")

        if not text:
            return jsonify({"error": "text es requerido"}), 400

        from src.nlu.pipeline import Pipeline
        pipeline = Pipeline()

        if mode == "analyze":
            result = pipeline.process(text, lang)
            return jsonify({
                "status": "analyzed",
                "lang": result.lang,
                "confidence": result.confidence,
                "intents": [
                    {"intent": i.intent, "score": i.score, "evidence": i.evidence}
                    for i in result.intents[:5]
                ],
                "entities": [
                    {"type": e.type, "value": str(e.value), "raw": e.raw}
                    for e in result.entities
                ],
                "slots": [
                    {"name": s.name, "required": s.required, "filled": s.filled, "value": s.value}
                    for s in result.slots
                ],
                "trace": list(result.trace),
            })

        elif mode == "simulate":
            result = pipeline.simulate(text, lang, context)
            return jsonify({
                "status": "simulated",
                "workflow_name": result.workflow_name,
                "trigger_type": result.trigger_type,
                "total_steps": result.total_steps,
                "would_succeed": result.steps_that_would_succeed,
                "would_fail": result.steps_that_would_fail,
                "feasible": result.overall_feasible,
                "warnings": list(result.warnings),
                "summary": result.summary,
                "steps": [
                    {"id": s.step_id, "tool": s.tool, "action": s.action, "ok": s.would_succeed}
                    for s in result.steps
                ],
            })

        else:  # compile (default)
            result = pipeline.compile(text, lang)
            return jsonify({
                "status": result.status,
                "explanation": result.explanation,
                "workflow": result.workflow,
                "missing_slots": list(result.missing_slots),
            })

    @app.route("/api/workflows/chat", methods=["POST"])
    @login_required
    def api_chat():
        data = request.get_json() or {}
        text = data.get("text", "")

        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.templates import TEMPLATES

        classifier = IntentClassifier()
        intent_matches = classifier.classify_text(text)

        if not intent_matches:
            return jsonify({"suggestions": [], "message": "No entendí tu solicitud. Intenta describir qué quieres automatizar."})

        # Mantener compatibilidad con el formato de respuesta legacy
        suggestions = []
        for im in intent_matches[:5]:
            template = next(
                (t for t in TEMPLATES if t["name"] == im.intent),
                None,
            )
            if template:
                suggestions.append({
                    "template_name": im.intent,
                    "confidence": im.score,
                    "description": template.get("description_es", ""),
                    "trigger": template["trigger"],
                    "steps": template["steps"],
                    "score": im.score,
                    "evidence": im.evidence,
                })

        return jsonify({
            "suggestions": suggestions,
            "message": f"Encontré {len(suggestions)} sugerencias para tu solicitud.",
        })

    @app.route("/api/nlu/ai-generate", methods=["POST"])
    @login_required
    def api_nlu_ai_generate():
        """Genera un workflow usando IA a partir de texto libre.

        Modos:
        - ai: Genera workflow con LLM (requiere proveedor configurado)
        - hybrid: Intenta determinista primero, fallback a IA
        - deterministic: Solo usa el compilador determinista (sin IA)
        """
        data = request.get_json() or {}
        text = data.get("text", "")
        mode = data.get("mode", "hybrid")  # 'ai' | 'hybrid' | 'deterministic'
        lang = data.get("lang", "es")

        if not text:
            return jsonify({"error": "text es requerido"}), 400

        from src.nlu.pipeline import Pipeline
        from src.nlu.ai_config import get_ai_config

        pipeline = Pipeline()
        ai_config = get_ai_config()

        # ── Modo deterministic: solo compilador NLU ────────
        if mode == "deterministic":
            result = pipeline.compile(text, lang)
            return jsonify({
                "status": result.status,
                "source": "deterministic",
                "explanation": result.explanation,
                "workflow": result.workflow,
                "missing_slots": list(result.missing_slots),
                "ai_provider": "none",
            })

        # ── Modo ai: solo LLM (requiere proveedor) ───────
        if mode == "ai":
            if not ai_config.is_ai_available():
                return jsonify({
                    "error": "No hay proveedor de IA configurado. "
                             "Activa Ollama, OpenAI o Anthropic en Configuración.",
                    "status": "no_provider",
                    "available_providers": ai_config.get_status(),
                }), 400

            ai_result = pipeline.ai_generate(text, lang)
            return jsonify({
                "status": "ready" if ai_result.validated else "validation_error",
                "source": "ai",
                "explanation": ai_result.explanation,
                "workflow": ai_result.workflow,
                "ai_provider": ai_result.provider,
                "ai_model": ai_result.model,
                "validated": ai_result.validated,
                "validation_errors": ai_result.validation_errors,
            })

        # ── Modo hybrid: determinista primero, fallback IA ──
        # Paso 1: Intentar compilador determinista
        det_result = pipeline.compile(text, lang)
        if det_result.status == "ready" and det_result.workflow:
            return jsonify({
                "status": det_result.status,
                "source": "deterministic",
                "explanation": det_result.explanation,
                "workflow": det_result.workflow,
                "missing_slots": list(det_result.missing_slots),
                "ai_provider": "none",
            })

        # Paso 2: Si determinista falló e IA está disponible, intentar IA
        if ai_config.is_ai_available():
            ai_result = pipeline.ai_generate(text, lang)
            if ai_result.validated and ai_result.workflow:
                return jsonify({
                    "status": "ready",
                    "source": "ai_fallback",
                    "explanation": ai_result.explanation,
                    "workflow": ai_result.workflow,
                    "ai_provider": ai_result.provider,
                    "ai_model": ai_result.model,
                    "validated": True,
                })

        # Paso 3: Ambos fallaron — retornar el resultado determinista con el error
        return jsonify({
            "status": det_result.status,
            "source": "deterministic",
            "explanation": det_result.explanation or "No pude generar un workflow para tu solicitud.",
            "workflow": {},
            "missing_slots": list(det_result.missing_slots),
            "ai_provider": ai_config.active_provider.value if ai_config.is_ai_available() else "none",
        })

    # ── API: Tools ──────────────────────────────────────────

    @app.route("/api/tools/crm/leads", methods=["GET"])
    @login_required
    def api_list_leads():
        from src.tools.crm.service import CRMService
        crm = CRMService()
        stage = request.args.get("stage")
        leads = crm.list_leads(stage)
        return jsonify(leads)

    @app.route("/api/tools/crm/leads", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_create_lead():
        from src.tools.crm.service import CRMService
        crm = CRMService()
        data = request.get_json() or {}
        lead = crm.create_lead(
            name=data.get("name", ""),
            email=data.get("email"),
            phone=data.get("phone"),
            company=data.get("company"),
            source=data.get("source", "web_form"),
            notes=data.get("notes"),
            user_id=session.get("user_id"),
        )
        return jsonify(lead), 201

    @app.route("/api/tools/inventory/products", methods=["GET"])
    @login_required
    def api_list_products():
        from src.tools.inventory.service import InventoryService
        inv = InventoryService()
        low_stock = request.args.get("low_stock", "false").lower() == "true"
        products = inv.list_products(low_stock_only=low_stock)
        return jsonify(products)

    @app.route("/api/tools/inventory/products", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_create_product():
        """Crear un nuevo producto en inventario."""
        from src.tools.inventory.service import InventoryService
        inv = InventoryService()
        data = request.get_json() or {}
        product = inv.add_product(
            sku=data.get("sku", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", ""),
            stock=data.get("stock", 0),
            min_stock=data.get("min_stock", 10),
            price=data.get("price", 0.0),
            user_id=session.get("user_id"),
        )
        return jsonify(product), 201

    @app.route("/api/tools/inventory/stock-movement", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_stock_movement():
        """Registrar un movimiento de stock (entrada/salida/ajuste)."""
        from src.tools.inventory.service import InventoryService
        inv = InventoryService()
        data = request.get_json() or {}
        product_id = data.get("product_id")
        quantity = data.get("quantity", 0)
        movement_type = data.get("type", "adjustment")
        reason = data.get("reason", "")
        if not product_id:
            return jsonify({"error": "product_id es requerido"}), 400
        result = inv.update_stock(product_id, quantity, movement_type, reason)
        if not result:
            return jsonify({"error": "Producto no encontrado"}), 404
        return jsonify(result)

    @app.route("/api/tools/inventory/low-stock", methods=["GET"])
    @login_required
    def api_low_stock():
        from src.tools.inventory.service import InventoryService
        inv = InventoryService()
        return jsonify(inv.get_low_stock_products())

    @app.route("/api/tools/invoice/create", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_create_invoice():
        """Crear una nueva factura."""
        from src.tools.invoice.service import InvoiceService
        inv = InvoiceService()
        data = request.get_json() or {}
        client_name = data.get("client_name", "")
        if not client_name:
            return jsonify({"error": "client_name es requerido"}), 400
        invoice = inv.create_invoice(
            client_name=client_name,
            client_email=data.get("client_email"),
            items=data.get("items", []),
            tax_rate=data.get("tax_rate", 0.16),
            discount=data.get("discount", 0.0),
            due_days=data.get("due_days", 30),
            notes=data.get("notes"),
            user_id=session.get("user_id"),
        )
        return jsonify(invoice), 201

    @app.route("/api/tools/invoice/list", methods=["GET"])
    @login_required
    def api_list_invoices():
        from src.tools.invoice.service import InvoiceService
        inv = InvoiceService()
        status = request.args.get("status")
        invoices = inv.list_invoices(status)
        return jsonify(invoices)

    # ── API: Settings ───────────────────────────────────────

    @app.route("/api/settings", methods=["GET"])
    @login_required
    def api_get_settings():
        return jsonify({
            "smtp_server": db.get_setting("smtp_server", ""),
            "smtp_port": db.get_setting("smtp_port", "587"),
            "email_user": db.get_setting("email_user", ""),
            "webhook_api_key": db.get_setting("webhook_api_key", ""),
        })

    @app.route("/api/settings", methods=["PUT"])
    @login_required
    @require_role("admin")
    def api_update_settings():
        data = request.get_json() or {}
        for key in ["smtp_server", "smtp_port", "email_user", "email_password",
                     "webhook_api_key", "imap_server", "imap_port"]:
            if key in data:
                db.set_setting(key, str(data[key]))
        return jsonify({"status": "saved"})

    @app.route("/api/settings/change-password", methods=["POST"])
    @login_required
    def api_change_password():
        import bcrypt
        data = request.get_json() or {}
        current = data.get("current_password", "")
        new_pass = data.get("new_password", "")

        if len(new_pass) < 6:
            return jsonify({"error": "La nueva contraseña debe tener al menos 6 caracteres"}), 400

        user_id = session.get("user_id")
        if user_id:
            # Multi-user: actualizar contraseña del usuario logueado
            user = db.get_user(user_id)
            if user:
                user_full = db.get_user_by_username(user["username"])
                if user_full and user_full.get("password_hash"):
                    try:
                        stored = user_full["password_hash"]
                        if not bcrypt.checkpw(current.encode(), stored.encode()):
                            return jsonify({"error": "Contraseña actual incorrecta"}), 400
                    except (ValueError, TypeError):
                        return jsonify({"error": "Error verificando contraseña"}), 400
                    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt(rounds=12)).decode()
                    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
                    db.commit()
                    db.audit("password.changed", "Contraseña cambiada", request.remote_addr, user_id)
                    return jsonify({"status": "ok"})
            # Fallback: si no hay usuario en tabla, usa legacy

        # Fallback legacy: admin_password_hash
        stored_hash = db.get_setting("admin_password_hash")
        if stored_hash:
            if isinstance(stored_hash, str):
                try:
                    if not bcrypt.checkpw(current.encode(), stored_hash.encode()):
                        return jsonify({"error": "Contraseña actual incorrecta"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Error verificando contraseña"}), 400

        new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt(rounds=12)).decode()
        db.set_setting("admin_password_hash", new_hash)
        db.audit("password.changed", "Contraseña cambiada", request.remote_addr)
        return jsonify({"status": "ok"})

    @app.route("/api/settings/test-email", methods=["POST"])
    @login_required
    def api_test_email():
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        result = ns.test_connection()
        return jsonify(result)

    # ── API: License ────────────────────────────────────────

    @app.route("/api/license/validate", methods=["POST"])
    def api_validate_license():
        data = request.get_json() or {}
        key = data.get("key", "")
        validator = LicenseValidator()
        result = validator.validate(key)
        if result["valid"]:
            validator.activate_key(key, result.get("type", "individual"),
                                    result.get("client_name", ""))
        return jsonify(result)

    @app.route("/api/license/info")
    def api_license_info():
        """Retorna información completa de la licencia incluyendo límites del Free Tier."""
        validator = LicenseValidator()
        info = validator.get_license_info()
        # Enriquecer con datos del Free Tier para que el frontend los consuma
        info["is_free"] = info.get("type") == "free"
        info["max_workflows"] = FREE_TIER_MAX_WORKFLOWS if info.get("is_free") or info.get("is_trial") else -1
        info["allowed_tools"] = FREE_TIER_ALLOWED_TOOLS if info.get("is_free") or info.get("is_trial") else ["all"]
        return jsonify(info)

    # ── API: System ─────────────────────────────────────────

    @app.route("/api/system/backup", methods=["POST"])
    @login_required
    @require_role("admin")
    def api_system_backup():
        from src.data.backup_engine import BackupEngine
        be = BackupEngine()
        path = be.backup_now()
        return jsonify({"path": path, "status": "completed"})

    @app.route("/api/system/logs", methods=["GET"])
    @login_required
    def api_system_logs():
        """Retorna los últimos 100 registros del audit log."""
        limit = min(int(request.args.get("limit", 100)), 100)
        logs = db.fetchall(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return jsonify(logs)

    # ── API: Reports ─────────────────────────────────────────

    @app.route("/api/reports/workflows/<fmt>")
    @login_required
    def api_report_workflows(fmt):
        from src.web.reports import ReportGenerator
        gen = ReportGenerator()
        if fmt == "csv":
            content = gen.workflows_csv()
            mimetype = "text/csv"
        elif fmt == "pdf":
            content = gen.workflows_pdf()
            mimetype = "application/pdf"
        else:
            return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
        response = app.response_class(response=content, mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("workflows", fmt)}"'
        return response

    @app.route("/api/reports/crm/<fmt>")
    @login_required
    def api_report_crm(fmt):
        from src.web.reports import ReportGenerator
        gen = ReportGenerator()
        if fmt == "csv":
            content = gen.crm_leads_csv()
            mimetype = "text/csv"
        elif fmt == "pdf":
            content = gen.crm_leads_pdf()
            mimetype = "application/pdf"
        else:
            return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
        response = app.response_class(response=content, mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("crm_leads", fmt)}"'
        return response

    @app.route("/api/reports/inventory/<fmt>")
    @login_required
    def api_report_inventory(fmt):
        from src.web.reports import ReportGenerator
        gen = ReportGenerator()
        if fmt == "csv":
            content = gen.inventory_csv()
            mimetype = "text/csv"
        elif fmt == "pdf":
            content = gen.inventory_pdf()
            mimetype = "application/pdf"
        else:
            return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
        response = app.response_class(response=content, mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("inventory", fmt)}"'
        return response

    @app.route("/api/reports/invoices/<fmt>")
    @login_required
    def api_report_invoices(fmt):
        from src.web.reports import ReportGenerator
        gen = ReportGenerator()
        if fmt == "csv":
            content = gen.invoices_csv()
            mimetype = "text/csv"
        elif fmt == "pdf":
            content = gen.invoices_pdf()
            mimetype = "application/pdf"
        else:
            return jsonify({"error": "Formato no soportado. Usa csv o pdf."}), 400
        response = app.response_class(response=content, mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{gen.filename("invoices", fmt)}"'
        return response

    # ── API: Users Management (RBAC) ─────────────────────────

    @app.route("/api/users", methods=["GET"])
    @login_required
    @require_role("admin")
    def api_list_users():
        users = db.list_users()
        return jsonify(users)

    @app.route("/api/users", methods=["POST"])
    @login_required
    @require_role("admin")
    def api_create_user():
        data = request.get_json() or {}
        username = data.get("username", "")
        password = data.get("password", "")
        role = data.get("role", "editor")
        allowed_roles = {"admin", "editor", "viewer"}
        if role not in allowed_roles:
            return jsonify({"error": f"Rol inválido. Roles válidos: {', '.join(sorted(allowed_roles))}"}), 400
        if not username or len(username) < 3:
            return jsonify({"error": "Usuario debe tener al menos 3 caracteres"}), 400
        if len(password) < 6:
            return jsonify({"error": "Contraseña debe tener al menos 6 caracteres"}), 400
        existing = db.get_user_by_username(username)
        if existing:
            return jsonify({"error": "El usuario ya existe"}), 400
        user = db.create_user(
            username=username,
            password=password,
            role=role,
            display_name=data.get("display_name", ""),
            email=data.get("email", ""),
        )
        db.audit("user.created", f"Usuario creado: {username}", request.remote_addr, session.get("user_id"))
        return jsonify(user), 201

    @app.route("/api/users/<int:user_id>", methods=["PUT"])
    @login_required
    @require_role("admin")
    def api_update_user(user_id):
        data = request.get_json() or {}
        allowed = {"role", "display_name", "email", "is_active"}
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return jsonify({"error": "Sin campos válidos para actualizar"}), 400
        db.update_user(user_id, updates)
        db.audit("user.updated", f"Usuario {user_id} actualizado", request.remote_addr, session.get("user_id"))
        return jsonify({"status": "updated"})

    @app.route("/api/users/<int:user_id>", methods=["DELETE"])
    @login_required
    @require_role("admin")
    def api_delete_user(user_id):
        if user_id == session.get("user_id"):
            return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
        db.delete_user(user_id)
        db.audit("user.deleted", f"Usuario {user_id} desactivado", request.remote_addr, session.get("user_id"))
        return jsonify({"status": "deleted"})

    @app.route("/api/settings/whatsapp", methods=["GET"])
    @login_required
    def api_get_whatsapp():
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        return jsonify(ns.get_whatsapp_status())

    @app.route("/api/settings/whatsapp", methods=["PUT"])
    @login_required
    def api_update_whatsapp():
        data = request.get_json() or {}
        token = data.get("token", "")
        phone_number_id = data.get("phone_number_id", "")
        if not token or not phone_number_id:
            return jsonify({"error": "token y phone_number_id son requeridos"}), 400
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token, phone_number_id)
        return jsonify({"status": "saved"})

    @app.route("/api/settings/whatsapp/test", methods=["POST"])
    @login_required
    def api_test_whatsapp():
        data = request.get_json() or {}
        test_number = data.get("test_number", "")
        if not test_number:
            return jsonify({"error": "Número de prueba requerido"}), 400
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        result = ns.send_whatsapp(
            to=test_number,
            message="🧪 Conexión WhatsApp exitosa desde Workflow Determinista",
        )
        return jsonify(result)

    # ── API: Dead Letter Queue (Sprint 4) ─────────────────────

    @app.route("/api/dead-letter", methods=["GET"])
    @login_required
    def api_dead_letter_list():
        """Lista entradas de la Dead Letter Queue."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        status = request.args.get("status")
        workflow_id = request.args.get("workflow_id", type=int)
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        entries = dl.list(status=status, workflow_id=workflow_id,
                          limit=limit, offset=offset)
        return jsonify({
            "entries": [e.to_dict() for e in entries],
            "stats": dl.get_stats(),
        })

    @app.route("/api/dead-letter/stats", methods=["GET"])
    @login_required
    def api_dead_letter_stats():
        """Estadísticas de la Dead Letter Queue."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        return jsonify(dl.get_stats())

    @app.route("/api/dead-letter/<int:entry_id>/retry", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_dead_letter_retry(entry_id):
        """Reintenta una entrada de dead letter."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        result = dl.retry(entry_id)
        return jsonify(result)

    @app.route("/api/dead-letter/<int:entry_id>/discard", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_dead_letter_discard(entry_id):
        """Descarta una entrada de dead letter."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        success = dl.discard(entry_id)
        return jsonify({"status": "discarded" if success else "not_found"})

    @app.route("/api/dead-letter/retry-all", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_dead_letter_retry_all():
        """Reintenta todas las entradas pendientes."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        results = dl.retry_all()
        return jsonify(results)

    @app.route("/api/dead-letter/discard-all", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_dead_letter_discard_all():
        """Descarta todas las entradas pendientes."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        count = dl.discard_all()
        return jsonify({"discarded": count})

    @app.route("/api/dead-letter/notify/<int:entry_id>", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_dead_letter_notify(entry_id):
        """Dispara notificación para una entrada."""
        from src.workflow.dead_letter import DeadLetterManager
        dl = DeadLetterManager()
        result = dl.notify_dead_letter(entry_id)
        return jsonify({"notified": result})

    # ── API: Work Queue + Workers (Sprint 7-8) ──────────────────

    @app.route("/api/queue/status")
    @login_required
    def api_queue_status():
        """Estado de la cola de ejecución."""
        from src.events.work_queue import WorkQueue
        queue = WorkQueue()
        metrics = queue.get_metrics()
        peek = queue.peek(limit=10)
        return jsonify({
            "metrics": metrics,
            "next_items": [item.to_dict() for item in peek],
        })

    @app.route("/api/queue/workers")
    @login_required
    def api_queue_workers():
        """Estado de los workers activos."""
        from src.events.worker_manager import WorkerManager
        mgr = WorkerManager()
        return jsonify(mgr.get_metrics())

    @app.route("/api/queue/enqueue", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_queue_enqueue():
        """Encola un workflow manualmente."""
        data = request.get_json() or {}
        workflow_id = data.get("workflow_id")
        if not workflow_id:
            return jsonify({"error": "workflow_id es requerido"}), 400
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        try:
            result = engine.execute_async(
                workflow_id=workflow_id,
                trigger_data=data.get("trigger_data"),
                priority=data.get("priority", 0),
            )
            return jsonify(result), 202
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/queue/<int:item_id>/retry", methods=["POST"])
    @login_required
    @require_role("editor")
    def api_queue_retry(item_id):
        """Re-intenta un item fallido."""
        from src.events.work_queue import WorkQueue
        queue = WorkQueue()
        result = queue.retry_failed(max_items=1)
        return jsonify({"retried": result})

    @app.route("/api/queue/cleanup", methods=["POST"])
    @login_required
    @require_role("admin")
    def api_queue_cleanup():
        """Limpia items completados/failed viejos."""
        data = request.get_json() or {}
        max_age = int(data.get("max_age_hours", 24))
        from src.events.work_queue import WorkQueue
        queue = WorkQueue()
        deleted = queue.cleanup(max_age_hours=max_age)
        return jsonify({"deleted": deleted})

    @app.route("/api/system/status")
    def api_system_status():
        return jsonify({
            "version": "1.0.0",
            "status": "running",
            "db_path": str(db._db_path),
        })

    return app
