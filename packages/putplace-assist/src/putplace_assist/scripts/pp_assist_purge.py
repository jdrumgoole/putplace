#!/usr/bin/env python3
"""Purge PutPlace Assist SQLite database.

This script completely purges the SQLite database used by pp_assist.
It uses the same config file search path as pp_assist to find the database location.

Safety Features:
- Automatically stops pp_assist daemon before purging (to release database lock)
- Backs up the database before deletion
- Requires confirmation before purging (unless --force is used)
- Shows database information before purging
- Supports dry-run mode
- Automatically restarts daemon after purging if it was running

Usage:
    # Purge database (will prompt for confirmation)
    pp_assist_purge

    # Force purge without confirmation
    pp_assist_purge --force

    # Dry run (show what would be purged without actually purging)
    pp_assist_purge --dry-run

    # Use specific config file
    pp_assist_purge --config-file /path/to/pp_assist.toml

    # Use explicit database path (bypass config file)
    pp_assist_purge --database-path /path/to/assist.db

Notes:
    - The daemon will be automatically stopped before purge and restarted after
    - This prevents issues with the daemon holding locks on the old database file
    - If daemon restart fails, you'll need to manually run: pp_assist start
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

# Import config
from putplace_assist.config import find_config_file, Settings

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


def get_database_info(db_path: Path) -> dict:
    """Get information about the database.

    Args:
        db_path: Path to the database file

    Returns:
        Dictionary with database information
    """
    info = {
        "exists": db_path.exists(),
        "size": 0,
        "path": str(db_path.resolve()),
    }

    if db_path.exists():
        info["size"] = db_path.stat().st_size

    return info


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string.

    Args:
        size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def is_daemon_running() -> bool:
    """Check if pp_assist daemon is running.

    Returns:
        True if daemon is running, False otherwise
    """
    try:
        result = subprocess.run(
            ["pp_assist", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # If status command succeeds and output contains "running", daemon is up
        return result.returncode == 0 and "running" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def stop_daemon() -> bool:
    """Stop the pp_assist daemon.

    Returns:
        True if stopped successfully, False otherwise
    """
    try:
        result = subprocess.run(
            ["pp_assist", "stop"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Return code 0 means success, or daemon wasn't running (also success)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print_error(f"Failed to stop daemon: {e}")
        return False


def start_daemon() -> bool:
    """Start the pp_assist daemon.

    Returns:
        True if started successfully, False otherwise
    """
    try:
        # Start daemon without capturing output (it forks and runs in background)
        # Using stdout=subprocess.DEVNULL to avoid capturing which would block
        result = subprocess.run(
            ["pp_assist", "start"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5  # Reduced timeout since parent should exit quickly
        )

        if result.returncode != 0:
            print_error(f"pp_assist start exited with code {result.returncode}")
            if result.stderr:
                print_error(f"Error: {result.stderr}")
            return False

        # Wait a moment for daemon to initialize
        import time
        time.sleep(2)

        # Verify daemon actually started by checking status
        return is_daemon_running()

    except subprocess.TimeoutExpired:
        # Timeout is expected if daemon doesn't properly fork
        # Check if daemon is running anyway
        import time
        time.sleep(2)
        if is_daemon_running():
            return True
        else:
            print_error("Daemon start timed out and daemon is not running")
            return False
    except FileNotFoundError:
        print_error("pp_assist command not found")
        return False
    except Exception as e:
        print_error(f"Failed to start daemon: {e}")
        return False


def purge_database(db_path: Path, force: bool = False, dry_run: bool = False) -> int:
    """Purge the SQLite database.

    Args:
        db_path: Path to the database file
        force: Skip confirmation prompt
        dry_run: Only show what would be deleted

    Returns:
        0 on success, 1 on error
    """
    # Get database info
    db_info = get_database_info(db_path)

    # Display database information
    console.print()
    console.print(Panel.fit(
        f"[bold]Database Path:[/bold] {db_info['path']}\n"
        f"[bold]Exists:[/bold] {'Yes' if db_info['exists'] else 'No'}\n"
        f"[bold]Size:[/bold] {format_bytes(db_info['size'])}",
        title="[bold red]PURGE DATABASE[/bold red]",
        border_style="red"
    ))
    console.print()

    # Check if database exists
    if not db_info['exists']:
        print_warning("Database does not exist (already clean)")
        return 0

    # Confirmation prompt (unless --force or --dry-run)
    if not force and not dry_run:
        console.print(Panel.fit(
            f"[bold red]WARNING:[/bold red] This will DELETE:\n"
            f"  • SQLite database at {db_info['path']}\n"
            f"  • Database size: {format_bytes(db_info['size'])}\n\n"
            f"[bold]A backup will be created before deletion.[/bold]\n"
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

    # Check if daemon is running and stop it
    daemon_was_running = False
    if not dry_run:
        console.print()
        print_info("Checking if pp_assist daemon is running...")
        daemon_was_running = is_daemon_running()

        if daemon_was_running:
            print_info("Daemon is running, stopping it to release database lock...")
            if stop_daemon():
                print_success("Daemon stopped successfully")
                # Give the daemon a moment to fully shut down
                import time
                time.sleep(1)
            else:
                print_error("Failed to stop daemon")
                print_warning("Attempting to purge anyway, but database may be locked")
        else:
            print_info("Daemon is not running")

    # Perform purge
    if dry_run:
        print_warning("[DRY RUN] Would check if daemon is running and stop it")
        print_warning("[DRY RUN] Would delete database")
        print_info(f"[DRY RUN] Would backup to: {db_path.with_suffix('.db.backup')}")
        print_info(f"[DRY RUN] Would delete: {db_info['path']}")
        print_warning("[DRY RUN] Would restart daemon if it was running")
        print_warning("[DRY RUN] No data was actually deleted")
    else:
        try:
            # Backup the database first
            backup_path = db_path.with_suffix('.db.backup')
            shutil.copy2(db_path, backup_path)
            print_success(f"Backed up database to: {backup_path}")

            # Delete the database
            db_path.unlink()
            print_success(f"Deleted database: {db_info['path']}")
            print_success("Purge completed successfully!")

            # Restart daemon if it was running
            if daemon_was_running:
                console.print()
                print_info("Restarting pp_assist daemon...")
                if start_daemon():
                    print_success("Daemon restarted successfully")
                else:
                    print_warning("Failed to restart daemon - you may need to start it manually")
                    print_info("Run: pp_assist start")

        except Exception as e:
            print_error(f"Failed to purge database: {e}")

            # Try to restart daemon if it was running
            if daemon_was_running:
                console.print()
                print_warning("Attempting to restart daemon after error...")
                if start_daemon():
                    print_success("Daemon restarted")
                else:
                    print_error("Failed to restart daemon - please start it manually")

            return 1

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Purge PutPlace Assist SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--config-file",
        type=Path,
        help="Path to pp_assist.toml config file (overrides default search path)"
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        help="Explicit database path (bypasses config file)"
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

    # Determine database path
    db_path: Optional[Path] = None
    config_file_used: Optional[Path] = None

    if args.database_path:
        # Explicit database path provided
        db_path = args.database_path.expanduser()
        print_info(f"Using explicit database path: {db_path}")
    else:
        # Use config file to find database path
        if args.config_file:
            # Explicit config file
            if not args.config_file.exists():
                print_error(f"Config file not found: {args.config_file}")
                return 1

            os.environ['PPASSIST_CONFIG'] = str(args.config_file)
            config_file_used = args.config_file.resolve()
        else:
            # Search for config file using default locations
            config_file_used = find_config_file()

        # Load settings to get database path
        try:
            settings = Settings()
            db_path = settings.db_path_resolved

            # Display config info
            console.print()
            if config_file_used:
                print_info(f"Config file: [cyan]{config_file_used}[/cyan]")
            else:
                print_info("Config file: [dim]Not found (using defaults)[/dim]")
            print_info(f"Database:    [cyan]{db_path}[/cyan]")

        except Exception as e:
            print_error(f"Failed to load settings: {e}")
            return 1

    # Purge the database
    return purge_database(db_path, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
