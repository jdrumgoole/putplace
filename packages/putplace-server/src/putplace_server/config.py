"""Application configuration.

Configuration priority (highest to lowest):
1. Environment variables
2. ppserver.toml file
3. Default values
"""

import os
import secrets
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
    1. PUTPLACE_CONFIG environment variable (if set)
    2. ./ppserver.toml (current directory)
    3. ~/.config/putplace/ppserver.toml (user config)
    4. /etc/putplace/ppserver.toml (system config)

    Returns:
        Path to config file if found, None otherwise
    """
    # Check environment variable first
    env_config = os.environ.get("PUTPLACE_CONFIG")
    if env_config:
        env_path = Path(env_config)
        if env_path.exists() and env_path.is_file():
            return env_path
        # If PUTPLACE_CONFIG is set but file doesn't exist, log warning but continue searching
        import logging
        logging.warning(f"PUTPLACE_CONFIG set to {env_config} but file not found, searching standard locations")

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

        # OAuth settings
        if "oauth" in toml_data:
            oauth = toml_data["oauth"]
            if "google_client_id" in oauth:
                config["google_client_id"] = oauth["google_client_id"]
            if "google_client_secret" in oauth:
                config["google_client_secret"] = oauth["google_client_secret"]

        # Email settings
        if "email" in toml_data:
            email = toml_data["email"]
            if "sender_email" in email:
                config["sender_email"] = email["sender_email"]
            if "base_url" in email:
                config["base_url"] = email["base_url"]
            if "aws_region" in email:
                config["email_aws_region"] = email["aws_region"]

        # Server settings
        if "server" in toml_data:
            server = toml_data["server"]
            if "registration_enabled" in server:
                config["registration_enabled"] = server["registration_enabled"]

        # JWT settings
        if "jwt" in toml_data:
            jwt = toml_data["jwt"]
            if "jwt_secret_key" in jwt:
                config["jwt_secret_key"] = jwt["jwt_secret_key"]
            if "jwt_algorithm" in jwt:
                config["jwt_algorithm"] = jwt["jwt_algorithm"]
            if "jwt_access_token_expire_minutes" in jwt:
                config["jwt_access_token_expire_minutes"] = jwt["jwt_access_token_expire_minutes"]

        # CORS settings
        if "cors" in toml_data:
            cors = toml_data["cors"]
            if "allow_origins" in cors:
                config["cors_allow_origins"] = cors["allow_origins"]
            if "allow_credentials" in cors:
                config["cors_allow_credentials"] = cors["allow_credentials"]
            if "allow_methods" in cors:
                config["cors_allow_methods"] = cors["allow_methods"]
            if "allow_headers" in cors:
                config["cors_allow_headers"] = cors["allow_headers"]

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
    2. ppserver.toml file (search order below)
    3. Default values defined below

    Config file search order (PUTPLACE_CONFIG overrides):
    - PUTPLACE_CONFIG environment variable (if set, takes highest priority)
    - ./ppserver.toml (current directory)
    - ~/.config/putplace/ppserver.toml (user config)
    - /etc/putplace/ppserver.toml (system config)
    """

    mongodb_url: str
    mongodb_database: str
    mongodb_collection: str

    # API settings
    api_title: str
    api_version: str = __version__
    api_description: str

    # Storage settings
    storage_backend: str
    storage_path: str

    # S3 storage settings (only used if storage_backend="s3")
    s3_bucket_name: Optional[str] = None
    s3_region_name: str = "us-east-1"
    s3_prefix: str = "files/"

    # AWS credentials (OPTIONAL - see SECURITY.md for best practices)
    aws_profile: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # OAuth settings
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # Email settings for SES
    sender_email: str = "noreply@putplace.org"
    base_url: str = "http://localhost:8000"
    email_aws_region: str = "eu-west-1"

    # Registration control
    registration_enabled: bool = True  # Set to False to disable new user registration

    # JWT settings
    jwt_secret_key: str = ""  # Will be auto-generated if not set
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # CORS settings
    cors_allow_origins: list[str] = ["*"]  # List of allowed origins, ["*"] allows all
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]  # ["GET", "POST", "PUT", "DELETE"] or ["*"]
    cors_allow_headers: list[str] = ["*"]

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables (e.g., PUTPLACE_API_KEY for client)
    )

    def __init__(self, **kwargs):
        """Initialize settings with priority: env vars > TOML > defaults."""
        # Load TOML config
        toml_config = load_toml_config()

        # Helper to get value with priority: explicit kwarg > env var > TOML > default
        def get_value(key: str, default: Any = None) -> Any:
            # 1. Check if explicitly passed as kwarg
            if key in kwargs:
                return kwargs[key]
            # 2. Check environment variable (uppercase)
            env_val = os.getenv(key.upper())
            if env_val is not None:
                return env_val
            # 3. Check TOML config
            if key in toml_config:
                return toml_config[key]
            # 4. Use default
            return default

        # Build values dict with proper priority
        values = {
            "mongodb_url": get_value("mongodb_url", "mongodb://localhost:27017"),
            "mongodb_database": get_value("mongodb_database", "putplace"),
            "mongodb_collection": get_value("mongodb_collection", "file_metadata"),
            "api_title": get_value("api_title", "PutPlace API"),
            "api_description": get_value("api_description", "File metadata storage API"),
            "storage_backend": get_value("storage_backend", "local"),
            "storage_path": get_value("storage_path", "/var/putplace/files"),
            "s3_bucket_name": get_value("s3_bucket_name"),
            "s3_region_name": get_value("s3_region_name", "us-east-1"),
            "s3_prefix": get_value("s3_prefix", "files/"),
            "aws_profile": get_value("aws_profile"),
            "aws_access_key_id": get_value("aws_access_key_id"),
            "aws_secret_access_key": get_value("aws_secret_access_key"),
            "google_client_id": get_value("google_client_id"),
            "google_client_secret": get_value("google_client_secret"),
            "sender_email": get_value("sender_email", "noreply@putplace.org"),
            "base_url": get_value("base_url", "http://localhost:8000"),
            "email_aws_region": get_value("email_aws_region", "eu-west-1"),
        }

        # JWT settings - generate secure random key if not provided
        jwt_secret = get_value("jwt_secret_key")
        if not jwt_secret:
            # Generate a secure random key (32 bytes = 256 bits)
            jwt_secret = secrets.token_urlsafe(32)
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY not set in environment or config. "
                "Generated random key for this session. "
                "Set JWT_SECRET_KEY environment variable for production!",
                UserWarning
            )

        values.update({
            "jwt_secret_key": jwt_secret,
            "jwt_algorithm": get_value("jwt_algorithm", "HS256"),
            "jwt_access_token_expire_minutes": int(get_value("jwt_access_token_expire_minutes", 1440)),
        })

        # CORS settings
        values.update({
            "cors_allow_origins": get_value("cors_allow_origins", ["*"]),
            "cors_allow_credentials": get_value("cors_allow_credentials", True),
            "cors_allow_methods": get_value("cors_allow_methods", ["*"]),
            "cors_allow_headers": get_value("cors_allow_headers", ["*"]),
        })

        # Merge with any remaining kwargs
        values.update({k: v for k, v in kwargs.items() if k not in values})

        super().__init__(**values)


# Create settings instance
# Pydantic Settings priority (highest to lowest):
# 1. Constructor arguments (not used here)
# 2. Environment variables
# 3. Defaults in class definition
# Since we're not passing any constructor args, env vars will naturally override defaults
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings
