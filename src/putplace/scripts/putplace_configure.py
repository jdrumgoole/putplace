#!/usr/bin/env python3
"""PutPlace Configuration Script

This script configures a PutPlace installation by:
- Creating an initial admin user
- Checking AWS S3 and SES access
- Configuring storage backend (local or S3)
- Setting up environment variables
- Validating the configuration

Can run interactively or non-interactively for automation.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import secrets
import string

# Enable readline for better input editing (if available)
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

# TOML reading support
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python 3.10
    except ImportError:
        tomllib = None

try:
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich.table import Table
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None


def print_message(message: str, style: str = ""):
    """Print message with or without rich formatting."""
    if RICH_AVAILABLE:
        rprint(f"[{style}]{message}[/{style}]" if style else message)
    else:
        print(message)


def print_panel(message: str, title: str = "", style: str = ""):
    """Print a panel with or without rich."""
    if RICH_AVAILABLE:
        console = Console()
        console.print(Panel(message, title=title, border_style=style))
    else:
        print(f"\n=== {title} ===")
        print(message)
        print("=" * (len(title) + 8))


def load_existing_config() -> Dict[str, Any]:
    """Load existing configuration from ppserver.toml if it exists.

    Searches for ppserver.toml in standard locations:
    1. ./ppserver.toml (current directory)
    2. ~/.config/putplace/ppserver.toml (user config)
    3. /etc/putplace/ppserver.toml (system config)

    Returns a dictionary with defaults extracted from the file, or empty dict if not found.
    """
    if not tomllib:
        return {}

    search_paths = [
        Path("./ppserver.toml"),
        Path.home() / ".config" / "putplace" / "ppserver.toml",
        Path("/etc/putplace/ppserver.toml")
    ]

    for config_path in search_paths:
        if config_path.exists():
            try:
                with open(config_path, 'rb') as f:
                    config = tomllib.load(f)

                # Extract defaults
                defaults = {}

                # MongoDB settings
                if 'database' in config:
                    defaults['mongodb_url'] = config['database'].get('mongodb_url', 'mongodb://localhost:27017')
                    defaults['mongodb_database'] = config['database'].get('mongodb_database', 'putplace')

                # Storage settings
                if 'storage' in config:
                    defaults['storage_backend'] = config['storage'].get('backend', 'local')
                    defaults['storage_path'] = config['storage'].get('path', './storage/files')
                    defaults['s3_bucket'] = config['storage'].get('s3_bucket_name')
                    defaults['s3_region'] = config['storage'].get('s3_region_name', 'eu-west-1')

                # AWS settings
                if 'aws' in config:
                    defaults['aws_region'] = config['aws'].get('region', defaults.get('s3_region', 'eu-west-1'))

                print_message(f"✓ Loaded defaults from {config_path}", "green")
                return defaults

            except Exception as e:
                print_message(f"Warning: Could not load {config_path}: {e}", "yellow")
                continue

    return {}


def input_with_prefill(prompt: str, prefill: str = '') -> str:
    """Get input with a pre-filled value that can be edited using backspace.

    Uses readline if available to provide editable pre-filled text.
    """
    if not READLINE_AVAILABLE or not prefill:
        # Fall back to regular input if readline not available
        return input(prompt)

    # Configure readline key bindings for proper editing behavior
    # Emacs mode is standard and should have correct backspace behavior
    readline.parse_and_bind('set editing-mode emacs')

    # Explicitly bind backspace keys to backward-delete-char
    # This ensures backspace deletes the character BEFORE the cursor
    readline.parse_and_bind('"\\C-h": backward-delete-char')  # Ctrl+H (backspace)
    readline.parse_and_bind('"\\C-?": backward-delete-char')  # DEL character (backspace)

    # Bind Delete key to delete-char (forward delete)
    readline.parse_and_bind('"\\e[3~": delete-char')  # Delete key

    def hook():
        readline.insert_text(prefill)
        readline.redisplay()

    readline.set_pre_input_hook(hook)

    try:
        result = input(prompt)
    finally:
        readline.set_pre_input_hook()

    return result


def generate_secure_password(length: int = 21) -> str:
    """Generate a cryptographically secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def check_mongodb_connection(mongodb_url: str) -> tuple[bool, str]:
    """Check if MongoDB is accessible."""
    try:
        from pymongo import AsyncMongoClient
        import certifi

        # Determine if TLS/SSL should be used based on the connection string
        # MongoDB Atlas (mongodb+srv://) and remote TLS connections need certificate validation
        # Local connections (mongodb://localhost) typically don't use TLS
        use_tls = 'mongodb+srv://' in mongodb_url or 'mongodb.net' in mongodb_url

        if use_tls:
            # For MongoDB Atlas and remote TLS connections, use certifi
            client = AsyncMongoClient(
                mongodb_url,
                serverSelectionTimeoutMS=5000,
                tlsCAFile=certifi.where()  # Use certifi's CA bundle for certificate validation
            )
        else:
            # For local MongoDB, don't use TLS
            client = AsyncMongoClient(
                mongodb_url,
                serverSelectionTimeoutMS=5000
            )

        # Try to get server info
        await client.admin.command('ping')
        await client.close()
        return True, "MongoDB connection successful"
    except ImportError as e:
        # Check which library is missing
        if 'certifi' in str(e):
            return False, "certifi library not installed (pip install certifi)"
        return False, "pymongo library not installed (PyMongo 4.10+ required)"
    except Exception as e:
        return False, f"MongoDB connection failed: {str(e)}"


