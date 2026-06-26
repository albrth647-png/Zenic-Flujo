"""
Workflow Determinista — Tests de la API Web (Flask)
Tests de integración usando Flask test client: auth, workflows, settings, license.
"""

import bcrypt
import pytest


@pytest.fixture
def app_client(db_manager, monkeypatch):
    """
    Provee un Flask test client configurado con base de datos temporal.
    Monkey-patches module-level db, repo, event_bus in app.py to use the test DB.
    """
    from src.core import config
    from src.events.bus import EventBus
    from src.web import app as app_module
    from src.workflow.repository import WorkflowRepository

    # Create fresh repo and event_bus that use the test DatabaseManager
    new_repo = WorkflowRepository()
    new_event_bus = EventBus()

    # Monkey-patch module-level variables in app.py so Flask routes use test DB
    monkeypatch.setattr(app_module, "db", db_manager)
    monkeypatch.setattr(app_module, "repo", new_repo)
    monkeypatch.setattr(app_module, "event_bus", new_event_bus)

    # Raise the free tier limit for testing
    monkeypatch.setattr(config, "FREE_TIER_MAX_WORKFLOWS", 100)

    # Create the Flask app
    app = app_module.create_app()
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_DOMAIN"] = "localhost"

    # Set up admin password in the test database
    password = "testpass123"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()
    db_manager.set_setting("admin_password_hash", hashed)

    # Reset rate limiting state
    app_module._login_attempts.clear()

    with app.test_client() as client:
        yield client, password


def _login(client, password):
    """Helper: iniciar sesión y retornar la respuesta."""
    return client.post(
        "/api/auth/login",
        json={"username": "admin", "password": password},
    )


class TestAuthAPI:
    """Tests para las rutas de autenticación."""

    def test_login_page_loads(self, app_client):
        """Test: GET /login retorna la página de login."""
        client, _ = app_client
        response = client.get("/login")
        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"Login" in response.data

    def test_login_valid_credentials(self, app_client):
        """Test: POST /api/auth/login con credenciales válidas retorna ok."""
        client, password = app_client
        response = _login(client, password)
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["user"] == "admin"

    def test_login_invalid_credentials(self, app_client):
        """Test: POST /api/auth/login con credenciales inválidas retorna 401."""
        client, _ = app_client
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert "error" in data

    def test_login_rate_limiting(self, app_client):
        """Test: rate limiting devuelve 429 después de 10 intentos fallidos."""
        client, _ = app_client
        # Make 10 failed login attempts
        for i in range(10):
            client.post(
                "/api/auth/login",
                json={"username": "admin", "password": f"wrong{i}"},
            )
        # 11th attempt should be rate limited
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong11"},
        )
        assert response.status_code == 429

    def test_dashboard_requires_authentication(self, app_client):
        """Test: acceder al dashboard sin login redirige a /login."""
        client, _ = app_client
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_logout(self, app_client):
        """Test: POST /api/auth/logout cierra la sesión."""
        client, password = app_client
        # Login first
        _login(client, password)
        # Then logout
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"


