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
# DeepSeek 官方 API（OpenAI 兼容）
# 官网: https://platform.deepseek.com
# 在 platform.deepseek.com → API Keys 获取 key
DEFAULT_DEEPSEEK_LLM_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_DEEPSEEK_LLM_MODEL = "deepseek-chat"
DEFAULT_DATABASE_URL = "sqlite:///backend/data/app.db"
DEFAULT_RESET_ON_SERVER_START = False
DEFAULT_SIMULATOR_ENABLED = True
DEFAULT_SIMULATOR_TICK_SECONDS = 3.0
DEFAULT_SIMULATOR_SPAWN_INTERVAL_SECONDS = 8.0
DEFAULT_SIMULATOR_MAX_ACTIVE_PATIENTS = 2
DEFAULT_SIMULATOR_QUEUE_WAIT_SECONDS = 6.0
DEFAULT_SIMULATOR_CONSULT_SECONDS = 9.0
DEFAULT_OPENEMR_ENABLED = False
DEFAULT_OPENEMR_BASE_URL = "http://localhost:8080"
DEFAULT_OPENEMR_API_BASE_PATH = "/apis/default/fhir"
DEFAULT_OPENEMR_TIMEOUT_SECONDS = 10
DEFAULT_OPENEMR_VERIFY_SSL = False
DEFAULT_OPENEMR_DRY_RUN = True
DEFAULT_OPENEMR_OAUTH_ENABLED = True
DEFAULT_OPENEMR_OAUTH_SCOPE = "api:fhir user/Patient.write user/DocumentReference.write"
DEFAULT_OPENEMR_OAUTH_USE_BASIC_FALLBACK = True
DEFAULT_OPENEMR_OUTBOUND_LOG_PATH = "backend/data/openemr_outbound_payloads.log"
DEFAULT_OPENEMR_PREPARED_LOG_PATH = "backend/data/openemr_prepared_payloads.log"
DEFAULT_REDIS_MIRROR_ENABLED = True
DEFAULT_HOSPITAL_REDIS_HOST = "127.0.0.1"
DEFAULT_HOSPITAL_REDIS_PORT = 6379
DEFAULT_HOSPITAL_REDIS_DB = 0
DEFAULT_HOSPITAL_REDIS_CHANNEL_PREFIX = "hospital"
DEFAULT_HOSPITAL_REDIS_DURABLE_STREAM_ENABLED = False
DEFAULT_HOSPITAL_REDIS_DURABLE_STREAM_KEY = "hospital:journal"
DEFAULT_EVENT_PRODUCER = "groupA.outpatient"
DEFAULT_STATE_DEBUG_ENABLED = True
DEFAULT_STATE_DEBUG_ALLOW_FORCE = True
DEFAULT_FULLVIEW_SYNC_ENABLED = False
DEFAULT_FULLVIEW_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FULLVIEW_TIMEOUT_SECONDS = 5.0
DEFAULT_FULLVIEW_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_FULLVIEW_MAX_ATTEMPTS = 8
DEFAULT_FULLVIEW_STEP_GATE_ENABLED = False
DEFAULT_FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER = 1.0
DEFAULT_FULLVIEW_DISCHARGE_LINGER_SECONDS = 30.0
DEFAULT_FULLVIEW_EVENT_LISTENER_INTERVAL_SECONDS = 0.5
DEFAULT_FULLVIEW_EVENT_OBSERVE_TIMEOUT_SECONDS = 30.0
DEFAULT_FULLVIEW_ADMISSION_GAP_SECONDS = 4.0
DEFAULT_FULLVIEW_CLEANUP_IDLE_SECONDS = 3.0

MODEL_API_KEY_ENV_MAP = {
    "GPT-5.2": "GPT52_API_KEY",
    "deepseek-v3:671b": "DEEPSEEK_V3_API_KEY",
    "deepseek-r1:671b": "DEEPSEEK_R1_API_KEY",
    "deepseek-chat": "DEEPSEEK_API_KEY",
    "deepseek-reasoner": "DEEPSEEK_API_KEY",
    "qwen-instruct": "QWEN_API_KEY",
    "qwen2.5-vl-instruct": "QWEN_VL_API_KEY",
}

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


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    normalized = value.strip()
    if not normalized:
        return default
    try:
        return int(normalized)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    normalized = value.strip()
    if not normalized:
        return default
    try:
        return float(normalized)
    except ValueError:
        return default


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
    if provider in {"current", "aliyun_dashscope", "deepseek_official"}:
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


def _resolve_deepseek_llm_profile() -> tuple[str, str, str]:
    """DeepSeek 官方 API（OpenAI 兼容接口）

    endpoint: https://api.deepseek.com/v1/chat/completions
    model: deepseek-chat (V3) 或 deepseek-reasoner (R1)
    api_key: 从 https://platform.deepseek.com/api_keys 获取
    """
    endpoint = os.getenv("DEEPSEEK_LLM_ENDPOINT", "").strip() or DEFAULT_DEEPSEEK_LLM_ENDPOINT
    model_name = os.getenv("DEEPSEEK_LLM_MODEL", "").strip() or DEFAULT_DEEPSEEK_LLM_MODEL
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return endpoint, model_name, api_key


