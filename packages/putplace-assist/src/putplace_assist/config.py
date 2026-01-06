"""Configuration for putplace-assist daemon."""

import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Cache for config file path
_config_file_path: Optional[Path] = None


def find_config_file() -> Optional[Path]:
    """Find configuration file in standard locations.

    Search order:
    1. PPASSIST_CONFIG environment variable
    2. ./pp_assist.toml (current directory)
    3. ~/.config/putplace/pp_assist.toml (user config)
    4. /etc/putplace/pp_assist.toml (system config)
    """
    # Check environment variable first
    env_config = os.environ.get("PPASSIST_CONFIG")
    if env_config:
        path = Path(env_config)
        if path.exists():
            return path

    # Check standard locations
    locations = [
        Path("pp_assist.toml"),
        Path.home() / ".config" / "putplace" / "pp_assist.toml",
        Path("/etc/putplace/pp_assist.toml"),
    ]

    for path in locations:
        if path.exists():
            return path

    return None


def load_toml_config() -> dict:
    """Load configuration from TOML file."""
    global _config_file_path

    config_path = find_config_file()
    if not config_path:
        return {}

    # Cache the config file path for later reference
    _config_file_path = config_path

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Flatten nested config for pydantic-settings
    flat = {}

    # Server settings
    if "server" in config:
        for key, value in config["server"].items():
            flat[f"server_{key}"] = value

    # Database settings
    if "database" in config:
        for key, value in config["database"].items():
            flat[f"db_{key}"] = value

    # Watcher settings
    if "watcher" in config:
        for key, value in config["watcher"].items():
            flat[f"watcher_{key}"] = value

    # Uploader settings
    if "uploader" in config:
        for key, value in config["uploader"].items():
            flat[f"uploader_{key}"] = value

    # SHA256 processor settings
    if "sha256" in config:
        for key, value in config["sha256"].items():
            flat[f"sha256_{key}"] = value

    # Remote server settings
    if "remote_server" in config:
        for key, value in config["remote_server"].items():
            flat[f"remote_server_{key}"] = value

    return flat


def get_config_file_path() -> Optional[Path]:
    """Get the path to the configuration file being used.

    Returns absolute path if config file was found, None otherwise.
    """
    if _config_file_path:
        return _config_file_path.resolve()
    return None


class Settings(BaseSettings):
    """Application settings with environment variable and TOML support."""

    # Server settings
    server_host: str = Field(default="127.0.0.1", description="Host to bind to")
    server_port: int = Field(default=8765, description="Port to bind to")
    server_log_level: str = Field(default="INFO", description="Logging level")

    # Database settings
    db_path: str = Field(
        default="~/.local/share/putplace/assist.db",
        description="Path to SQLite database"
    )

    # Watcher settings
    watcher_enabled: bool = Field(default=True, description="Enable file watching")
    watcher_debounce_seconds: float = Field(
        default=2.0,
        description="Debounce delay for file change events"
    )

    # Uploader settings
    uploader_parallel_uploads: int = Field(
        default=4,
        description="Number of parallel uploads"
    )
    uploader_retry_attempts: int = Field(default=3, description="Number of retry attempts")
    uploader_retry_delay_seconds: float = Field(
        default=5.0,
        description="Delay between retries"
    )
    uploader_timeout_seconds: int = Field(
        default=600,
        description="Timeout for uploading each file (in seconds, default 10 minutes)"
    )
    uploader_chunk_size_mb: int = Field(
        default=2,
        description="Chunk size for uploading files (in MB, default 2MB)"
    )

    # SHA256 processor settings
    sha256_chunk_size: int = Field(
        default=65536,
        description="Chunk size for reading files during SHA256 calculation (bytes)"
    )
    sha256_chunk_delay_ms: int = Field(
        default=1,
        description="Delay in milliseconds between chunks to avoid CPU saturation"
    )
    sha256_batch_size: int = Field(
        default=100,
        description="Number of files to process in each batch"
    )
    sha256_batch_delay_seconds: float = Field(
        default=1.0,
        description="Delay between processing batches"
    )

    # PID file location
    pid_file: str = Field(
        default="~/.local/share/putplace/ppassist.pid",
        description="Path to PID file"
    )

    # Remote server settings (default PutPlace server to upload to)
    remote_server_name: Optional[str] = Field(
        default="localhost:8100",
        description="Name for the remote server configuration"
    )
    remote_server_url: Optional[str] = Field(
        default="http://localhost:8100",
        description="URL of the remote PutPlace server"
    )
    remote_server_username: Optional[str] = Field(
        default=None,
        description="Username for remote server authentication"
    )
    remote_server_password: Optional[str] = Field(
        default=None,
        description="Password for remote server authentication"
    )

    model_config = {
        "env_prefix": "PPASSIST_",
        "env_file": ".env",
        "extra": "ignore",
    }

    def __init__(self, **kwargs):
        # Load TOML config as defaults
        toml_config = load_toml_config()

        # Environment variables override TOML config
        for key, value in toml_config.items():
            env_key = f"PPASSIST_{key.upper()}"
            if env_key not in os.environ and key not in kwargs:
                kwargs[key] = value

        super().__init__(**kwargs)

    @property
    def db_path_resolved(self) -> Path:
        """Return resolved database path."""
        return Path(self.db_path).expanduser()

    @property
    def pid_file_resolved(self) -> Path:
        """Return resolved PID file path."""
        return Path(self.pid_file).expanduser()

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.db_path_resolved.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file_resolved.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