async def check_s3_access(aws_region: Optional[str] = None) -> tuple[bool, str]:
    """Check if AWS S3 is accessible."""
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError

        # Create S3 client
        if aws_region:
            s3_client = boto3.client('s3', region_name=aws_region)
        else:
            s3_client = boto3.client('s3')

        # Try to list buckets as a simple connectivity test
        s3_client.list_buckets()
        return True, "AWS S3 access confirmed"
    except ImportError:
        return False, "boto3 library not installed"
    except NoCredentialsError:
        return False, "AWS credentials not configured"
    except ClientError as e:
        return False, f"AWS S3 access failed: {e.response['Error']['Message']}"
    except Exception as e:
        return False, f"AWS S3 check failed: {str(e)}"


async def check_ses_access(aws_region: Optional[str] = None) -> tuple[bool, str]:
    """Check if AWS SES is accessible."""
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError

        # Create SES client
        if aws_region:
            ses_client = boto3.client('ses', region_name=aws_region)
        else:
            ses_client = boto3.client('ses')

        # Try to get account sending quota
        ses_client.get_send_quota()
        return True, "AWS SES access confirmed"
    except ImportError:
        return False, "boto3 library not installed"
    except NoCredentialsError:
        return False, "AWS credentials not configured"
    except ClientError as e:
        return False, f"AWS SES access failed: {e.response['Error']['Message']}"
    except Exception as e:
        return False, f"AWS SES check failed: {str(e)}"


async def create_admin_user(
    mongodb_url: str,
    username: str,
    email: str,
    password: str
) -> tuple[bool, str]:
    """Create an admin user in the database."""
    try:
        from pymongo import AsyncMongoClient
        from putplace.user_auth import get_password_hash
        from datetime import datetime
        import certifi

        # Use same TLS detection logic as check_mongodb_connection
        use_tls = 'mongodb+srv://' in mongodb_url or 'mongodb.net' in mongodb_url

        if use_tls:
            # For MongoDB Atlas and remote TLS connections
            client = AsyncMongoClient(
                mongodb_url,
                tlsCAFile=certifi.where()
            )
        else:
            # For local MongoDB without TLS
            client = AsyncMongoClient(mongodb_url)

        db = client.get_database("putplace")
        users_collection = db.users

        # Check if user already exists
        existing_user = await users_collection.find_one({"username": username})
        if existing_user:
            await client.close()
            return False, f"User '{username}' already exists"

        # Create user document
        user_doc = {
            "username": username,
            "email": email,
            "password_hash": get_password_hash(password),
            "full_name": "Administrator",
            "is_admin": True,
            "created_at": datetime.utcnow()
        }

        # Insert user
        await users_collection.insert_one(user_doc)
        await client.close()

        return True, f"Admin user '{username}' created successfully"
    except ImportError as e:
        return False, f"Required libraries not installed: {e}"
    except Exception as e:
        return False, f"Failed to create admin user: {str(e)}"