def get_settings() -> dict:
    base_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(base_dir / ".env")

    active_llm_provider = _resolve_active_llm_provider()
    if active_llm_provider == "aliyun_dashscope":
        llm_endpoint, llm_model, llm_api_key = _resolve_aliyun_llm_profile()
    elif active_llm_provider == "deepseek_official":
        llm_endpoint, llm_model, llm_api_key = _resolve_deepseek_llm_profile()
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
        "database_url": os.getenv("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        "reset_on_server_start": _parse_bool(
            os.getenv("RESET_ON_SERVER_START"),
            DEFAULT_RESET_ON_SERVER_START,
        ),
        "simulator_enabled": _parse_bool(
            os.getenv("SIMULATOR_ENABLED"),
            DEFAULT_SIMULATOR_ENABLED,
        ),
        "simulator_tick_seconds": _parse_float(
            os.getenv("SIMULATOR_TICK_SECONDS"),
            DEFAULT_SIMULATOR_TICK_SECONDS,
        ),
        "simulator_spawn_interval_seconds": _parse_float(
            os.getenv("SIMULATOR_SPAWN_INTERVAL_SECONDS"),
            DEFAULT_SIMULATOR_SPAWN_INTERVAL_SECONDS,
        ),
        "simulator_max_active_patients": max(
            1,
            _parse_int(
                os.getenv("SIMULATOR_MAX_ACTIVE_PATIENTS"),
                DEFAULT_SIMULATOR_MAX_ACTIVE_PATIENTS,
            ),
        ),
        "simulator_queue_wait_seconds": _parse_float(
            os.getenv("SIMULATOR_QUEUE_WAIT_SECONDS"),
            DEFAULT_SIMULATOR_QUEUE_WAIT_SECONDS,
        ),
        "simulator_consult_seconds": _parse_float(
            os.getenv("SIMULATOR_CONSULT_SECONDS"),
            DEFAULT_SIMULATOR_CONSULT_SECONDS,
        ),
        "openemr_enabled": _parse_bool(
            os.getenv("OPENEMR_ENABLED"),
            DEFAULT_OPENEMR_ENABLED,
        ),
        "openemr_base_url": os.getenv("OPENEMR_BASE_URL", "").strip() or DEFAULT_OPENEMR_BASE_URL,
        "openemr_api_base_path": os.getenv("OPENEMR_API_BASE_PATH", "").strip() or DEFAULT_OPENEMR_API_BASE_PATH,
        "openemr_client_id": os.getenv("OPENEMR_CLIENT_ID", "").strip() or None,
        "openemr_client_secret": os.getenv("OPENEMR_CLIENT_SECRET", "").strip() or None,
        "openemr_oauth_enabled": _parse_bool(
            os.getenv("OPENEMR_OAUTH_ENABLED"),
            DEFAULT_OPENEMR_OAUTH_ENABLED,
        ),
        "openemr_oauth_discovery_url": os.getenv("OPENEMR_OAUTH_DISCOVERY_URL", "").strip() or None,
        "openemr_oauth_token_url": os.getenv("OPENEMR_OAUTH_TOKEN_URL", "").strip() or None,
        "openemr_oauth_scope": os.getenv("OPENEMR_OAUTH_SCOPE", "").strip() or DEFAULT_OPENEMR_OAUTH_SCOPE,
        "openemr_oauth_audience": os.getenv("OPENEMR_OAUTH_AUDIENCE", "").strip() or None,
        "openemr_oauth_use_basic_fallback": _parse_bool(
            os.getenv("OPENEMR_OAUTH_USE_BASIC_FALLBACK"),
            DEFAULT_OPENEMR_OAUTH_USE_BASIC_FALLBACK,
        ),
        "openemr_username": os.getenv("OPENEMR_USERNAME", "").strip() or None,
        "openemr_password": os.getenv("OPENEMR_PASSWORD", "").strip() or None,
        "openemr_timeout_seconds": max(
            1,
            _parse_int(
                os.getenv("OPENEMR_TIMEOUT_SECONDS"),
                DEFAULT_OPENEMR_TIMEOUT_SECONDS,
            ),
        ),
        "openemr_verify_ssl": _parse_bool(
            os.getenv("OPENEMR_VERIFY_SSL"),
            DEFAULT_OPENEMR_VERIFY_SSL,
        ),
        "openemr_dry_run": _parse_bool(
            os.getenv("OPENEMR_DRY_RUN"),
            DEFAULT_OPENEMR_DRY_RUN,
        ),
        "openemr_outbound_log_path": os.getenv("OPENEMR_OUTBOUND_LOG_PATH", "").strip() or DEFAULT_OPENEMR_OUTBOUND_LOG_PATH,
        "openemr_prepared_log_path": os.getenv("OPENEMR_PREPARED_LOG_PATH", "").strip() or DEFAULT_OPENEMR_PREPARED_LOG_PATH,
        "redis_mirror_enabled": _parse_bool(
            os.getenv("REDIS_MIRROR_ENABLED"),
            DEFAULT_REDIS_MIRROR_ENABLED,
        ),
        "hospital_redis_host": os.getenv("HOSPITAL_REDIS_HOST", "").strip() or DEFAULT_HOSPITAL_REDIS_HOST,
        "hospital_redis_port": max(
            1,
            _parse_int(
                os.getenv("HOSPITAL_REDIS_PORT"),
                DEFAULT_HOSPITAL_REDIS_PORT,
            ),
        ),
        "hospital_redis_db": max(
            0,
            _parse_int(
                os.getenv("HOSPITAL_REDIS_DB"),
                DEFAULT_HOSPITAL_REDIS_DB,
            ),
        ),
        "hospital_redis_password": os.getenv("HOSPITAL_REDIS_PASSWORD", "").strip() or None,
        "hospital_redis_channel_prefix": os.getenv("HOSPITAL_REDIS_CHANNEL_PREFIX", "").strip() or DEFAULT_HOSPITAL_REDIS_CHANNEL_PREFIX,
        "hospital_redis_durable_stream_enabled": _parse_bool(
            os.getenv("HOSPITAL_REDIS_DURABLE_STREAM_ENABLED"),
            DEFAULT_HOSPITAL_REDIS_DURABLE_STREAM_ENABLED,
        ),
        "hospital_redis_durable_stream_key": os.getenv("HOSPITAL_REDIS_DURABLE_STREAM_KEY", "").strip() or DEFAULT_HOSPITAL_REDIS_DURABLE_STREAM_KEY,
        "event_producer": os.getenv("EVENT_PRODUCER", "").strip() or DEFAULT_EVENT_PRODUCER,
        "state_debug_enabled": _parse_bool(
            os.getenv("STATE_DEBUG_ENABLED"),
            DEFAULT_STATE_DEBUG_ENABLED,
        ),
        "state_debug_allow_force": _parse_bool(
            os.getenv("STATE_DEBUG_ALLOW_FORCE"),
            DEFAULT_STATE_DEBUG_ALLOW_FORCE,
        ),
        "fullview_sync_enabled": _parse_bool(
            os.getenv("FULLVIEW_SYNC_ENABLED"),
            DEFAULT_FULLVIEW_SYNC_ENABLED,
        ),
        "fullview_base_url": os.getenv("FULLVIEW_BASE_URL", "").strip() or DEFAULT_FULLVIEW_BASE_URL,
        "fullview_timeout_seconds": max(
            0.1,
            _parse_float(
                os.getenv("FULLVIEW_TIMEOUT_SECONDS"),
                DEFAULT_FULLVIEW_TIMEOUT_SECONDS,
            ),
        ),
        "fullview_poll_interval_seconds": max(
            0.1,
            _parse_float(
                os.getenv("FULLVIEW_POLL_INTERVAL_SECONDS"),
                DEFAULT_FULLVIEW_POLL_INTERVAL_SECONDS,
            ),
        ),
        "fullview_max_attempts": max(
            1,
            _parse_int(
                os.getenv("FULLVIEW_MAX_ATTEMPTS"),
                DEFAULT_FULLVIEW_MAX_ATTEMPTS,
            ),
        ),
        "fullview_step_gate_enabled": _parse_bool(
            os.getenv("FULLVIEW_STEP_GATE_ENABLED"),
            DEFAULT_FULLVIEW_STEP_GATE_ENABLED,
        ),
        "fullview_visual_cooldown_multiplier": max(
            1.0,
            _parse_float(
                os.getenv("FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER"),
                DEFAULT_FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER,
            ),
        ),
        "fullview_discharge_linger_seconds": max(
            0.0,
            _parse_float(
                os.getenv("FULLVIEW_DISCHARGE_LINGER_SECONDS"),
                DEFAULT_FULLVIEW_DISCHARGE_LINGER_SECONDS,
            ),
        ),
        "fullview_event_listener_interval_seconds": max(
            0.1,
            _parse_float(
                os.getenv("FULLVIEW_EVENT_LISTENER_INTERVAL_SECONDS"),
                DEFAULT_FULLVIEW_EVENT_LISTENER_INTERVAL_SECONDS,
            ),
        ),
        "fullview_event_observe_timeout_seconds": max(
            1.0,
            _parse_float(
                os.getenv("FULLVIEW_EVENT_OBSERVE_TIMEOUT_SECONDS"),
                DEFAULT_FULLVIEW_EVENT_OBSERVE_TIMEOUT_SECONDS,
            ),
        ),
        "fullview_admission_gap_seconds": max(
            0.0,
            _parse_float(
                os.getenv("FULLVIEW_ADMISSION_GAP_SECONDS"),
                DEFAULT_FULLVIEW_ADMISSION_GAP_SECONDS,
            ),
        ),
        "fullview_cleanup_idle_seconds": max(
            0.0,
            _parse_float(
                os.getenv("FULLVIEW_CLEANUP_IDLE_SECONDS"),
                DEFAULT_FULLVIEW_CLEANUP_IDLE_SECONDS,
            ),
        ),
    }
