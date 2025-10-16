#!/usr/bin/env python3
"""Bootstrap script to create the first API key for PutPlace.

Usage:
    python -m putplace.scripts.create_api_key --name "my-first-key" --description "Initial API key"

This script connects directly to MongoDB and creates an API key without requiring
existing authentication. Use this to create your first API key.
"""

import asyncio
import sys
from typing import Optional

import configargparse

from putplace.auth import APIKeyAuth
from putplace.config import settings
from putplace.database import MongoDB


async def create_first_api_key(name: str, description: Optional[str] = None) -> None:
    """Create an API key directly in the database.

    Args:
        name: Name for the API key
        description: Optional description
    """
    # Create database connection
    db = MongoDB()

    try:
        # Connect to MongoDB
        print(f"Connecting to MongoDB at {settings.mongodb_url}...")
        await db.connect()
        print("✓ Connected to MongoDB")

        # Create API key auth
        auth = APIKeyAuth(db)

        # Create the API key
        print(f"\nCreating API key '{name}'...")
        api_key, metadata = await auth.create_api_key(name=name, description=description)

        print("\n" + "=" * 80)
        print("✓ API Key Created Successfully!")
        print("=" * 80)
        print(f"\nAPI Key ID: {metadata['_id']}")
        print(f"Name: {metadata['name']}")
        if metadata.get('description'):
            print(f"Description: {metadata['description']}")
        print(f"Created: {metadata['created_at']}")
        print(f"\n⚠️  IMPORTANT: Save this API key - it won't be shown again!")
        print(f"\n  API Key: {api_key}")
        print(f"\n")
        print("=" * 80)
        print("\nUsage:")
        print(f"  curl -H 'X-API-Key: {api_key}' http://localhost:8000/api_keys")
        print("\nOr in your .env file:")
        print(f"  PUTPLACE_API_KEY={api_key}")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Close database connection
        await db.close()
        print("\n✓ Database connection closed")


def main() -> int:
    """Main entry point."""
    parser = configargparse.ArgumentParser(
        description="Create a new PutPlace API key (bootstrap script)",
        formatter_class=configargparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create first API key
  python -m putplace.scripts.create_api_key --name "admin-key"

  # With description
  python -m putplace.scripts.create_api_key \\
      --name "production-server-01" \\
      --description "API key for production server #1"

Configuration:
  This script uses settings from .env file or environment variables:
  - MONGODB_URL
  - MONGODB_DATABASE

Notes:
  - This script bypasses API authentication (bootstrap only)
  - After creating the first key, use the API to create additional keys
  - The API key is shown only once - save it securely!
        """,
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Name for the API key (e.g., 'admin-key', 'server-01')",
    )

    parser.add_argument(
        "--description",
        help="Optional description of the key's purpose",
    )

    args = parser.parse_args()

    # Run async function
    asyncio.run(create_first_api_key(name=args.name, description=args.description))

    return 0


if __name__ == "__main__":
    sys.exit(main())