def write_toml_file(config: dict, toml_path: Path) -> tuple[bool, str]:
    """Write configuration to ppserver.toml file."""
    try:
        import tomli_w

        # Build TOML configuration
        from pathlib import Path as PathLib

        toml_config = {
            "server": {
                # Secure defaults: bind to localhost only for initial setup
                # Users must explicitly change to 0.0.0.0 to expose externally
                "host": config.get('server_host', '127.0.0.1'),
                "port": config.get('server_port', 8000),
                # Workers: 1 for development, should be increased for production
                "workers": config.get('server_workers', 1),
            },
            "database": {
                "mongodb_url": config.get('mongodb_url', 'mongodb://localhost:27017'),
                "mongodb_database": config.get('mongodb_database', 'putplace'),
                "mongodb_collection": "file_metadata"
            },
            "api": {
                "title": "PutPlace API",
                "description": "File metadata storage API"
            },
            "logging": {
                "pid_file": config.get('pid_file', str(PathLib.home() / ".putplace" / "ppserver.pid")),
            },
            "storage": {}
        }

        # Add log_file to logging section only if specified (TOML doesn't support None)
        log_file = config.get('log_file')
        if log_file:
            toml_config["logging"]["log_file"] = log_file

        # Storage configuration
        storage_backend = config.get('storage_backend', 'local')
        toml_config["storage"]["backend"] = storage_backend

        if storage_backend == 'local':
            toml_config["storage"]["path"] = config.get('storage_path', './storage/files')
        elif storage_backend == 's3':
            toml_config["storage"]["s3_bucket_name"] = config.get('s3_bucket', '')
            if config.get('aws_region'):
                toml_config["storage"]["s3_region_name"] = config['aws_region']
            toml_config["storage"]["s3_prefix"] = "files/"

        # Write TOML file with header comment
        header = "# PutPlace Server Configuration\n"
        header += "# Generated by putplace_configure\n"
        header += "#\n"
        header += "# Security Notes:\n"
        header += "#   - Server binds to 127.0.0.1 (localhost) by default for security\n"
        header += "#   - To expose externally, change host to 0.0.0.0 and use reverse proxy\n"
        header += "#   - Increase workers for production (recommended: 2-4 per CPU core)\n"
        header += "#   - Always use HTTPS in production (configure reverse proxy)\n\n"

        toml_content = tomli_w.dumps(toml_config)

        # Add AWS section comments if S3 is used
        if storage_backend == 's3':
            aws_comments = "\n[aws]\n"
            aws_comments += "# AWS credentials use the standard AWS credential chain\n"
            aws_comments += "# Recommended: Use IAM roles or AWS CLI config instead of hardcoding credentials\n"
            toml_content += aws_comments

        toml_path.write_text(header + toml_content)

        return True, f"Configuration written to {toml_path}"
    except ImportError:
        return False, "tomli-w library not installed (required for TOML writing)"
    except Exception as e:
        return False, f"Failed to write TOML file: {str(e)}"


