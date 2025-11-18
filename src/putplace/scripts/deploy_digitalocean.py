#!/usr/bin/env python3
"""
Improved deployment script for PutPlace on Digital Ocean with better error handling.

Features:
- Real-time output during long operations
- Validation after each step
- Clear error messages
- Automatic cleanup on failure
- Retry logic for flaky operations
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


def load_env_file() -> None:
    """Load .env file from project root if it exists."""
    try:
        from dotenv import load_dotenv

        possible_paths = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent.parent.parent / ".env",
            Path.home() / ".env",
        ]

        for env_path in possible_paths:
            if env_path.exists():
                load_dotenv(env_path)
                print(f"✓ Loaded environment from: {env_path}\n")
                break
    except ImportError:
        pass


class DeploymentError(Exception):
    """Custom exception for deployment errors."""
    pass


class DigitalOceanDeployer:
    """Manages Digital Ocean droplet deployment with improved error handling."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        region: str = "fra1",
        size: str = "s-1vcpu-1gb",
        image: str = "ubuntu-22-04-x64",
    ):
        load_env_file()

        self.api_token = api_token or os.environ.get("DIGITALOCEAN_TOKEN")
        if not self.api_token:
            raise DeploymentError(
                "Digital Ocean API token required. Set DIGITALOCEAN_TOKEN in .env file, "
                "environment variable, or pass as argument."
            )
        self.region = region
        self.size = size
        self.image = image
        self.droplet_id: Optional[int] = None
        self.droplet_ip: Optional[str] = None
        self.created_droplet = False  # Track if we created it (for cleanup)

    def run_command(self, command: list[str], description: str, show_progress: bool = False) -> Tuple[bool, str]:
        """Execute command and return success status and output."""
        try:
            print(f"→ {description}...", end='', flush=True)

            if show_progress:
                # Show progress dots for long operations
                import threading
                stop_progress = threading.Event()

                def show_dots():
                    while not stop_progress.is_set():
                        print(".", end='', flush=True)
                        time.sleep(2)

                progress_thread = threading.Thread(target=show_dots, daemon=True)
                progress_thread.start()

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=300,
                )
            finally:
                if show_progress:
                    stop_progress.set()
                    time.sleep(0.1)  # Let last dot print

            print(f" ✓ Success")
            return True, result.stdout
        except subprocess.TimeoutExpired:
            print(f" ✗ Timeout (>5 minutes)")
            return False, "Command timed out"
        except subprocess.CalledProcessError as e:
            print(f" ✗ Failed")
            print(f"  Error: {e.stderr[:200]}")
            return False, e.stderr
        except Exception as e:
            print(f" ✗ Error: {e}")
            return False, str(e)

    def run_doctl(self, command: list[str], description: str, show_progress: bool = False) -> Optional[dict]:
        """Execute doctl command and return JSON output."""
        full_command = ["doctl"] + command + [
            "--access-token", self.api_token,
            "--output", "json"
        ]
        success, output = self.run_command(full_command, description, show_progress=show_progress)

        if not success:
            return None

        try:
            return json.loads(output) if output.strip() else {}
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse JSON output: {e}")
            return None

    def run_ssh_realtime(self, ip: str, command: str, description: str, user: str = "root") -> bool:
        """Execute SSH command with real-time output."""
        print(f"\n→ {description}...")
        print(f"  Running on {user}@{ip}")

        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",  # Suppress SSH warnings
            f"{user}@{ip}",
            command,
        ]

        try:
            # Run with real-time output
            result = subprocess.run(ssh_command, text=True)

            if result.returncode == 0:
                print(f"✓ {description} - Success\n")
                return True
            else:
                print(f"✗ {description} - Failed (exit code: {result.returncode})\n")
                return False
        except Exception as e:
            print(f"✗ {description} - Error: {e}\n")
            return False

    def run_ssh_quiet(self, ip: str, command: str, user: str = "root") -> Tuple[bool, str]:
        """Execute SSH command and capture output (for checks)."""
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            f"{user}@{ip}",
            command,
        ]

        try:
            result = subprocess.run(ssh_command, capture_output=True, text=True, timeout=30)
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, str(e)

    def validate_step(self, condition: bool, success_msg: str, error_msg: str) -> None:
        """Validate a step and raise error if it failed."""
        if condition:
            print(f"✓ Validated: {success_msg}")
        else:
            raise DeploymentError(f"Validation failed: {error_msg}")

    def create_droplet(self, name: str, ssh_keys: Optional[list[str]] = None) -> dict:
        """Create a new Digital Ocean droplet."""
        print(f"\n{'='*60}")
        print(f"STEP 1: Creating Droplet")
        print(f"{'='*60}")
        print(f"Name: {name}")
        print(f"Region: {self.region}")
        print(f"Size: {self.size}")
        print(f"Image: {self.image}\n")

        # Get SSH keys if not provided
        if not ssh_keys:
            print("→ Fetching SSH keys from Digital Ocean account...")
            keys_data = self.run_doctl(["compute", "ssh-key", "list"], "Fetch SSH keys")

            if not keys_data:
                raise DeploymentError(
                    "No SSH keys found in Digital Ocean account.\n"
                    "Add one with: doctl compute ssh-key create my-laptop --public-key \"$(cat ~/.ssh/id_ed25519.pub)\""
                )

            ssh_keys = [str(key["id"]) for key in keys_data]
            print(f"✓ Found SSH keys: {', '.join(ssh_keys)}\n")

        # Create droplet
        print(f"\n→ Creating droplet '{name}'")
        print(f"  Region: {self.region}, Size: {self.size}")
        print(f"  This may take 1-2 minutes...\n")

        result = self.run_doctl([
            "compute", "droplet", "create", name,
            "--region", self.region,
            "--size", self.size,
            "--image", self.image,
            "--ssh-keys", ",".join(ssh_keys),
            "--wait",
        ], "Creating and waiting for droplet", show_progress=True)

        if not result or len(result) == 0:
            raise DeploymentError("Failed to create droplet")

        droplet = result[0]
        self.droplet_id = droplet["id"]
        self.created_droplet = True

        # Get public IP
        networks = droplet.get("networks", {}).get("v4", [])
        for network in networks:
            if network["type"] == "public":
                self.droplet_ip = network["ip_address"]
                break

        if not self.droplet_ip:
            raise DeploymentError("Could not get droplet IP address")

        print(f"\n✓ Droplet created successfully!")
        print(f"  ID: {self.droplet_id}")
        print(f"  IP: {self.droplet_ip}\n")

        return droplet

    def wait_for_ssh(self, ip: str, max_attempts: int = 30) -> None:
        """Wait for SSH to become available with retry logic."""
        print(f"\n{'='*60}")
        print(f"STEP 2: Waiting for SSH")
        print(f"{'='*60}\n")

        for i in range(max_attempts):
            success, _ = self.run_ssh_quiet(ip, "echo ready")
            if success:
                print(f"✓ SSH is ready on {ip}\n")
                return

            wait_time = min(10, 5 + i)  # Gradually increase wait time
            print(f"  Attempt {i+1}/{max_attempts} - waiting {wait_time}s...")
            time.sleep(wait_time)

        raise DeploymentError(f"SSH did not become available after {max_attempts} attempts")

    def provision_server(self, ip: str, mongodb_url: str = "mongodb://localhost:27017") -> None:
        """Provision the server with required software.

        Args:
            ip: Droplet IP address
            mongodb_url: MongoDB connection string (skips MongoDB install if not localhost)
        """
        print(f"\n{'='*60}")
        print(f"STEP 3: Provisioning Server")
        print(f"{'='*60}\n")

        # Check if we need to install MongoDB locally
        install_mongodb = "localhost" in mongodb_url or "127.0.0.1" in mongodb_url

        if install_mongodb:
            print("This will install: Python, MongoDB, nginx, uv, and dependencies")
        else:
            print("This will install: Python, nginx, uv, and dependencies")
            print(f"Using external MongoDB: {mongodb_url.split('@')[0] if '@' in mongodb_url else 'external'}")
        print("Expected time: 5-10 minutes\n")

        # Step 3a: System update (with retry for common issues)
        print("→ Updating package lists (may need to retry)...\n")

        # First attempt - might fail with command-not-found database issue
        success = self.run_ssh_realtime(
            ip,
            "apt-get update -qq 2>&1 || true",
            "Update package lists (attempt 1)"
        )

        # Second attempt - usually fixes command-not-found issues
        if not self.run_ssh_realtime(
            ip,
            "apt-get update -qq",
            "Update package lists (attempt 2)"
        ):
            # If still failing, try with command-not-found disabled
            print("  Retrying with command-not-found hooks disabled...\n")
            if not self.run_ssh_realtime(
                ip,
                "APT_LISTCHANGES_FRONTEND=none apt-get update -o APT::Update::Post-Invoke-Success=''",
                "Update package lists (attempt 3, hooks disabled)"
            ):
                raise DeploymentError("Failed to update package lists after multiple attempts")

        # Step 3b: Install basic packages one at a time
        packages = [
            ("python3.10", "python3.10"),
            ("python3-pip", "pip3"),
            ("git", "git"),
            ("curl", "curl"),
            ("nginx", "nginx"),
            ("supervisor", "supervisord"),
            ("certbot", "certbot"),
            ("python3-certbot-nginx", None),  # No binary to check
        ]

        print("→ Installing packages individually for better error tracking...\n")

        for package_name, binary_name in packages:
            # Install package
            if not self.run_ssh_realtime(
                ip,
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y {package_name}",
                f"Install {package_name}"
            ):
                raise DeploymentError(f"Failed to install {package_name}")

            # Validate installation (if we have a binary to check)
            if binary_name:
                success, _ = self.run_ssh_quiet(ip, f"which {binary_name}")
                if success:
                    print(f"  ✓ Verified: {binary_name} installed")
                else:
                    print(f"  ⚠ Warning: {binary_name} not found in PATH")
            else:
                print(f"  ✓ Package installed (no binary check)")

            print()  # Blank line between packages

        # Step 3c: Install uv
        if not self.run_ssh_realtime(
            ip,
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "Install uv (Python package manager)"
        ):
            raise DeploymentError("Failed to install uv")

        # Validate uv installation (check both old and new locations)
        success, _ = self.run_ssh_quiet(ip, "test -f /root/.local/bin/uv || test -f /root/.cargo/bin/uv")
        self.validate_step(
            success,
            "uv installed successfully",
            "uv binary not found in /root/.local/bin or /root/.cargo/bin"
        )

        # Step 3d: Install MongoDB (only if using local MongoDB)
        if install_mongodb:
            print("\n→ Installing MongoDB...")
            mongo_install = """
set -e
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --batch --yes --no-tty --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
apt-get update -qq
apt-get install -y -qq mongodb-org
systemctl enable mongod
systemctl start mongod
"""
            if not self.run_ssh_realtime(ip, mongo_install, "Install and start MongoDB"):
                raise DeploymentError("Failed to install MongoDB")

            # Validate MongoDB is running
            time.sleep(3)  # Give MongoDB time to start
            success, _ = self.run_ssh_quiet(ip, "systemctl is-active mongod")
            self.validate_step(
                success,
                "MongoDB is running",
                "MongoDB failed to start"
            )
        else:
            print("\n✓ Skipping MongoDB installation (using external MongoDB)\n")

        # Step 3e: Create directories
        if not self.run_ssh_realtime(
            ip,
            "mkdir -p /opt/putplace /var/log/putplace",
            "Create application directories"
        ):
            raise DeploymentError("Failed to create directories")

        print(f"\n✓ Server provisioning complete!\n")

    def generate_local_config(
        self,
        output_path: str = "./ppserver.toml",
        mongodb_url: str = "mongodb://localhost:27017",
        storage_backend: str = "local",
        storage_path: str = "/var/putplace/storage",
        s3_bucket: Optional[str] = None,
        aws_region: str = "eu-west-1",
    ) -> Path:
        """Generate ppserver.toml configuration file locally.

        Args:
            output_path: Where to save the config file
            mongodb_url: MongoDB connection string
            storage_backend: 'local' or 's3'
            storage_path: Path for local storage
            s3_bucket: S3 bucket name (required if storage_backend='s3')
            aws_region: AWS region

        Returns:
            Path to generated config file
        """
        print(f"\n{'='*60}")
        print(f"Generating Local Configuration")
        print(f"{'='*60}\n")

        config_path = Path(output_path).resolve()

        # Build putplace_configure command
        cmd = [
            "putplace_configure",
            "--non-interactive",
            "--mongodb-url", mongodb_url,
            "--mongodb-database", "putplace",
            "--storage-backend", storage_backend,
            "--storage-path", storage_path,
            "--config-file", str(config_path),
            "--skip-checks",  # Skip validation checks when generating for remote server
        ]

        if storage_backend == "s3":
            if not s3_bucket:
                raise DeploymentError("S3 bucket required when storage_backend='s3'")
            cmd.extend(["--s3-bucket", s3_bucket, "--aws-region", aws_region])

        print(f"→ Running putplace_configure...")
        print(f"  Backend: {storage_backend}")
        print(f"  MongoDB: {mongodb_url}")
        if storage_backend == "s3":
            print(f"  S3 Bucket: {s3_bucket}")
            print(f"  AWS Region: {aws_region}")
        print()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            print(f"✓ Configuration generated: {config_path}\n")
            return config_path
        except subprocess.CalledProcessError as e:
            raise DeploymentError(
                f"Failed to generate config:\n{e.stderr}\n{e.stdout}"
            )
        except FileNotFoundError:
            raise DeploymentError(
                "putplace_configure command not found. Install putplace first:\n"
                "  pip install putplace"
            )

    def copy_file_to_droplet(self, ip: str, local_path: str, remote_path: str) -> None:
        """Copy a file to the droplet using SCP.

        Args:
            ip: Droplet IP address
            local_path: Local file path
            remote_path: Remote destination path
        """
        local_file = Path(local_path)
        if not local_file.exists():
            raise DeploymentError(f"Local file not found: {local_path}")

        print(f"→ Copying {local_file.name} to droplet...")

        scp_cmd = [
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            str(local_file),
            f"root@{ip}:{remote_path}"
        ]

        try:
            result = subprocess.run(
                scp_cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            print(f"✓ Copied {local_file.name} → {remote_path}\n")
        except subprocess.CalledProcessError as e:
            raise DeploymentError(
                f"Failed to copy file:\n{e.stderr}\n{e.stdout}"
            )

    def setup_aws_credentials(
        self,
        ip: str,
        credentials_dir: str = "./aws_credentials_output",
        aws_profile: Optional[str] = None
    ) -> None:
        """Setup AWS credentials on the droplet.

        Args:
            ip: Droplet IP address
            credentials_dir: Local directory containing AWS credentials
            aws_profile: AWS profile name to use (e.g., 'putplace-prod')
        """
        creds_path = Path(credentials_dir)
        if not creds_path.exists():
            print(f"⚠ AWS credentials directory not found: {credentials_dir}")
            print("  Skipping AWS credentials setup\n")
            return

        aws_creds_file = creds_path / "aws_credentials"
        aws_config_file = creds_path / "aws_config"

        if not aws_creds_file.exists():
            print(f"⚠ AWS credentials file not found: {aws_creds_file}")
            print("  Skipping AWS credentials setup\n")
            return

        print(f"\n{'='*60}")
        print(f"Setting up AWS Credentials")
        print(f"{'='*60}\n")

        # Create .aws directory on droplet
        if not self.run_ssh_realtime(ip, "mkdir -p /root/.aws", "Create .aws directory"):
            raise DeploymentError("Failed to create .aws directory")

        # Copy credentials file
        self.copy_file_to_droplet(ip, str(aws_creds_file), "/root/.aws/credentials")

        # Copy config file if it exists
        if aws_config_file.exists():
            self.copy_file_to_droplet(ip, str(aws_config_file), "/root/.aws/config")

        # Set proper permissions
        if not self.run_ssh_realtime(
            ip,
            "chmod 600 /root/.aws/credentials /root/.aws/config 2>/dev/null || chmod 600 /root/.aws/credentials",
            "Set AWS credentials permissions"
        ):
            raise DeploymentError("Failed to set AWS credentials permissions")

        # Validate credentials were copied
        success, _ = self.run_ssh_quiet(ip, "test -f /root/.aws/credentials")
        self.validate_step(
            success,
            "AWS credentials configured successfully",
            "AWS credentials file not found on droplet"
        )

        if aws_profile:
            print(f"  AWS Profile: {aws_profile}\n")
        else:
            print("  AWS Profile: default (from credentials file)\n")

        print(f"✓ AWS credentials setup complete!\n")

    def deploy_application(self, ip: str, config_path: str, version: str = "latest") -> None:
        """Deploy the PutPlace application from pip.

        Args:
            ip: Droplet IP address
            config_path: Path to locally-generated ppserver.toml
            version: PutPlace version to install ('latest' or specific version like '0.7.0')
        """
        print(f"\n{'='*60}")
        print(f"STEP 4: Deploying Application")
        print(f"{'='*60}\n")
        print(f"Installing from: PyPI")
        print(f"Version: {version}\n")

        # Install putplace from pip
        install_cmd = """
set -e
export PATH="/root/.local/bin:/root/.cargo/bin:$PATH"
"""
        if version == "latest":
            install_cmd += "uv pip install --system putplace\n"
        else:
            install_cmd += f"uv pip install --system putplace=={version}\n"

        if not self.run_ssh_realtime(ip, install_cmd, f"Install putplace {version} from PyPI"):
            raise DeploymentError("Failed to install putplace from pip")

        # Validate installation
        success, output = self.run_ssh_quiet(ip, "which ppserver")
        self.validate_step(
            success,
            "putplace installed successfully",
            "ppserver command not found after installation"
        )

        # Create storage directory (if using local storage)
        if not self.run_ssh_realtime(ip, "mkdir -p /var/putplace/storage", "Create storage directory"):
            raise DeploymentError("Failed to create storage directory")

        # Copy ppserver.toml to the droplet
        self.copy_file_to_droplet(ip, config_path, "/opt/putplace/ppserver.toml")

        # Validate config file was copied
        success, _ = self.run_ssh_quiet(ip, "test -f /opt/putplace/ppserver.toml")
        self.validate_step(
            success,
            "Configuration file copied successfully",
            "Configuration file not found on droplet"
        )

        print(f"✓ Application deployed successfully!\n")

    def setup_systemd_service(self, ip: str, aws_profile: Optional[str] = None, mongodb_url: str = "mongodb://localhost:27017") -> None:
        """Create and enable systemd service for PutPlace.

        Args:
            ip: Droplet IP address
            aws_profile: Optional AWS profile name to set in environment
            mongodb_url: MongoDB connection string (determines if local MongoDB is required)
        """
        print(f"\n{'='*60}")
        print(f"STEP 5: Setting up Systemd Service")
        print(f"{'='*60}\n")

        # Build environment variables
        env_vars = [
            'Environment="PATH=/root/.local/bin:/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"',
            'Environment="PUTPLACE_CONFIG=/opt/putplace/ppserver.toml"',
        ]

        if aws_profile:
            env_vars.append(f'Environment="AWS_PROFILE={aws_profile}"')
            print(f"  AWS Profile: {aws_profile}")

        env_section = "\n".join(env_vars)

        # Conditionally require MongoDB service only if using local MongoDB
        install_mongodb = "localhost" in mongodb_url or "127.0.0.1" in mongodb_url

        if install_mongodb:
            after_line = "After=network.target mongod.service"
            requires_line = "Requires=mongod.service"
        else:
            after_line = "After=network.target"
            requires_line = ""

        service_file = f"""[Unit]
Description=PutPlace FastAPI Server
{after_line}
{requires_line}

[Service]
Type=simple
User=root
WorkingDirectory=/opt/putplace
{env_section}
ExecStart=/root/.local/bin/ppserver start --config /opt/putplace/ppserver.toml --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/var/log/putplace/access.log
StandardError=append:/var/log/putplace/error.log

[Install]
WantedBy=multi-user.target
"""

        setup_service = f"""
cat > /etc/systemd/system/putplace.service << 'EOF'
{service_file}
EOF
systemctl daemon-reload
systemctl enable putplace
systemctl start putplace
sleep 2
"""
        if not self.run_ssh_realtime(ip, setup_service, "Install and start systemd service"):
            raise DeploymentError("Failed to setup systemd service")

        # Validate service is running
        time.sleep(3)
        success, _ = self.run_ssh_quiet(ip, "systemctl is-active putplace")
        self.validate_step(
            success,
            "PutPlace service is running",
            "PutPlace service failed to start"
        )

        print("✓ Systemd service configured and running!\n")

    def setup_nginx(self, ip: str, domain: Optional[str] = None) -> None:
        """Configure nginx as reverse proxy."""
        print(f"\n{'='*60}")
        print(f"STEP 6: Setting up Nginx")
        print(f"{'='*60}\n")

        server_name = domain if domain else ip

        nginx_config = f"""server {{
    listen 80;
    server_name {server_name};

    location / {{
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

        setup_nginx = f"""
cat > /etc/nginx/sites-available/putplace << 'EOF'
{nginx_config}
EOF
ln -sf /etc/nginx/sites-available/putplace /etc/nginx/sites-enabled/putplace
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
"""
        if not self.run_ssh_realtime(ip, setup_nginx, "Configure nginx"):
            raise DeploymentError("Failed to configure nginx")

        # Validate nginx is running
        success, _ = self.run_ssh_quiet(ip, "systemctl is-active nginx")
        self.validate_step(
            success,
            "Nginx is running",
            "Nginx failed to start"
        )

        print("✓ Nginx configured successfully!\n")

        if domain:
            print(f"ℹ To enable SSL, run:")
            print(f"  ssh root@{ip} 'certbot --nginx -d {domain}'\n")

    def cleanup_on_failure(self) -> None:
        """Clean up resources if deployment fails."""
        if self.created_droplet and self.droplet_id:
            print(f"\n⚠ Cleaning up failed droplet (ID: {self.droplet_id})...")
            try:
                self.run_doctl(
                    ["compute", "droplet", "delete", str(self.droplet_id), "--force"],
                    "Delete failed droplet"
                )
                print("✓ Cleanup complete")
            except Exception as e:
                print(f"✗ Failed to cleanup droplet: {e}")
                print(f"  Please manually delete droplet ID: {self.droplet_id}")

    def deploy(
        self,
        droplet_name: Optional[str] = None,
        droplet_ip: Optional[str] = None,
        create_droplet: bool = False,
        domain: Optional[str] = None,
        mongodb_url: str = "mongodb://localhost:27017",
        storage_backend: str = "local",
        storage_path: str = "/var/putplace/storage",
        s3_bucket: Optional[str] = None,
        aws_region: str = "eu-west-1",
        version: str = "latest",
        config_output: str = "./ppserver.toml",
        aws_credentials_dir: str = "./aws_credentials_output",
        aws_profile: Optional[str] = None,
    ) -> None:
        """Run full deployment process with validation.

        Args:
            droplet_name: Name of existing droplet to deploy to
            droplet_ip: IP of existing droplet
            create_droplet: Create a new droplet
            domain: Optional domain name for nginx
            mongodb_url: MongoDB connection string
            storage_backend: 'local' or 's3'
            storage_path: Path for local storage
            s3_bucket: S3 bucket name (required if storage_backend='s3')
            aws_region: AWS region
            version: PutPlace version to install from PyPI
            config_output: Where to save generated ppserver.toml locally
            aws_credentials_dir: Directory containing AWS credentials (default: ./aws_credentials_output)
            aws_profile: AWS profile name to use (e.g., 'putplace-prod')
        """
        print(f"\n{'#'*60}")
        print(f"# PutPlace Digital Ocean Deployment")
        print(f"{'#'*60}\n")

        try:
            # Step 0: Generate configuration locally
            config_path = self.generate_local_config(
                output_path=config_output,
                mongodb_url=mongodb_url,
                storage_backend=storage_backend,
                storage_path=storage_path,
                s3_bucket=s3_bucket,
                aws_region=aws_region,
            )

            # Get or create droplet
            if create_droplet:
                if not droplet_name:
                    droplet_name = "putplace-droplet"
                self.create_droplet(droplet_name)
                ip = self.droplet_ip
                self.wait_for_ssh(ip)
            elif droplet_ip:
                ip = droplet_ip
            elif droplet_name:
                print("→ Looking up existing droplet...")
                droplets = self.run_doctl(["compute", "droplet", "list"], "List droplets")
                if not droplets:
                    raise DeploymentError("Could not list droplets")

                for droplet in droplets:
                    if droplet["name"] == droplet_name:
                        self.droplet_id = droplet["id"]
                        networks = droplet.get("networks", {}).get("v4", [])
                        for network in networks:
                            if network["type"] == "public":
                                ip = network["ip_address"]
                                break
                        break

                if not ip:
                    raise DeploymentError(f"Droplet '{droplet_name}' not found")

                print(f"✓ Found droplet: {droplet_name} ({ip})\n")
            else:
                raise DeploymentError("Must provide --droplet-name, --ip, or --create-droplet")

            # Run deployment steps
            self.provision_server(ip, mongodb_url)
            self.deploy_application(ip, str(config_path), version)

            # Setup AWS credentials if using S3 or if credentials directory exists
            if storage_backend == "s3" or Path(aws_credentials_dir).exists():
                self.setup_aws_credentials(ip, aws_credentials_dir, aws_profile)

            self.setup_systemd_service(ip, aws_profile, mongodb_url)
            self.setup_nginx(ip, domain)

            # Success!
            print(f"\n{'#'*60}")
            print(f"# Deployment Complete!")
            print(f"{'#'*60}\n")
            print(f"✓ Application URL: http://{domain if domain else ip}")
            print(f"✓ API Docs: http://{domain if domain else ip}/docs")
            print(f"✓ Health Check: http://{domain if domain else ip}/health")
            print(f"✓ SSH Access: ssh root@{ip}\n")
            print("Next steps:")
            print("1. Get admin credentials: ssh root@{} 'cat /tmp/putplace_initial_creds.txt'".format(ip))
            print("2. Test the API: curl http://{}/health".format(domain if domain else ip))
            if domain:
                print(f"3. Enable SSL: ssh root@{ip} 'certbot --nginx -d {domain}'")
            print()

        except DeploymentError as e:
            print(f"\n{'!'*60}")
            print(f"! Deployment Failed")
            print(f"{'!'*60}\n")
            print(f"Error: {e}\n")

            if create_droplet:
                response = input("Delete failed droplet? [y/N]: ").strip().lower()
                if response == 'y':
                    self.cleanup_on_failure()

            sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n\n⚠ Deployment interrupted by user\n")
            if create_droplet:
                response = input("Delete partial droplet? [y/N]: ").strip().lower()
                if response == 'y':
                    self.cleanup_on_failure()
            sys.exit(1)
        except Exception as e:
            print(f"\n{'!'*60}")
            print(f"! Unexpected Error")
            print(f"{'!'*60}\n")
            print(f"Error: {e}\n")
            self.cleanup_on_failure()
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy PutPlace to Digital Ocean from PyPI with local configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy to existing droplet with local MongoDB
  python -m putplace.scripts.deploy_digitalocean --droplet-name putplace-droplet

  # Deploy with MongoDB Atlas and S3 storage (with AWS credentials)
  python -m putplace.scripts.deploy_digitalocean --droplet-name putplace-droplet \\
      --mongodb-url "mongodb+srv://user:pass@cluster.mongodb.net/" \\
      --storage-backend s3 \\
      --s3-bucket putplace-prod \\
      --aws-region eu-west-1 \\
      --aws-profile putplace-prod

  # Create new droplet
  python -m putplace.scripts.deploy_digitalocean --create-droplet --droplet-name my-droplet

  # Deploy with custom AWS credentials directory
  python -m putplace.scripts.deploy_digitalocean --droplet-name putplace-droplet \\
      --storage-backend s3 \\
      --s3-bucket putplace-prod \\
      --aws-credentials-dir ./aws_credentials_output \\
      --aws-profile putplace-prod
        """
    )

    # Droplet selection
    parser.add_argument("--create-droplet", action="store_true", help="Create a new droplet")
    parser.add_argument("--droplet-name", help="Droplet name (for lookup or creation)")
    parser.add_argument("--ip", help="Droplet IP address (if already exists)")
    parser.add_argument("--domain", help="Domain name for the application")

    # Droplet configuration (only for --create-droplet)
    parser.add_argument("--region", default="fra1", help="Digital Ocean region (default: fra1)")
    parser.add_argument("--size", default="s-1vcpu-1gb", help="Droplet size (default: s-1vcpu-1gb)")

    # Application configuration
    parser.add_argument("--version", default="latest", help="PutPlace version from PyPI (default: latest)")
    parser.add_argument("--mongodb-url", default="mongodb://localhost:27017",
                       help="MongoDB connection string (default: mongodb://localhost:27017)")
    parser.add_argument("--storage-backend", default="local", choices=["local", "s3"],
                       help="Storage backend: local or s3 (default: local)")
    parser.add_argument("--storage-path", default="/var/putplace/storage",
                       help="Path for local storage (default: /var/putplace/storage)")
    parser.add_argument("--s3-bucket", help="S3 bucket name (required if --storage-backend=s3)")
    parser.add_argument("--aws-region", default="eu-west-1", help="AWS region (default: eu-west-1)")
    parser.add_argument("--config-output", default="./ppserver.toml",
                       help="Where to save generated config locally (default: ./ppserver.toml)")

    # AWS credentials configuration
    parser.add_argument("--aws-credentials-dir", default="./aws_credentials_output",
                       help="Directory containing AWS credentials (default: ./aws_credentials_output)")
    parser.add_argument("--aws-profile", help="AWS profile name (e.g., putplace-prod)")

    args = parser.parse_args()

    deployer = DigitalOceanDeployer(region=args.region, size=args.size)

    deployer.deploy(
        droplet_name=args.droplet_name,
        droplet_ip=args.ip,
        create_droplet=args.create_droplet,
        domain=args.domain,
        mongodb_url=args.mongodb_url,
        storage_backend=args.storage_backend,
        storage_path=args.storage_path,
        s3_bucket=args.s3_bucket,
        aws_region=args.aws_region,
        version=args.version,
        config_output=args.config_output,
        aws_credentials_dir=args.aws_credentials_dir,
        aws_profile=args.aws_profile,
    )


if __name__ == "__main__":
    main()
