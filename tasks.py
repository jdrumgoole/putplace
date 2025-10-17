"""Invoke tasks for development workflow."""

from invoke import task


@task
def setup_venv(c):
    """Create virtual environment with uv."""
    c.run("uv venv")
    print("\n✓ Virtual environment created")
    print("Activate with: source .venv/bin/activate")


@task
def install(c):
    """Install the project dependencies using uv."""
    c.run("uv pip install -e '.[dev]'")
    print("\n✓ Package and dependencies installed")
    print("\nIMPORTANT: Activate the virtual environment to use console scripts:")
    print("  source .venv/bin/activate")
    print("\nThen you can use:")
    print("  ppclient --help")
    print("  ppserver --help")


@task
def setup_env(c):
    """Copy .env.example to .env if it doesn't exist."""
    result = c.run("test -f .env", warn=True)
    if result.ok:
        print("✓ .env file already exists")
    else:
        c.run("cp .env.example .env")
        print("✓ Created .env file from .env.example")
        print("  Edit .env to customize your configuration")


@task
def test(c, verbose=False, coverage=True):
    """Run the test suite with pytest."""
    cmd = "uv run pytest"
    if verbose:
        cmd += " -v"
    if not coverage:
        cmd += " --no-cov"
    c.run(cmd)


@task
def test_all(c, verbose=True, coverage=True):
    """Run all tests with proper PYTHONPATH setup.

    Args:
        verbose: Show verbose test output (default: True)
        coverage: Generate coverage report (default: True)
    """
    import os
    pythonpath = f"{os.getcwd()}/src:{os.environ.get('PYTHONPATH', '')}"

    cmd = f"PYTHONPATH={pythonpath} uv run python -m pytest tests/ -v --tb=short"
    if not coverage:
        cmd += " --no-cov"

    c.run(cmd)

    if coverage:
        print("\n✓ All tests passed!")
        print("Coverage report: htmlcov/index.html")


@task
def test_one(c, path):
    """Run a single test file or test function.

    Examples:
        inv test-one tests/test_example.py
        inv test-one tests/test_example.py::test_function
    """
    c.run(f"uv run pytest {path} -v")


@task
def lint(c, fix=False):
    """Run ruff linter on the codebase."""
    cmd = "uv run ruff check src tests"
    if fix:
        cmd += " --fix"
    c.run(cmd)


@task
def format(c, check=False):
    """Format code with ruff."""
    cmd = "uv run ruff format src tests"
    if check:
        cmd += " --check"
    c.run(cmd)


@task
def typecheck(c):
    """Run mypy type checker."""
    c.run("uv run mypy src")


@task
def check(c):
    """Run all checks: format, lint, typecheck, and test."""
    format(c, check=True)
    lint(c)
    typecheck(c)
    test(c)


@task
def clean(c):
    """Remove build artifacts and caches."""
    patterns = [
        "build",
        "dist",
        "*.egg-info",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        ".coverage",
        "**/__pycache__",
        "**/*.pyc",
    ]
    for pattern in patterns:
        c.run(f"rm -rf {pattern}", warn=True)


@task
def build(c):
    """Build the package."""
    clean(c)
    c.run("uv build")


@task
def sync(c):
    """Sync dependencies with uv."""
    c.run("uv pip sync requirements.txt")


@task
def serve(c, host="127.0.0.1", port=8000, reload=True):
    """Run the FastAPI development server.

    Args:
        host: Host to bind to (default: 127.0.0.1)
        port: Port to bind to (default: 8000)
        reload: Enable auto-reload on code changes (default: True)
    """
    reload_flag = "--reload" if reload else ""
    c.run(f"uv run uvicorn putplace.main:app --host {host} --port {port} {reload_flag}")


@task
def serve_prod(c, host="0.0.0.0", port=8000, workers=4):
    """Run the FastAPI server in production mode.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        workers: Number of worker processes (default: 4)
    """
    c.run(f"uv run uvicorn putplace.main:app --host {host} --port {port} --workers {workers}")


