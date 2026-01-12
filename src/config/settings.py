"""Application settings and configuration."""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://scraper:password@localhost:5432/competitor_data",
        description="PostgreSQL connection URL"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # Encryption
    encryption_key: str = Field(
        default="",
        description="Fernet encryption key for storing credentials"
    )

    # Application
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="Africa/Cairo")

    # Tager elSaada credentials
    tager_elsaada_username: Optional[str] = None
    tager_elsaada_password: Optional[str] = None
    tager_elsaada_base_url: str = Field(
        default="https://api.tagerelsaada.com",  # Placeholder - update after API discovery
        description="Tager elSaada API base URL"
    )

    # Ben Soliman credentials
    ben_soliman_username: Optional[str] = None
    ben_soliman_password: Optional[str] = None
    ben_soliman_base_url: str = Field(
        default="https://api.bensoliman.com",  # Placeholder - update after API discovery
        description="Ben Soliman API base URL"
    )

    # Rate limiting
    requests_per_second: float = Field(default=1.5)
    burst_size: int = Field(default=3)

    # Request timing (anti-detection)
    min_request_delay: float = Field(default=0.5)
    max_request_delay: float = Field(default=2.0)
    min_page_delay: float = Field(default=1.0)
    max_page_delay: float = Field(default=3.5)

    # Retry settings
    max_retries: int = Field(default=3)
    retry_min_wait: int = Field(default=2)
    retry_max_wait: int = Field(default=30)

    # Session settings
    session_timeout: float = Field(default=30.0)
    max_connections: int = Field(default=10)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
