#!/usr/bin/env python3
"""Purge database and S3 files (DEV/TEST ONLY).

This script completely purges all data from MongoDB and S3 storage.
It is ONLY allowed to run on development and test environments.

Safety Features:
- Environment detection from database name, config, or explicit flag
- Only runs on databases with 'dev' or 'test' in the name, or with --allow-environment flag
- Requires confirmation before purging (unless --force is used)
- Shows statistics before and after purging

Usage:
    # Purge dev environment (default - will prompt for confirmation)
    purge_data

    # Purge test environment
    purge_data --environment test

    # Force purge dev without confirmation
    purge_data --force

    # Dry run (show what would be purged without actually purging)
    purge_data --dry-run

    # Specify custom MongoDB URL with dev environment (default)
    purge_data --mongodb-url mongodb://localhost:27017 --database putplace_dev
"""

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from pymongo import AsyncMongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import config and storage
from putplace_server.config import Settings
from putplace_server.storage import S3Storage, get_storage_backend

console = Console()


def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message in blue."""
    console.print(f"[blue]→[/blue] {message}")


def detect_environment(database_name: str, mongodb_url: str) -> Optional[str]:
    """Detect environment from database name or URL.

    Args:
        database_name: Name of the MongoDB database
        mongodb_url: MongoDB connection URL

    Returns:
        'dev', 'test', 'prod', or None if cannot determine
    """
    db_lower = database_name.lower()
    url_lower = mongodb_url.lower()

    # Check database name
    if "test" in db_lower:
        return "test"
    elif "dev" in db_lower:
        return "dev"
    elif "prod" in db_lower or "production" in db_lower:
        return "prod"

    # Check URL
    if "test" in url_lower:
        return "test"
    elif "dev" in url_lower:
        return "dev"
    elif "prod" in url_lower or "production" in url_lower:
        return "prod"

    # Check environment variable
    env_var = os.environ.get("PUTPLACE_ENVIRONMENT", "").lower()
    if env_var in ["dev", "test", "prod", "production"]:
        return "test" if env_var == "production" else env_var

    # Default to None (unknown)
    return None


def is_safe_environment(environment: Optional[str]) -> bool:
    """Check if environment is safe to purge.

    Args:
        environment: Environment name

    Returns:
        True if safe to purge (dev or test), False otherwise
    """
    return environment in ["dev", "test"]


async def get_collection_counts(client: AsyncMongoClient, database: str) -> dict[str, int]:
    """Get document counts for all collections.

    Args:
        client: MongoDB client
        database: Database name

    Returns:
        Dictionary mapping collection name to document count
    """
    db = client[database]
    counts = {}

    # List all collections
    collection_names = await db.list_collection_names()

    for name in collection_names:
        collection = db[name]
        count = await collection.count_documents({})
        counts[name] = count

    return counts


async def purge_database(
    client: AsyncMongoClient,
    database: str,
    dry_run: bool = False
) -> dict[str, int]:
    """Purge all collections in the database.

    Args:
        client: MongoDB client
        database: Database name
        dry_run: If True, only show what would be deleted

    Returns:
        Dictionary mapping collection name to number of deleted documents
    """
    db = client[database]
    deleted_counts = {}

    # Get all collections
    collection_names = await db.list_collection_names()

    for name in collection_names:
        collection = db[name]

        if dry_run:
            count = await collection.count_documents({})
            deleted_counts[name] = count
        else:
            result = await collection.delete_many({})
            deleted_counts[name] = result.deleted_count

    return deleted_counts


async def purge_s3_files(
    bucket_name: str,
    region_name: str,
    prefix: str,
    aws_profile: Optional[str] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    dry_run: bool = False
) -> int:
    """Purge all files from S3 bucket.

    Args:
        bucket_name: S3 bucket name
        region_name: AWS region name
        prefix: Key prefix for files
        aws_profile: AWS profile name (optional)
        aws_access_key_id: AWS access key (optional)
        aws_secret_access_key: AWS secret key (optional)
        dry_run: If True, only show what would be deleted

    Returns:
        Number of files deleted (or would be deleted in dry run)
    """
    try:
        import aioboto3

        # Create session
        session_kwargs = {}
        if aws_profile:
            session_kwargs["profile_name"] = aws_profile
        elif aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        session = aioboto3.Session(**session_kwargs)

        deleted_count = 0

        async with session.client("s3", region_name=region_name) as s3:
            # List all objects with the prefix
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                if "Contents" not in page:
                    continue

                objects = page["Contents"]
                deleted_count += len(objects)

                if not dry_run:
                    # Delete objects in batches
                    delete_keys = [{"Key": obj["Key"]} for obj in objects]
                    if delete_keys:
                        await s3.delete_objects(
                            Bucket=bucket_name,
                            Delete={"Objects": delete_keys}
                        )

        return deleted_count

    except ImportError:
        print_error("aioboto3 library not installed. Install with: pip install aioboto3")
        return 0
    except Exception as e:
        print_error(f"Failed to purge S3 files: {e}")
        return 0


def purge_ppassist_database(dry_run: bool = False) -> bool:
    """Purge the ppassist SQLite database.

    This now uses the proper pp_assist_purge script which handles:
    - Stopping the pp_assist daemon if running
    - Backing up the database
    - Deleting the database
    - Restarting the daemon if it was running

    Args:
        dry_run: If True, only show what would be deleted without deleting

    Returns:
        True if database was deleted (or would be in dry run), False otherwise
    """
    import subprocess

    try:
        # Use pp_assist_purge script which properly stops/restarts daemon
        cmd = ["pp_assist_purge", "--force"]
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            # Script output is already nicely formatted, don't duplicate
            return True
        else:
            print_warning(f"pp_assist_purge exited with code {result.returncode}")
            if result.stderr:
                print_error(f"Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print_error("pp_assist_purge timed out after 30 seconds")
        return False
    except FileNotFoundError:
        print_warning("pp_assist_purge command not found - ppassist may not be installed")
        return False
    except Exception as e:
        print_warning(f"Failed to purge ppassist database: {e}")
        return False


def display_statistics(title: str, counts: dict[str, int]) -> None:
    """Display collection statistics in a table.

    Args:
        title: Table title
        counts: Dictionary mapping collection name to document count
    """
    if not counts:
        print_info("No collections found")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents", justify="right", style="yellow")

    total = 0
    for name, count in sorted(counts.items()):
        table.add_row(name, str(count))
        total += count

    table.add_section()
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total}[/bold]")

    console.print(table)


async def run_purge(
    mongodb_url: str,
    database: str,
    environment: Optional[str],
    allow_environment: bool,
    storage_backend: str,
    s3_bucket_name: Optional[str],
    s3_region_name: str,
    s3_prefix: str,
    aws_profile: Optional[str],
    aws_access_key_id: Optional[str],
    aws_secret_access_key: Optional[str],
    force: bool,
    dry_run: bool
) -> int:
    """Run the purge operation.

    Returns:
        0 on success, 1 on error
    """
    # Detect environment if not explicitly provided
    if environment is None:
        environment = detect_environment(database, mongodb_url)

    # Display environment information
    console.print(Panel.fit(
        f"[bold]Database:[/bold] {database}\n"
        f"[bold]MongoDB URL:[/bold] {mongodb_url}\n"
        f"[bold]Environment:[/bold] {environment or 'UNKNOWN'}\n"
        f"[bold]Storage Backend:[/bold] {storage_backend}",
        title="[bold red]PURGE OPERATION[/bold red]",
        border_style="red"
    ))

    # Safety check: only allow dev/test environments
    if not allow_environment and not is_safe_environment(environment):
        print_error(
            f"Cannot purge environment '{environment}'. "
            "Only 'dev' and 'test' environments are allowed."
        )
        print_info(
            "If you really want to purge this environment, use --allow-environment flag "
            "(NOT recommended for production!)"
        )
        return 1

    # Connect to MongoDB
    try:
        print_info("Connecting to MongoDB...")
        client = AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
        print_success("Connected to MongoDB")
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print_error(f"Failed to connect to MongoDB: {e}")
        return 1

    try:
        # Get current statistics
        print_info("Gathering statistics...")
        counts_before = await get_collection_counts(client, database)
        display_statistics("Current Database Contents", counts_before)

        # Count S3 files if using S3 storage
        s3_files_count = 0
        if storage_backend == "s3" and s3_bucket_name:
            print_info("Counting S3 files...")
            s3_files_count = await purge_s3_files(
                bucket_name=s3_bucket_name,
                region_name=s3_region_name,
                prefix=s3_prefix,
                aws_profile=aws_profile,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                dry_run=True  # Just count
            )
            print_info(f"S3 files to delete: {s3_files_count}")

        # Calculate total documents
        total_docs = sum(counts_before.values())

        if total_docs == 0 and s3_files_count == 0:
            print_warning("Database and storage are already empty")
            return 0

        # Confirmation prompt (unless --force or --dry-run)
        if not force and not dry_run:
            console.print()
            console.print(Panel.fit(
                f"[bold red]WARNING:[/bold red] This will DELETE:\n"
                f"  • [yellow]{total_docs}[/yellow] documents from MongoDB\n"
                f"  • [yellow]{s3_files_count}[/yellow] files from S3 storage\n\n"
                f"[bold]This operation CANNOT be undone![/bold]",
                border_style="red"
            ))
            console.print()

            confirmation = console.input(
                "[bold red]Type 'DELETE' to confirm purge:[/bold red] "
            )

            if confirmation != "DELETE":
                print_warning("Purge cancelled")
                return 0

        # Perform purge
        if dry_run:
            print_warning("[DRY RUN] No data will be deleted")
        else:
            print_info("Purging database...")

        deleted_counts = await purge_database(client, database, dry_run=dry_run)

        if dry_run:
            display_statistics("Would Delete from Database", deleted_counts)
        else:
            display_statistics("Deleted from Database", deleted_counts)

        # Purge S3 files if using S3 storage
        if storage_backend == "s3" and s3_bucket_name and s3_files_count > 0:
            if dry_run:
                print_info(f"[DRY RUN] Would delete {s3_files_count} files from S3")
            else:
                print_info("Purging S3 files...")
                deleted_s3 = await purge_s3_files(
                    bucket_name=s3_bucket_name,
                    region_name=s3_region_name,
                    prefix=s3_prefix,
                    aws_profile=aws_profile,
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key,
                    dry_run=dry_run
                )
                print_success(f"Deleted {deleted_s3} files from S3")

        # Purge ppassist SQLite database
        print_info("Purging ppassist database...")
        purge_ppassist_database(dry_run=dry_run)

        # Get final statistics
        if not dry_run:
            counts_after = await get_collection_counts(client, database)
            display_statistics("Final Database Contents", counts_after)

        if dry_run:
            print_warning("[DRY RUN] No data was actually deleted")
        else:
            print_success("Purge completed successfully!")

        return 0

    finally:
        await client.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Purge database and S3 files (DEV/TEST ONLY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--config-file",
        help="Path to ppserver.toml config file (overrides PUTPLACE_CONFIG env var)"
    )
    parser.add_argument(
        "--mongodb-url",
        help="MongoDB connection URL (default: from config or mongodb://localhost:27017)"
    )
    parser.add_argument(
        "--database",
        help="Database name (default: from config or 'putplace')"
    )
    parser.add_argument(
        "--environment",
        choices=["dev", "test"],
        default="dev",
        help="Environment to purge (default: dev)"
    )
    parser.add_argument(
        "--allow-environment",
        action="store_true",
        help="Allow purging any environment (DANGEROUS - use with extreme caution!)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be purged without actually purging"
    )

    args = parser.parse_args()

    # Set PUTPLACE_CONFIG environment variable if --config-file is specified
    if args.config_file:
        import os
        os.environ['PUTPLACE_CONFIG'] = args.config_file
        print_info(f"Using config file: {args.config_file}")

    # Load settings from config
    try:
        settings = Settings()
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        return 1

    # Use command line args or fall back to config
    mongodb_url = args.mongodb_url or settings.mongodb_url
    database = args.database or settings.mongodb_database
    storage_backend = settings.storage_backend
    s3_bucket_name = settings.s3_bucket_name
    s3_region_name = settings.s3_region_name
    s3_prefix = settings.s3_prefix
    aws_profile = settings.aws_profile
    aws_access_key_id = settings.aws_access_key_id
    aws_secret_access_key = settings.aws_secret_access_key

    # Run the purge
    return asyncio.run(run_purge(
        mongodb_url=mongodb_url,
        database=database,
        environment=args.environment,
        allow_environment=args.allow_environment,
        storage_backend=storage_backend,
        s3_bucket_name=s3_bucket_name,
        s3_region_name=s3_region_name,
        s3_prefix=s3_prefix,
        aws_profile=aws_profile,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        force=args.force,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    sys.exit(main())
