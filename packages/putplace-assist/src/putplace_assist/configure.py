#!/usr/bin/env python3
"""Interactive configuration wizard for PutPlace Assist."""

import argparse
import getpass
import sys
from pathlib import Path
from typing import Optional

try:
    import tomli_w
except ImportError:
    print("Error: tomli_w not installed. Run: pip install tomli-w")
    sys.exit(1)


def prompt(question: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Prompt user for input with optional default."""
    if default:
        prompt_text = f"{question} [{default}]: "
    else:
        prompt_text = f"{question}: "

    while True:
        response = input(prompt_text).strip()

        if not response:
            if default is not None:
                return default
            elif required:
                print("This field is required. Please enter a value.")
                continue
            else:
                return None
        return response


def prompt_bool(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no with default."""
    default_str = "Y/n" if default else "y/N"
    response = input(f"{question} [{default_str}]: ").strip().lower()

    if not response:
        return default

    return response in ("y", "yes", "true", "1")


def prompt_int(question: str, default: int, min_val: Optional[int] = None) -> int:
    """Prompt user for integer with validation."""
    while True:
        response = input(f"{question} [{default}]: ").strip()

        if not response:
            return default

        try:
            value = int(response)
            if min_val is not None and value < min_val:
                print(f"Value must be at least {min_val}")
                continue
            return value
        except ValueError:
            print("Please enter a valid integer.")


def prompt_float(question: str, default: float, min_val: Optional[float] = None) -> float:
    """Prompt user for float with validation."""
    while True:
        response = input(f"{question} [{default}]: ").strip()

        if not response:
            return default

        try:
            value = float(response)
            if min_val is not None and value < min_val:
                print(f"Value must be at least {min_val}")
                continue
            return value
        except ValueError:
            print("Please enter a valid number.")


def get_config_path() -> Path:
    """Prompt user for config file location."""
    print("\n=== PutPlace Assist Configuration Wizard ===\n")
    print("This wizard will help you create a pp_assist.toml configuration file.\n")

    default_path = Path.home() / ".config" / "putplace" / "pp_assist.toml"
    path_str = prompt(
        "Where should the configuration file be saved?",
        default=str(default_path),
        required=True
    )

    return Path(path_str).expanduser()


def configure_server() -> dict:
    """Configure local API server settings."""
    print("\n--- Local API Server Configuration ---")
    print("These settings control the local pp_assist web server and API.\n")

    return {
        "host": prompt("Host to bind to", default="127.0.0.1"),
        "port": prompt_int("Port for web server and API", default=8765, min_val=1),
        "log_level": prompt(
            "Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
            default="INFO"
        ).upper(),
    }


def configure_remote_server() -> dict:
    """Configure remote PutPlace server settings."""
    print("\n--- Remote PutPlace Server Configuration ---")
    print("Configure the remote pp_server that files will be uploaded to.\n")

    configure = prompt_bool("Configure remote server?", default=True)
    if not configure:
        return {}

    # Ask for URL first
    url = prompt(
        "Server URL",
        default="http://localhost:8100",
        required=True
    )

    # Derive a default name from the URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname:
        if parsed.port and parsed.port not in (80, 443):
            derived_name = f"{parsed.hostname}:{parsed.port}"
        else:
            derived_name = parsed.hostname
    else:
        derived_name = url

    # Ask if they want to customize the name
    custom_name = prompt(
        f"Server name (optional, derived from URL: {derived_name})",
        default=derived_name
    )

    config = {
        "name": custom_name,
        "url": url,
    }

    # Optional authentication
    auth = prompt_bool("Configure authentication?", default=False)
    if auth:
        username = prompt("Username")
        if username:
            config["username"] = username

        # Use getpass for secure password input
        password = getpass.getpass("Password (hidden): ")
        if password:
            config["password"] = password

    return config


def configure_database() -> dict:
    """Configure database settings."""
    print("\n--- Database Configuration ---")
    print("SQLite database for storing file metadata and activity logs.\n")

    return {
        "path": prompt(
            "Database path",
            default="~/.local/share/putplace/assist.db"
        ),
    }


def configure_watcher() -> dict:
    """Configure file watcher settings."""
    print("\n--- File Watcher Configuration ---")
    print("Automatic file watching for registered paths.\n")

    return {
        "enabled": prompt_bool("Enable file watching?", default=True),
        "debounce_seconds": prompt_float(
            "Debounce delay in seconds",
            default=2.0,
            min_val=0.1
        ),
    }


def configure_uploader() -> dict:
    """Configure uploader settings."""
    print("\n--- Upload Configuration ---")
    print("Settings for uploading files to the remote server.\n")

    return {
        "parallel_uploads": prompt_int(
            "Number of parallel upload workers",
            default=4,
            min_val=1
        ),
        "retry_attempts": prompt_int(
            "Number of retry attempts for failed uploads",
            default=3,
            min_val=0
        ),
        "retry_delay_seconds": prompt_float(
            "Delay between retries in seconds",
            default=5.0,
            min_val=0.1
        ),
    }


def configure_sha256() -> dict:
    """Configure SHA256 processor settings."""
    print("\n--- SHA256 Processing Configuration ---")
    print("Settings for calculating file checksums.\n")

    advanced = prompt_bool("Configure advanced SHA256 settings?", default=False)
    if not advanced:
        return {
            "chunk_size": 65536,
            "chunk_delay_ms": 1,
            "batch_size": 100,
            "batch_delay_seconds": 1.0,
        }

    return {
        "chunk_size": prompt_int(
            "Chunk size for reading files (bytes)",
            default=65536,
            min_val=1024
        ),
        "chunk_delay_ms": prompt_int(
            "Delay between chunks in milliseconds",
            default=1,
            min_val=0
        ),
        "batch_size": prompt_int(
            "Number of files to process in each batch",
            default=100,
            min_val=1
        ),
        "batch_delay_seconds": prompt_float(
            "Delay between batches in seconds",
            default=1.0,
            min_val=0.0
        ),
    }


def write_config(config: dict, path: Path) -> None:
    """Write configuration to TOML file."""
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write TOML file
    with open(path, "wb") as f:
        tomli_w.dump(config, f)

    print(f"\n✓ Configuration saved to: {path}")


def show_config(config: dict) -> None:
    """Display the configuration to the user."""
    print("\n=== Configuration Summary ===\n")

    for section, values in config.items():
        print(f"[{section}]")
        for key, value in values.items():
            if key == "password" and value:
                print(f"{key} = ***")
            else:
                print(f"{key} = {value!r}")
        print()


def main() -> int:
    """Main entry point for configuration wizard."""
    parser = argparse.ArgumentParser(
        description="Interactive configuration wizard for PutPlace Assist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pp_assist_configure                    # Interactive mode
  pp_assist_configure --non-interactive  # Use all defaults
        """
    )

    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use default values without prompting"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output path for config file (default: ~/.config/putplace/pp_assist.toml)"
    )

    args = parser.parse_args()

    try:
        if args.non_interactive:
            # Use all defaults
            config_path = args.output or Path.home() / ".config" / "putplace" / "pp_assist.toml"
            print(f"Creating default configuration at: {config_path}")

            config = {
                "server": {
                    "host": "127.0.0.1",
                    "port": 8765,
                    "log_level": "INFO",
                },
                "remote_server": {
                    "name": "localhost:8100",
                    "url": "http://localhost:8100",
                },
                "database": {
                    "path": "~/.local/share/putplace/assist.db",
                },
                "watcher": {
                    "enabled": True,
                    "debounce_seconds": 2.0,
                },
                "uploader": {
                    "parallel_uploads": 4,
                    "retry_attempts": 3,
                    "retry_delay_seconds": 5.0,
                },
                "sha256": {
                    "chunk_size": 65536,
                    "chunk_delay_ms": 1,
                    "batch_size": 100,
                    "batch_delay_seconds": 1.0,
                },
            }
        else:
            # Interactive mode
            config_path = args.output or get_config_path()

            config = {}
            config["server"] = configure_server()

            remote_server = configure_remote_server()
            if remote_server:
                config["remote_server"] = remote_server

            config["database"] = configure_database()
            config["watcher"] = configure_watcher()
            config["uploader"] = configure_uploader()
            config["sha256"] = configure_sha256()

        # Show configuration summary
        show_config(config)

        # Confirm before writing
        if not args.non_interactive:
            confirm = prompt_bool(f"\nWrite configuration to {config_path}?", default=True)
            if not confirm:
                print("Configuration cancelled.")
                return 1

        # Write configuration
        write_config(config, config_path)

        print("\nNext steps:")
        print(f"  1. Review the configuration: cat {config_path}")
        print("  2. Start pp_assist: pp_assist start")
        print("  3. Access web UI: http://127.0.0.1:8765/ui")

        return 0

    except KeyboardInterrupt:
        print("\n\nConfiguration cancelled by user.")
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
