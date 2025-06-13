import pytest
from core.config_service import ConfigService

def test_config_service_default():
    config = ConfigService().get_config()
    assert config.app_name == "Agent Data Platform"
    assert hasattr(config, "llm")
    assert hasattr(config, "persistence")
    assert hasattr(config, "tools")
    assert hasattr(config, "agent")

def test_config_service_override():
    cs = ConfigService()
    cs.override("llm.provider", "openai")
    config = cs.get_config()
    assert config.llm.provider == "openai"
