"""Daemon process management for putplace-assist."""

import atexit
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn

from .config import settings, get_config_file_path
from .version import __version__

logger = logging.getLogger(__name__)


class DaemonManager:
    """Manages the daemon process."""

    def __init__(self, pid_file: Optional[Path] = None):
        """Initialize daemon manager.

        Args:
            pid_file: Path to PID file
        """
        self.pid_file = pid_file or settings.pid_file_resolved

    def is_running(self) -> tuple[bool, Optional[int]]:
        """Check if daemon is running.

        Returns:
            Tuple of (is_running, pid)
        """
        if not self.pid_file.exists():
            return False, None

        try:
            pid = int(self.pid_file.read_text().strip())

            # Check if process is running
            os.kill(pid, 0)
            return True, pid

        except (ValueError, ProcessLookupError, PermissionError):
            # Invalid PID or process not running
            self._cleanup_pid_file()
            return False, None

    def _cleanup_pid_file(self) -> None:
        """Remove stale PID file."""
        try:
            self.pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    def _write_pid_file(self) -> None:
        """Write current PID to file."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))
        atexit.register(self._cleanup_pid_file)

    def start(self, foreground: bool = False, port: Optional[int] = None) -> int:
        """Start the daemon.

        Args:
            foreground: Run in foreground (don't daemonize)
            port: Port to listen on (overrides settings if provided)

        Returns:
            Exit code
        """
        running, pid = self.is_running()
        if running:
            print(f"Daemon already running (PID: {pid})")
            return 1

        # Use provided port or fall back to settings
        effective_port = port if port is not None else settings.server_port

        if foreground:
            return self._run_foreground(effective_port)
        else:
            return self._daemonize(effective_port)

    def _run_foreground(self, port: int) -> int:
        """Run the daemon in the foreground.

        Args:
            port: Port to listen on
        """
        self._write_pid_file()

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, settings.server_log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        print(f"Starting PutPlace Assist v{__version__}")

        # Show config file if one is being used
        config_path = get_config_file_path()
        if config_path:
            print(f"  Config: {config_path}")
        else:
            print(f"  Config: No config file found, using defaults")

        print(f"  Host: {settings.server_host}")
        print(f"  Port: {port}")
        print(f"  Database: {settings.db_path_resolved}")
        print(f"  PID file: {self.pid_file}")

        # Handle signals
        def signal_handler(signum, frame):
            print("\nReceived shutdown signal, exiting...")
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Run uvicorn
        uvicorn.run(
            "putplace_assist.main:app",
            host=settings.server_host,
            port=port,
            log_level=settings.server_log_level.lower(),
            access_log=True,
            timeout_graceful_shutdown=1,  # Quick shutdown but allow SSE connections to close
        )

        return 0

    def _daemonize(self, port: int) -> int:
        """Daemonize the process.

        Args:
            port: Port to listen on
        """
        # Show config info before forking
        config_path = get_config_file_path()
        if config_path:
            print(f"Using config from {config_path}")

        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                # Parent process
                print(f"Daemon started with PID: {pid}")
                return 0
        except OSError as e:
            print(f"Fork failed: {e}")
            return 1

        # Decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                # Exit from second parent
                sys.exit(0)
        except OSError as e:
            print(f"Second fork failed: {e}")
            sys.exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        with open("/dev/null", "rb", 0) as devnull:
            os.dup2(devnull.fileno(), sys.stdin.fileno())

        # Set up logging to file
        log_file = settings.db_path_resolved.parent / "ppassist.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, settings.server_log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            filename=str(log_file),
        )

        # Write PID file
        self._write_pid_file()

        # Run the server
        uvicorn.run(
            "putplace_assist.main:app",
            host=settings.server_host,
            port=port,
            log_level=settings.server_log_level.lower(),
            access_log=False,
            timeout_graceful_shutdown=1,  # Quick shutdown but allow SSE connections to close
        )

        return 0

    def stop(self) -> int:
        """Stop the daemon.

        Returns:
            Exit code
        """
        running, pid = self.is_running()
        if not running:
            print("Daemon is not running")
            return 0

        try:
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            import time
            try:
                for _ in range(30):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.5)
                    except ProcessLookupError:
                        break
                else:
                    # Force kill
                    print("Daemon did not stop gracefully, forcing...")
                    os.kill(pid, signal.SIGKILL)
            except KeyboardInterrupt:
                # User pressed Ctrl-C, force kill immediately
                print("\nForce stopping daemon...")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            self._cleanup_pid_file()
            print("Daemon stopped")
            return 0

        except ProcessLookupError:
            self._cleanup_pid_file()
            print("Daemon stopped")
            return 0

        except PermissionError:
            print(f"Permission denied to stop daemon (PID: {pid})")
            return 1

        except KeyboardInterrupt:
            # User interrupted during initial stop
            print("\nStopping interrupted")
            return 1

    def restart(self, foreground: bool = False, port: Optional[int] = None) -> int:
        """Restart the daemon.

        Args:
            foreground: Run in foreground (don't daemonize)
            port: Port to listen on (overrides settings if provided)

        Returns:
            Exit code
        """
        try:
            self.stop()
            return self.start(foreground=foreground, port=port)
        except KeyboardInterrupt:
            print("\nRestart interrupted")
            return 1

    def status(self) -> int:
        """Print daemon status.

        Returns:
            Exit code (0 if running, 1 if not)
        """
        running, pid = self.is_running()

        if running:
            print(f"Daemon is running (PID: {pid})")
            print(f"  API: http://{settings.server_host}:{settings.server_port}")
            return 0
        else:
            print("Daemon is not running")
            return 1


# Global daemon manager
daemon = DaemonManager()
