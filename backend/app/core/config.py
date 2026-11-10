"""Application settings.

All values can be overridden with environment variables prefixed with ``BI_``
(for example ``BI_DATABASE_URL``). List values use JSON syntax, e.g.
``BI_PROVIDERS='["blockstream","mempool"]'``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.2.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BI_", env_file=".env", extra="ignore")

    app_name: str = "BITCOIN INTELLIGENCE"
    environment: str = "development"
    log_level: str = "INFO"

    # Persistence. SQLite is the zero-config default for local development;
    # docker-compose sets a PostgreSQL URL (postgresql+asyncpg://...).
    database_url: str = "sqlite+aiosqlite:///./bitcoin_intelligence.db"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Data providers, in priority order. The first healthy provider that
    # supports an operation is used; the rest act as automatic fallback.
    providers: list[str] = ["mempool", "blockstream"]
    mempool_base_url: str = "https://mempool.space/api"
    blockstream_base_url: str = "https://blockstream.info/api"

    http_timeout_s: float = 10.0
    http_max_retries: int = 2
    provider_failure_threshold: int = 3
    provider_cooldown_s: float = 30.0

    # Background ingestion (stores block history + network snapshots).
    ingestion_enabled: bool = True
    ingestion_interval_s: int = 60
    ingestion_backfill_blocks: int = 144  # ~1 day of blocks
    ingestion_max_pages_per_run: int = 20

    # Basic abuse protection for the public API (per client IP).
    rate_limit_per_minute: int = 240

    # Whale Tracker. Transactions whose total output value is at or above
    # ``whale_min_btc`` are stored. Tiers classify them by volume (BTC).
    whale_tracking_enabled: bool = True
    whale_interval_s: int = 30
    whale_min_btc: float = 100.0
    whale_tiers_btc: list[float] = [100.0, 1_000.0, 10_000.0]
    whale_max_blocks_per_cycle: int = 6
    whale_enrich_per_cycle: int = 20

    # Write endpoints (alert rules). Required in any non-development
    # environment; in development, writes are allowed without a key.
    admin_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
