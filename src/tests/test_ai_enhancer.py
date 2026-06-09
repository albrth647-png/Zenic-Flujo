"""
Tests para AI Enhancer (Mejora #9).
Usa mocks HTTP para no requerir Ollama instalado.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestAIEnhancer:
    """Tests para el AI Enhancer."""

    def test_disabled_by_default(self):
        """AI Enhancer deshabilitado por defecto."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()
        assert enhancer.enabled is False

    def test_is_available_returns_false_when_disabled(self):
        """is_available() retorna False si deshabilitado."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()
        assert enhancer.is_available() is False

    def test_enhance_returns_fallback_when_disabled(self):
        """enhance_intents() retorna fallback si deshabilitado."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()
        fallback = [{"name": "test", "confidence": 0.5}]
        result = enhancer.enhance_intents("test", fallback)
        assert result == fallback

    def test_enhance_returns_empty_when_disabled_no_fallback(self):
        """enhance_intents() retorna [] si deshabilitado sin fallback."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()
        result = enhancer.enhance_intents("test")
        assert result == []

    def test_parse_response_valid_json(self):
        """Parsea respuesta JSON correcta."""
        from src.nlp.ai_enhancer import AIEnhancer
        raw = '[{"name": "test_wf", "description": "Test", "trigger_type": "manual", "steps": []}]'
        parsed = AIEnhancer._parse_response(raw)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "test_wf"

    def test_parse_response_with_extra_text(self):
        """Parsea JSON dentro de texto adicional."""
        from src.nlp.ai_enhancer import AIEnhancer
        raw = 'Aquí está:\n[{"name": "wf1", "description": "d1", "trigger_type": "manual", "steps": []}]\nFin'
        parsed = AIEnhancer._parse_response(raw)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "wf1"

    def test_parse_response_invalid(self):
        """Texto inválido retorna lista vacía."""
        from src.nlp.ai_enhancer import AIEnhancer
        parsed = AIEnhancer._parse_response("no es json")
        assert parsed == []

    def test_parse_response_multiple_intents(self):
        """Parsea múltiples intents."""
        from src.nlp.ai_enhancer import AIEnhancer
        raw = """[
            {"name": "wf1", "description": "d1", "trigger_type": "manual", "steps": []},
            {"name": "wf2", "description": "d2", "trigger_type": "schedule", "steps": []}
        ]"""
        parsed = AIEnhancer._parse_response(raw)
        assert len(parsed) == 2

    def test_build_prompt_includes_text(self):
        """El prompt incluye el texto del usuario."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()
        prompt = enhancer._build_prompt("enviar email a clientes")
        assert "enviar email a clientes" in prompt
        assert "JSON" in prompt

    def test_query_ollama_success(self):
        """Query a Ollama exitosa retorna contenido."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '[{"name": "ai_wf", "trigger_type": "manual", "steps": []}]'}
        }

        with patch("requests.post", return_value=mock_response):
            result = enhancer._query_ollama("test prompt")
            assert "ai_wf" in result

    def test_query_ollama_http_error(self):
        """Error HTTP en Ollama se propaga."""
        from src.nlp.ai_enhancer import AIEnhancer
        enhancer = AIEnhancer()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(Exception):
                enhancer._query_ollama("test")
