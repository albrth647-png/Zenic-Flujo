"""
Tests del auth unificado Flask + FastAPI (Fase 6 — BUG-ARCH-03).

Verifica que:
- `require_permission` y `get_current_user` se pueden importar tanto desde
  `src.api_v2.auth` como desde `src.api_v2.dependencies` (re-export).
- `api_v2.app` carga sin ImportError (era el síntoma del bug).
- Los routers que usan `require_permission` de `dependencies` funcionan.
- SSOService es accesible vía `src.security.sso` (paquete) sin conflicto
  con el módulo legacy `src.security.sso.py`.
"""
from __future__ import annotations

import importlib
import sys


class TestUnifiedAuthImports:
    """Verifica que ambos paths de import funcionan (auth y dependencies)."""

    def test_require_permission_importable_from_auth(self):
        """Fuente de verdad: src.api_v2.auth.require_permission."""
        from src.api_v2.auth import require_permission
        assert callable(require_permission)

    def test_require_permission_importable_from_dependencies(self):
        """Re-export: src.api_v2.dependencies.require_permission."""
        from src.api_v2.dependencies import require_permission
        assert callable(require_permission)

    def test_both_imports_return_same_object(self):
        """Ambos imports deben retornar el mismo objeto (re-export, no copia)."""
        from src.api_v2.auth import require_permission as from_auth
        from src.api_v2.dependencies import require_permission as from_deps
        assert from_auth is from_deps

    def test_get_current_user_importable_from_both(self):
        from src.api_v2.auth import get_current_user as from_auth
        from src.api_v2.dependencies import get_current_user as from_deps
        assert from_auth is from_deps

    def test_generate_token_importable_from_both(self):
        from src.api_v2.auth import generate_token as from_auth
        from src.api_v2.dependencies import generate_token as from_deps
        assert from_auth is from_deps

    def test_validate_token_importable_from_both(self):
        from src.api_v2.auth import validate_token as from_auth
        from src.api_v2.dependencies import validate_token as from_deps
        assert from_auth is from_deps

    def test_dependencies_all_includes_auth_symbols(self):
        """__all__ de dependencies debe incluir los re-exports."""
        from src.api_v2 import dependencies
        assert "require_permission" in dependencies.__all__
        assert "get_current_user" in dependencies.__all__
        assert "generate_token" in dependencies.__all__
        assert "validate_token" in dependencies.__all__


class TestApiV2AppLoads:
    """El síntoma principal del bug: api_v2.app no cargaba."""

    def test_api_v2_app_imports_without_error(self):
        """Debe poder importar src.api_v2.app sin ImportError."""
        # Si falla, este test lanza ImportError y pytest lo marca como failed
        from src.api_v2.app import app
        assert app is not None
        assert hasattr(app, "routes")
        assert len(app.routes) > 0

    def test_api_v2_app_has_health_endpoint(self):
        from src.api_v2.app import app
        # Buscar la ruta /api/v2/health
        health_routes = [
            r for r in app.routes
            if hasattr(r, "path") and "/health" in str(r.path)
        ]
        assert len(health_routes) > 0, "Health endpoint not found"

    def test_api_v2_app_has_workflows_router(self):
        from src.api_v2.app import app
        workflow_routes = [
            r for r in app.routes
            if hasattr(r, "path") and "/workflows" in str(r.path)
        ]
        assert len(workflow_routes) > 0, "Workflows routes not found"


class TestSSOServiceAccessibility:
    """SSOService debe ser accesible vía el paquete sso/ (no solo sso.py)."""

    def test_sso_service_importable_from_package(self):
        """from src.security.sso import SSOService debe funcionar."""
        from src.security.sso import SSOService
        assert SSOService is not None
        assert hasattr(SSOService, "__init__")

    def test_sso_service_is_class(self):
        from src.security.sso import SSOService
        import inspect
        assert inspect.isclass(SSOService)

    def test_security_init_imports_sso_service(self):
        """from src.security import SSOService también debe funcionar."""
        from src.security import SSOService
        assert SSOService is not None

    def test_security_init_imports_register_sso_routes(self):
        from src.security import register_sso_routes
        assert callable(register_sso_routes)


class TestRoutersLoadWithoutError:
    """Cada router de api_v2 debe importar sin error."""

    def test_workflows_router_loads(self):
        from src.api_v2.routers.workflows import router
        assert router is not None

    def test_agents_router_loads(self):
        """Este router usa `from src.api_v2.dependencies import require_permission`
        — era el que fallaba antes del fix."""
        from src.api_v2.routers.agents import router
        assert router is not None

    def test_bpmn_router_loads(self):
        from src.api_v2.routers.bpmn import router
        assert router is not None

    def test_compliance_router_loads(self):
        from src.api_v2.routers.compliance import router
        assert router is not None

    def test_auth_routes_router_loads(self):
        from src.api_v2.routers.auth_routes import router
        assert router is not None

    def test_connectors_router_loads(self):
        from src.api_v2.routers.connectors import router
        assert router is not None

    def test_nlu_router_loads(self):
        from src.api_v2.routers.nlu import router
        assert router is not None

    def test_tenants_router_loads(self):
        from src.api_v2.routers.tenants import router
        assert router is not None

    def test_marketplace_router_loads(self):
        from src.api_v2.routers.marketplace import router
        assert router is not None


class TestNoMappingModuleReferences:
    """Verifica que no quedan imports del módulo inexistente `sso.mapping`."""

    def test_no_mapping_import_in_sso_init(self):
        """src.security.sso.__init__ no debe importar de .mapping."""
        import src.security.sso as sso_pkg
        # Verificar que el módulo cargó sin AttributeError por mapping
        assert hasattr(sso_pkg, "__all__")
        assert "SSOService" in sso_pkg.__all__

    def test_no_mapping_import_in_sso_routes(self):
        """src.security.sso.routes no debe importar de .mapping."""
        # Si el import de routes falla, este test falla
        from src.security.sso import routes
        assert hasattr(routes, "register_sso_routes")

    def test_no_mapping_import_in_sso_legacy_module(self):
        """src.security.sso (módulo legacy .py) no debe importar de .mapping."""
        # Cargar el módulo legacy vía importlib (como hace el __getattr__)
        import importlib.util
        import pathlib
        sso_py_path = pathlib.Path(__file__).parent.parent / "security" / "sso.py"
        spec = importlib.util.spec_from_file_location("sso_legacy_test", sso_py_path)
        module = importlib.util.module_from_spec(spec)
        # Si el import de mapping fallaba, esto levantaría ImportError
        spec.loader.exec_module(module)
        assert hasattr(module, "SSOService")
