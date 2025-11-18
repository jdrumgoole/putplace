#!/usr/bin/env python3
"""
Quick update script for PutPlace on Digital Ocean.

Updates the application code and restarts the service without
full reprovisioning. Use this for quick deployments after
initial setup.

Usage:
    python -m putplace.scripts.update_deployment --ip 165.22.xxx.xxx
    python -m putplace.scripts.update_deployment --droplet-name putplace-prod
    python -m putplace.scripts.update_deployment --ip 165.22.xxx.xxx --branch develop
"""

import argparse
import subprocess
import sys
from pathlib import Path


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
                break
    except ImportError:
        # dotenv not installed, skip
        pass


def run_ssh(ip: str, command: str, user: str = "root") -> str:
    """Execute command via SSH and return output."""
    ssh_command = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"{user}@{ip}",
        command,
    ]
    result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
    return result.stdout


def get_droplet_ip(droplet_name: str) -> str:
    """Get droplet IP from name using doctl."""
    try:
        result = subprocess.run(
            ["doctl", "compute", "droplet", "list", "--format", "Name,PublicIPv4", "--no-header"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.strip().split("\n"):
            if line.startswith(droplet_name):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[-1]
    except subprocess.CalledProcessError:
        pass
    raise ValueError(f"Could not find IP for droplet: {droplet_name}")


def update_deployment(ip: str, branch: str = "main") -> None:
    """Update the application code and restart service."""
    print(f"\n=== Updating PutPlace Deployment on {ip} ===\n")

    update_script = f"""#!/bin/bash
set -e

cd /opt/putplace/putplace

echo "Pulling latest code from {branch}..."
git fetch origin
git checkout {branch}
git pull origin {branch}

echo "Activating virtual environment..."
export PATH="/root/.cargo/bin:$PATH"
source .venv/bin/activate

echo "Updating dependencies..."
uv pip install -e '.[dev]'

echo "Restarting service..."
systemctl restart putplace

echo "Checking service status..."
sleep 2
systemctl status putplace --no-pager || true

echo ""
echo "✓ Deployment updated successfully"
echo ""
echo "Application logs:"
echo "  tail -f /var/log/putplace/error.log"
echo "  tail -f /var/log/putplace/access.log"
echo ""
echo "Service status:"
echo "  systemctl status putplace"
"""

    print("Uploading update script...")
    run_ssh(ip, f"cat > /tmp/update.sh << 'EOF'\n{update_script}\nEOF")
    run_ssh(ip, "chmod +x /tmp/update.sh")

    print("Running update script...\n")
    output = run_ssh(ip, "bash /tmp/update.sh")
    print(output)

    print("\n=== Update Complete! ===\n")
    print(f"Check application: http://{ip}")
    print(f"View logs: ssh root@{ip} 'tail -f /var/log/putplace/error.log'")


def main():
    """Main entry point."""
    # Load .env file if it exists
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Quick update for PutPlace on Digital Ocean"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--ip",
        help="Droplet IP address",
    )
    group.add_argument(
        "--droplet-name",
        help="Droplet name (will lookup IP)",
    )

    parser.add_argument(
        "--branch",
        default="main",
        help="Git branch to deploy (default: main)",
    )

    args = parser.parse_args()

    # Get IP
    if args.ip:
        ip = args.ip
    else:
        print(f"Looking up IP for droplet: {args.droplet_name}")
        ip = get_droplet_ip(args.droplet_name)
        print(f"Found IP: {ip}\n")

    # Run update
    try:
        update_deployment(ip, args.branch)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Update failed: {e}", file=sys.stderr)
        if e.stderr:
            print(f"Error output: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Update failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