def create_aws_secrets(config: dict, aws_region: str = 'eu-west-1') -> tuple[bool, str]:
    """Create secrets in AWS Secrets Manager for App Runner deployment.

    Creates three secrets:
    - putplace/mongodb: MongoDB connection settings
    - putplace/admin: Admin user credentials
    - putplace/aws-config: AWS and API configuration
    """
    try:
        import boto3
        import json
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return False, "boto3 library not installed (pip install boto3)"

    try:
        # Create Secrets Manager client
        client = boto3.client('secretsmanager', region_name=aws_region)

        # Define secrets to create
        secrets = {
            'putplace/mongodb': {
                'MONGODB_URL': config.get('mongodb_url', 'mongodb://localhost:27017'),
                'MONGODB_DATABASE': config.get('mongodb_database', 'putplace'),
                'MONGODB_COLLECTION': 'file_metadata'
            },
            'putplace/admin': {
                'PUTPLACE_ADMIN_USERNAME': config.get('admin_username', 'admin'),
                'PUTPLACE_ADMIN_EMAIL': config.get('admin_email', 'admin@localhost'),
                'PUTPLACE_ADMIN_PASSWORD': config.get('admin_password', '')
            },
            'putplace/aws-config': {
                'AWS_DEFAULT_REGION': aws_region,
                'API_TITLE': 'PutPlace File Metadata API',
                'API_VERSION': '0.5.8',
                'PYTHONUNBUFFERED': '1',
                'PYTHONDONTWRITEBYTECODE': '1'
            }
        }

        created_secrets = []
        updated_secrets = []

        for secret_name, secret_value in secrets.items():
            secret_string = json.dumps(secret_value)

            try:
                # Try to create the secret
                client.create_secret(
                    Name=secret_name,
                    SecretString=secret_string,
                    Description=f'PutPlace configuration for {secret_name.split("/")[1]}'
                )
                created_secrets.append(secret_name)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceExistsException':
                    # Secret exists, update it
                    client.update_secret(
                        SecretId=secret_name,
                        SecretString=secret_string
                    )
                    updated_secrets.append(secret_name)
                else:
                    raise

        result_msg = f"AWS Secrets Manager setup complete in {aws_region}:\n"
        if created_secrets:
            result_msg += f"  Created: {', '.join(created_secrets)}\n"
        if updated_secrets:
            result_msg += f"  Updated: {', '.join(updated_secrets)}\n"
        result_msg += "\nGrant App Runner IAM role access to secrets:\n"
        result_msg += f"  Action: secretsmanager:GetSecretValue\n"
        result_msg += f"  Resource: arn:aws:secretsmanager:{aws_region}:*:secret:putplace/*"

        return True, result_msg

    except NoCredentialsError:
        return False, "AWS credentials not configured. Set up AWS CLI or environment variables."
    except ClientError as e:
        error_msg = e.response['Error']['Message']
        return False, f"AWS Secrets Manager error: {error_msg}"
    except Exception as e:
        return False, f"Failed to create AWS secrets: {str(e)}"


def delete_aws_secrets(aws_region: str = 'eu-west-1', force: bool = False) -> tuple[bool, str]:
    """Delete PutPlace secrets from AWS Secrets Manager."""
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return False, "boto3 library not installed (pip install boto3)"

    try:
        client = boto3.client('secretsmanager', region_name=aws_region)

        secret_names = [
            'putplace/mongodb',
            'putplace/admin',
            'putplace/aws-config'
        ]

        deleted = []
        not_found = []

        for secret_name in secret_names:
            try:
                if force:
                    client.delete_secret(
                        SecretId=secret_name,
                        ForceDeleteWithoutRecovery=True
                    )
                    deleted.append(f"{secret_name} (permanent)")
                else:
                    client.delete_secret(
                        SecretId=secret_name,
                        RecoveryWindowInDays=7
                    )
                    deleted.append(f"{secret_name} (7 day recovery)")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    not_found.append(secret_name)
                else:
                    raise

        result_msg = f"Deleted secrets in {aws_region}:\n"
        if deleted:
            result_msg += "  " + "\n  ".join(deleted)
        if not_found:
            result_msg += f"\n  Not found: {', '.join(not_found)}"

        return True, result_msg

    except NoCredentialsError:
        return False, "AWS credentials not configured"
    except ClientError as e:
        return False, f"AWS error: {e.response['Error']['Message']}"
    except Exception as e:
        return False, f"Failed to delete secrets: {str(e)}"


