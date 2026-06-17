"""
Tests del split de TenantService (Fase 6 — BUG-ARCH-02).

Verifica que los 3 módulos extraídos (TenantResolver, TenantSettings,
TenantProvisioner) delegan correctamente en TenantService sin perder
funcionalidad.
"""
from __future__ import annotations

from src.tenant.provisioner import TenantProvisioner
from src.tenant.resolver import TenantResolver
from src.tenant.service import TenantService
from src.tenant.settings_service import TenantSettings


class TestTenantResolver:
    """Tests de TenantResolver."""

    def test_resolver_instantiates_with_default_service(self):
        resolver = TenantResolver()
        assert resolver._tenant_service is not None
        assert isinstance(resolver._tenant_service, TenantService)

    def test_resolver_accepts_injected_service(self):
        svc = TenantService()
        resolver = TenantResolver(tenant_service=svc)
        assert resolver._tenant_service is svc

    def test_resolve_from_header_returns_none_if_no_header(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_header({})
        assert result is None

    def test_resolve_from_header_returns_none_if_no_x_tenant_id(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_header({"Other-Header": "value"})
        assert result is None

    def test_resolve_from_subdomain_returns_none_for_www(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_subdomain("www.app.zenic-flijo.com")
        assert result is None

    def test_resolve_from_subdomain_returns_none_for_app(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_subdomain("app.zenic-flijo.com")
        assert result is None

    def test_resolve_from_subdomain_returns_none_for_no_dot(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_subdomain("localhost")
        assert result is None

    def test_resolve_from_subdomain_returns_none_for_short_host(self):
        resolver = TenantResolver()
        result = resolver.resolve_from_subdomain("zenic-flijo.com")
        assert result is None


class TestTenantSettings:
    """Tests de TenantSettings."""

    def test_settings_instantiates_with_default_service(self):
        settings = TenantSettings()
        assert settings._tenant_service is not None
        assert isinstance(settings._tenant_service, TenantService)

    def test_settings_accepts_injected_service(self):
        svc = TenantService()
        settings = TenantSettings(tenant_service=svc)
        assert settings._tenant_service is svc

    def test_settings_has_feature_methods(self):
        settings = TenantSettings()
        assert hasattr(settings, "set_feature")
        assert hasattr(settings, "check_feature")
        assert hasattr(settings, "get_features")
        assert callable(settings.set_feature)
        assert callable(settings.check_feature)
        assert callable(settings.get_features)

    def test_settings_has_setting_methods(self):
        settings = TenantSettings()
        assert hasattr(settings, "get_setting")
        assert hasattr(settings, "set_setting")
        assert hasattr(settings, "get_all_settings")
        assert callable(settings.get_setting)
        assert callable(settings.set_setting)
        assert callable(settings.get_all_settings)

    def test_settings_has_rate_limit_method(self):
        settings = TenantSettings()
        assert hasattr(settings, "check_rate_limit")
        assert callable(settings.check_rate_limit)


class TestTenantProvisioner:
    """Tests de TenantProvisioner."""

    def test_provisioner_instantiates_with_default_service(self):
        provisioner = TenantProvisioner()
        assert provisioner._tenant_service is not None
        assert isinstance(provisioner._tenant_service, TenantService)

    def test_provisioner_accepts_injected_service(self):
        svc = TenantService()
        provisioner = TenantProvisioner(tenant_service=svc)
        assert provisioner._tenant_service is svc

    def test_provisioner_has_create_method(self):
        provisioner = TenantProvisioner()
        assert hasattr(provisioner, "create_tenant")
        assert callable(provisioner.create_tenant)

    def test_provisioner_has_lifecycle_methods(self):
        provisioner = TenantProvisioner()
        assert hasattr(provisioner, "suspend_tenant")
        assert hasattr(provisioner, "activate_tenant")
        assert hasattr(provisioner, "delete_tenant")
        assert callable(provisioner.suspend_tenant)
        assert callable(provisioner.activate_tenant)
        assert callable(provisioner.delete_tenant)

    def test_provisioner_has_get_tenant_db(self):
        provisioner = TenantProvisioner()
        assert hasattr(provisioner, "get_tenant_db")
        assert callable(provisioner.get_tenant_db)


class TestBackwardCompatibility:
    """Los módulos nuevos no deben romper la API existente de TenantService."""

    def test_tenant_service_still_has_all_methods(self):
        """TenantService original debe seguir teniendo todos sus métodos."""
        svc = TenantService()
        # Métodos de resolver
        assert hasattr(svc, "resolve_tenant")
        assert hasattr(svc, "get_tenant")
        assert hasattr(svc, "get_tenant_by_slug")
        # Métodos de settings
        assert hasattr(svc, "set_feature")
        assert hasattr(svc, "check_feature")
        assert hasattr(svc, "get_features")
        assert hasattr(svc, "get_setting")
        assert hasattr(svc, "set_setting")
        # Métodos de provisioner
        assert hasattr(svc, "create_tenant")
        assert hasattr(svc, "suspend_tenant")
        assert hasattr(svc, "activate_tenant")
        assert hasattr(svc, "delete_tenant")
        assert hasattr(svc, "get_tenant_db")

    def test_resolver_delegates_to_service(self):
        """TenantResolver.resolve_from_header delega en get_tenant."""
        # Crear un mock simple
        class MockService:
            def __init__(self):
                self.called_with = None

            def get_tenant(self, tenant_id):
                self.called_with = tenant_id
                return {"id": tenant_id, "name": "mock"}

        mock = MockService()
        resolver = TenantResolver(tenant_service=mock)
        result = resolver.resolve_from_header({"X-Tenant-ID": "test-123"})

        assert mock.called_with == "test-123"
        assert result["id"] == "test-123"

    def test_settings_delegates_to_service(self):
        """TenantSettings.check_feature delega en check_feature del service."""
        class MockService:
            def __init__(self):
                self.checked = None

            def check_feature(self, tenant_id, feature):
                self.checked = (tenant_id, feature)
                return True

        mock = MockService()
        settings = TenantSettings(tenant_service=mock)
        result = settings.check_feature("tenant-1", "advanced_analytics")

        assert mock.checked == ("tenant-1", "advanced_analytics")
        assert result is True
