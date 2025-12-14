"""Command-line interface for putplace-assist."""

import argparse
import sys

from .daemon import daemon
from .version import __version__

# Default port for the daemon
DEFAULT_PORT = 8765


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="pp_assist",
        description="PutPlace Assist - Local assistant daemon for file uploads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Use 'pp_assist <command> --help' for more information on a command.

Examples:
  pp_assist start                  Start daemon on default port ({DEFAULT_PORT})
  pp_assist start --port 9000      Start daemon on port 9000
  pp_assist start --foreground     Start in foreground mode
  pp_assist stop                   Stop the daemon
  pp_assist status                 Check daemon status

pp_assist version {__version__}""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the daemon")
    start_parser.add_argument(
        "-f", "--foreground",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    start_parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )

    # Stop command
    subparsers.add_parser("stop", help="Stop the daemon")

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart the daemon")
    restart_parser.add_argument(
        "-f", "--foreground",
        action="store_true",
        help="Run in foreground (don't daemonize)",
    )
    restart_parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )

    # Status command
    subparsers.add_parser("status", help="Check daemon status")

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "start":
        return daemon.start(foreground=args.foreground, port=args.port)

    elif args.command == "stop":
        return daemon.stop()

    elif args.command == "restart":
        return daemon.restart(foreground=args.foreground, port=args.port)

    elif args.command == "status":
        return daemon.status()

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
