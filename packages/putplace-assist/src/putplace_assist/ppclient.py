#!/usr/bin/env python3
"""PutPlace Client - Process files and directories via the ppassist daemon or directly."""

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

from putplace_assist.version import __version__

console = Console()

# Global flag for interrupt handling
interrupted = False

# Default daemon URL
DEFAULT_DAEMON_URL = "http://localhost:8765"


def signal_handler(signum, frame):
    """Handle Ctrl-C signal gracefully."""
    global interrupted
    interrupted = True
    console.print("\n[yellow]Interrupt received, stopping...[/yellow]")


def check_daemon_running(daemon_url: str) -> bool:
    """Check if the ppassist daemon is running.

    Args:
        daemon_url: URL of the daemon

    Returns:
        True if daemon is running
    """
    try:
        response = httpx.get(f"{daemon_url}/health", timeout=5.0)
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def get_daemon_status(daemon_url: str) -> Optional[dict]:
    """Get daemon status.

    Args:
        daemon_url: URL of the daemon

    Returns:
        Status dict or None if unavailable
    """
    try:
        response = httpx.get(f"{daemon_url}/status", timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return None


def register_path(daemon_url: str, path: Path, recursive: bool = True) -> Optional[dict]:
    """Register a path with the daemon.

    Args:
        daemon_url: URL of the daemon
        path: Path to register
        recursive: Whether to scan recursively

    Returns:
        Path response dict or None if failed
    """
    try:
        response = httpx.post(
            f"{daemon_url}/paths",
            json={"path": str(path.absolute()), "recursive": recursive},
            timeout=30.0,
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 409:
            # Already registered, get existing
            console.print(f"[yellow]Path already registered: {path}[/yellow]")
            paths_response = httpx.get(f"{daemon_url}/paths", timeout=10.0)
            if paths_response.status_code == 200:
                for p in paths_response.json().get("paths", []):
                    if p["path"] == str(path.absolute()):
                        return p
        else:
            console.print(f"[red]Failed to register path: {response.text}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error registering path: {e}[/red]")
    return None


def add_exclude_pattern(daemon_url: str, pattern: str) -> bool:
    """Add an exclude pattern to the daemon.

    Args:
        daemon_url: URL of the daemon
        pattern: Pattern to exclude

    Returns:
        True if successful
    """
    try:
        response = httpx.post(
            f"{daemon_url}/excludes",
            json={"pattern": pattern},
            timeout=10.0,
        )
        if response.status_code == 200:
            return True
        elif response.status_code == 409:
            # Already exists
            return True
        else:
            console.print(f"[red]Failed to add exclude pattern: {response.text}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error adding exclude: {e}[/red]")
    return False


def configure_server(
    daemon_url: str,
    name: str,
    url: str,
    username: str,
    password: str,
) -> bool:
    """Configure a remote server in the daemon.

    Args:
        daemon_url: URL of the daemon
        name: Server name
        url: Server URL
        username: Username for authentication
        password: Password for authentication

    Returns:
        True if successful
    """
    try:
        response = httpx.post(
            f"{daemon_url}/servers",
            json={
                "name": name,
                "url": url,
                "username": username,
                "password": password,
            },
            timeout=10.0,
        )
        if response.status_code == 200:
            console.print(f"[green]Server '{name}' configured[/green]")
            return True
        elif response.status_code == 409:
            console.print(f"[yellow]Server '{name}' already configured[/yellow]")
            return True
        else:
            console.print(f"[red]Failed to configure server: {response.text}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error configuring server: {e}[/red]")
    return False


def get_servers(daemon_url: str) -> list[dict]:
    """Get configured servers from daemon.

    Args:
        daemon_url: URL of the daemon

    Returns:
        List of server configs
    """
    try:
        response = httpx.get(f"{daemon_url}/servers", timeout=10.0)
        if response.status_code == 200:
            return response.json().get("servers", [])
    except httpx.HTTPError:
        pass
    return []


def login(daemon_url: str, email: str, password: str) -> bool:
    """Login to the remote server via pp_assist.

    Args:
        daemon_url: URL of the pp_assist daemon
        email: User email
        password: User password

    Returns:
        True if login successful
    """
    try:
        response = httpx.post(
            f"{daemon_url}/login",
            json={"email": email, "password": password},
            timeout=10.0,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                console.print(f"[green]✓ Login successful[/green]")
                if data.get("token"):
                    console.print(f"[dim]Token stored in pp_assist[/dim]")
                return True
            else:
                console.print(f"[red]Login failed: {data.get('error', 'Unknown error')}[/red]")
        else:
            console.print(f"[red]Login failed: HTTP {response.status_code}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error during login: {e}[/red]")
    return False


def register(
    daemon_url: str,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
) -> bool:
    """Register a new user on the remote server via pp_assist.

    Args:
        daemon_url: URL of the pp_assist daemon
        username: Username
        email: User email
        password: User password
        full_name: Optional full name

    Returns:
        True if registration successful
    """
    try:
        payload = {
            "username": username,
            "email": email,
            "password": password,
        }
        if full_name:
            payload["full_name"] = full_name

        response = httpx.post(
            f"{daemon_url}/register",
            json=payload,
            timeout=10.0,
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                console.print(f"[green]✓ Registration successful[/green]")
                console.print(f"[dim]You can now login with your credentials[/dim]")
                return True
            else:
                console.print(f"[red]Registration failed: {data.get('error', 'Unknown error')}[/red]")
        else:
            console.print(f"[red]Registration failed: HTTP {response.status_code}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error during registration: {e}[/red]")
    return False


def trigger_scan(daemon_url: str, path_id: int) -> bool:
    """Trigger a scan of a registered path.

    Args:
        daemon_url: URL of the daemon
        path_id: ID of the path to scan

    Returns:
        True if scan started
    """
    try:
        response = httpx.post(
            f"{daemon_url}/paths/{path_id}/scan",
            timeout=10.0,
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def trigger_uploads(daemon_url: str, upload_content: bool = False, path_prefix: Optional[str] = None) -> Optional[dict]:
    """Trigger uploads via the daemon.

    Args:
        daemon_url: URL of the daemon
        upload_content: Whether to upload file content
        path_prefix: Optional path prefix filter

    Returns:
        Upload response or None if failed
    """
    try:
        payload = {"upload_content": upload_content}
        if path_prefix:
            payload["path_prefix"] = path_prefix

        response = httpx.post(
            f"{daemon_url}/uploads",
            json=payload,
            timeout=30.0,
        )
        if response.status_code == 200:
            return response.json()
        else:
            console.print(f"[red]Failed to trigger uploads: {response.text}[/red]")
    except httpx.HTTPError as e:
        console.print(f"[red]Error triggering uploads: {e}[/red]")
    return None


def get_queue_status(daemon_url: str) -> Optional[dict]:
    """Get upload queue status from daemon.

    Args:
        daemon_url: URL of the daemon

    Returns:
        Queue status dict or None
    """
    try:
        response = httpx.get(f"{daemon_url}/uploads/queue", timeout=10.0)
        if response.status_code == 200:
            return response.json()
    except httpx.HTTPError:
        pass
    return None


def get_sha256_status(daemon_url: str) -> Optional[dict]:
    """Get SHA256 processor status from daemon.

    Args:
        daemon_url: URL of the daemon

    Returns:
        SHA256 processor status dict or None
    """
    try:
        response = httpx.get(f"{daemon_url}/sha256/status", timeout=10.0)
        if response.status_code == 200:
            return response.json()
    except httpx.HTTPError:
        pass
    return None


def get_file_stats(daemon_url: str) -> Optional[dict]:
    """Get file statistics from daemon.

    Args:
        daemon_url: URL of the daemon

    Returns:
        File stats dict or None
    """
    try:
        response = httpx.get(f"{daemon_url}/files/stats", timeout=10.0)
        if response.status_code == 200:
            return response.json()
    except httpx.HTTPError:
        pass
    return None


def stream_activity(daemon_url: str, timeout: float = 60.0) -> None:
    """Stream activity events from daemon via SSE.

    Args:
        daemon_url: URL of the daemon
        timeout: How long to stream (seconds)
    """
    global interrupted

    start_time = time.time()

    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", f"{daemon_url}/activity/stream") as response:
                for line in response.iter_lines():
                    if interrupted:
                        break
                    if time.time() - start_time > timeout:
                        break

                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            event_type = data.get("event_type", "")
                            message = data.get("message", "")

                            # Color code by event type
                            if "complete" in event_type.lower():
                                console.print(f"  [green]{message}[/green]")
                            elif "failed" in event_type.lower() or "error" in event_type.lower():
                                console.print(f"  [red]{message}[/red]")
                            elif "started" in event_type.lower():
                                console.print(f"  [cyan]{message}[/cyan]")
                            elif "sha256" in event_type.lower():
                                console.print(f"  [yellow]{message}[/yellow]")
                            elif "cleanup" in event_type.lower():
                                console.print(f"  [magenta]{message}[/magenta]")
                            else:
                                console.print(f"  [dim]{message}[/dim]")
                        except json.JSONDecodeError:
                            pass
    except (httpx.ConnectError, httpx.TimeoutException):
        pass


def wait_for_completion(daemon_url: str, timeout: float = 300.0, wait_for_sha256: bool = True) -> bool:
    """Wait for SHA256 processing and uploads to complete.

    Args:
        daemon_url: URL of the daemon
        timeout: Maximum time to wait (seconds)
        wait_for_sha256: Whether to wait for SHA256 processing first

    Returns:
        True if all processing completed successfully
    """
    global interrupted

    start_time = time.time()
    last_pending_sha256 = -1
    last_pending_upload = -1

    while not interrupted and (time.time() - start_time) < timeout:
        sha256_status = get_sha256_status(daemon_url)
        queue_status = get_queue_status(daemon_url)

        if not sha256_status or not queue_status:
            time.sleep(1)
            continue

        pending_sha256 = sha256_status.get("pending_count", 0)
        processed_today = sha256_status.get("processed_today", 0)
        failed_today = sha256_status.get("failed_today", 0)
        pending_upload = queue_status.get("pending_upload", 0)
        completed_today = queue_status.get("completed_today", 0)

        # Show SHA256 progress if changed
        if pending_sha256 != last_pending_sha256:
            if pending_sha256 > 0:
                console.print(
                    f"  [cyan]SHA256: {pending_sha256} pending | "
                    f"Processed: {processed_today} | Failed: {failed_today}[/cyan]"
                )
            last_pending_sha256 = pending_sha256

        # Show upload progress if changed
        if pending_upload != last_pending_upload:
            if pending_upload > 0:
                console.print(
                    f"  [cyan]Uploads: {pending_upload} pending | "
                    f"Completed: {completed_today}[/cyan]"
                )
            last_pending_upload = pending_upload

        # Check if done
        sha256_done = not wait_for_sha256 or pending_sha256 == 0
        uploads_done = pending_upload == 0

        if sha256_done and uploads_done:
            return failed_today == 0

        time.sleep(2)

    return False


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable string.

    Args:
        bytes_val: Size in bytes

    Returns:
        Human readable string (e.g., "1.5 MB")
    """
    if bytes_val == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_val >= 1024 and i < len(units) - 1:
        bytes_val /= 1024
        i += 1
    return f"{bytes_val:.1f} {units[i]}"


def show_status_table(daemon_url: str) -> None:
    """Show daemon status as a table.

    Args:
        daemon_url: URL of the daemon
    """
    status = get_daemon_status(daemon_url)
    if not status:
        console.print("[red]Could not get daemon status[/red]")
        return

    stats = get_file_stats(daemon_url)
    sha256_status = get_sha256_status(daemon_url)

    # Main status table
    table = Table(title="PutPlace Assist Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Running", "Yes" if status.get("running") else "No")
    table.add_row("Version", status.get("version", "unknown"))
    table.add_row("Uptime", f"{status.get('uptime_seconds', 0):.0f} seconds")
    table.add_row("Watcher Active", "Yes" if status.get("watcher_active") else "No")
    table.add_row("SHA256 Processor", "Active" if status.get("sha256_processor_active") else "Inactive")
    table.add_row("Paths Watched", str(status.get("paths_watched", 0)))
    table.add_row("Files Tracked", str(status.get("files_tracked", 0)))

    if stats:
        table.add_row("Total Size", format_bytes(stats.get("total_size", 0)))
        table.add_row("Pending SHA256", str(stats.get("pending_sha256", 0)))
        table.add_row("Pending Uploads", str(stats.get("pending_uploads", 0)))
        table.add_row("Meta Uploads", str(stats.get("meta_uploads", 0)))
        table.add_row("Full Uploads", str(stats.get("full_uploads", 0)))

    console.print(table)

    # SHA256 processor status
    if sha256_status:
        sha_table = Table(title="SHA256 Processor")
        sha_table.add_column("Property", style="cyan")
        sha_table.add_column("Value", style="green")

        sha_table.add_row("Running", "Yes" if sha256_status.get("is_running") else "No")
        sha_table.add_row("Pending Files", str(sha256_status.get("pending_count", 0)))
        sha_table.add_row("Processed Today", str(sha256_status.get("processed_today", 0)))
        sha_table.add_row("Failed Today", str(sha256_status.get("failed_today", 0)))

        current_file = sha256_status.get("current_file")
        if current_file:
            # Truncate long paths
            if len(current_file) > 50:
                current_file = "..." + current_file[-47:]
            sha_table.add_row("Current File", current_file)

        console.print(sha_table)


def main() -> int:
    """Main entry point."""
    global interrupted

    parser = argparse.ArgumentParser(
        prog="ppclient",
        description="PutPlace Client - Register paths and trigger uploads via ppassist daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register a new user
  %(prog)s --register --username john --email john@example.com --password secret

  # Login to remote server
  %(prog)s --login --email john@example.com --password secret

  # Configure remote server (stores credentials in pp_assist)
  %(prog)s --configure-server --server-url https://app.putplace.org \\
           --email user@example.com --password secret

  # Register a directory for scanning and uploading
  %(prog)s --path /var/log

  # Register with exclude patterns
  %(prog)s --path /var/log --exclude .git --exclude "*.tmp"

  # Trigger immediate upload after registering
  %(prog)s --path /var/log --upload

  # Upload file content (not just metadata)
  %(prog)s --path /var/log --upload --upload-content

  # Check daemon status
  %(prog)s --status

  # Use custom daemon URL
  %(prog)s --path /var/log --daemon-url http://localhost:9000

ppclient version """ + __version__,
    )

    # Path registration
    parser.add_argument(
        "--path", "-p",
        type=Path,
        help="Path to register for scanning and uploading",
    )

    parser.add_argument(
        "--exclude", "-e",
        action="append",
        dest="exclude_patterns",
        default=[],
        help="Exclude pattern (can be specified multiple times)",
    )

    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=True,
        help="Don't scan recursively (default: scan recursively)",
    )

    # Upload options
    parser.add_argument(
        "--upload", "-u",
        action="store_true",
        help="Trigger upload after registering path",
    )

    parser.add_argument(
        "--upload-content",
        action="store_true",
        help="Upload file content (not just metadata)",
    )

    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for uploads to complete",
    )

    # Server configuration
    parser.add_argument(
        "--configure-server",
        action="store_true",
        help="Configure remote server",
    )

    parser.add_argument(
        "--server-name",
        default="default",
        help="Name for the server configuration (default: 'default')",
    )

    parser.add_argument(
        "--server-url",
        help="Remote server URL (e.g., https://app.putplace.org)",
    )

    parser.add_argument(
        "--email",
        help="Email for server authentication",
    )

    parser.add_argument(
        "--password",
        help="Password for server authentication",
    )

    # Authentication
    parser.add_argument(
        "--login",
        action="store_true",
        help="Login to remote server via pp_assist",
    )

    parser.add_argument(
        "--register",
        action="store_true",
        help="Register new user on remote server via pp_assist",
    )

    parser.add_argument(
        "--username",
        help="Username for registration",
    )

    parser.add_argument(
        "--full-name",
        help="Full name for registration (optional)",
    )

    # Daemon options
    parser.add_argument(
        "--daemon-url",
        default=DEFAULT_DAEMON_URL,
        help=f"PutPlace Assist daemon URL (default: {DEFAULT_DAEMON_URL})",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show daemon status",
    )

    parser.add_argument(
        "--scan",
        action="store_true",
        help="Trigger rescan of registered path",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output (stream activity events)",
    )

    args = parser.parse_args()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Check daemon is running
    if not check_daemon_running(args.daemon_url):
        console.print(f"[red]PutPlace Assist daemon is not running at {args.daemon_url}[/red]")
        console.print("[yellow]Start the daemon with: ppassist start[/yellow]")
        return 1

    console.print(f"[green]Connected to daemon at {args.daemon_url}[/green]")

    # Handle --status
    if args.status:
        show_status_table(args.daemon_url)
        return 0

    # Handle --configure-server
    if args.configure_server:
        if not all([args.server_url, args.email, args.password]):
            console.print("[red]--configure-server requires --server-url, --email, and --password[/red]")
            return 1

        if configure_server(
            args.daemon_url,
            args.server_name,
            args.server_url,
            args.email,
            args.password,
        ):
            return 0
        return 1

    # Handle --login
    if args.login:
        if not all([args.email, args.password]):
            console.print("[red]--login requires --email and --password[/red]")
            return 1

        if login(args.daemon_url, args.email, args.password):
            return 0
        return 1

    # Handle --register
    if args.register:
        if not all([args.username, args.email, args.password]):
            console.print("[red]--register requires --username, --email, and --password[/red]")
            return 1

        if register(
            args.daemon_url,
            args.username,
            args.email,
            args.password,
            args.full_name,
        ):
            return 0
        return 1

    # Check if server is configured (needed for uploads)
    servers = get_servers(args.daemon_url)
    if not servers and args.upload:
        console.print("[red]No server configured. Use --configure-server first.[/red]")
        return 1

    # Handle --path
    if args.path:
        path = args.path.expanduser().resolve()

        if not path.exists():
            console.print(f"[red]Path does not exist: {path}[/red]")
            return 1

        if not path.is_dir():
            console.print(f"[red]Path is not a directory: {path}[/red]")
            return 1

        # Add exclude patterns first
        for pattern in args.exclude_patterns:
            if add_exclude_pattern(args.daemon_url, pattern):
                console.print(f"[dim]Added exclude pattern: {pattern}[/dim]")

        # Register path
        console.print(f"[cyan]Registering path: {path}[/cyan]")
        path_response = register_path(args.daemon_url, path, args.recursive)

        if path_response:
            path_id = path_response["id"]
            console.print(f"[green]Path registered (ID: {path_id})[/green]")

            # Trigger scan if requested
            if args.scan:
                console.print("[cyan]Triggering rescan...[/cyan]")
                trigger_scan(args.daemon_url, path_id)

            # Trigger upload if requested
            if args.upload:
                console.print("[cyan]Triggering uploads...[/cyan]")
                upload_response = trigger_uploads(
                    args.daemon_url,
                    upload_content=args.upload_content,
                    path_prefix=str(path),
                )

                if upload_response:
                    files_queued = upload_response.get("files_queued", 0)
                    console.print(f"[green]Queued {files_queued} files for upload[/green]")

                    if args.verbose:
                        console.print("[dim]Streaming activity...[/dim]")
                        stream_activity(args.daemon_url, timeout=60.0)

                    if args.wait:
                        console.print("[cyan]Waiting for SHA256 processing and uploads to complete...[/cyan]")
                        success = wait_for_completion(args.daemon_url)
                        if success:
                            console.print("[green]All processing completed successfully[/green]")
                        else:
                            console.print("[red]Some processing failed[/red]")
                            return 1
        else:
            return 1

    # If only --upload without --path, upload all pending files
    elif args.upload:
        console.print("[cyan]Triggering uploads for all pending files...[/cyan]")
        upload_response = trigger_uploads(
            args.daemon_url,
            upload_content=args.upload_content,
        )

        if upload_response:
            files_queued = upload_response.get("files_queued", 0)
            console.print(f"[green]Queued {files_queued} files for upload[/green]")

            if args.wait:
                console.print("[cyan]Waiting for SHA256 processing and uploads to complete...[/cyan]")
                success = wait_for_completion(args.daemon_url)
                if success:
                    console.print("[green]All processing completed successfully[/green]")
                else:
                    console.print("[red]Some processing failed[/red]")
                    return 1

    # No action specified
    elif not args.status and not args.configure_server:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
