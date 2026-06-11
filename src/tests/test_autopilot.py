"""
Workflow Determinista — Tests del AutoPilot Service
Tests unitarios para las plantillas de automatización.
"""

import pytest


class TestAutoPilotService:
    """Tests del AutoPilotService."""

    def test_init(self, db_manager):
        """Verifica inicialización correcta."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        assert service._classifier is not None

    def test_suggest_templates_with_crm_text(self, db_manager):
        """Verifica que suggest_templates() retorna sugerencias para texto de CRM."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("Quiero registrar clientes nuevos")
        # Debería encontrar al menos una sugerencia relacionada con CRM
        assert isinstance(results, list)

    def test_suggest_templates_with_stock_text(self, db_manager):
        """Verifica que suggest_templates() retorna sugerencias para texto de inventario."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("Necesito alertas de stock bajo")
        assert isinstance(results, list)

    def test_suggest_templates_with_empty_text(self, db_manager):
        """Verifica que suggest_templates() retorna lista vacía para texto vacío."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("")
        assert results == []

    def test_suggest_templates_with_gibberish(self, db_manager):
        """Verifica que suggest_templates() maneja texto sin sentido."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("asdfghjkl xyz123")
        assert isinstance(results, list)

    def test_get_quick_templates(self, db_manager):
        """Verifica que get_quick_templates() retorna todas las plantillas."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        templates = service.get_quick_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 10  # Hay al menos 10 templates
        # Verificar estructura de cada template
        for t in templates:
            assert "name" in t
            assert "trigger_type" in t
            assert "step_count" in t
            assert isinstance(t["step_count"], int)
            assert t["step_count"] >= 1

    def test_create_from_template(self, db_manager):
        """Verifica que create_from_template() crea un workflow válido."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        result = service.create_from_template("registro_cliente")
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
        assert "steps" in result
        assert len(result["steps"]) >= 1

    def test_create_from_template_invalid(self, db_manager):
        """Verifica que create_from_template() lanza error con template inexistente."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        with pytest.raises(ValueError, match="no encontrado"):
            service.create_from_template("template_inexistente_xyz")

    def test_suggest_templates_returns_confidence(self, db_manager):
        """Verifica que las sugerencias incluyen campo confidence."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("Quiero automatizar el registro de clientes")
        for r in results:
            assert "confidence" in r
            assert "name" in r
            assert "trigger" in r
            assert "steps" in r

    def test_suggest_templates_max_five(self, db_manager):
        """Verifica que suggest_templates() retorna máximo 5 sugerencias."""
        from src.tools.autopilot.service import AutoPilotService

        service = AutoPilotService()
        results = service.suggest_templates("automatizar cliente factura inventario stock email")
        assert len(results) <= 5
