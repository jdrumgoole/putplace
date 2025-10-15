"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "putplace"
    mongodb_collection: str = "file_metadata"

    # API settings
    api_title: str = "PutPlace API"
    api_version: str = "0.1.0"
    api_description: str = "File metadata storage API"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