class TestWorkflowAPI:
    """Tests para las rutas de workflows."""

    def test_list_workflows(self, app_client):
        """Test: GET /api/workflows retorna lista de workflows."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/workflows")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_create_workflow(self, app_client):
        """Test: POST /api/workflows crea un workflow."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/workflows",
            json={
                "name": "Test WF API",
                "description": "Workflow creado via API",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [
                    {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "API Test"}},
                ],
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Test WF API"
        assert data["id"] is not None

    def test_get_workflow_by_id(self, app_client):
        """Test: GET /api/workflows/:id retorna un workflow."""
        client, password = app_client
        _login(client, password)
        # Create first
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Get Test WF",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"
        wf_id = create_resp.get_json()["id"]
        # Get it
        response = client.get(f"/api/workflows/{wf_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == wf_id
        assert data["name"] == "Get Test WF"

    def test_update_workflow(self, app_client):
        """Test: PUT /api/workflows/:id actualiza un workflow."""
        client, password = app_client
        _login(client, password)
        # Create
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Update Test WF",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"
        wf_id = create_resp.get_json()["id"]
        # Update
        response = client.put(
            f"/api/workflows/{wf_id}",
            json={"name": "Updated WF Name"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated WF Name"

    def test_delete_workflow(self, app_client):
        """Test: DELETE /api/workflows/:id elimina un workflow."""
        client, password = app_client
        _login(client, password)
        # Create
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Delete Test WF",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"
        wf_id = create_resp.get_json()["id"]
        # Delete
        response = client.delete(f"/api/workflows/{wf_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "deleted"

    def test_activate_workflow(self, app_client):
        """Test: POST /api/workflows/:id/activate activa un workflow."""
        client, password = app_client
        _login(client, password)
        # Create and pause first
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Activate Test WF",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"
        wf_id = create_resp.get_json()["id"]
        # Pause it
        client.post(f"/api/workflows/{wf_id}/pause")
        # Activate it
        response = client.post(f"/api/workflows/{wf_id}/activate")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "active"

    def test_pause_workflow(self, app_client):
        """Test: POST /api/workflows/:id/pause pausa un workflow."""
        client, password = app_client
        _login(client, password)
        # Create
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Pause Test WF",
                "trigger_type": "manual",
                "trigger_config": {},
                "steps": [],
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.get_json()}"
        wf_id = create_resp.get_json()["id"]
        # Pause
        response = client.post(f"/api/workflows/{wf_id}/pause")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "paused"

    def test_get_workflow_not_found(self, app_client):
        """Test: GET /api/workflows/:id con ID inexistente retorna 404."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/workflows/99999")
        assert response.status_code == 404


class TestSettingsAPI:
    """Tests para las rutas de configuración."""

    def test_get_settings(self, app_client):
        """Test: GET /api/settings retorna la configuración."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.get_json()
        assert "smtp_server" in data
        assert "smtp_port" in data
        assert "email_user" in data

    def test_update_settings(self, app_client):
        """Test: PUT /api/settings actualiza la configuración."""
        client, password = app_client
        _login(client, password)
        response = client.put(
            "/api/settings",
            json={
                "smtp_server": "smtp.newserver.com",
                "smtp_port": "465",
                "email_user": "newuser@test.com",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "saved"
        # Verify the update
        get_resp = client.get("/api/settings")
        settings = get_resp.get_json()
        assert settings["smtp_server"] == "smtp.newserver.com"


class TestLicenseAPI:
    """Tests para las rutas de licencia."""

    def test_validate_license_invalid_key(self, app_client):
        """Test: POST /api/license/validate con key inválida retorna valid=false."""
        client, _ = app_client
        response = client.post(
            "/api/license/validate",
            json={"key": "INVALID-KEY"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["valid"] is False

    def test_validate_license_no_key(self, app_client):
        """Test: POST /api/license/validate sin key retorna valid=false."""
        client, _ = app_client
        response = client.post(
            "/api/license/validate",
            json={},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["valid"] is False


class TestDashboardAPI:
    """Tests para las rutas del dashboard."""

    def test_dashboard_stats(self, app_client):
        """Test: GET /api/dashboard/stats retorna estadísticas."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/dashboard/stats")
        assert response.status_code == 200
        data = response.get_json()
        assert "stats" in data
        assert "trial" in data

    def test_dashboard_timeline(self, app_client):
        """Test: GET /api/dashboard/timeline retorna datos de ejecuciones por día."""
        client, password = app_client
        _login(client, password)
        # Crear workflow con ejecuciones para tener datos en el timeline
        create_resp = client.post(
            "/api/workflows",
            json={"name": "Timeline Test WF", "trigger_type": "manual", "trigger_config": {}, "steps": []},
        )
        assert create_resp.status_code == 201
        wf_id = create_resp.get_json()["id"]

        # Ejecutar el workflow (crea una ejecución)
        client.post(f"/api/workflows/{wf_id}/retry")

        # Obtener timeline
        response = client.get("/api/dashboard/timeline?days=30")
        assert response.status_code == 200
        data = response.get_json()
        assert "daily" in data
        assert "tools" in data
        assert isinstance(data["daily"], list)
        assert isinstance(data["tools"], list)

        # Si hay datos, verificar estructura
        if data["daily"]:
            day = data["daily"][0]
            assert "day" in day
            assert "completed" in day
            assert "failed" in day

    def test_dashboard_timeline_default_days(self, app_client):
        """Test: GET /api/dashboard/timeline sin parámetro days usa 14 por defecto."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/dashboard/timeline")
        assert response.status_code == 200
        data = response.get_json()
        assert "daily" in data


class TestChatAPI:
    """Tests para la ruta de chat NLP."""

    def test_chat_processes_nlp(self, app_client):
        """Test: POST /api/workflows/chat procesa texto NLP."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/workflows/chat",
            json={"text": "crear lead para Juan"},
        )
        assert response.status_code == 200
        data = response.get_json()
        # Should return suggestions or a message
        assert "suggestions" in data or "message" in data

    def test_chat_empty_text(self, app_client):
        """Test: POST /api/workflows/chat con texto vacío."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/workflows/chat",
            json={"text": ""},
        )
        assert response.status_code == 200


class TestPageRoutes:
    """Tests para las rutas de páginas (HTML)."""

    def test_index_redirects_to_dashboard(self, app_client):
        """Test: GET / redirige al dashboard si autenticado."""
        client, password = app_client
        _login(client, password)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "dashboard" in response.headers.get("Location", "")

    def test_login_page_redirects_if_authenticated(self, app_client):
        """Test: GET /login redirige al dashboard si ya autenticado."""
        client, password = app_client
        _login(client, password)
        response = client.get("/login", follow_redirects=False)
        assert response.status_code == 302
        assert "dashboard" in response.headers.get("Location", "")

    def test_chat_page_loads(self, app_client):
        """Test: GET /chat carga la página de chat."""
        client, password = app_client
        _login(client, password)
        response = client.get("/chat")
        assert response.status_code == 200

    def test_editor_page_loads(self, app_client):
        """Test: GET /editor carga la página del editor."""
        client, password = app_client
        _login(client, password)
        response = client.get("/editor")
        assert response.status_code == 200

    def test_workflow_list_page_loads(self, app_client):
        """Test: GET /workflows carga la lista de workflows."""
        client, password = app_client
        _login(client, password)
        response = client.get("/workflows")
        assert response.status_code == 200

    def test_workflow_detail_page_loads(self, app_client):
        """Test: GET /workflows/:id carga el detalle."""
        client, password = app_client
        _login(client, password)
        # Create a workflow first
        create_resp = client.post(
            "/api/workflows",
            json={"name": "Detail Page Test", "trigger_type": "manual", "trigger_config": {}, "steps": []},
        )
        wf_id = create_resp.get_json()["id"]
        response = client.get(f"/workflows/{wf_id}")
        assert response.status_code == 200

    def test_settings_page_loads(self, app_client):
        """Test: GET /settings carga la página de configuración."""
        client, password = app_client
        _login(client, password)
        response = client.get("/settings")
        assert response.status_code == 200


class TestWorkflowHistoryAPI:
    """Tests para historial de ejecuciones."""

    def test_workflow_history(self, app_client):
        """Test: GET /api/workflows/:id/history retorna historial."""
        client, password = app_client
        _login(client, password)
        create_resp = client.post(
            "/api/workflows",
            json={"name": "History Test WF", "trigger_type": "manual", "trigger_config": {}, "steps": []},
        )
        wf_id = create_resp.get_json()["id"]
        response = client.get(f"/api/workflows/{wf_id}/history")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_workflow_execution_detail_not_found(self, app_client):
        """Test: GET /api/workflows/:id/history/:exec_id retorna 404."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/workflows/1/history/99999")
        assert response.status_code == 404


class TestCRMAPI:
    """Tests para las rutas de CRM."""

    def test_list_leads(self, app_client):
        """Test: GET /api/tools/crm/leads retorna leads."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/tools/crm/leads")
        assert response.status_code == 200

    def test_create_lead(self, app_client):
        """Test: POST /api/tools/crm/leads crea un lead."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/crm/leads",
            json={"name": "Lead API Test", "email": "lead@test.com"},
        )
        assert response.status_code == 201


class TestInventoryAPI:
    """Tests para las rutas de inventario."""

    def test_list_products(self, app_client):
        """Test: GET /api/tools/inventory/products retorna productos."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/tools/inventory/products")
        assert response.status_code == 200

    def test_create_product(self, app_client):
        """Test: POST /api/tools/inventory/products crea un producto."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/inventory/products",
            json={"sku": "TEST-001", "name": "Test Product", "stock": 10, "price": 9.99},
        )
        assert response.status_code == 201

    def test_stock_movement_missing_product_id(self, app_client):
        """Test: POST /api/tools/inventory/stock-movement sin product_id retorna 400."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/inventory/stock-movement",
            json={"quantity": 5, "type": "in"},
        )
        assert response.status_code == 400

    def test_stock_movement_product_not_found(self, app_client):
        """Test: POST /api/tools/inventory/stock-movement con product_id inexistente retorna 404."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/inventory/stock-movement",
            json={"product_id": 99999, "quantity": 5, "type": "in"},
        )
        assert response.status_code == 404

    def test_low_stock_endpoint(self, app_client):
        """Test: GET /api/tools/inventory/low-stock retorna productos con stock bajo."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/tools/inventory/low-stock")
        assert response.status_code == 200


class TestInvoiceAPI:
    """Tests para las rutas de facturación."""

    def test_create_invoice(self, app_client):
        """Test: POST /api/tools/invoice/create crea una factura."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/invoice/create",
            json={
                "client_name": "Cliente Test",
                "items": [{"description": "Servicio", "quantity": 1, "price": 100.0}],
            },
        )
        assert response.status_code == 201

    def test_create_invoice_missing_client(self, app_client):
        """Test: POST /api/tools/invoice/create sin client_name retorna 400."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/tools/invoice/create",
            json={"items": []},
        )
        assert response.status_code == 400

    def test_list_invoices(self, app_client):
        """Test: GET /api/tools/invoice/list retorna facturas."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/tools/invoice/list")
        assert response.status_code == 200


class TestPasswordAPI:
    """Tests para cambio de contraseña."""

    def test_change_password(self, app_client):
        """Test: POST /api/settings/change-password cambia la contraseña."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/settings/change-password",
            json={"current_password": password, "new_password": "newpass456"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"

    def test_change_password_wrong_current(self, app_client):
        """Test: POST /api/settings/change-password con contraseña actual incorrecta retorna 400."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/settings/change-password",
            json={"current_password": "wrongpass", "new_password": "newpass456"},
        )
        assert response.status_code == 400

    def test_change_password_too_short(self, app_client):
        """Test: POST /api/settings/change-password con nueva contraseña corta retorna 400."""
        client, password = app_client
        _login(client, password)
        response = client.post(
            "/api/settings/change-password",
            json={"current_password": password, "new_password": "abc"},
        )
        assert response.status_code == 400


class TestSystemAPI:
    """Tests para las rutas del sistema."""

    def test_system_status(self, app_client):
        """Test: GET /api/system/status retorna estado del sistema."""
        client, _ = app_client
        response = client.get("/api/system/status")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "running"
        assert "version" in data

    def test_system_logs(self, app_client):
        """Test: GET /api/system/logs retorna logs de auditoría."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/system/logs")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_system_backup(self, app_client):
        """Test: POST /api/system/backup realiza un backup."""
        client, password = app_client
        _login(client, password)
        response = client.post("/api/system/backup")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "completed"


class TestLicenseInfoAPI:
    """Tests para la ruta de info de licencia."""

    def test_license_info(self, app_client):
        """Test: GET /api/license/info retorna información de la licencia."""
        client, _ = app_client
        response = client.get("/api/license/info")
        assert response.status_code == 200
        data = response.get_json()
        assert "is_free" in data
        assert "max_workflows" in data
        assert "allowed_tools" in data


class TestAuthStatusAPI:
    """Tests para la ruta de estado de auth."""

    def test_auth_status_unauthenticated(self, app_client):
        """Test: GET /api/auth/status retorna authenticated=false sin sesión."""
        client, _ = app_client
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.get_json()
        assert data["authenticated"] is False

    def test_auth_status_authenticated(self, app_client):
        """Test: GET /api/auth/status retorna authenticated=true con sesión."""
        client, password = app_client
        _login(client, password)
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.get_json()
        assert data["authenticated"] is True

    def test_login_no_password_hash(self, app_client):
        """Test: POST /api/auth/login sin hash configurado retorna 401."""
        client, _ = app_client
        # Remove the password hash temporarily
        from src.core.db import DatabaseManager
        from src.web import app as app_module

        # Delete the setting from DB directly
        db_inst = DatabaseManager()
        db_inst.execute("DELETE FROM settings WHERE key = ?", ("admin_password_hash",))
        db_inst.commit()
        # Also clear from the module-level db
        app_module.db.execute("DELETE FROM settings WHERE key = ?", ("admin_password_hash",))
        app_module.db.commit()
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "test"},
        )
        assert response.status_code == 401
