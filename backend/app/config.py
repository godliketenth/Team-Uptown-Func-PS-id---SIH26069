from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    scheduler_interval_seconds: int = 8
    scheduler_enabled: bool = True

    open_meteo_enabled: bool = True
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_timeout_seconds: float = 4.0

    raw_lake_dir: str = "./data/raw"
    # S3-compatible object store for the raw lake (Phase 3.2). Empty endpoint
    # keeps the local filesystem backend, so the project still runs with no
    # infrastructure at all.
    s3_endpoint_url: str = ""
    s3_bucket: str = "nwap-raw"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    # Live news RSS (Phase 4.1). Real content, no API key. Off switch exists
    # because it is an outbound network call and a demo may need to run
    # offline.
    news_rss_enabled: bool = True
    news_rss_timeout_seconds: float = 12.0

    # Kafka transport (Phase 3.1). Empty = in-process asyncio queue, which is
    # the default because the load test put the bottleneck in outbound HTTP,
    # not in the transport.
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = "nwap.raw-events"

    @property
    def kafka_enabled(self) -> bool:
        return bool(self.kafka_bootstrap_servers)

    @property
    def s3_enabled(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key and self.s3_secret_key)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Alembic runs sync; strip the async driver."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
