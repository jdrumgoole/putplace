#!/usr/bin/env python3
"""
Automated deployment script for PutPlace on Digital Ocean.

This script automates the entire deployment process:
1. Creates a Digital Ocean droplet (if needed)
2. Provisions the server with required software
3. Deploys the PutPlace application
4. Sets up systemd service and nginx reverse proxy
5. Configures SSL with Let's Encrypt (optional)

Prerequisites:
    - Digital Ocean API token (set in DIGITALOCEAN_TOKEN env var)
    - SSH key added to Digital Ocean account
    - Domain name pointed to droplet IP (for SSL)

Usage:
    python -m putplace.scripts.deploy_digitalocean --create-droplet
    python -m putplace.scripts.deploy_digitalocean --ip 165.22.xxx.xxx
    python -m putplace.scripts.deploy_digitalocean --droplet-name putplace-prod
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def load_env_file() -> None:
    """Load .env file from project root if it exists."""
    try:
        from dotenv import load_dotenv

        # Try to find .env file in common locations
        possible_paths = [
            Path.cwd() / ".env",  # Current directory
            Path(__file__).parent.parent.parent.parent / ".env",  # Project root
            Path.home() / ".env",  # Home directory
        ]

        for env_path in possible_paths:
            if env_path.exists():
                load_dotenv(env_path)
                print(f"Loaded environment from: {env_path}")
                break
    except ImportError:
        # dotenv not installed, skip
        pass


class DigitalOceanDeployer:
    """Manages Digital Ocean droplet deployment for PutPlace."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        region: str = "fra1",
        size: str = "s-1vcpu-1gb",
        image: str = "ubuntu-22-04-x64",
    ):
        # Try to load from .env file first
        load_env_file()

        self.api_token = api_token or os.environ.get("DIGITALOCEAN_TOKEN")
        if not self.api_token:
            raise ValueError(
                "Digital Ocean API token required. Set DIGITALOCEAN_TOKEN in .env file, "
                "environment variable, or pass as argument."
            )
        self.region = region
        self.size = size
        self.image = image
        self.droplet_id: Optional[int] = None
        self.droplet_ip: Optional[str] = None

    def run_doctl(self, command: list[str]) -> dict:
        """Execute doctl command and return JSON output."""
        try:
            result = subprocess.run(
                ["doctl"] + command + ["--access-token", self.api_token, "--output", "json"],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {}
        except subprocess.CalledProcessError as e:
            print(f"Error executing doctl: {e.stderr}", file=sys.stderr)
            raise
        except FileNotFoundError:
            print(
                "Error: doctl not found. Install with: brew install doctl",
                file=sys.stderr,
            )
            sys.exit(1)

    def run_ssh(self, ip: str, command: str, user: str = "root") -> subprocess.CompletedProcess:
        """Execute command via SSH."""
        ssh_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{user}@{ip}",
            command,
        ]
        return subprocess.run(ssh_command, capture_output=True, text=True, check=True)

    def create_droplet(self, name: str, ssh_keys: Optional[list[str]] = None) -> dict:
        """Create a new Digital Ocean droplet."""
        print(f"\nCreating droplet: {name}")
        print(f"  Region: {self.region}")
        print(f"  Size: {self.size}")
        print(f"  Image: {self.image}")

        # Get SSH keys if not provided
        if not ssh_keys:
            print("\nFetching SSH keys from Digital Ocean account...")
            keys_data = self.run_doctl(["compute", "ssh-key", "list"])
            if not keys_data:
                print("Error: No SSH keys found in Digital Ocean account.", file=sys.stderr)
                print("Add an SSH key first: doctl compute ssh-key create ...", file=sys.stderr)
                sys.exit(1)
            ssh_keys = [str(key["id"]) for key in keys_data]
            print(f"  Using SSH keys: {', '.join(ssh_keys)}")

        # Create droplet
        result = self.run_doctl([
            "compute", "droplet", "create", name,
            "--region", self.region,
            "--size", self.size,
            "--image", self.image,
            "--ssh-keys", ",".join(ssh_keys),
            "--wait",
        ])

        if result and len(result) > 0:
            droplet = result[0]
            self.droplet_id = droplet["id"]
            # Get public IP
            networks = droplet.get("networks", {}).get("v4", [])
            for network in networks:
                if network["type"] == "public":
                    self.droplet_ip = network["ip_address"]
                    break

            print(f"✓ Droplet created successfully!")
            print(f"  ID: {self.droplet_id}")
            print(f"  IP: {self.droplet_ip}")
            return droplet

        raise RuntimeError("Failed to create droplet")

    def get_droplet_by_name(self, name: str) -> Optional[dict]:
        """Get droplet information by name."""
        droplets = self.run_doctl(["compute", "droplet", "list"])
        for droplet in droplets:
            if droplet["name"] == name:
                self.droplet_id = droplet["id"]
                # Get public IP
                networks = droplet.get("networks", {}).get("v4", [])
                for network in networks:
                    if network["type"] == "public":
                        self.droplet_ip = network["ip_address"]
                        break
                return droplet
        return None

    def wait_for_ssh(self, ip: str, max_attempts: int = 30) -> None:
        """Wait for SSH to become available."""
        print(f"\nWaiting for SSH to be available on {ip}...")
        for i in range(max_attempts):
            try:
                subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
                     "-o", "UserKnownHostsFile=/dev/null", f"root@{ip}", "echo ready"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                print("✓ SSH is ready")
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                print(f"  Attempt {i+1}/{max_attempts}...")
                time.sleep(10)

        raise RuntimeError("SSH did not become available in time")

    def provision_server(self, ip: str) -> None:
        """Provision the server with required software."""
        print(f"\nProvisioning server at {ip}...")

        # Create provisioning script
        provision_script = """#!/bin/bash
set -e

echo "Updating system packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

echo "Installing required packages..."
apt-get install -y -qq \\
    python3.10 \\
    python3-pip \\
    git \\
    curl \\
    nginx \\
    supervisor \\
    certbot \\
    python3-certbot-nginx

echo "Installing uv (Python package manager)..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.cargo/bin:$PATH"

echo "Installing MongoDB..."
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \\
    gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \\
    tee /etc/apt/sources.list.d/mongodb-org-7.0.list
apt-get update -qq
apt-get install -y -qq mongodb-org

echo "Starting MongoDB..."
systemctl enable mongod
systemctl start mongod

echo "Creating application directory..."
mkdir -p /opt/putplace
mkdir -p /var/log/putplace

echo "✓ Server provisioning complete"
"""

        # Write script to temporary file and execute
        script_path = "/tmp/provision.sh"
        self.run_ssh(ip, f"cat > {script_path} << 'EOF'\n{provision_script}\nEOF")
        self.run_ssh(ip, f"chmod +x {script_path}")

        print("  Running provisioning script (this may take 5-10 minutes)...")
        result = self.run_ssh(ip, f"bash {script_path}")
        print(result.stdout)

        print("✓ Server provisioned successfully")

    def deploy_application(self, ip: str, git_repo: str, branch: str = "main") -> None:
        """Deploy the PutPlace application."""
        print(f"\nDeploying application from {git_repo}...")

        deploy_script = f"""#!/bin/bash
set -e

cd /opt/putplace

echo "Cloning repository..."
if [ -d "putplace" ]; then
    cd putplace
    git fetch origin
    git checkout {branch}
    git pull origin {branch}
else
    git clone {git_repo} putplace
    cd putplace
    git checkout {branch}
fi

echo "Setting up Python environment..."
export PATH="/root/.cargo/bin:$PATH"
uv venv
source .venv/bin/activate

echo "Installing dependencies..."
uv pip install -e '.[dev]'

echo "Creating .env file..."
cat > .env << 'ENVEOF'
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace
MONGODB_COLLECTION=file_metadata
API_TITLE=PutPlace API
API_VERSION=0.7.0
API_DESCRIPTION=File metadata storage service
ALLOW_REGISTRATION=false
ENVEOF

echo "Running database migrations (if any)..."
# Add migration commands here if needed

echo "✓ Application deployed successfully"
"""

        script_path = "/tmp/deploy.sh"
        self.run_ssh(ip, f"cat > {script_path} << 'EOF'\n{deploy_script}\nEOF")
        self.run_ssh(ip, f"chmod +x {script_path}")

        print("  Running deployment script...")
        result = self.run_ssh(ip, f"bash {script_path}")
        print(result.stdout)

        print("✓ Application deployed successfully")

    def setup_systemd_service(self, ip: str) -> None:
        """Create and enable systemd service for PutPlace."""
        print("\nSetting up systemd service...")

        service_file = """[Unit]
Description=PutPlace FastAPI Server
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/putplace/putplace
Environment="PATH=/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/putplace/putplace/.venv/bin/uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10
StandardOutput=append:/var/log/putplace/access.log
StandardError=append:/var/log/putplace/error.log

[Install]
WantedBy=multi-user.target
"""

        self.run_ssh(ip, f"cat > /etc/systemd/system/putplace.service << 'EOF'\n{service_file}\nEOF")
        self.run_ssh(ip, "systemctl daemon-reload")
        self.run_ssh(ip, "systemctl enable putplace")
        self.run_ssh(ip, "systemctl start putplace")

        print("✓ Systemd service configured and started")

    def setup_nginx(self, ip: str, domain: Optional[str] = None) -> None:
        """Configure nginx as reverse proxy."""
        print("\nSetting up nginx reverse proxy...")

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

        self.run_ssh(ip, f"cat > /etc/nginx/sites-available/putplace << 'EOF'\n{nginx_config}\nEOF")
        self.run_ssh(ip, "ln -sf /etc/nginx/sites-available/putplace /etc/nginx/sites-enabled/putplace")
        self.run_ssh(ip, "rm -f /etc/nginx/sites-enabled/default")
        self.run_ssh(ip, "nginx -t")
        self.run_ssh(ip, "systemctl reload nginx")

        print("✓ Nginx configured successfully")

        if domain:
            print(f"\nTo enable SSL, run:")
            print(f"  ssh root@{ip} 'certbot --nginx -d {domain}'")

    def deploy(
        self,
        droplet_name: Optional[str] = None,
        droplet_ip: Optional[str] = None,
        create_droplet: bool = False,
        git_repo: str = "https://github.com/jdrumgoole/putplace.git",
        branch: str = "main",
        domain: Optional[str] = None,
    ) -> None:
        """Run full deployment process."""
        print("=== PutPlace Digital Ocean Deployment ===\n")

        # Get or create droplet
        if create_droplet:
            if not droplet_name:
                droplet_name = "putplace-droplet"
            self.create_droplet(droplet_name)
            ip = self.droplet_ip
        elif droplet_ip:
            ip = droplet_ip
        elif droplet_name:
            droplet = self.get_droplet_by_name(droplet_name)
            if not droplet:
                print(f"Error: Droplet '{droplet_name}' not found", file=sys.stderr)
                sys.exit(1)
            ip = self.droplet_ip
        else:
            print("Error: Must provide --droplet-name, --ip, or --create-droplet", file=sys.stderr)
            sys.exit(1)

        if not ip:
            print("Error: Could not determine droplet IP", file=sys.stderr)
            sys.exit(1)

        # Wait for SSH if newly created
        if create_droplet:
            self.wait_for_ssh(ip)

        # Run deployment steps
        self.provision_server(ip)
        self.deploy_application(ip, git_repo, branch)
        self.setup_systemd_service(ip)
        self.setup_nginx(ip, domain)

        print("\n=== Deployment Complete! ===\n")
        print(f"Application URL: http://{domain if domain else ip}")
        print(f"API Docs: http://{domain if domain else ip}/docs")
        print(f"SSH Access: ssh root@{ip}")
        print("\nNext steps:")
        print("1. Configure admin user and API keys")
        print("2. Set up SSL certificate (if using domain)")
        print("3. Configure firewall rules")
        print("4. Set up monitoring and backups")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy PutPlace to Digital Ocean",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--create-droplet",
        action="store_true",
        help="Create a new droplet",
    )
    parser.add_argument(
        "--droplet-name",
        help="Droplet name (for lookup or creation)",
    )
    parser.add_argument(
        "--ip",
        help="Droplet IP address (if already exists)",
    )
    parser.add_argument(
        "--region",
        default="fra1",
        help="Digital Ocean region (default: fra1/Frankfurt)",
    )
    parser.add_argument(
        "--size",
        default="s-1vcpu-1gb",
        help="Droplet size (default: s-1vcpu-1gb, $6/month)",
    )
    parser.add_argument(
        "--git-repo",
        default="https://github.com/jdrumgoole/putplace.git",
        help="Git repository URL",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Git branch to deploy (default: main)",
    )
    parser.add_argument(
        "--domain",
        help="Domain name for the application (for nginx and SSL)",
    )

    args = parser.parse_args()

    deployer = DigitalOceanDeployer(
        region=args.region,
        size=args.size,
    )

    deployer.deploy(
        droplet_name=args.droplet_name,
        droplet_ip=args.ip,
        create_droplet=args.create_droplet,
        git_repo=args.git_repo,
        branch=args.branch,
        domain=args.domain,
    )


if __name__ == "__main__":
    main()
