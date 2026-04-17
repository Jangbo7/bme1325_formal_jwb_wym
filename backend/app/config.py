import os
from pathlib import Path


DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8787
DEFAULT_MOCK_API_KEY = "mock-key-001"
DEFAULT_LLM_ENDPOINT = "https://genaiapi.shanghaitech.edu.cn/api/v1/start"
DEFAULT_LLM_MODEL = "GPT-5.2"
DEFAULT_DATABASE_URL = "sqlite:///backend/data/app.db"

_DOTENV_LOADED = False


def _load_dotenv(dotenv_path: Path) -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED or not dotenv_path.exists():
        _DOTENV_LOADED = True
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

    _DOTENV_LOADED = True


def get_settings() -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(base_dir / ".env")

    llm_api_key = (
        os.getenv("GPT52_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )

    return {
        "host": os.getenv("BACKEND_HOST", "").strip() or DEFAULT_BACKEND_HOST,
        "port": int(os.getenv("BACKEND_PORT", "").strip() or DEFAULT_BACKEND_PORT),
        "mock_api_key": os.getenv("MOCK_API_KEY", "").strip() or DEFAULT_MOCK_API_KEY,
        "mock_key_source": "env" if os.getenv("MOCK_API_KEY", "").strip() else "fallback",
        "llm_endpoint": os.getenv("LLM_ENDPOINT", "").strip() or DEFAULT_LLM_ENDPOINT,
        "llm_model": os.getenv("LLM_MODEL", "").strip() or DEFAULT_LLM_MODEL,
        "llm_api_key": llm_api_key,
        "database_url": os.getenv("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        "reset_on_server_start": os.getenv("RESET_ON_SERVER_START", "").strip().lower() in ("1", "true", "yes"),
    }
