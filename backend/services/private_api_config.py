import os
from pathlib import Path


DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8787
DEFAULT_MOCK_API_KEY = "mock-key-001"
DEFAULT_ACTIVE_LLM_PROVIDER = "current"
DEFAULT_LLM_ENDPOINT = "https://genaiapi.shanghaitech.edu.cn/api/v1/start"
DEFAULT_LLM_MODEL = "deepseek-v3:671b"
DEFAULT_ALIYUN_LLM_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_ALIYUN_LLM_MODEL = "deepseek-v4-flash"

MODEL_API_KEY_ENV_MAP = {
    "GPT-5.2": "GPT52_API_KEY",
    "deepseek-v3:671b": "DEEPSEEK_V3_API_KEY",
    "deepseek-r1:671b": "DEEPSEEK_R1_API_KEY",
    "qwen-instruct": "QWEN_API_KEY",
    "qwen2.5-vl-instruct": "QWEN_VL_API_KEY",
}


_dotenv_loaded = False


def _load_dotenv(dotenv_path: Path):
    global _dotenv_loaded
    if _dotenv_loaded or not dotenv_path.exists():
        _dotenv_loaded = True
        return

    with dotenv_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    _dotenv_loaded = True


def _resolve_legacy_model_api_key(model_name: str) -> str:
    specific_key_env = MODEL_API_KEY_ENV_MAP.get(model_name, "")
    if specific_key_env:
        specific_key = os.getenv(specific_key_env, "").strip()
        if specific_key:
            return specific_key

    return (
        os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def _resolve_active_llm_provider() -> str:
    provider = os.getenv("ACTIVE_LLM_PROVIDER", "").strip().lower() or DEFAULT_ACTIVE_LLM_PROVIDER
    if provider in {"current", "aliyun_dashscope"}:
        return provider
    return DEFAULT_ACTIVE_LLM_PROVIDER


def _resolve_current_llm_profile() -> tuple[str, str, str]:
    model_name = os.getenv("CURRENT_LLM_MODEL", "").strip() or os.getenv("LLM_MODEL", "").strip() or DEFAULT_LLM_MODEL
    endpoint = os.getenv("CURRENT_LLM_ENDPOINT", "").strip() or os.getenv("LLM_ENDPOINT", "").strip() or DEFAULT_LLM_ENDPOINT
    api_key = os.getenv("CURRENT_LLM_API_KEY", "").strip() or _resolve_legacy_model_api_key(model_name)
    return endpoint, model_name, api_key


def _resolve_aliyun_llm_profile() -> tuple[str, str, str]:
    endpoint = os.getenv("ALIYUN_LLM_ENDPOINT", "").strip() or DEFAULT_ALIYUN_LLM_ENDPOINT
    model_name = os.getenv("ALIYUN_LLM_MODEL", "").strip() or DEFAULT_ALIYUN_LLM_MODEL
    api_key = (
        os.getenv("DASHSCOPE_API_KEY", "").strip()
        or os.getenv("ALIYUN_LLM_API_KEY", "").strip()
    )
    return endpoint, model_name, api_key


def get_backend_private_config():
    base_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(base_dir / ".env")

    active_llm_provider = _resolve_active_llm_provider()
    if active_llm_provider == "aliyun_dashscope":
        llm_endpoint, llm_model, llm_api_key = _resolve_aliyun_llm_profile()
    else:
        llm_endpoint, llm_model, llm_api_key = _resolve_current_llm_profile()

    return {
        "host": os.getenv("BACKEND_HOST", "").strip() or DEFAULT_BACKEND_HOST,
        "port": int(os.getenv("BACKEND_PORT", "").strip() or DEFAULT_BACKEND_PORT),
        "mock_api_key": os.getenv("MOCK_API_KEY", "").strip() or DEFAULT_MOCK_API_KEY,
        "mock_key_source": "env" if os.getenv("MOCK_API_KEY", "").strip() else "fallback",
        "active_llm_provider": active_llm_provider,
        "llm_endpoint": llm_endpoint,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
    }
