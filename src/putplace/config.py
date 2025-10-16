"""Application configuration.

Configuration priority (highest to lowest):
1. Environment variables
2. ppserver.toml file
3. .env file
4. Default values
"""

import sys
from pathlib import Path
from typing import Any, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from .version import __version__

# Import tomli for Python < 3.11, tomllib for Python >= 3.11
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


def find_config_file() -> Optional[Path]:
    """Find ppserver.toml file in standard locations.

    Search order:
    1. ./ppserver.toml (current directory)
    2. ~/.config/putplace/ppserver.toml (user config)
    3. /etc/putplace/ppserver.toml (system config)

    Returns:
        Path to config file if found, None otherwise
    """
    search_paths = [
        Path.cwd() / "ppserver.toml",
        Path.home() / ".config" / "putplace" / "ppserver.toml",
        Path("/etc/putplace/ppserver.toml"),
    ]

    for path in search_paths:
        if path.exists() and path.is_file():
            return path

    return None


def load_toml_config() -> dict[str, Any]:
    """Load configuration from TOML file.

    Returns:
        Dictionary with configuration values, empty dict if no config file found
    """
    if tomllib is None:
        return {}

    config_file = find_config_file()
    if config_file is None:
        return {}

    try:
        with open(config_file, "rb") as f:
            toml_data = tomllib.load(f)

        # Flatten nested TOML structure to match Settings field names
        config = {}

        # Database settings
        if "database" in toml_data:
            db = toml_data["database"]
            if "mongodb_url" in db:
                config["mongodb_url"] = db["mongodb_url"]
            if "mongodb_database" in db:
                config["mongodb_database"] = db["mongodb_database"]
            if "mongodb_collection" in db:
                config["mongodb_collection"] = db["mongodb_collection"]

        # API settings
        if "api" in toml_data:
            api = toml_data["api"]
            if "title" in api:
                config["api_title"] = api["title"]
            if "description" in api:
                config["api_description"] = api["description"]

        # Storage settings
        if "storage" in toml_data:
            storage = toml_data["storage"]
            if "backend" in storage:
                config["storage_backend"] = storage["backend"]
            if "path" in storage:
                config["storage_path"] = storage["path"]
            if "s3_bucket_name" in storage:
                config["s3_bucket_name"] = storage["s3_bucket_name"]
            if "s3_region_name" in storage:
                config["s3_region_name"] = storage["s3_region_name"]
            if "s3_prefix" in storage:
                config["s3_prefix"] = storage["s3_prefix"]

        # AWS settings
        if "aws" in toml_data:
            aws = toml_data["aws"]
            if "profile" in aws:
                config["aws_profile"] = aws["profile"]
            if "access_key_id" in aws:
                config["aws_access_key_id"] = aws["access_key_id"]
            if "secret_access_key" in aws:
                config["aws_secret_access_key"] = aws["secret_access_key"]

        return config

    except Exception as e:
        # If there's an error reading TOML, just return empty config
        # Environment variables and defaults will still work
        import logging
        logging.warning(f"Failed to load TOML config from {config_file}: {e}")
        return {}


class Settings(BaseSettings):
    """Application settings.

    Configuration is loaded in this priority order (highest to lowest):
    1. Environment variables (e.g., MONGODB_URL, STORAGE_BACKEND)
    2. ppserver.toml file (./ppserver.toml, ~/.config/putplace/ppserver.toml, /etc/putplace/ppserver.toml)
    3. .env file (for backward compatibility)
    4. Default values defined below
    """

    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "putplace"
    mongodb_collection: str = "file_metadata"

    # API settings
    api_title: str = "PutPlace API"
    api_version: str = __version__
    api_description: str = "File metadata storage API"

    # Storage settings
    storage_backend: str = "local"  # "local" or "s3"
    storage_path: str = "/var/putplace/files"  # For local storage

    # S3 storage settings (only used if storage_backend="s3")
    s3_bucket_name: Optional[str] = None
    s3_region_name: str = "us-east-1"
    s3_prefix: str = "files/"

    # AWS credentials (OPTIONAL - see SECURITY.md for best practices)
    # If not specified, boto3 will use standard credential chain:
    # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    # 2. AWS credentials file (~/.aws/credentials)
    # 3. IAM role (if running on EC2/ECS/Lambda) - RECOMMENDED
    aws_profile: Optional[str] = None  # Use specific profile from ~/.aws/credentials
    aws_access_key_id: Optional[str] = None  # NOT RECOMMENDED: use IAM roles or profiles instead
    aws_secret_access_key: Optional[str] = None  # NOT RECOMMENDED: use IAM roles or profiles instead

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables (e.g., PUTPLACE_API_KEY for client)
    )


# Load TOML config first, then create Settings (env vars will override)
_toml_config = load_toml_config()
settings = Settings(**_toml_config)
