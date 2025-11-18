#!/usr/bin/env python3
"""MongoDB Atlas Cluster Control CLI.

This script allows you to pause and resume MongoDB Atlas clusters using the Atlas API.

Usage:
    python -m putplace.scripts.atlas_cluster_control pause --cluster <name>
    python -m putplace.scripts.atlas_cluster_control resume --cluster <name>
    python -m putplace.scripts.atlas_cluster_control status --cluster <name>
    python -m putplace.scripts.atlas_cluster_control list

Prerequisites:
    1. MongoDB Atlas Service Account (OAuth 2.0)
    2. Set environment variables in .env file:
       ATLAS_CLIENT_ID="your-client-id"
       ATLAS_CLIENT_SECRET="your-client-secret"
       ATLAS_PROJECT_ID="your-project-id"

    Or set environment variables directly:
       export ATLAS_CLIENT_ID="your-client-id"
       export ATLAS_CLIENT_SECRET="your-client-secret"
       export ATLAS_PROJECT_ID="your-project-id"

How to create Service Account:
    1. Go to MongoDB Atlas console
    2. Click your profile → "Organization Access Manager"
    3. Click "Service Accounts" tab
    4. Click "Create Service Account"
    5. Give it Organization Member or Project Owner permissions
    6. Copy the Client ID and Client Secret
    7. Save the secret securely (you won't see it again!)

Cost savings:
    - Paused clusters cost ~10% of running cost (only storage)
    - Great for dev/test environments
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests


class AtlasClusterControl:
    """MongoDB Atlas cluster control via API using OAuth 2.0."""

    def __init__(self, client_id: str, client_secret: str, project_id: str):
        """Initialize Atlas API client with service account credentials.

        Args:
            client_id: Atlas service account client ID
            client_secret: Atlas service account client secret
            project_id: Atlas project/group ID
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.project_id = project_id
        self.base_url = "https://cloud.mongodb.com/api/atlas/v2"
        self.access_token = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Atlas API and get access token."""
        token_url = "https://cloud.mongodb.com/api/oauth/token"

        # MongoDB Atlas OAuth 2.0 uses Basic Auth with client_id:client_secret
        from base64 import b64encode
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = b64encode(credentials.encode()).decode()

        response = requests.post(
            token_url,
            data={"grant_type": "client_credentials"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }
        )

        if response.status_code != 200:
            print(f"✗ Authentication failed: {response.status_code}")
            print(f"  Response: {response.text}")
            print(f"\nTroubleshooting:")
            print(f"  - Verify your ATLAS_CLIENT_ID and ATLAS_CLIENT_SECRET are correct")
            print(f"  - Make sure you're using a Service Account (not API keys)")
            print(f"  - Check that the service account has proper permissions")
            sys.exit(1)

        token_data = response.json()
        self.access_token = token_data.get("access_token")

        if not self.access_token:
            print("✗ Failed to get access token from response")
            print(f"  Response: {token_data}")
            sys.exit(1)

    def _get_headers(self) -> dict:
        """Get authorization headers for API requests.

        Returns:
            Dictionary with authorization header
        """
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.atlas.2023-02-01+json"
        }

    def list_clusters(self) -> list[dict]:
        """List all clusters in the project.

        Returns:
            List of cluster information dictionaries
        """
        url = f"{self.base_url}/groups/{self.project_id}/clusters"
        response = requests.get(url, headers=self._get_headers())

        if response.status_code != 200:
            print(f"✗ Failed to list clusters: {response.status_code}")
            print(f"  Response: {response.text}")
            sys.exit(1)

        data = response.json()
        return data.get("results", [])

    def get_cluster(self, cluster_name: str) -> Optional[dict]:
        """Get information about a specific cluster.

        Args:
            cluster_name: Name of the cluster

        Returns:
            Cluster information dictionary or None if not found
        """
        url = f"{self.base_url}/groups/{self.project_id}/clusters/{cluster_name}"
        response = requests.get(url, headers=self._get_headers())

        if response.status_code == 404:
            return None
        elif response.status_code != 200:
            print(f"✗ Failed to get cluster: {response.status_code}")
            print(f"  Response: {response.text}")
            sys.exit(1)

        return response.json()

    def pause_cluster(self, cluster_name: str) -> bool:
        """Pause a cluster.

        Args:
            cluster_name: Name of the cluster to pause

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/groups/{self.project_id}/clusters/{cluster_name}"
        payload = {"paused": True}

        response = requests.patch(url, json=payload, headers=self._get_headers())

        if response.status_code == 200:
            return True
        else:
            print(f"✗ Failed to pause cluster: {response.status_code}")
            print(f"  Response: {response.text}")
            return False

    def resume_cluster(self, cluster_name: str) -> bool:
        """Resume a paused cluster.

        Args:
            cluster_name: Name of the cluster to resume

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/groups/{self.project_id}/clusters/{cluster_name}"
        payload = {"paused": False}

        response = requests.patch(url, json=payload, headers=self._get_headers())

        if response.status_code == 200:
            return True
        else:
            print(f"✗ Failed to resume cluster: {response.status_code}")
            print(f"  Response: {response.text}")
            return False


def load_credentials() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Load Atlas credentials from environment variables or .env file.

    Returns:
        Tuple of (client_id, client_secret, project_id)
    """
    # Try loading from .env file in current directory
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value and key not in os.environ:
                            os.environ[key] = value
        except Exception as e:
            print(f"Warning: Failed to read .env file: {e}")

    # Get from environment variables (either from .env or already set)
    client_id = os.environ.get("ATLAS_CLIENT_ID")
    client_secret = os.environ.get("ATLAS_CLIENT_SECRET")
    project_id = os.environ.get("ATLAS_PROJECT_ID")

    if client_id and client_secret and project_id:
        return client_id, client_secret, project_id

    return None, None, None