# MongoDB management tasks
@task
def mongo_start(c, name="mongodb", port=27017):
    """Start MongoDB in Docker.

    Args:
        name: Container name (default: mongodb)
        port: Port to expose (default: 27017)
    """
    # Check if container exists
    result = c.run(f"docker ps -a -q -f name=^{name}$", hide=True, warn=True)

    if result.stdout.strip():
        # Container exists, check if running
        running = c.run(f"docker ps -q -f name=^{name}$", hide=True, warn=True)
        if running.stdout.strip():
            print(f"✓ MongoDB container '{name}' is already running")
        else:
            print(f"Starting existing MongoDB container '{name}'...")
            c.run(f"docker start {name}")
            print(f"✓ MongoDB started on port {port}")
    else:
        # Create and start new container
        print(f"Creating MongoDB container '{name}'...")
        c.run(f"docker run -d -p {port}:27017 --name {name} mongo:latest")
        print(f"✓ MongoDB started on port {port}")


@task
def mongo_stop(c, name="mongodb"):
    """Stop MongoDB Docker container.

    Args:
        name: Container name (default: mongodb)
    """
    result = c.run(f"docker ps -q -f name=^{name}$", hide=True, warn=True)
    if result.stdout.strip():
        c.run(f"docker stop {name}")
        print(f"✓ MongoDB container '{name}' stopped")
    else:
        print(f"MongoDB container '{name}' is not running")


@task
def mongo_remove(c, name="mongodb"):
    """Remove MongoDB Docker container.

    Args:
        name: Container name (default: mongodb)
    """
    result = c.run(f"docker ps -a -q -f name=^{name}$", hide=True, warn=True)
    if result.stdout.strip():
        # Stop if running
        running = c.run(f"docker ps -q -f name=^{name}$", hide=True, warn=True)
        if running.stdout.strip():
            c.run(f"docker stop {name}", hide=True)
        c.run(f"docker rm {name}")
        print(f"✓ MongoDB container '{name}' removed")
    else:
        print(f"MongoDB container '{name}' does not exist")


@task
def mongo_status(c, name="mongodb"):
    """Check MongoDB Docker container status.

    Args:
        name: Container name (default: mongodb)
    """
    result = c.run(f"docker ps -a -f name=^{name}$ --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'", warn=True)
    if not result.stdout.strip() or "NAMES" == result.stdout.strip():
        print(f"MongoDB container '{name}' does not exist")
        print("\nStart MongoDB with: invoke mongo-start")
    else:
        print(result.stdout)


@task
def mongo_logs(c, name="mongodb", follow=False):
    """Show MongoDB Docker container logs.

    Args:
        name: Container name (default: mongodb)
        follow: Follow log output (default: False)
    """
    follow_flag = "-f" if follow else ""
    c.run(f"docker logs {follow_flag} {name}")


# Quick setup tasks
@task(pre=[setup_venv])
def setup(c):
    """Complete project setup: venv, dependencies, and .env file."""
    print("\nInstalling dependencies...")
    install(c)
    print("\nSetting up environment file...")
    setup_env(c)
    print("\n✓ Setup complete!")
    print("\nNext steps:")
    print("  1. Activate venv: source .venv/bin/activate")
    print("  2. Start MongoDB: invoke mongo-start")
    print("  3. Run server: invoke serve")


@task(pre=[mongo_start])
def quickstart(c):
    """Quick start: Start MongoDB and run the development server."""
    print("\nStarting development server...")
    print("API will be available at: http://localhost:8000")
    print("Interactive docs at: http://localhost:8000/docs\n")
    serve(c)


# PutPlace server management
@task
def ppserver_start(c, host="127.0.0.1", port=8000):
    """Install package locally and start ppserver in background.

    Args:
        host: Host to bind to (default: 127.0.0.1)
        port: Port to bind to (default: 8000)
    """
    import os
    import signal

    pid_file = ".ppserver.pid"

    # Check if server is already running
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            old_pid = f.read().strip()

        # Check if process is still running
        try:
            os.kill(int(old_pid), 0)
            print(f"✗ ppserver is already running (PID: {old_pid})")
            print("  Stop it first with: invoke ppserver-stop")
            return
        except (OSError, ValueError):
            # Process not running, remove stale PID file
            os.remove(pid_file)

    print("Installing putplace package locally...")
    c.run("uv pip install -e .", pty=False)
    print("✓ Package installed\n")

    print(f"Starting ppserver on {host}:{port}...")

    # Start uvicorn in background and save PID
    cmd = f"uv run uvicorn putplace.main:app --host {host} --port {port}"
    result = c.run(f"{cmd} > ppserver.log 2>&1 & echo $!", hide=True, pty=False)
    pid = result.stdout.strip()

    # Save PID to file
    with open(pid_file, 'w') as f:
        f.write(pid)

    print(f"✓ ppserver started (PID: {pid})")
    print(f"  API: http://{host}:{port}")
    print(f"  Docs: http://{host}:{port}/docs")
    print(f"  Logs: ppserver.log")
    print(f"\nStop with: invoke ppserver-stop")


