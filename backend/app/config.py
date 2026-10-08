from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Auth
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database
    database_url: str = "sqlite:///./factcheck.db"

    # Search sources
    serpapi_key: str = ""
    newsapi_key: str = ""

    # AI summary
    groq_api_key: str = ""

    # Image / audio
    huggingface_api_key: str = ""
    assemblyai_api_key: str = ""

    # Groq model to use for the AI summary. Groq's free-tier model lineup
    # changes periodically -- if you see a "model_not_found" error, check
    # https://console.groq.com/docs/models for the current list and update
    # this value (or set GROQ_MODEL in .env) instead of editing code.
    groq_model: str = "openai/gpt-oss-20b"

    # Scraping / cache
    # Scrape more than the top 10 candidate results for deeper corroboration
    # (rather than the old top-3), and keep enough of them cached to avoid
    # redundant re-scraping.
    scrape_top_n: int = 15
    scrape_cache_size: int = 30
    scrape_timeout_seconds: int = 8

    # Rate limits
    guest_rate_limit: str = "3/hour"
    user_rate_limit: str = "15/minute"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
