from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Resume Analyzer API"
    app_version: str = "1.0.0"
    debug: bool = False

    spacy_model: str = "en_core_web_sm"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"
    gemini_timeout_seconds: int = 45
    gemini_fallback_enabled: bool = True

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "resumes"
    supabase_strict: bool = False

    max_upload_size_mb: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_write_key)

    @property
    def supabase_write_key(self) -> str:
        if self.supabase_service_role_key:
            return self.supabase_service_role_key
        return self.supabase_key

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "dev", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return bool(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