async def run_interactive_config() -> dict:
    """Run interactive configuration wizard."""
    config = {}

    if RICH_AVAILABLE:
        console = Console()
        console.print("\n[bold cyan]PutPlace Configuration Wizard[/bold cyan]\n")
    else:
        print("\n=== PutPlace Configuration Wizard ===\n")

    # Load existing configuration for defaults
    existing_config = load_existing_config()

    # MongoDB Configuration
    print_panel("MongoDB Configuration", title="Step 1/5", style="cyan")

    # Use input_with_prefill for better editing experience
    default_mongodb = existing_config.get('mongodb_url', "mongodb://localhost:27017")

    if READLINE_AVAILABLE:
        print_message(f"MongoDB URL (pre-filled, edit as needed): {default_mongodb}", "cyan")
        print_message("Press Enter to accept, or edit/backspace to change", "dim")
        mongodb_url = input_with_prefill("> ", default_mongodb).strip()
    else:
        # Fallback for systems without readline
        print_message(f"MongoDB URL:", "cyan")
        mongodb_url_input = input(f"[{default_mongodb}] > ").strip()
        mongodb_url = mongodb_url_input if mongodb_url_input else default_mongodb

    if not mongodb_url:
        mongodb_url = default_mongodb

    config['mongodb_url'] = mongodb_url

    # Test MongoDB connection
    print_message("Testing MongoDB connection...", "yellow")
    success, message = await check_mongodb_connection(mongodb_url)
    print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

    if not success:
        print_message("Warning: MongoDB connection failed. Configuration will continue but server may not start.", "yellow")

    # Admin User Configuration
    print_panel("Admin User Configuration", title="Step 2/5", style="cyan")

    if RICH_AVAILABLE:
        admin_username = Prompt.ask("Admin username", default="admin")
        admin_email = Prompt.ask("Admin email", default="admin@localhost")
        generate_pwd = Confirm.ask("Generate secure password?", default=True)
    else:
        admin_username = input("Admin username [admin]: ").strip() or "admin"
        admin_email = input("Admin email [admin@localhost]: ").strip() or "admin@localhost"
        generate_pwd_input = input("Generate secure password? [Y/n]: ").strip().lower()
        generate_pwd = generate_pwd_input != 'n'

    if generate_pwd:
        admin_password = generate_secure_password()
        print_message(f"Generated password: {admin_password}", "green bold")
        print_message("IMPORTANT: Save this password securely!", "red bold")
    else:
        if RICH_AVAILABLE:
            admin_password = Prompt.ask("Admin password", password=True)
        else:
            import getpass
            admin_password = getpass.getpass("Admin password: ")

    config['admin_username'] = admin_username
    config['admin_email'] = admin_email
    config['admin_password'] = admin_password

    # Create admin user
    print_message("Creating admin user...", "yellow")
    success, message = await create_admin_user(mongodb_url, admin_username, admin_email, admin_password)
    print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

    # AWS Configuration
    print_panel("AWS Configuration (Optional)", title="Step 3/5", style="cyan")

    if RICH_AVAILABLE:
        check_aws = Confirm.ask("Check AWS access (S3/SES)?", default=False)
    else:
        check_aws_input = input("Check AWS access (S3/SES)? [y/N]: ").strip().lower()
        check_aws = check_aws_input == 'y'

    config['has_s3_access'] = False
    config['has_ses_access'] = False

    if check_aws:
        default_region = existing_config.get('aws_region', existing_config.get('s3_region', 'eu-west-1'))
        if RICH_AVAILABLE:
            aws_region = Prompt.ask("AWS Region", default=default_region)
        else:
            aws_region = input(f"AWS Region [{default_region}]: ").strip() or default_region

        config['aws_region'] = aws_region

        # Check S3 access
        print_message("Checking S3 access...", "yellow")
        s3_success, s3_message = await check_s3_access(aws_region)
        print_message(f"{'✓' if s3_success else '✗'} {s3_message}", "green" if s3_success else "red")
        config['has_s3_access'] = s3_success

        # Check SES access
        print_message("Checking SES access...", "yellow")
        ses_success, ses_message = await check_ses_access(aws_region)
        print_message(f"{'✓' if ses_success else '✗'} {ses_message}", "green" if ses_success else "red")
        config['has_ses_access'] = ses_success

    # Storage Backend Selection
    print_panel("Storage Backend Selection", title="Step 4/5", style="cyan")

    # Determine default storage backend from existing config
    default_backend = existing_config.get('storage_backend', 'local')

    if config.get('has_s3_access'):
        default_use_s3 = (default_backend == 's3')
        if RICH_AVAILABLE:
            use_s3 = Confirm.ask("Use S3 for storage?", default=default_use_s3)
        else:
            prompt_default = "Y/n" if default_use_s3 else "y/N"
            use_s3_input = input(f"Use S3 for storage? [{prompt_default}]: ").strip().lower()
            use_s3 = use_s3_input == 'y' if not default_use_s3 else use_s3_input != 'n'

        if use_s3:
            default_bucket = existing_config.get('s3_bucket', '')
            if RICH_AVAILABLE:
                s3_bucket = Prompt.ask("S3 bucket name", default=default_bucket if default_bucket else None)
            else:
                bucket_prompt = f"S3 bucket name [{default_bucket}]: " if default_bucket else "S3 bucket name: "
                s3_bucket = input(bucket_prompt).strip() or default_bucket

            config['storage_backend'] = 's3'
            config['s3_bucket'] = s3_bucket
        else:
            config['storage_backend'] = 'local'
    else:
        config['storage_backend'] = 'local'
        print_message("Using local storage (S3 not available)", "yellow")

    if config['storage_backend'] == 'local':
        default_path = existing_config.get('storage_path', './storage/files')
        if RICH_AVAILABLE:
            storage_path = Prompt.ask("Local storage path", default=default_path)
        else:
            storage_path = input(f"Local storage path [{default_path}]: ").strip() or default_path

        config['storage_path'] = storage_path

    # Configuration File
    print_panel("Configuration File", title="Step 5/5", style="cyan")

    if RICH_AVAILABLE:
        config_path_str = Prompt.ask("Path to configuration file", default="ppserver.toml")
    else:
        config_path_str = input("Path to configuration file [ppserver.toml]: ").strip() or "ppserver.toml"

    config['config_path'] = Path(config_path_str)

    return config


