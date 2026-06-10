"""
Tests para AI Config (Sprint 5).
Valida configuración multi-proveedor: Ollama, OpenAI, Anthropic.
"""
from unittest.mock import patch
import os


class TestAIProvider:
    """Tests para el enum AIProvider."""

    def test_provider_values(self):
        from src.nlu.ai_config import AIProvider
        assert AIProvider.OLLAMA.value == "ollama"
        assert AIProvider.OPENAI.value == "openai"
        assert AIProvider.ANTHROPIC.value == "anthropic"
        assert AIProvider.NONE.value == "none"

    def test_provider_is_string(self):
        from src.nlu.ai_config import AIProvider
        assert isinstance(AIProvider.OLLAMA, str)


class TestProviderConfig:
    """Tests para ProviderConfig."""

    def test_is_configured_disabled(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(provider=AIProvider.OLLAMA, enabled=False)
        assert config.is_configured is False

    def test_is_configured_ollama_no_url(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(provider=AIProvider.OLLAMA, enabled=True, base_url="")
        assert config.is_configured is False

    def test_is_configured_ollama_with_url(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(
            provider=AIProvider.OLLAMA, enabled=True,
            base_url="http://localhost:11434"
        )
        assert config.is_configured is True

    def test_is_configured_openai_no_key(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(provider=AIProvider.OPENAI, enabled=True)
        assert config.is_configured is False

    def test_is_configured_openai_full(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(
            provider=AIProvider.OPENAI, enabled=True,
            api_key="sk-test", model="gpt-4o-mini"
        )
        assert config.is_configured is True

    def test_is_configured_anthropic_full(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(
            provider=AIProvider.ANTHROPIC, enabled=True,
            api_key="sk-ant-test", model="claude-3"
        )
        assert config.is_configured is True

    def test_default_temperature(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(provider=AIProvider.OLLAMA, enabled=True,
                                base_url="http://localhost:11434")
        assert config.temperature == 0.3

    def test_default_timeout(self):
        from src.nlu.ai_config import AIProvider, ProviderConfig
        config = ProviderConfig(provider=AIProvider.OLLAMA, enabled=True,
                                base_url="http://localhost:11434")
        assert config.timeout == 30


class TestAIConfig:
    """Tests para AIConfig."""

    def setup_method(self):
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()

    def test_default_no_providers(self):
        from src.nlu.ai_config import AIConfig
        config = AIConfig()
        assert config.active_provider.value == "none"
        assert config.is_ai_available() is False

    def test_ollama_detection(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            config = AIConfig()
            assert config.active_provider == AIProvider.OLLAMA
            assert config.is_ai_available() is True

    def test_openai_detection(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        with patch.dict(os.environ, {
            "WFD_OPENAI_ENABLED": "true",
            "WFD_OPENAI_API_KEY": "sk-test-key",
        }):
            config = AIConfig()
            assert config.active_provider == AIProvider.OPENAI
            assert config.is_ai_available() is True

    def test_anthropic_detection(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        with patch.dict(os.environ, {
            "WFD_ANTHROPIC_ENABLED": "true",
            "WFD_ANTHROPIC_API_KEY": "sk-ant-test",
        }):
            config = AIConfig()
            assert config.active_provider == AIProvider.ANTHROPIC
            assert config.is_ai_available() is True

    def test_ollama_preferred_over_openai(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
            "WFD_OPENAI_ENABLED": "true",
            "WFD_OPENAI_API_KEY": "sk-test-key",
        }):
            config = AIConfig()
            assert config.active_provider == AIProvider.OLLAMA

    def test_get_active_config_none(self):
        from src.nlu.ai_config import AIConfig
        config = AIConfig()
        assert config.get_active_config() is None

    def test_get_active_config_ollama(self):
        from src.nlu.ai_config import AIConfig
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            config = AIConfig()
            active = config.get_active_config()
            assert active is not None
            assert active.provider.value == "ollama"

    def test_get_status(self):
        from src.nlu.ai_config import AIConfig
        config = AIConfig()
        status = config.get_status()
        assert "active_provider" in status
        assert "providers" in status
        assert "ollama" in status["providers"]
        assert "openai" in status["providers"]
        assert "anthropic" in status["providers"]

    def test_fallback_to_deterministic_default(self):
        from src.nlu.ai_config import AIConfig
        config = AIConfig()
        assert config.fallback_to_deterministic is True

    def test_set_provider(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        config = AIConfig()
        config.set_provider(AIProvider.OPENAI, True, api_key="sk-new", model="gpt-4o")
        assert config.active_provider == AIProvider.OPENAI

    def test_set_provider_disable(self):
        from src.nlu.ai_config import AIConfig, AIProvider
        with patch.dict(os.environ, {
            "WFD_OLLAMA_ENABLED": "true",
            "WFD_OLLAMA_URL": "http://localhost:11434",
        }):
            config = AIConfig()
            assert config.active_provider == AIProvider.OLLAMA
            config.set_provider(AIProvider.OLLAMA, False)
            assert config.active_provider == AIProvider.NONE


class TestSingleton:
    """Tests para el singleton de AIConfig."""

    def setup_method(self):
        from src.nlu.ai_config import reset_ai_config
        reset_ai_config()

    def test_get_ai_config_singleton(self):
        from src.nlu.ai_config import get_ai_config
        a = get_ai_config()
        b = get_ai_config()
        assert a is b

    def test_reset_creates_new(self):
        from src.nlu.ai_config import get_ai_config, reset_ai_config
        a = get_ai_config()
        reset_ai_config()
        b = get_ai_config()
        assert a is not b
