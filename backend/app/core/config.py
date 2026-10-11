from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings, read from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: SecretStr | None = None
    supabase_url: str = ""
    supabase_secret_key: SecretStr | None = None
    cors_origins: str = "http://localhost:3000"  # comma-separated

    # Product settings (PlaceChat Technical Design §11).
    message_max_length: int = 500
    rate_limit_max_messages: int = 5
    rate_limit_window_seconds: int = 10
    presence_timeout_seconds: int = 30
    nickname_hold_seconds: int = 60
    history_limit: int = 20
    message_retention_days: int = 7
    block_duration_options_minutes: tuple[int, ...] = (15, 60, 1440)
    sweeper_interval_seconds: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
