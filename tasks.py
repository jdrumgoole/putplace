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
def test(c, verbose=False, coverage=True):
    """Run the test suite with pytest."""
    cmd = "uv run pytest"
    if verbose:
        cmd += " -v"
    if not coverage:
        cmd += " --no-cov"
    c.run(cmd)


@task
def test_all(c, verbose=True, coverage=True, parallel=True, workers=4):
    """Run all tests with proper PYTHONPATH setup.

    Tests include:
        - Python unit tests (models, API, database, auth, storage)
        - Integration tests (end-to-end, admin creation)
        - Electron GUI tests (packaging, installation, launch/quit) - macOS only

    Args:
        verbose: Show verbose test output (default: True)
        coverage: Generate coverage report (default: True)
        parallel: Run tests in parallel (default: True, ~40% faster)
        workers: Number of parallel workers (default: 4, balanced speed/reliability)

    Examples:
        invoke test-all                     # Run in parallel with 4 workers (default)
        invoke test-all --workers=8         # Use 8 workers (faster, may be less stable)
        invoke test-all --parallel=False    # Run serially (slower but most stable)

    Note: Each test worker gets its own isolated database to prevent race conditions.
          Default of 4 workers provides good balance between speed and reliability.
          Electron GUI tests require 'invoke gui-electron-package' to be run first.
    """
    import os
    pythonpath = f"{os.getcwd()}/src:{os.environ.get('PYTHONPATH', '')}"

    cmd = f"PYTHONPATH={pythonpath} uv run python -m pytest tests/ -v --tb=short"

    # Add parallel execution if enabled
    # Use --dist loadscope to run tests in the same module/class in the same worker
    # This prevents database race conditions between related tests
    if parallel:
        cmd += f" -n {workers} --dist loadscope"

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
    print("\n✓ Package built successfully")
    print("  Distribution files in: dist/")


@task
def sync(c):
    """Sync dependencies with uv."""
    c.run("uv pip sync requirements.txt")


# Docker management tasks
@task
def docker_start(c):
    """Start Docker Desktop/daemon if not running.

    Automatically detects the platform and starts Docker accordingly:
    - macOS: Starts Docker Desktop application
    - Linux: Starts docker service via systemd
    - Windows: Starts Docker Desktop (requires manual start)
    """
    import time
    import platform

    # Check if Docker is already running
    result = c.run("docker ps", hide=True, warn=True)
    if result.ok:
        print("✓ Docker is already running")
        return

    system = platform.system()
    print(f"Docker is not running. Starting Docker on {system}...")

    if system == "Darwin":  # macOS
        print("Starting Docker Desktop...")
        c.run("open -a Docker", warn=True)

        # Wait for Docker to be ready (max 60 seconds)
        print("Waiting for Docker to start", end="", flush=True)
        for i in range(60):
            time.sleep(1)
            print(".", end="", flush=True)
            result = c.run("docker ps", hide=True, warn=True)
            if result.ok:
                print()
                print("✓ Docker Desktop started successfully")
                return

        print()
        print("⚠️  Docker Desktop is taking longer than expected to start")
        print("   Please check Docker Desktop manually")

    elif system == "Linux":
        print("Starting Docker daemon...")
        c.run("sudo systemctl start docker", warn=True)

        # Wait for Docker to be ready
        print("Waiting for Docker daemon", end="", flush=True)
        for i in range(30):
            time.sleep(1)
            print(".", end="", flush=True)
            result = c.run("docker ps", hide=True, warn=True)
            if result.ok:
                print()
                print("✓ Docker daemon started successfully")
                return

        print()
        print("⚠️  Docker daemon failed to start")
        print("   Try: sudo systemctl status docker")

    elif system == "Windows":
        print("Please start Docker Desktop manually on Windows")
        print("Waiting for Docker to start", end="", flush=True)
        for i in range(60):
            time.sleep(1)
            print(".", end="", flush=True)
            result = c.run("docker ps", hide=True, warn=True)
            if result.ok:
                print()
                print("✓ Docker Desktop is running")
                return

        print()
        print("⚠️  Docker Desktop is not running")
        print("   Please start Docker Desktop manually")
    else:
        print(f"⚠️  Unsupported platform: {system}")
        print("   Please start Docker manually")