def format_cluster_status(cluster: dict) -> str:
    """Format cluster information for display.

    Args:
        cluster: Cluster information dictionary

    Returns:
        Formatted string
    """
    name = cluster.get("name", "Unknown")
    state = cluster.get("stateName", "Unknown")
    paused = cluster.get("paused", False)
    tier = cluster.get("providerSettings", {}).get("instanceSizeName", "Unknown")
    provider = cluster.get("providerSettings", {}).get("providerName", "Unknown")
    region = cluster.get("providerSettings", {}).get("regionName", "Unknown")

    status = "PAUSED" if paused else state
    status_icon = "⏸️ " if paused else "▶️ "

    return (
        f"{status_icon}{name}\n"
        f"  Status: {status}\n"
        f"  Tier: {tier}\n"
        f"  Provider: {provider}\n"
        f"  Region: {region}"
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MongoDB Atlas Cluster Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all clusters")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get cluster status")
    status_parser.add_argument("--cluster", "-c", required=True, help="Cluster name")

    # Pause command
    pause_parser = subparsers.add_parser("pause", help="Pause a cluster")
    pause_parser.add_argument("--cluster", "-c", required=True, help="Cluster name")

    # Resume command
    resume_parser = subparsers.add_parser("resume", help="Resume a paused cluster")
    resume_parser.add_argument("--cluster", "-c", required=True, help="Cluster name")

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load credentials
    client_id, client_secret, project_id = load_credentials()

    if not all([client_id, client_secret, project_id]):
        print("✗ MongoDB Atlas credentials not found")
        print("\nPlease add to your .env file:")
        print("  ATLAS_CLIENT_ID='your-client-id'")
        print("  ATLAS_CLIENT_SECRET='your-client-secret'")
        print("  ATLAS_PROJECT_ID='your-project-id'")
        print("\nOr set environment variables:")
        print("  export ATLAS_CLIENT_ID='your-client-id'")
        print("  export ATLAS_CLIENT_SECRET='your-client-secret'")
        print("  export ATLAS_PROJECT_ID='your-project-id'")
        print("\nHow to create a Service Account:")
        print("  1. Go to MongoDB Atlas console")
        print("  2. Click your profile → 'Organization Access Manager'")
        print("  3. Click 'Service Accounts' tab")
        print("  4. Click 'Create Service Account'")
        print("  5. Give it Organization Member or Project Owner permissions")
        print("  6. Copy the Client ID and Client Secret")
        print("  7. Save the secret securely (you won't see it again!)")
        sys.exit(1)

    # Initialize client
    client = AtlasClusterControl(client_id, client_secret, project_id)

    # Execute command
    if args.command == "list":
        print("Fetching clusters...\n")
        clusters = client.list_clusters()

        if not clusters:
            print("No clusters found in this project")
            sys.exit(0)

        for cluster in clusters:
            print(format_cluster_status(cluster))
            print()

    elif args.command == "status":
        print(f"Getting status for cluster '{args.cluster}'...\n")
        cluster = client.get_cluster(args.cluster)

        if not cluster:
            print(f"✗ Cluster '{args.cluster}' not found")
            sys.exit(1)

        print(format_cluster_status(cluster))

    elif args.command == "pause":
        print(f"Pausing cluster '{args.cluster}'...")

        # Check current status
        cluster = client.get_cluster(args.cluster)
        if not cluster:
            print(f"✗ Cluster '{args.cluster}' not found")
            sys.exit(1)

        if cluster.get("paused"):
            print(f"ℹ️  Cluster '{args.cluster}' is already paused")
            sys.exit(0)

        # Pause the cluster
        if client.pause_cluster(args.cluster):
            print(f"✓ Cluster '{args.cluster}' is being paused")
            print("  Note: It may take a few minutes to fully pause")
            print("  Paused clusters cost ~10% of running cost (storage only)")
        else:
            sys.exit(1)

    elif args.command == "resume":
        print(f"Resuming cluster '{args.cluster}'...")

        # Check current status
        cluster = client.get_cluster(args.cluster)
        if not cluster:
            print(f"✗ Cluster '{args.cluster}' not found")
            sys.exit(1)

        if not cluster.get("paused"):
            print(f"ℹ️  Cluster '{args.cluster}' is already running")
            sys.exit(0)

        # Resume the cluster
        if client.resume_cluster(args.cluster):
            print(f"✓ Cluster '{args.cluster}' is being resumed")
            print("  Note: It may take 5-10 minutes for cluster to be fully operational")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