@task
def ppserver_stop(c):
    """Stop ppserver and uninstall local package."""
    import os
    import signal
    import time

    pid_file = ".ppserver.pid"

    # Check if PID file exists
    if not os.path.exists(pid_file):
        print("✗ ppserver PID file not found")
        print("  Server may not be running or was started manually")

        # Try to find and kill any running uvicorn processes
        result = c.run("pgrep -f 'uvicorn putplace.main:app'", warn=True, hide=True)
        if result.ok and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            print(f"\nFound {len(pids)} uvicorn process(es) for putplace:")
            for pid in pids:
                print(f"  Killing PID {pid}...")
                c.run(f"kill {pid}", warn=True)
            time.sleep(1)
            print("✓ Processes killed")
        else:
            print("  No running ppserver processes found")
    else:
        # Read PID and kill the process
        with open(pid_file, 'r') as f:
            pid = f.read().strip()

        print(f"Stopping ppserver (PID: {pid})...")

        try:
            # Try graceful shutdown first (SIGTERM)
            os.kill(int(pid), signal.SIGTERM)
            time.sleep(2)

            # Check if still running
            try:
                os.kill(int(pid), 0)
                # Still running, force kill
                print("  Process still running, forcing shutdown...")
                os.kill(int(pid), signal.SIGKILL)
                time.sleep(1)
            except OSError:
                pass  # Process already terminated

            print("✓ ppserver stopped")
        except (OSError, ValueError) as e:
            print(f"✗ Could not kill process {pid}: {e}")
            print("  Process may have already terminated")

        # Remove PID file
        try:
            os.remove(pid_file)
            print("✓ PID file removed")
        except OSError:
            pass

    # Uninstall the package
    print("\nUninstalling putplace package...")
    result = c.run("echo y | uv pip uninstall putplace", warn=True)
    if result.ok:
        print("✓ Package uninstalled")
    else:
        print("✗ Failed to uninstall package (may not be installed)")

    print("\n✓ Cleanup complete")


@task
def ppserver_status(c):
    """Check ppserver status."""
    import os

    pid_file = ".ppserver.pid"

    if not os.path.exists(pid_file):
        print("✗ ppserver is not running (no PID file)")

        # Check for any uvicorn processes anyway
        result = c.run("pgrep -f 'uvicorn putplace.main:app'", warn=True, hide=True)
        if result.ok and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            print(f"\nWarning: Found {len(pids)} uvicorn process(es) without PID file:")
            for pid in pids:
                print(f"  PID {pid}")
            print("\nUse 'invoke ppserver-stop' to clean up")
        return

    with open(pid_file, 'r') as f:
        pid = f.read().strip()

    try:
        os.kill(int(pid), 0)
        print(f"✓ ppserver is running (PID: {pid})")

        # Try to get process info
        result = c.run(f"ps -p {pid} -o pid,ppid,etime,command", warn=True)

        # Check if log file exists
        if os.path.exists("ppserver.log"):
            print("\nRecent logs (last 10 lines):")
            c.run("tail -n 10 ppserver.log")
    except (OSError, ValueError):
        print(f"✗ ppserver PID file exists but process {pid} is not running")
        print("  Stale PID file detected")
        print("\nClean up with: invoke ppserver-stop")


@task
def ppserver_logs(c, lines=50, follow=False):
    """Show ppserver logs.

    Args:
        lines: Number of lines to show (default: 50)
        follow: Follow log output (default: False)
    """
    import os

    log_file = "ppserver.log"

    if not os.path.exists(log_file):
        print("✗ Log file not found: ppserver.log")
        print("  Server may not have been started or logs were deleted")
        return

    if follow:
        print(f"Following ppserver logs (Ctrl+C to stop)...\n")
        c.run(f"tail -f {log_file}")
    else:
        print(f"Last {lines} lines from ppserver.log:\n")
        c.run(f"tail -n {lines} {log_file}")
