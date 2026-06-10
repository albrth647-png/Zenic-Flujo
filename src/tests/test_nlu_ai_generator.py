"""
Tests para AI Workflow Generator (Sprint 5).
Valida generación de workflows con LLM: parseo, validación, fallback.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


import os


class TestWorkflowAIGenerator:
    """Tests para el generador de workflows con IA."""

    def test_no_provider_returns_error(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        gen = WorkflowAIGenerator()
        result = gen.generate("Crear un workflow")
        assert result.validated is False
        assert result.provider == "none"
        assert "No hay proveedor" in result.explanation

    def test_parse_valid_workflow(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        raw = json.dumps({
            "name": "test_workflow",
            "description": "Test",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}}
            ]
        })
        parsed = WorkflowAIGenerator._parse_workflow(raw)
        assert parsed is not None
        assert parsed["name"] == "test_workflow"
        assert len(parsed["steps"]) == 1

    def test_parse_workflow_with_extra_text(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        raw = 'Aquí está el workflow:\n{"name": "wf1", "trigger_type": "manual", "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}]}\nEspero que sirva.'
        parsed = WorkflowAIGenerator._parse_workflow(raw)
        assert parsed is not None
        assert parsed["name"] == "wf1"

    def test_parse_invalid_json(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        parsed = WorkflowAIGenerator._parse_workflow("esto no es json")
        assert parsed is None

    def test_parse_missing_name(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        raw = json.dumps({
            "trigger_type": "manual",
            "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}]
        })
        parsed = WorkflowAIGenerator._parse_workflow(raw)
        # Falta "name", parse_workflow retorna None porque no tiene name
        assert parsed is None

    def test_parse_missing_steps(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        raw = json.dumps({
            "name": "test",
            "trigger_type": "manual",
        })
        parsed = WorkflowAIGenerator._parse_workflow(raw)
        assert parsed is None

    def test_validate_valid_workflow(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "test_wf",
            "trigger_type": "manual",
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}}
            ]
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert errors == []

    def test_validate_invalid_tool(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "test_wf",
            "trigger_type": "manual",
            "steps": [
                {"id": 1, "tool": "tool_inexistente", "action": "do_something", "params": {}}
            ]
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert len(errors) > 0
        assert any("tool_inexistente" in e for e in errors)

    def test_validate_invalid_trigger_type(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "test_wf",
            "trigger_type": "invalid_type",
            "steps": []
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert any("trigger_type" in e for e in errors)

    def test_validate_empty_steps(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "test_wf",
            "trigger_type": "manual",
            "steps": []
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert any("no tiene pasos" in e for e in errors)

    def test_validate_missing_action(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "test_wf",
            "trigger_type": "manual",
            "steps": [
                {"id": 1, "tool": "crm", "action": "", "params": {}}
            ]
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert any("action" in e for e in errors)

    def test_validate_missing_name(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "",
            "trigger_type": "manual",
            "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}]
        }
        errors = WorkflowAIGenerator._validate_workflow(workflow)
        assert any("name" in e for e in errors)

    def test_validate_all_known_tools(self):
        from src.nlu.ai_generator import WorkflowAIGenerator, KNOWN_TOOLS
        for tool in KNOWN_TOOLS:
            workflow = {
                "name": f"test_{tool}",
                "trigger_type": "manual",
                "steps": [
                    {"id": 1, "tool": tool, "action": "test_action", "params": {}}
                ]
            }
            errors = WorkflowAIGenerator._validate_workflow(workflow)
            assert errors == [], f"Tool '{tool}' debería ser válida"

    def test_generate_explanation_es(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "Alerta Stock",
            "trigger_type": "schedule",
            "steps": [
                {"id": 1, "tool": "inventory", "action": "get_low_stock_products", "params": {}},
                {"id": 2, "tool": "notification", "action": "send_email", "params": {}},
            ]
        }
        explanation = WorkflowAIGenerator()._generate_explanation(workflow, "es")
        assert "Alerta Stock" in explanation
        assert "inventory.get_low_stock_products" in explanation
        assert "notification.send_email" in explanation

    def test_generate_explanation_en(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        workflow = {
            "name": "Stock Alert",
            "trigger_type": "manual",
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
            ]
        }
        explanation = WorkflowAIGenerator()._generate_explanation(workflow, "en")
        assert "Stock Alert" in explanation

    def test_generate_explanation_trigger_types(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        gen = WorkflowAIGenerator()
        for trigger in ["manual", "schedule", "event", "webhook"]:
            workflow = {
                "name": "Test",
                "trigger_type": trigger,
                "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}]
            }
            explanation = gen._generate_explanation(workflow, "es")
            assert len(explanation) > 0


class TestAIGeneratorLLM:
    """Tests con mocks para las llamadas LLM."""

    def setup_method(self):
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()

    def test_generate_with_ollama_mock(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            gen = WorkflowAIGenerator()
            # Mock la llamada HTTP
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "content": json.dumps({
                        "name": "Lead Automático",
                        "description": "Crear lead cuando llegue un email",
                        "trigger_type": "manual",
                        "trigger_config": {},
                        "steps": [
                            {"id": 1, "tool": "crm", "action": "create_lead",
                             "params": {"name": "$input.nombre"}}
                        ]
                    })
                }
            }
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = gen.generate("Crear lead automático")

            assert result.validated is True
            assert result.workflow["name"] == "Lead Automático"
            assert result.provider == "ollama"

    def test_generate_ollama_invalid_json(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            gen = WorkflowAIGenerator()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"content": "No puedo generar eso"}
            }
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = gen.generate("Algo imposible")

            assert result.validated is False
            assert "Failed to parse" in str(result.validation_errors)

    def test_generate_ollama_http_error(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            gen = WorkflowAIGenerator()
            with patch("requests.post", side_effect=Exception("Connection refused")):
                result = gen.generate("Test")

            assert result.validated is False
            assert "Error" in result.explanation

    def test_generate_with_openai_mock(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        with patch.dict(os.environ, {
            "WFD_OPENAI_ENABLED": "true",
            "WFD_OPENAI_API_KEY": "sk-test",
            "WFD_OPENAI_MODEL": "gpt-4o-mini",
        }):
            gen = WorkflowAIGenerator()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "name": "Email Automático",
                            "trigger_type": "manual",
                            "trigger_config": {},
                            "steps": [
                                {"id": 1, "tool": "notification",
                                 "action": "send_email", "params": {}}
                            ]
                        })
                    }
                }]
            }
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = gen.generate("Enviar email automático")

            assert result.validated is True
            assert result.provider == "openai"

    def test_generate_with_anthropic_mock(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        with patch.dict(os.environ, {
            "WFD_ANTHROPIC_ENABLED": "true",
            "WFD_ANTHROPIC_API_KEY": "sk-ant-test",
            "WFD_ANTHROPIC_MODEL": "claude-3",
        }):
            gen = WorkflowAIGenerator()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "content": [{
                    "text": json.dumps({
                        "name": "Factura Automática",
                        "trigger_type": "schedule",
                        "trigger_config": {"cron": "0 9 * * *"},
                        "steps": [
                            {"id": 1, "tool": "invoice",
                             "action": "get_overdue_invoices", "params": {}}
                        ]
                    })
                }]
            }
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = gen.generate("Revisar facturas vencidas cada día")

            assert result.validated is True
            assert result.provider == "anthropic"

    def test_workflow_with_invalid_tool_fails_validation(self):
        from src.nlu.ai_generator import WorkflowAIGenerator
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            gen = WorkflowAIGenerator()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {
                    "content": json.dumps({
                        "name": "Bad WF",
                        "trigger_type": "manual",
                        "steps": [
                            {"id": 1, "tool": "nonexistent_tool",
                             "action": "do_stuff", "params": {}}
                        ]
                    })
                }
            }
            mock_response.raise_for_status = MagicMock()

            with patch("requests.post", return_value=mock_response):
                result = gen.generate("Test con tool inválido")

            assert result.validated is False
            assert len(result.validation_errors) > 0


@pytest.fixture(autouse=True)
def reset_config():
    """Reset AI config before each test."""
    from src.nlu.ai_config import reset_ai_config
    reset_ai_config()
    yield
    reset_config_cleanup()


def reset_config_cleanup():
    from src.nlu.ai_config import reset_ai_config
    reset_ai_config()
