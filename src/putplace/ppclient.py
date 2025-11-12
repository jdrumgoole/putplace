#!/usr/bin/env python3
"""PutPlace Client - Process files and directories, send file metadata to the server."""

import configargparse
import configparser
import hashlib
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Global flag for interrupt handling
interrupted = False


def login_and_get_token(base_url: str, username: str, password: str) -> Optional[str]:
    """Login to the server and get JWT access token.

    Args:
        base_url: Base URL of the API server
        username: Username for authentication
        password: Password for authentication

    Returns:
        JWT access token if successful, None otherwise
    """
    login_url = f"{base_url.rstrip('/')}/api/login"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                login_url,
                json={"username": username, "password": password}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")
            else:
                console.print(f"[red]✗ Login failed: {response.status_code}[/red]")
                if response.status_code == 401:
                    console.print("[yellow]  Incorrect username or password[/yellow]")
                else:
                    console.print(f"[dim]  {response.text}[/dim]")
                return None

    except httpx.ConnectError:
        console.print(f"[red]✗ Could not connect to server at {base_url}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]✗ Login error: {e}[/red]")
        return None


def signal_handler(signum, frame):
    """Handle Ctrl-C signal gracefully."""
    global interrupted
    interrupted = True
    console.print("\n[yellow]⚠ Interrupt received, finishing current file and exiting...[/yellow]")
    console.print("[dim](Press Ctrl-C again to force quit)[/dim]")


def get_exclude_patterns_from_config(config_files: list[str]) -> list[str]:
    """Manually extract exclude patterns from config files.

    This is needed because configargparse doesn't properly handle
    multiple values with action="append" in config files.

    Args:
        config_files: List of config file paths to check

    Returns:
        List of exclude patterns found in config files
    """
    exclude_patterns = []

    for config_file in config_files:
        # Expand ~ in path
        config_path = Path(config_file).expanduser()

        if not config_path.exists():
            continue

        try:
            # Read the file manually to get all exclude patterns
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('exclude'):
                        # Parse "exclude = value"
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            pattern = parts[1].strip()
                            if pattern:
                                exclude_patterns.append(pattern)
        except Exception:
            # Ignore errors reading config files
            pass

    return exclude_patterns


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


