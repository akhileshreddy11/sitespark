from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    dry_run: bool = True
    database_url: str = "sqlite:///./sitespark.db"
    google_places_api_key: str = ""
    google_places_base_url: str = "https://places.googleapis.com/v1"
    google_maps_embed_api_key: str = ""
    google_places_cache_ttl_days: int = 30
    min_lead_score: int = 60
    max_place_details_per_run: int = 50
    max_estimated_cost_usd_micros_per_run: int = 5_000_000
    queue_mode: str = "local"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    demo_preview_base_url: str = "http://127.0.0.1:8000"
    demo_expiry_days: int = 14
    demo_max_retries: int = 3
    demo_deploy_enabled: bool = False
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""
    cloudflare_pages_project: str = ""
    cloudflare_preview_domain: str = ""
    screenshot_upload_url: str = ""
    screenshot_upload_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