async def run_noninteractive_config(args) -> dict:
    """Run non-interactive configuration using command-line arguments."""
    config = {
        'mongodb_url': args.mongodb_url,
        'mongodb_database': args.mongodb_database,
        'admin_username': args.admin_username,
        'admin_email': args.admin_email,
        'storage_backend': args.storage_backend,
        'config_path': Path(args.config_file),
    }

    # Only add log_file and pid_file if specified (avoid None values)
    if args.log_file:
        config['log_file'] = args.log_file
    if args.pid_file:
        config['pid_file'] = args.pid_file

    # Generate or use provided password
    if args.admin_password:
        config['admin_password'] = args.admin_password
    else:
        config['admin_password'] = generate_secure_password()
        print_message(f"Generated admin password: {config['admin_password']}", "green bold")
        print_message("IMPORTANT: Save this password securely!", "red bold")

    # Storage configuration
    if args.storage_backend == 'local':
        config['storage_path'] = args.storage_path
    elif args.storage_backend == 's3':
        config['s3_bucket'] = args.s3_bucket
        config['aws_region'] = args.aws_region

    # Test MongoDB
    print_message("Testing MongoDB connection...", "yellow")
    success, message = await check_mongodb_connection(config['mongodb_url'])
    print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

    if not success and not args.skip_checks:
        print_message("Error: MongoDB connection failed. Use --skip-checks to continue anyway.", "red")
        sys.exit(1)

    # Create admin user
    print_message("Creating admin user...", "yellow")
    success, message = await create_admin_user(
        config['mongodb_url'],
        config['admin_username'],
        config['admin_email'],
        config['admin_password']
    )
    print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

    if not success and not args.skip_checks:
        print_message("Error: Failed to create admin user.", "red")
        sys.exit(1)

    # Check AWS if S3 backend
    if args.storage_backend == 's3' and not args.skip_aws_checks:
        print_message("Checking S3 access...", "yellow")
        s3_success, s3_message = await check_s3_access(args.aws_region)
        print_message(f"{'✓' if s3_success else '✗'} {s3_message}", "green" if s3_success else "red")

        if not s3_success and not args.skip_checks:
            print_message("Error: S3 access check failed.", "red")
            sys.exit(1)

    return config