def upload_file_content(
    filepath: Path,
    sha256: str,
    hostname: str,
    upload_url: str,
    base_url: str,
    access_token: Optional[str] = None,
) -> bool:
    """Upload file content to server.

    Args:
        filepath: Path to the file to upload
        sha256: SHA256 hash of the file
        hostname: Hostname where file is located
        upload_url: Upload URL path (e.g., /upload_file/{sha256})
        base_url: Base API URL
        access_token: Optional JWT access token for authentication

    Returns:
        True if upload successful, False otherwise
    """
    try:
        # Construct full URL
        full_url = f"{base_url.rstrip('/')}{upload_url}"

        # Add query parameters for hostname and filepath
        params = {
            "hostname": hostname,
            "filepath": str(filepath.absolute()),
        }

        # Prepare headers
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        # Open file and upload
        with open(filepath, "rb") as f:
            files = {"file": (filepath.name, f, "application/octet-stream")}
            response = httpx.post(full_url, files=files, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()

        console.print(f"[green]✓ Uploaded: {filepath.name}[/green]")
        return True

    except httpx.HTTPError as e:
        console.print(f"[red]Failed to upload {filepath.name}: {e}[/red]")
        return False
    except (IOError, OSError) as e:
        console.print(f"[red]Cannot read file {filepath}: {e}[/red]")
        return False


def process_path(
    start_path: Path,
    exclude_patterns: list[str],
    hostname: str,
    ip_address: str,
    api_url: str,
    dry_run: bool = False,
    access_token: Optional[str] = None,
) -> tuple[int, int, int, int]:
    """Process a file or directory and send file metadata to server.

    Args:
        start_path: File or directory path to process
        exclude_patterns: List of patterns to exclude (only applies to directories)
        hostname: Hostname to send
        ip_address: IP address to send
        api_url: API endpoint URL (e.g., http://localhost:8000/put_file)
        dry_run: If True, don't actually send data to server
        access_token: Optional JWT access token for authentication

    Returns:
        Tuple of (total_files, successful, failed, uploaded)
    """
    global interrupted

    if not start_path.exists():
        console.print(f"[red]Error: Path does not exist: {start_path}[/red]")
        return 0, 0, 0, 0

    # Collect all files first to show progress
    files_to_process = []

    if start_path.is_file():
        # Single file mode
        console.print(f"[cyan]Processing file: {start_path}[/cyan]")
        files_to_process.append(start_path)
    elif start_path.is_dir():
        # Directory mode - scan recursively
        console.print(f"[cyan]Scanning directory: {start_path}[/cyan]")

        for filepath in start_path.rglob("*"):
            if not filepath.is_file():
                continue

            # Check exclude patterns
            if matches_exclude_pattern(filepath, start_path, exclude_patterns):
                console.print(f"[dim]Excluded: {filepath.relative_to(start_path)}[/dim]")
                continue

            files_to_process.append(filepath)
    else:
        console.print(f"[red]Error: Path is neither a file nor a directory: {start_path}[/red]")
        return 0, 0, 0, 0

    if not files_to_process:
        console.print("[yellow]No files to process[/yellow]")
        return 0, 0, 0, 0

    console.print(f"[green]Found {len(files_to_process)} files to process[/green]")

    total_files = len(files_to_process)
    successful = 0
    failed = 0
    uploaded = 0

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
            # Check for interrupt
            if interrupted:
                console.print("\n[yellow]Processing interrupted by user[/yellow]")
                break

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
                    # Prepare headers with access token if provided
                    headers = {}
                    if access_token:
                        headers["Authorization"] = f"Bearer {access_token}"

                    response = httpx.post(api_url, json=metadata, headers=headers, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    successful += 1

                    # Check if file upload is required
                    if data.get("upload_required", False):
                        upload_url = data.get("upload_url")
                        if upload_url:
                            # Extract base URL from api_url (remove /put_file suffix)
                            base_url = api_url.rsplit("/", 1)[0]
                            if upload_file_content(filepath, sha256, hostname, upload_url, base_url, access_token):
                                uploaded += 1
                    else:
                        console.print(f"[dim]Skipped upload (deduplicated): {filepath.name}[/dim]")

                except httpx.HTTPError as e:
                    console.print(
                        f"[red]Failed to send {filepath.name}: {e}[/red]"
                    )
                    failed += 1

            progress.advance(task)

    return total_files, successful, failed, uploaded


def main() -> int:
    """Main entry point."""
    global interrupted

    parser = configargparse.ArgumentParser(
        default_config_files=["~/ppclient.conf", "ppclient.conf"],
        ignore_unknown_config_file_keys=True,
        description="Process files or directories and send file metadata to PutPlace server",
        formatter_class=configargparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single file
  %(prog)s --path /var/log/app.log

  # Scan current directory
  %(prog)s --path .

  # Scan specific directory
  %(prog)s --path /var/log

  # Exclude .git directories and *.log files (when scanning directories)
  %(prog)s --path /var/log --exclude .git --exclude "*.log"

  # Dry run (don't send to server)
  %(prog)s --path /var/log --dry-run

  # Use custom server URL
  %(prog)s --path /var/log --url http://localhost:8080/put_file

  # Use config file
  %(prog)s --path /var/log --config myconfig.conf

Config file format (INI style):
  [DEFAULT]
  url = http://remote-server:8000/put_file
  username = your-username
  password = your-password
  exclude = .git
  exclude = *.log
  hostname = myserver

Authentication:
  # Option 1: Command line
  %(prog)s --path /var/log --username admin --password secret

  # Option 2: Environment variables
  export PUTPLACE_USERNAME=admin
  export PUTPLACE_PASSWORD=secret
  %(prog)s --path /var/log

  # Option 3: Config file (~/ppclient.conf)
  echo "username = admin" >> ~/ppclient.conf
  echo "password = secret" >> ~/ppclient.conf
  %(prog)s --path /var/log
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        is_config_file=True,
        help="Config file path (default: ~/ppclient.conf or ppclient.conf)",
    )

    parser.add_argument(
        "--path",
        "-p",
        type=Path,
        required=True,
        help="File or directory path to process (directories are scanned recursively)",
    )

    parser.add_argument(
        "--exclude",
        "-e",
        action="append",
        dest="exclude_list",
        default=None,
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

    parser.add_argument(
        "--username",
        "-u",
        env_var="PUTPLACE_USERNAME",
        default=None,
        help="Username for authentication. "
        "Can be specified via: 1) --username flag, 2) PUTPLACE_USERNAME environment variable, "
        "or 3) 'username' in config file.",
    )

    parser.add_argument(
        "--password",
        env_var="PUTPLACE_PASSWORD",
        default=None,
        help="Password for authentication. "
        "Can be specified via: 1) --password flag, 2) PUTPLACE_PASSWORD environment variable, "
        "or 3) 'password' in config file.",
    )

    args = parser.parse_args()

    # Get username and password
    username = args.username
    password = args.password

    # Login and get access token if credentials provided
    access_token = None
    if username and password:
        console.print(f"[cyan]Logging in as {username}...[/cyan]")
        access_token = login_and_get_token(args.url.rsplit('/', 1)[0], username, password)
        if not access_token:
            console.print("[red]✗ Login failed. Exiting.[/red]")
            sys.exit(1)
        console.print("[green]✓ Login successful[/green]")
    elif username or password:
        console.print("[red]✗ Both username and password are required for authentication[/red]")
        sys.exit(1)

    # Get hostname and IP
    hostname = args.hostname or get_hostname()
    ip_address = args.ip or get_ip_address()

    # Handle exclude patterns: merge config file and CLI patterns
    # configargparse doesn't properly handle action="append" with config files,
    # so we manually read exclude patterns from config files
    config_files_to_check = []

    # Add explicit config file if specified
    if hasattr(args, 'config') and args.config:
        config_files_to_check.append(args.config)
    # Add default config files
    config_files_to_check.extend(["~/ppclient.conf", "ppclient.conf"])

    # Get exclude patterns from config files
    config_exclude_patterns = get_exclude_patterns_from_config(config_files_to_check)

    # Get exclude patterns from CLI (may include duplicates from config)
    cli_exclude_patterns = args.exclude_list if args.exclude_list is not None else []

    # Merge both lists, removing duplicates while preserving order
    seen = set()
    exclude_patterns = []
    for pattern in config_exclude_patterns + cli_exclude_patterns:
        if pattern not in seen:
            seen.add(pattern)
            exclude_patterns.append(pattern)

    # Display configuration
    console.print("\n[bold cyan]PutPlace Client[/bold cyan]")
    console.print(f"  Path: {args.path.absolute()}")
    console.print(f"  Hostname: {hostname}")
    console.print(f"  IP Address: {ip_address}")
    console.print(f"  API URL: {args.url}")

    if access_token:
        console.print(f"  [green]Authentication: Bearer token ({len(access_token)} chars)[/green]")
    else:
        console.print("  [yellow]Warning: No authentication provided (may fail for protected endpoints)[/yellow]")

    if exclude_patterns:
        console.print(f"  Exclude patterns: {', '.join(exclude_patterns)}")

    if args.dry_run:
        console.print("  [yellow]DRY RUN MODE[/yellow]")

    console.print()

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Scan and process
    total, successful, failed, uploaded = process_path(
        args.path,
        exclude_patterns,
        hostname,
        ip_address,
        args.url,
        args.dry_run,
        access_token,
    )

    # Display results
    console.print("\n[bold]Results:[/bold]")
    if interrupted:
        console.print("  [yellow]Status: Interrupted (partial completion)[/yellow]")
    console.print(f"  Total files: {total}")
    console.print(f"  [green]Successful: {successful}[/green]")
    if uploaded > 0:
        console.print(f"  [cyan]Uploaded: {uploaded}[/cyan]")
    if failed > 0:
        console.print(f"  [red]Failed: {failed}[/red]")
    if interrupted:
        console.print(f"  [dim]Remaining: {total - successful - failed}[/dim]")

    return 0 if (failed == 0 and not interrupted) else 1


if __name__ == "__main__":
    sys.exit(main())