# MongoDB management tasks
@task(pre=[docker_start])
def mongo_start(c, name="mongodb", port=27017):
    """Start MongoDB in Docker.

    Automatically starts Docker if not running.

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


# Server tasks
# ============================================================================
# Three ways to run the PutPlace server:
#
# 1. invoke serve (RECOMMENDED FOR DEVELOPMENT)
#    - Runs in foreground with live output
#    - Auto-reload on code changes
#    - Easy to stop with Ctrl+C
#    - Automatically starts MongoDB
#
# 2. invoke ppserver-start (FOR BACKGROUND TESTING)
#    - Runs in background
#    - No auto-reload (manual restart needed)
#    - Logs to ppserver.log in current directory
#    - Stop with: invoke ppserver-stop
#
# 3. ppserver start (FOR PRODUCTION/DAEMON)
#    - CLI tool for production daemon management
#    - Logs to ~/.putplace/ppserver.log
#    - Has status, restart, logs commands
#    - Stop with: ppserver stop
# ============================================================================

@task(pre=[mongo_start])
def serve(c, host="127.0.0.1", port=8000, reload=True):
    """Run the FastAPI development server in foreground (recommended for development).

    This task runs the server in the foreground with live output and auto-reload.
    Press Ctrl+C to stop the server.

    Automatically starts MongoDB if not running.

    Features:
        - Runs in foreground with live console output
        - Auto-reload enabled by default (picks up code changes)
        - Easy to stop with Ctrl+C
        - Best for active development

    Compare with:
        - invoke ppserver-start: Runs in background, no auto-reload, logs to file
        - ppserver start: CLI tool for production daemon management

    Args:
        host: Host to bind to (default: 127.0.0.1)
        port: Port to bind to (default: 8000)
        reload: Enable auto-reload on code changes (default: True)
    """
    reload_flag = "--reload" if reload else ""
    c.run(f"uv run uvicorn putplace.main:app --host {host} --port {port} {reload_flag}")


@task(pre=[mongo_start])
def serve_prod(c, host="0.0.0.0", port=8000, workers=4):
    """Run the FastAPI server in production mode.

    Automatically starts MongoDB if not running.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        workers: Number of worker processes (default: 4)
    """
    c.run(f"uv run uvicorn putplace.main:app --host {host} --port {port} --workers {workers}")


# Client tasks
@task
def gui_electron_build(c):
    """Build the Electron GUI desktop app.

    Builds the TypeScript source files and copies assets to dist directory.
    The Electron app provides a modern cross-platform desktop interface.

    Requirements:
        - Node.js and npm must be installed
        - Run from project root directory
    """
    import os
    electron_dir = "ppgui-electron"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        print("Make sure you're running from the project root directory")
        return

    print("🔨 Building Electron GUI app...")
    with c.cd(electron_dir):
        # Check if node_modules exists
        if not os.path.exists(f"{electron_dir}/node_modules"):
            print("📦 Installing npm dependencies...")
            c.run("npm install")

        print("🔧 Compiling TypeScript and copying assets...")
        c.run("npm run build")

    print("✓ Electron GUI build complete!")
    print(f"  Build output: {electron_dir}/dist/")


@task
def gui_electron_package(c):
    """Package the Electron GUI app into a distributable .app bundle.

    Creates a properly signed macOS application with correct menu names.
    Output will be in ppgui-electron/release/ directory.

    Requirements:
        - Node.js and npm must be installed
        - electron-builder package installed
    """
    import os
    electron_dir = "ppgui-electron"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        return

    print("📦 Packaging Electron GUI app...")
    with c.cd(electron_dir):
        # Check if node_modules exists
        if not os.path.exists(f"{electron_dir}/node_modules"):
            print("📦 Installing npm dependencies...")
            c.run("npm install")

        print("🔧 Building and packaging app...")
        c.run("npm run package")

    print("✓ Packaging complete!")
    print(f"  macOS app: {electron_dir}/release/mac-arm64/PutPlace Client.app")
    print(f"  DMG installer: {electron_dir}/release/PutPlace Client-*.dmg")


@task
def gui_electron(c, dev=False, packaged=True):
    """Run the Electron GUI desktop app.

    Launches the cross-platform desktop application for PutPlace.

    Args:
        dev: Run in development mode with DevTools (default: False)
        packaged: Use packaged .app with correct menu names (default: True)

    Features:
        - Native directory picker
        - File scanning with exclude patterns
        - SHA256 hash calculation
        - Real-time progress tracking
        - JWT authentication
        - Settings persistence

    Requirements:
        - Node.js and npm must be installed
        - App must be built/packaged first
    """
    import os
    import sys
    electron_dir = "ppgui-electron"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        return

    # Use packaged app by default (has correct menu names)
    if packaged and sys.platform == 'darwin':
        app_path = f"{electron_dir}/release/mac-arm64/PutPlace Client.app"

        if not os.path.exists(app_path):
            print("⚠️  Packaged app not found. Packaging now...")
            gui_electron_package(c)

        # Convert to absolute path for 'open' command
        abs_app_path = os.path.abspath(app_path)

        print("🚀 Launching PutPlace Client (packaged app)...")
        if dev:
            # Open with DevTools
            c.run(f'open "{abs_app_path}" --args --dev')
        else:
            c.run(f'open "{abs_app_path}"')
    else:
        # Development mode (menu will show "Electron")
        if not os.path.exists(f"{electron_dir}/dist/main.js"):
            print("⚠️  App not built yet. Building now...")
            gui_electron_build(c)

        print("🚀 Launching Electron GUI (development mode)...")
        print("⚠️  Note: Menu bar will show 'Electron' in dev mode")
        with c.cd(electron_dir):
            if dev:
                c.run("npm run dev")
            else:
                c.run("npm start")


@task
def gui_electron_test_install(c, automated=False):
    """Test the packaged Electron app installation and uninstallation.

    Args:
        automated: If True, copy app directly without manual DMG installation (default: False)

    This task:
    1. Packages the app if not already packaged
    2. Installs to /Applications (automated or via DMG)
    3. Tests launching the installed app
    4. Automatically quits the app
    5. Provides uninstallation instructions

    Semi-automated test - some manual verification required.
    """
    import os
    import sys
    import time

    if sys.platform != 'darwin':
        print("❌ This test is only for macOS")
        return

    electron_dir = "ppgui-electron"
    app_name = "PutPlace Client"

    # Step 1: Ensure app is packaged
    print("Step 1: Checking for packaged app...")
    dmg_dir = f"{electron_dir}/release"

    # Check if any DMG files exist
    import glob
    dmg_files = glob.glob(f"{dmg_dir}/{app_name}-*.dmg")

    if not dmg_files:
        print("⚠️  DMG not found. Packaging now...")
        gui_electron_package(c)
        # Re-check for DMG files
        dmg_files = glob.glob(f"{dmg_dir}/{app_name}-*.dmg")

    if not dmg_files:
        print("❌ Failed to create DMG file")
        return

    dmg_path = dmg_files[0]
    print(f"✓ Found DMG: {dmg_path}\n")

    # Step 2: Install the app
    installed_app = f"/Applications/{app_name}.app"
    app_bundle = f"{electron_dir}/release/mac-arm64/{app_name}.app"

    if automated:
        print("Step 2: Installing app to /Applications (automated)...")
        # Remove existing installation if present
        if os.path.exists(installed_app):
            print(f"  Removing existing installation...")
            c.run(f'rm -rf "{installed_app}"', warn=True)

        # Copy the app bundle directly
        print(f"  Copying app to /Applications...")
        c.run(f'cp -R "{app_bundle}" /Applications/')
        print("✓ App installed\n")
    else:
        print("Step 2: Opening DMG installer...")
        c.run(f'open "{dmg_path}"')
        print("✓ DMG opened\n")

        print("=" * 60)
        print("MANUAL STEP REQUIRED:")
        print("1. Drag 'PutPlace Client' to the Applications folder")
        print("2. Wait for the copy to complete")
        print("3. Press Enter here to continue...")
        print("=" * 60)
        try:
            input()
        except EOFError:
            print("\n⚠️  Running in non-interactive mode. Switching to automated install...")
            automated = True
            if os.path.exists(installed_app):
                c.run(f'rm -rf "{installed_app}"', warn=True)
            c.run(f'cp -R "{app_bundle}" /Applications/')
            print("✓ App installed")

    # Step 3: Test launching the installed app
    print("\nStep 3: Testing installed app...")
    installed_app = f"/Applications/{app_name}.app"

    if os.path.exists(installed_app):
        print(f"✓ Found installed app: {installed_app}")
        print("🚀 Launching installed app...")
        c.run(f'open -a "{installed_app}"')
        print("✓ App launched\n")

        print("Please check:")
        print("  - Does the menu bar show 'PutPlace Client' (not 'Electron')?")
        print("  - Can you login successfully?")
        print("  - Does file scanning work?")

        if not automated:
            print("\nPress Enter to quit the app and continue...")
            try:
                input()
            except EOFError:
                print("\n⚠️  Running in non-interactive mode. Continuing automatically...")
        else:
            print("\nWaiting 5 seconds for testing...")
            time.sleep(5)

        # Quit the app
        print("\n🛑 Quitting PutPlace Client...")
        c.run(f'osascript -e \'quit app "{app_name}"\'', warn=True)
        time.sleep(1)
        print("✓ App quit\n")

        # Step 4: Uninstallation instructions
        print("\n" + "=" * 60)
        print("UNINSTALLATION INSTRUCTIONS:")
        print("=" * 60)
        print("To remove the app, run these commands:")
        print(f'  1. Quit the app if running')
        print(f'  2. rm -rf "{installed_app}"')
        print(f'  3. rm -rf ~/Library/Application\\ Support/PutPlace\\ Client')
        print(f'  4. rm -rf ~/Library/Preferences/com.putplace.client.plist')
        print(f'  5. Eject the DMG volume if mounted')

        if automated:
            print("\n⚠️  Automated mode: Automatically uninstalling...")
            choice = 'y'
        else:
            print("\nWould you like to uninstall now? (y/N): ", end='')
            try:
                choice = input().strip().lower()
            except EOFError:
                print("\n⚠️  Running in non-interactive mode. Skipping uninstall.")
                choice = 'n'

        if choice == 'y':
            print("\nUninstalling...")
            c.run(f'rm -rf "{installed_app}"', warn=True)
            c.run(f'rm -rf ~/Library/Application\\ Support/PutPlace\\ Client', warn=True)
            c.run(f'rm -rf ~/Library/Preferences/com.putplace.client.plist', warn=True)
            print("✓ App uninstalled")
        else:
            print("\nSkipping uninstallation.")
            print("The app will remain in /Applications/")
    else:
        print(f"❌ App not found at {installed_app}")
        print("Installation may have failed.")

    print("\n✓ Test complete!")


@task
def configure(c, non_interactive=False, admin_username=None, admin_email=None,
              storage_backend=None, config_file='ppserver.toml', test_mode=None,
              aws_region=None):
    """Run the server configuration wizard.

    Args:
        non_interactive: Run in non-interactive mode (requires other args)
        admin_username: Admin username (for non-interactive mode)
        admin_email: Admin email (for non-interactive mode)
        storage_backend: Storage backend: "local" or "s3"
        config_file: Path to configuration file (default: ppserver.toml)
        test_mode: Run standalone test: "S3" or "SES"
        aws_region: AWS region for tests (default: us-east-1)

    Examples:
        invoke configure                      # Interactive mode
        invoke configure --non-interactive \
          --admin-username=admin \
          --admin-email=admin@example.com \
          --storage-backend=local
        invoke configure --test-mode=S3       # Test S3 access
        invoke configure --test-mode=SES      # Test SES access
        invoke configure --test-mode=S3 --aws-region=us-west-2
    """
    # Run script directly from source (no installation needed)
    cmd = "uv run python -m putplace.scripts.putplace_configure"

    # Handle standalone test mode
    if test_mode:
        cmd += f" {test_mode}"
        if aws_region:
            cmd += f" --aws-region={aws_region}"
        c.run(cmd, pty=True)
        return

    if non_interactive:
        cmd += " --non-interactive"
        if admin_username:
            cmd += f" --admin-username={admin_username}"
        if admin_email:
            cmd += f" --admin-email={admin_email}"
        if storage_backend:
            cmd += f" --storage-backend={storage_backend}"

    if config_file != 'ppserver.toml':
        cmd += f" --config-file={config_file}"

    # Use pty=True to properly inherit terminal settings for readline
    c.run(cmd, pty=True)


# Quick setup tasks
@task(pre=[setup_venv])
def setup(c):
    """Complete project setup: venv, dependencies, and configuration."""
    print("\nInstalling dependencies...")
    install(c)
    print("\n✓ Setup complete!")
    print("\nNext steps:")
    print("  1. Activate venv: source .venv/bin/activate")
    print("  2. Configure server: invoke configure (or putplace-configure)")
    print("  3. Start MongoDB: invoke mongo-start")
    print("  4. Run server: invoke serve")


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
    """Start server in background (for testing/background work).

    This task runs the server as a background process with output logged to file.
    Use invoke ppserver-stop to stop it.

    Features:
        - Runs in background (detached from terminal)
        - No auto-reload (must restart manually for code changes)
        - Logs to ppserver.log file
        - Saves PID to .ppserver.pid
        - Installs package before starting
        - Good for running tests while server is up

    Compare with:
        - invoke serve: Runs in foreground with auto-reload (better for development)
        - ppserver start: CLI tool for production daemon (uses ~/.putplace/ directory)

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