def print_summary(config: dict):
    """Print configuration summary."""
    if RICH_AVAILABLE:
        console = Console()

        table = Table(title="Configuration Summary", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("MongoDB URL", config.get('mongodb_url', 'N/A'))
        table.add_row("Admin Username", config.get('admin_username', 'N/A'))
        table.add_row("Admin Email", config.get('admin_email', 'N/A'))
        table.add_row("Storage Backend", config.get('storage_backend', 'N/A'))

        if config.get('storage_backend') == 'local':
            table.add_row("Storage Path", config.get('storage_path', 'N/A'))
        elif config.get('storage_backend') == 's3':
            table.add_row("S3 Bucket", config.get('s3_bucket', 'N/A'))
            table.add_row("AWS Region", config.get('aws_region', 'N/A'))

        table.add_row("Configuration File", str(config.get('config_path', 'N/A')))

        console.print(table)
    else:
        print("\n=== Configuration Summary ===")
        print(f"MongoDB URL: {config.get('mongodb_url', 'N/A')}")
        print(f"Admin Username: {config.get('admin_username', 'N/A')}")
        print(f"Admin Email: {config.get('admin_email', 'N/A')}")
        print(f"Storage Backend: {config.get('storage_backend', 'N/A')}")

        if config.get('storage_backend') == 'local':
            print(f"Storage Path: {config.get('storage_path', 'N/A')}")
        elif config.get('storage_backend') == 's3':
            print(f"S3 Bucket: {config.get('s3_bucket', 'N/A')}")
            print(f"AWS Region: {config.get('aws_region', 'N/A')}")

        print(f"Configuration File: {config.get('config_path', 'N/A')}")
        print("=" * 30)


async def async_main():
    """Async main function for the configuration script."""
    parser = argparse.ArgumentParser(
        description="Configure PutPlace server installation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive configuration
  putplace-configure

  # Non-interactive with local storage
  putplace-configure --non-interactive \\
    --admin-username admin \\
    --admin-email admin@example.com \\
    --storage-backend local

  # Non-interactive with S3 storage
  putplace-configure --non-interactive \\
    --admin-username admin \\
    --admin-email admin@example.com \\
    --storage-backend s3 \\
    --s3-bucket my-putplace-bucket \\
    --aws-region us-west-2

  # Standalone AWS tests
  putplace-configure S3                # Test S3 access
  putplace-configure SES               # Test SES access
  putplace-configure S3 --aws-region us-west-2  # Test S3 in specific region
        """
    )

    # Positional argument for standalone tests
    parser.add_argument(
        'test_mode',
        nargs='?',
        choices=['S3', 'SES'],
        help='Run standalone test for S3 or SES configuration'
    )

    # General options
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode (requires all options)'
    )
    parser.add_argument(
        '--skip-checks',
        action='store_true',
        help='Skip validation checks and continue on errors'
    )
    parser.add_argument(
        '--skip-aws-checks',
        action='store_true',
        help='Skip AWS S3/SES connectivity checks'
    )
    parser.add_argument(
        '--create-aws-secrets',
        action='store_true',
        help='Create secrets in AWS Secrets Manager for App Runner deployment'
    )
    parser.add_argument(
        '--delete-aws-secrets',
        action='store_true',
        help='Delete PutPlace secrets from AWS Secrets Manager'
    )
    parser.add_argument(
        '--force-delete',
        action='store_true',
        help='Force delete secrets without recovery window (use with --delete-aws-secrets)'
    )

    # MongoDB options
    parser.add_argument(
        '--mongodb-url',
        default='mongodb://localhost:27017',
        help='MongoDB connection URL (default: mongodb://localhost:27017)'
    )
    parser.add_argument(
        '--mongodb-database',
        default='putplace',
        help='MongoDB database name (default: putplace)'
    )

    # Admin user options
    parser.add_argument(
        '--admin-username',
        default='admin',
        help='Admin username (default: admin)'
    )
    parser.add_argument(
        '--admin-email',
        default='admin@localhost',
        help='Admin email (default: admin@localhost)'
    )
    parser.add_argument(
        '--admin-password',
        help='Admin password (will be generated if not provided)'
    )

    # Storage options
    parser.add_argument(
        '--storage-backend',
        choices=['local', 's3'],
        default='local',
        help='Storage backend to use (default: local)'
    )
    parser.add_argument(
        '--storage-path',
        default='./storage/files',
        help='Local storage path (default: ./storage/files)'
    )
    parser.add_argument(
        '--s3-bucket',
        help='S3 bucket name (required if storage-backend=s3)'
    )
    parser.add_argument(
        '--aws-region',
        default='eu-west-1',
        help='AWS region (default: eu-west-1)'
    )

    # Configuration file options
    parser.add_argument(
        '--config-file',
        default='ppserver.toml',
        help='Path to configuration file (default: ppserver.toml)'
    )

    # Logging options
    parser.add_argument(
        '--log-file',
        help='Path to log file (default: console only for development)'
    )
    parser.add_argument(
        '--pid-file',
        help='Path to PID file (default: ~/.putplace/ppserver.pid)'
    )

    args = parser.parse_args()

    # Handle delete AWS secrets mode
    if args.delete_aws_secrets:
        print_panel("Deleting PutPlace AWS Secrets", style="red")
        print_message(f"Region: {args.aws_region}", "yellow")

        if RICH_AVAILABLE:
            confirm = Confirm.ask("Are you sure you want to delete all PutPlace secrets?", default=False)
        else:
            confirm_input = input("Are you sure you want to delete all PutPlace secrets? [y/N]: ").strip().lower()
            confirm = confirm_input == 'y'

        if not confirm:
            print_message("Deletion cancelled.", "yellow")
            sys.exit(0)

        success, message = delete_aws_secrets(args.aws_region, args.force_delete)
        print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")
        sys.exit(0 if success else 1)

    # Handle standalone test modes
    if args.test_mode == 'S3':
        print_panel("Testing S3 Access", style="cyan")
        print_message(f"Region: {args.aws_region}", "yellow")
        success, message = await check_s3_access(args.aws_region)
        print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")
        sys.exit(0 if success else 1)

    if args.test_mode == 'SES':
        print_panel("Testing SES Access", style="cyan")
        print_message(f"Region: {args.aws_region}", "yellow")
        success, message = await check_ses_access(args.aws_region)
        print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")
        sys.exit(0 if success else 1)

    # Validate S3 options
    if args.non_interactive and args.storage_backend == 's3' and not args.s3_bucket:
        parser.error("--s3-bucket is required when using --storage-backend=s3")

    try:
        # Run configuration
        if args.non_interactive:
            print_panel("Non-Interactive Configuration Mode", style="cyan")
            config = await run_noninteractive_config(args)
        else:
            config = await run_interactive_config()

        # Write configuration file
        print_message("\nWriting configuration...", "yellow")
        success, message = write_toml_file(config, config['config_path'])
        print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

        if not success:
            sys.exit(1)

        # Print summary
        print_summary(config)

        # Create AWS Secrets if requested
        if args.create_aws_secrets:
            print_message("\nCreating AWS Secrets Manager secrets...", "yellow")
            success, message = create_aws_secrets(config, args.aws_region)
            print_message(f"{'✓' if success else '✗'} {message}", "green" if success else "red")

            if not success:
                print_message("Warning: AWS Secrets creation failed. Continue with local configuration.", "yellow")

        # Final instructions
        final_msg = f"""Configuration complete!

Next steps:
1. Review the generated configuration: {config['config_path']}
2. Start MongoDB if not already running: invoke mongo-start
3. Start the PutPlace server: invoke serve

Admin credentials:
  Username: {config['admin_username']}
  Password: {config['admin_password']}
  Email: {config['admin_email']}

IMPORTANT: Save the admin password securely!
"""

        if args.create_aws_secrets:
            final_msg += f"""
AWS App Runner Deployment:
  Secrets created in region: {args.aws_region}
  Next: Deploy to App Runner with: invoke deploy-apprunner --region={args.aws_region}
"""

        print_panel(
            final_msg,
            title="Setup Complete",
            style="green"
        )

    except KeyboardInterrupt:
        print_message("\n\nConfiguration cancelled by user.", "yellow")
        sys.exit(1)
    except Exception as e:
        print_message(f"\nError: {e}", "red")
        if not args.skip_checks:
            sys.exit(1)


def main():
    """Synchronous entry point wrapper."""
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
