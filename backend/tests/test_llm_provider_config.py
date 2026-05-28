import importlib

from fastapi.testclient import TestClient


def _reset_llm_env(monkeypatch):
    for key in [
        "ACTIVE_LLM_PROVIDER",
        "CURRENT_LLM_ENDPOINT",
        "CURRENT_LLM_MODEL",
        "CURRENT_LLM_API_KEY",
        "ALIYUN_LLM_ENDPOINT",
        "ALIYUN_LLM_MODEL",
        "ALIYUN_LLM_API_KEY",
        "DASHSCOPE_API_KEY",
        "LLM_ENDPOINT",
        "LLM_MODEL",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_R1_API_KEY",
        "DEEPSEEK_V3_API_KEY",
        "GPT52_API_KEY",
        "QWEN_API_KEY",
        "QWEN_VL_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_current_provider_uses_legacy_llm_variables(monkeypatch):
    _reset_llm_env(monkeypatch)
    monkeypatch.setenv("ACTIVE_LLM_PROVIDER", "current")
    monkeypatch.setenv("CURRENT_LLM_ENDPOINT", "")
    monkeypatch.setenv("CURRENT_LLM_MODEL", "")
    monkeypatch.setenv("CURRENT_LLM_API_KEY", "")
    monkeypatch.setenv("LLM_ENDPOINT", "https://legacy.example/v1/chat/completions")
    monkeypatch.setenv("LLM_MODEL", "deepseek-r1:671b")
    monkeypatch.setenv("DEEPSEEK_R1_API_KEY", "legacy-r1-key")

    import app.config as config_module
    import services.private_api_config as private_config_module

    importlib.reload(config_module)
    importlib.reload(private_config_module)

    settings = config_module.get_settings()
    private_settings = private_config_module.get_backend_private_config()

    assert settings["active_llm_provider"] == "current"
    assert settings["llm_endpoint"] == "https://legacy.example/v1/chat/completions"
    assert settings["llm_model"] == "deepseek-r1:671b"
    assert settings["llm_api_key"] == "legacy-r1-key"

    assert private_settings["active_llm_provider"] == "current"
    assert private_settings["llm_endpoint"] == settings["llm_endpoint"]
    assert private_settings["llm_model"] == settings["llm_model"]
    assert private_settings["llm_api_key"] == settings["llm_api_key"]


def test_aliyun_provider_health_reports_active_profile(tmp_path, monkeypatch):
    _reset_llm_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'aliyun_health.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("ACTIVE_LLM_PROVIDER", "aliyun_dashscope")
    monkeypatch.setenv("ALIYUN_LLM_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    monkeypatch.setenv("ALIYUN_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("ALIYUN_LLM_API_KEY", "")

    import app.config as config_module
    from app.main import create_app

    importlib.reload(config_module)
    client = TestClient(create_app())

    health = client.get("/api/v1/health", headers={"X-API-Key": "mock-key-001"})
    assert health.status_code == 200
    payload = health.json()["data"]

    assert payload["active_llm_provider"] == "aliyun_dashscope"
    assert payload["llm_endpoint"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert payload["llm_model"] == "deepseek-v4-flash"
    assert payload["llm_enabled"] is False
