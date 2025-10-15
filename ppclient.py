#!/usr/bin/env python3
"""PutPlace Client - Scan directories and send file metadata to the server."""

import configargparse
import hashlib
import os
import socket
import sys
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()


def get_hostname() -> str:
    """Get the current hostname."""
    return socket.gethostname()


def get_ip_address() -> str:
    """Get the primary IP address of this machine."""
    try:
        # Connect to a public DNS server to determine the local IP
        # This doesn't actually send data, just determines routing
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def calculate_sha256(filepath: Path, chunk_size: int = 8192) -> Optional[str]:
    """Calculate SHA256 hash of a file.

    Args:
        filepath: Path to the file
        chunk_size: Size of chunks to read (default: 8KB)

    Returns:
        Hexadecimal SHA256 hash or None if file cannot be read
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except (IOError, OSError) as e:
        console.print(f"[yellow]Warning: Cannot read {filepath}: {e}[/yellow]")
        return None


def get_file_stats(filepath: Path) -> Optional[dict]:
    """Get file stat information.

    Args:
        filepath: Path to the file

    Returns:
        Dictionary with stat information or None if stat fails
    """
    try:
        stat_info = os.stat(filepath)
        return {
            "file_size": stat_info.st_size,
            "file_mode": stat_info.st_mode,
            "file_uid": stat_info.st_uid,
            "file_gid": stat_info.st_gid,
            "file_mtime": stat_info.st_mtime,
            "file_atime": stat_info.st_atime,
            "file_ctime": stat_info.st_ctime,
        }
    except (IOError, OSError) as e:
        console.print(f"[yellow]Warning: Cannot stat {filepath}: {e}[/yellow]")
        return None


def matches_exclude_pattern(path: Path, base_path: Path, patterns: list[str]) -> bool:
    """Check if a path matches any exclude pattern.

    Args:
        path: Path to check
        base_path: Base path for relative matching
        patterns: List of exclude patterns

    Returns:
        True if path matches any pattern
    """
    if not patterns:
        return False

    try:
        relative_path = path.relative_to(base_path)
    except ValueError:
        # Path is not relative to base_path
        return False

    relative_str = str(relative_path)
    path_parts = relative_path.parts

    for pattern in patterns:
        # Check if pattern matches the full relative path
        if relative_str == pattern:
            return True

        # Check if pattern matches any part of the path
        if pattern in path_parts:
            return True

        # Check for wildcard patterns
        if "*" in pattern:
            import fnmatch

            if fnmatch.fnmatch(relative_str, pattern):
                return True

            # Check each part for pattern match
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

    return False


def scan_directory(
    start_path: Path,
    exclude_patterns: list[str],
    hostname: str,
    ip_address: str,
    api_url: str,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Scan directory and send file metadata to server.

    Args:
        start_path: Starting directory path
        exclude_patterns: List of patterns to exclude
        hostname: Hostname to send
        ip_address: IP address to send
        api_url: API endpoint URL
        dry_run: If True, don't actually send data to server

    Returns:
        Tuple of (total_files, successful, failed)
    """
    if not start_path.exists():
        console.print(f"[red]Error: Path does not exist: {start_path}[/red]")
        return 0, 0, 0

    if not start_path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {start_path}[/red]")
        return 0, 0, 0

    # Collect all files first to show progress
    console.print(f"[cyan]Scanning directory: {start_path}[/cyan]")
    files_to_process = []

    for filepath in start_path.rglob("*"):
        if not filepath.is_file():
            continue

        # Check exclude patterns
        if matches_exclude_pattern(filepath, start_path, exclude_patterns):
            console.print(f"[dim]Excluded: {filepath.relative_to(start_path)}[/dim]")
            continue

        files_to_process.append(filepath)

    if not files_to_process:
        console.print("[yellow]No files to process[/yellow]")
        return 0, 0, 0

    console.print(f"[green]Found {len(files_to_process)} files to process[/green]")

    total_files = len(files_to_process)
    successful = 0
    failed = 0

    # Process files with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing files...", total=total_files)

        for filepath in files_to_process:
            progress.update(
                task, description=f"[cyan]Processing: {filepath.name[:30]}..."
            )

            # Calculate SHA256
            sha256 = calculate_sha256(filepath)
            if sha256 is None:
                failed += 1
                progress.advance(task)
                continue

            # Get file stats
            file_stats = get_file_stats(filepath)
            if file_stats is None:
                failed += 1
                progress.advance(task)
                continue

            # Prepare metadata
            metadata = {
                "filepath": str(filepath.absolute()),
                "hostname": hostname,
                "ip_address": ip_address,
                "sha256": sha256,
                **file_stats,  # Unpack stat information
            }

            # Send to server
            if dry_run:
                console.print(f"[dim]Dry run: Would send {filepath.name}[/dim]")
                successful += 1
            else:
                try:
                    response = httpx.post(api_url, json=metadata, timeout=10.0)
                    response.raise_for_status()
                    successful += 1
                except httpx.HTTPError as e:
                    console.print(
                        f"[red]Failed to send {filepath.name}: {e}[/red]"
                    )
                    failed += 1

            progress.advance(task)

    return total_files, successful, failed


