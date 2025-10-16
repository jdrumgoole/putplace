#!/usr/bin/env python3
"""PutPlace Server - Manage the PutPlace API server."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console

console = Console()


def get_pid_file() -> Path:
    """Get the PID file path.

    Returns:
        Path to PID file
    """
    # Use ~/.putplace/ppserver.pid for user-level installation
    pid_dir = Path.home() / ".putplace"
    pid_dir.mkdir(exist_ok=True)
    return pid_dir / "ppserver.pid"


def get_log_file() -> Path:
    """Get the log file path.

    Returns:
        Path to log file
    """
    log_dir = Path.home() / ".putplace"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "ppserver.log"


def is_running() -> tuple[bool, int | None]:
    """Check if the server is running.

    Returns:
        Tuple of (is_running, pid)
    """
    pid_file = get_pid_file()

    if not pid_file.exists():
        return False, None

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())

        # Check if process is actually running
        os.kill(pid, 0)  # Send signal 0 (no-op, just checks if process exists)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        # PID file exists but process is not running
        # Clean up stale PID file
        pid_file.unlink(missing_ok=True)
        return False, None


def start_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> int:
    """Start the PutPlace server.

    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload for development

    Returns:
        0 on success, 1 on failure
    """
    running, pid = is_running()
    if running:
        console.print(f"[yellow]Server is already running (PID: {pid})[/yellow]")
        console.print(f"[yellow]Use 'ppserver stop' to stop it first[/yellow]")
        return 1

    console.print(f"[cyan]Starting PutPlace server on {host}:{port}...[/cyan]")

    # Build uvicorn command
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "putplace.main:app",
        "--host", host,
        "--port", str(port),
    ]

    if reload:
        cmd.append("--reload")

    # Get log file path
    log_file = get_log_file()

    try:
        # Start server in background
        with open(log_file, "w") as log:
            process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from parent
            )

        # Wait a moment to see if it starts successfully
        time.sleep(1)

        # Check if process is still running
        if process.poll() is not None:
            console.print("[red]✗ Server failed to start[/red]")
            console.print(f"[red]Check log file: {log_file}[/red]")
            return 1

        # Write PID file
        pid_file = get_pid_file()
        with open(pid_file, "w") as f:
            f.write(str(process.pid))

        console.print(f"[green]✓ Server started successfully (PID: {process.pid})[/green]")
        console.print(f"[green]  URL: http://{host}:{port}[/green]")
        console.print(f"[dim]  Log file: {log_file}[/dim]")
        console.print(f"[dim]  PID file: {pid_file}[/dim]")

        return 0

    except Exception as e:
        console.print(f"[red]✗ Failed to start server: {e}[/red]")
        return 1


def stop_server() -> int:
    """Stop the PutPlace server.

    Returns:
        0 on success, 1 on failure
    """
    running, pid = is_running()

    if not running:
        console.print("[yellow]Server is not running[/yellow]")
        return 1

    console.print(f"[cyan]Stopping PutPlace server (PID: {pid})...[/cyan]")

    try:
        # Send SIGTERM for graceful shutdown
        os.kill(pid, signal.SIGTERM)

        # Wait for process to terminate (max 10 seconds)
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)  # Check if still running
            except ProcessLookupError:
                # Process has terminated
                break
        else:
            # Process still running after 10 seconds, force kill
            console.print("[yellow]Server did not stop gracefully, forcing shutdown...[/yellow]")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

        # Clean up PID file
        pid_file = get_pid_file()
        pid_file.unlink(missing_ok=True)

        console.print("[green]✓ Server stopped successfully[/green]")
        return 0

    except ProcessLookupError:
        # Process already gone
        pid_file = get_pid_file()
        pid_file.unlink(missing_ok=True)
        console.print("[green]✓ Server stopped[/green]")
        return 0
    except PermissionError:
        console.print(f"[red]✗ Permission denied to stop server (PID: {pid})[/red]")
        console.print("[red]  Try running with sudo or as the user who started the server[/red]")
        return 1
    except Exception as e:
        console.print(f"[red]✗ Failed to stop server: {e}[/red]")
        return 1


def restart_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> int:
    """Restart the PutPlace server.

    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload for development

    Returns:
        0 on success, 1 on failure
    """
    console.print("[cyan]Restarting PutPlace server...[/cyan]")

    # Stop if running
    running, _ = is_running()
    if running:
        if stop_server() != 0:
            return 1
        # Wait a moment for port to be released
        time.sleep(1)

    # Start server
    return start_server(host, port, reload)


def status_server() -> int:
    """Check the status of the PutPlace server.

    Returns:
        0 if running, 1 if not running
    """
    running, pid = is_running()

    if running:
        console.print(f"[green]✓ Server is running (PID: {pid})[/green]")

        # Show log file location
        log_file = get_log_file()
        console.print(f"[dim]  Log file: {log_file}[/dim]")

        # Show PID file location
        pid_file = get_pid_file()
        console.print(f"[dim]  PID file: {pid_file}[/dim]")

        return 0
    else:
        console.print("[yellow]Server is not running[/yellow]")
        return 1


def logs_server(follow: bool = False, lines: int = 50) -> int:
    """Show server logs.

    Args:
        follow: Follow log output (like tail -f)
        lines: Number of lines to show

    Returns:
        0 on success, 1 on failure
    """
    log_file = get_log_file()

    if not log_file.exists():
        console.print("[yellow]No log file found[/yellow]")
        console.print(f"[yellow]Expected location: {log_file}[/yellow]")
        return 1

    if follow:
        # Follow logs (like tail -f)
        console.print(f"[cyan]Following logs from {log_file}[/cyan]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            # Use tail -f command
            subprocess.run(["tail", "-f", str(log_file)])
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following logs[/dim]")

        return 0
    else:
        # Show last N lines
        console.print(f"[cyan]Last {lines} lines from {log_file}:[/cyan]\n")

        try:
            # Use tail command to show last N lines
            subprocess.run(["tail", "-n", str(lines), str(log_file)])
        except Exception as e:
            console.print(f"[red]Failed to read log file: {e}[/red]")
            return 1

        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ppserver",
        description="Manage the PutPlace API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  start     Start the server
  stop      Stop the server
  restart   Restart the server
  status    Check server status
  logs      Show server logs

Examples:
  # Start server on default port (8000)
  ppserver start

  # Start server on custom port
  ppserver start --port 8080

  # Start server on all interfaces
  ppserver start --host 0.0.0.0

  # Start with auto-reload (development)
  ppserver start --reload

  # Stop server
  ppserver stop

  # Restart server
  ppserver restart

  # Check status
  ppserver status

  # Show logs
  ppserver logs

  # Follow logs
  ppserver logs --follow
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the server")
    start_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    start_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # Stop command
    subparsers.add_parser("stop", help="Stop the server")

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart the server")
    restart_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    restart_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    restart_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    # Status command
    subparsers.add_parser("status", help="Check server status")

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show server logs")
    logs_parser.add_argument(
        "-f", "--follow",
        action="store_true",
        help="Follow log output (like tail -f)",
    )
    logs_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=50,
        help="Number of lines to show (default: 50)",
    )

    args = parser.parse_args()

    # Show help if no command provided
    if args.command is None:
        parser.print_help()
        return 1

    # Execute command
    if args.command == "start":
        return start_server(args.host, args.port, args.reload)
    elif args.command == "stop":
        return stop_server()
    elif args.command == "restart":
        return restart_server(args.host, args.port, args.reload)
    elif args.command == "status":
        return status_server()
    elif args.command == "logs":
        return logs_server(args.follow, args.lines)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
