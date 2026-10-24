from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str = ""
    jwt_secret: str = ""
    api_key_pepper: str = ""
    jwt_ttl_minutes: int = 480
    login_rate_per_min: int = 10

    llm_backend: str = "ollama"          # ollama | openai (vLLM / OpenAI-compatible)
    llm_base_url: str = "http://ollama:11434"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_s: int = 300
    llm_num_ctx: int = 8192

    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_cpu: bool = True
    map_candidates_k: int = 8
    map_translate: bool = True
    map_margin: float = 0.05

    stt_url: str = "http://stt:9000"
    stt_timeout_s: int = 900
    stt_language: str = "id"

    audio_dir: str = "/audio"
    max_audio_mb: int = 200
    transcript_retention_days: int = 30
    vocab_dir: str = "config"

    gpu_timeshare: bool = False        # gilir VRAM: bongkar LLM saat merekam, bongkar STT sebelum LLM bekerja
    celery_eager: bool = False
    low_quality_reject_ratio: float = 0.3


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # dibaca dari environment variable
    return s


def require_secrets(s: Settings) -> None:
    for name in ("jwt_secret", "api_key_pepper"):
        v = getattr(s, name)
        if len(v) < 16 or v.startswith("CHANGE_ME"):
            raise RuntimeError(f"{name.upper()} belum diatur (minimal 16 karakter, bukan CHANGE_ME)")
