from app.core.config import Settings
from app.core.db import normalize_database_url


def test_cors_origins_are_split_on_commas() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://placechat.vercel.app,")

    assert settings.cors_origin_list == ["http://localhost:3000", "https://placechat.vercel.app"]


def test_product_settings_match_design_doc() -> None:
    settings = Settings(_env_file=None)  # ignore a developer's local .env overrides

    assert settings.message_max_length == 500
    assert (settings.rate_limit_max_messages, settings.rate_limit_window_seconds) == (5, 10)
    assert settings.nickname_hold_seconds == 60


def test_supabase_url_gets_psycopg_driver() -> None:
    url = "postgresql://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres"

    assert normalize_database_url(url).startswith("postgresql+psycopg://postgres.ref:pw@")
    assert normalize_database_url("postgresql+psycopg://x") == "postgresql+psycopg://x"