def main() -> int:
    """Main entry point."""
    parser = configargparse.ArgumentParser(
        default_config_files=["~/.ppclient.conf", ".ppclient.conf"],
        description="Scan directories and send file metadata to PutPlace server",
        formatter_class=configargparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan current directory
  %(prog)s .

  # Scan specific directory
  %(prog)s /var/log

  # Exclude .git directories and *.log files
  %(prog)s /var/log --exclude .git --exclude "*.log"

  # Dry run (don't send to server)
  %(prog)s /var/log --dry-run

  # Use custom server URL
  %(prog)s /var/log --url http://localhost:8080/put_file

  # Use config file
  %(prog)s /var/log --config myconfig.conf

Config file format (INI style):
  [DEFAULT]
  url = http://remote-server:8000/put_file
  exclude = .git
  exclude = *.log
  hostname = myserver
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        is_config_file=True,
        help="Config file path (default: ~/.ppclient.conf or .ppclient.conf)",
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Starting directory path to scan",
    )

    parser.add_argument(
        "--exclude",
        "-e",
        action="append",
        default=[],
        help="Exclude pattern (can be specified multiple times). "
        "Supports wildcards like *.log or directory names like .git",
    )

    parser.add_argument(
        "--url",
        default="http://localhost:8000/put_file",
        help="API endpoint URL (default: http://localhost:8000/put_file)",
    )

    parser.add_argument(
        "--hostname",
        default=None,
        help="Override hostname (default: auto-detect)",
    )

    parser.add_argument(
        "--ip",
        default=None,
        help="Override IP address (default: auto-detect)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan files but don't send to server",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Get hostname and IP
    hostname = args.hostname or get_hostname()
    ip_address = args.ip or get_ip_address()

    # Display configuration
    console.print("\n[bold cyan]PutPlace Client[/bold cyan]")
    console.print(f"  Path: {args.path.absolute()}")
    console.print(f"  Hostname: {hostname}")
    console.print(f"  IP Address: {ip_address}")
    console.print(f"  API URL: {args.url}")

    if args.exclude:
        console.print(f"  Exclude patterns: {', '.join(args.exclude)}")

    if args.dry_run:
        console.print("  [yellow]DRY RUN MODE[/yellow]")

    console.print()

    # Scan and process
    total, successful, failed = scan_directory(
        args.path,
        args.exclude,
        hostname,
        ip_address,
        args.url,
        args.dry_run,
    )

    # Display results
    console.print("\n[bold]Results:[/bold]")
    console.print(f"  Total files: {total}")
    console.print(f"  [green]Successful: {successful}[/green]")
    if failed > 0:
        console.print(f"  [red]Failed: {failed}[/red]")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
