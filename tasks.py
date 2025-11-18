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

# Server management tasks removed - use ppserver-start --dev or --prod instead


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


@task(pre=[mongo_start])
def configure(c, non_interactive=False, admin_username=None, admin_email=None,
              storage_backend=None, config_file='ppserver.toml', test_mode=None,
              aws_region=None):
    """Run the server configuration wizard.

    Automatically starts MongoDB if not running (required for admin user creation).

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
    print("  4. Run server: invoke ppserver-start --dev")


@task
def quickstart(c):
    """Quick start: Start MongoDB and run the development server.

    This is equivalent to: invoke ppserver-start --dev
    """
    ppserver_start(c, dev=True)


# PutPlace server management
@task(pre=[mongo_start])
def ppserver_start(c, host="127.0.0.1", port=8000, dev=True, prod=False, background=False, reload=True, workers=1):
    """Start PutPlace server with automatic MongoDB startup.

    This unified task replaces the old serve/serve-prod tasks.
    Supports three modes: development (default), background (--background), and production (--prod).

    Automatically starts MongoDB if not running.

    Modes:
        Development (default):
            - Runs in foreground with console output
            - Auto-reload enabled (picks up code changes)
            - Easy to stop with Ctrl+C
            - Best for active development

        Background (--background):
            - Runs in background using ppserver CLI
            - Logs to ~/.putplace/ppserver.log
            - No auto-reload
            - Good for testing/CI
            - Stop with: invoke ppserver-stop

        Production (--prod):
            - Runs in background with multiple workers
            - Logs to file
            - No auto-reload
            - Bind to 0.0.0.0 for external access

    Args:
        host: Host to bind to (default: 127.0.0.1, prod uses 0.0.0.0)
        port: Port to bind to (default: 8000)
        dev: Run in development mode - default True (use --no-dev to disable)
        prod: Run in production mode (background, multiple workers)
        background: Run in background mode (for testing/CI)
        reload: Enable auto-reload in dev mode (default: True)
        workers: Number of workers for prod mode (default: 1)

    Examples:
        invoke ppserver-start                    # Development mode (default)
        invoke ppserver-start --background       # Background mode (testing)
        invoke ppserver-start --prod             # Production mode
        invoke ppserver-start --no-reload        # Dev without auto-reload
        invoke ppserver-start --prod --workers=4 # Production with 4 workers
    """
    import os
    from pathlib import Path

    # Production or background mode disable dev
    if prod or background:
        dev = False

    # Development mode: run in foreground with console output
    if dev:
        print("Starting development server (foreground, console output)...")
        print(f"API will be available at: http://{host}:{port}")
        print(f"Interactive docs at: http://{host}:{port}/docs")
        print("Press Ctrl+C to stop\n")
        reload_flag = "--reload" if reload else ""
        c.run(f"uv run uvicorn putplace.main:app --host {host} --port {port} {reload_flag}")
        return

    # Production mode: background with multiple workers
    if prod:
        if host == "127.0.0.1":
            host = "0.0.0.0"  # Production default: bind to all interfaces
        if workers == 1:
            workers = 4  # Production default: 4 workers

    print("Installing putplace package locally...")
    c.run("uv pip install -e .", pty=False)
    print("✓ Package installed\n")

    # Set up configuration using putplace_configure non-interactively
    config_dir = Path.home() / ".config" / "putplace"
    config_path = config_dir / "ppserver.toml"
    storage_path = Path.home() / ".putplace" / "storage"

    # Ensure config directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Only run configure if config doesn't exist
    if not config_path.exists():
        print("Setting up PutPlace configuration...")
        log_file = Path.home() / ".putplace" / "ppserver.log"
        pid_file = Path.home() / ".putplace" / "ppserver.pid"
        configure_cmd = [
            "uv", "run", "putplace_configure",
            "--non-interactive",
            "--skip-checks",
            "--mongodb-url", "mongodb://localhost:27017",
            "--mongodb-database", "putplace",
            "--admin-username", "admin",
            "--admin-email", "admin@localhost",
            "--admin-password", "admin_password_123",
            "--storage-backend", "local",
            "--storage-path", str(storage_path),
            "--config-file", str(config_path),
            "--log-file", str(log_file),
            "--pid-file", str(pid_file),
        ]
        result = c.run(" ".join(configure_cmd), warn=True)
        if result.ok:
            print("✓ Configuration created\n")
        else:
            print("✗ Failed to create configuration")
            return
    else:
        print(f"✓ Using existing configuration: {config_path}\n")

    mode_desc = "production" if prod else "background"
    print(f"Starting ppserver in {mode_desc} mode on {host}:{port}...")

    # Use ppserver CLI to start the server
    result = c.run(f"uv run ppserver start --host {host} --port {port}", warn=True)

    if result.ok:
        print(f"\n✓ ppserver started successfully ({mode_desc} mode)")
        print(f"  API: http://{host}:{port}")
        print(f"  Docs: http://{host}:{port}/docs")
        print(f"  Config: {config_path}")
        print(f"  Storage: {storage_path}")
        print(f"  Logs: ~/.putplace/ppserver.log")
        print(f"  PID file: ~/.putplace/ppserver.pid")
        if prod:
            print(f"  Workers: {workers}")
        print(f"\nStop with: invoke ppserver-stop")
        print(f"Check status with: invoke ppserver-status")
    else:
        print("\n✗ Failed to start ppserver")
        print("Check logs with: ppserver logs")


@task
def ppserver_stop(c):
    """Stop ppserver using ppserver CLI and uninstall local package."""
    print("Stopping ppserver using ppserver CLI...")

    # Use ppserver CLI to stop the server
    result = c.run("uv run ppserver stop", warn=True)

    if result.ok:
        print("\n✓ ppserver stopped successfully")
    else:
        print("\n✗ ppserver may not be running or already stopped")

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
    """Check ppserver status using ppserver CLI."""
    c.run("uv run ppserver status", warn=True)


@task
def ppserver_logs(c, lines=50, follow=False):
    """Show ppserver logs using ppserver CLI.

    Args:
        lines: Number of lines to show (default: 50)
        follow: Follow log output (default: False)
    """
    cmd = f"uv run ppserver logs --lines {lines}"
    if follow:
        cmd += " --follow"
    c.run(cmd, warn=True)


@task
def send_test_email(c, to="joe@joedrumgoole.com", verbose=False):
    """Send a test email via Amazon SES.

    This is a convenience task that sends a test email to verify SES configuration.
    By default, sends to joe@joedrumgoole.com.

    Requirements:
        - AWS credentials configured (environment, ~/.aws/credentials, or IAM role)
        - Sender email verified in SES (Joe.Drumgoole@putplace.org)
        - If in SES sandbox, recipient email must also be verified

    Args:
        to: Recipient email address (default: joe@joedrumgoole.com)
        verbose: Show detailed output (default: False)

    Examples:
        invoke send-test-email                           # Send to joe@joedrumgoole.com
        invoke send-test-email --to=user@example.com     # Send to specific address
        invoke send-test-email --verbose                 # Show detailed output
    """

    # Build command - use -m to run as module instead of file path
    import shlex

    cmd = [
        "uv", "run", "python", "-m",
        "putplace.scripts.send_ses_email",
        "--from", "Joe.Drumgoole@putplace.org",
        "--to", to,
        "--subject", "TestSES",
        "--body", "Hello Joe"
    ]

    if verbose:
        cmd.append("--verbose")

    print(f"Sending test email to {to}...")
    # Use shlex.join to properly quote arguments with spaces
    result = c.run(shlex.join(cmd), warn=True)

    if result.ok:
        print(f"\n✓ Test email sent successfully to {to}")
    else:
        print(f"\n✗ Failed to send test email")
        print("\nCommon issues:")
        print("  - AWS credentials not configured")
        print("  - Sender email not verified in SES")
        print("  - Recipient email not verified (if in SES sandbox)")
        print("  - Wrong AWS region")
        print("\nSee: src/putplace/scripts/README_send_ses_email.md")


@task
def verify_ses_email(c, email=None, region="eu-west-1"):
    """Verify an email address in Amazon SES.

    Sends a verification email to the specified address. You must click the
    verification link in the email to complete the process.

    Requirements:
        - AWS CLI installed (aws command available)
        - AWS credentials configured (environment, ~/.aws/credentials, or IAM role)

    Args:
        email: Email address to verify (required)
        region: AWS region for SES (default: eu-west-1)

    Examples:
        invoke verify-ses-email --email=user@example.com
        invoke verify-ses-email --email=user@example.com --region=us-east-1

    After running:
        1. Check the email inbox for verification link
        2. Click the link to complete verification
        3. Check status with: invoke check-ses-email --email=user@example.com
    """

    if not email:
        print("Error: --email argument is required")
        return 1

    print(f"Requesting verification for {email} in {region}...")
    result = c.run(
        f"aws ses verify-email-identity --email-address {email} --region {region}",
        warn=True
    )

    if result.ok:
        print(f"\n✓ Verification email sent to {email}")
        print(f"\nNext steps:")
        print(f"  1. Check inbox for {email}")
        print(f"  2. Click the verification link in the email")
        print(f"  3. Check status: invoke check-ses-email --email={email}")
    else:
        print(f"\n✗ Failed to request verification")
        print("\nCommon issues:")
        print("  - AWS CLI not installed")
        print("  - AWS credentials not configured")
        print("  - Invalid email address format")
        print("  - Insufficient IAM permissions (need ses:VerifyEmailIdentity)")


@task
def check_ses_email(c, email=None, region="eu-west-1"):
    """Check verification status of an email address in Amazon SES.

    Requirements:
        - AWS CLI installed (aws command available)
        - AWS credentials configured

    Args:
        email: Email address to check (required)
        region: AWS region for SES (default: eu-west-1)

    Examples:
        invoke check-ses-email --email=user@example.com
        invoke check-ses-email --email=user@example.com --region=us-east-1
    """

    if not email:
        print("Error: --email argument is required")
        return 1

    print(f"Checking verification status for {email} in {region}...")
    result = c.run(
        f"aws ses get-identity-verification-attributes --identities {email} --region {region}",
        warn=True
    )

    if not result.ok:
        print(f"\n✗ Failed to check verification status")
        print("\nCommon issues:")
        print("  - AWS CLI not installed")
        print("  - AWS credentials not configured")
        print("  - Insufficient IAM permissions")


@task
def list_ses_emails(c, region="eu-west-1"):
    """List all verified email identities in Amazon SES.

    Requirements:
        - AWS CLI installed (aws command available)
        - AWS credentials configured

    Args:
        region: AWS region for SES (default: eu-west-1)

    Examples:
        invoke list-ses-emails
        invoke list-ses-emails --region=us-east-1
    """

    print(f"Listing verified identities in {region}...")
    result = c.run(
        f"aws ses list-verified-email-addresses --region {region}",
        warn=True
    )

    if not result.ok:
        print(f"\n✗ Failed to list identities")
        print("\nCommon issues:")
        print("  - AWS CLI not installed")
        print("  - AWS credentials not configured")


@task
def configure_apprunner(c, region="eu-west-1", mongodb_url=None, non_interactive=False):
    """Configure PutPlace for AWS App Runner deployment.

    Creates AWS Secrets Manager secrets with MongoDB connection, admin user,
    and API configuration for App Runner deployment.

    Requirements:
        - AWS CLI installed and configured
        - MongoDB connection string (MongoDB Atlas recommended)
        - boto3 library installed

    Args:
        region: AWS region for deployment (default: eu-west-1)
        mongodb_url: MongoDB connection string (will prompt if not provided)
        non_interactive: Skip prompts and use defaults (default: False)

    Examples:
        # Interactive mode (recommended)
        invoke configure-apprunner

        # Non-interactive with MongoDB Atlas
        invoke configure-apprunner --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # Different region
        invoke configure-apprunner --region=us-east-1
    """
    import shlex

    cmd = [
        "uv", "run", "python", "-m",
        "putplace.scripts.putplace_configure",
        "--create-aws-secrets",
        "--aws-region", region
    ]

    if non_interactive:
        cmd.append("--non-interactive")

    if mongodb_url:
        cmd.append("--mongodb-url")
        cmd.append(mongodb_url)

    print(f"Configuring PutPlace for App Runner deployment in {region}...")
    print("This will create secrets in AWS Secrets Manager.\n")

    result = c.run(shlex.join(cmd), warn=True, pty=True)

    if result.ok:
        print(f"\n✓ Configuration complete!")
        print(f"\nNext steps:")
        print(f"  1. Review the secrets in AWS Secrets Manager console")
        print(f"  2. Deploy to App Runner: invoke deploy-apprunner --region={region}")
    else:
        print(f"\n✗ Configuration failed")
        print("\nCommon issues:")
        print("  - AWS credentials not configured")
        print("  - boto3 not installed (pip install boto3)")
        print("  - MongoDB connection string invalid")


@task
def setup_github_connection(c, region="eu-west-1"):
    """Check and guide setup of GitHub connection for App Runner.

    App Runner requires a GitHub connection to deploy from GitHub repositories.
    This task checks if a connection exists and provides setup instructions.

    Args:
        region: AWS region (default: eu-west-1)

    Examples:
        invoke setup-github-connection
        invoke setup-github-connection --region=us-east-1
    """
    import json

    print(f"Checking GitHub connections in {region}...\n")

    # List connections
    connections_cmd = f"aws apprunner list-connections --region {region}"
    result = c.run(connections_cmd, warn=True, hide=True)

    if not result.ok:
        print("✗ Failed to list connections")
        print("\nMake sure AWS CLI is configured and you have App Runner permissions.")
        return 1

    connections = json.loads(result.stdout)
    connection_list = connections.get('ConnectionSummaryList', [])

    if not connection_list:
        print("⚠️  No GitHub connections found")
    else:
        print(f"Found {len(connection_list)} connection(s):\n")
        for conn in connection_list:
            status = conn.get('Status', 'UNKNOWN')
            status_icon = '✓' if status == 'AVAILABLE' else '✗'
            print(f"{status_icon} {conn['ConnectionName']}")
            print(f"  Provider: {conn.get('ProviderType', 'Unknown')}")
            print(f"  Status: {status}")
            print(f"  ARN: {conn['ConnectionArn']}")
            print()

    # Check for available GitHub connection
    github_available = any(
        conn.get('ProviderType') == 'GITHUB' and conn.get('Status') == 'AVAILABLE'
        for conn in connection_list
    )

    if github_available:
        print("✓ GitHub connection is ready!")
        print(f"\nYou can now deploy with: invoke deploy-apprunner --region={region}")
    else:
        print("\n" + "="*60)
        print("GitHub Connection Setup Instructions")
        print("="*60)
        print("\nOption 1: AWS Console (Recommended)")
        print(f"1. Open: https://console.aws.amazon.com/apprunner/home?region={region}#/settings")
        print("2. Click the 'Source connections' tab")
        print("3. Click 'Add connection' button")
        print("4. Select 'GitHub' as the source code provider")
        print("5. Click 'Add connection'")
        print("6. Authorize AWS App Runner in GitHub")
        print("7. Give the connection a name (e.g., 'github-connection')")
        print("8. Click 'Connect'")
        print("\nOption 2: AWS CLI")
        print(f"aws apprunner create-connection \\")
        print(f"  --connection-name github-connection \\")
        print(f"  --provider-type GITHUB \\")
        print(f"  --region {region}")
        print("\nNote: You'll still need to complete GitHub authorization in the console.")
        print(f"\nAfter setup, verify with: invoke setup-github-connection --region={region}")


@task
def deploy_apprunner(
    c,
    service_name="putplace-api",
    region="eu-west-1",
    github_repo="https://github.com/jdrumgoole/putplace",
    github_branch="main",
    cpu="1 vCPU",
    memory="2 GB",
    auto_deploy=False
):
    """Deploy PutPlace to AWS App Runner.

    Creates or updates an App Runner service with manual deployment trigger.
    Requires AWS Secrets Manager secrets to be created first.

    Requirements:
        - AWS CLI installed and configured
        - Secrets created (run: invoke configure-apprunner first)
        - GitHub repository access (will prompt for connection)

    Args:
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)
        github_repo: GitHub repository URL (default: https://github.com/jdrumgoole/putplace)
        github_branch: Git branch to deploy (default: main)
        cpu: CPU allocation (default: 1 vCPU)
        memory: Memory allocation (default: 2 GB)
        auto_deploy: Enable automatic deployment on git push (default: False - manual only)

    Examples:
        # Deploy with defaults (uses jdrumgoole/putplace repo)
        invoke deploy-apprunner

        # Deploy with custom repository
        invoke deploy-apprunner --github-repo=https://github.com/user/putplace

        # Different instance size
        invoke deploy-apprunner --cpu="2 vCPU" --memory="4 GB"

        # Enable auto-deploy on commits
        invoke deploy-apprunner --auto-deploy

    Notes:
        - By default, deployment is MANUAL only (no auto-deploy on commits)
        - Use App Runner console or CLI to trigger deployments manually
        - Automatic deployments can be enabled with --auto-deploy flag
    """
    import json

    # Check for uncommitted changes
    print("Checking git status...")
    git_status = c.run("git status --porcelain", hide=True, warn=True)

    if git_status.ok and git_status.stdout.strip():
        print("\n⚠️  You have uncommitted changes!")
        print("\nUncommitted files:")
        for line in git_status.stdout.strip().split('\n'):
            print(f"  {line}")
        print("\nPlease commit or stash your changes before deploying:")
        print("  git add .")
        print("  git commit -m 'Your commit message'")
        print("  git push")
        print(f"\nThen run: invoke deploy-apprunner --region={region}")
        return 1

    # Check if local branch is up to date with remote
    print("Checking if local branch is up to date...")
    git_fetch = c.run("git fetch", hide=True, warn=True)
    if git_fetch.ok:
        git_status_remote = c.run(f"git status -uno", hide=True, warn=True)
        if git_status_remote.ok and "Your branch is behind" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is behind the remote!")
            print("\nPull the latest changes:")
            print("  git pull")
            print(f"\nThen run: invoke deploy-apprunner --region={region}")
            return 1
        elif git_status_remote.ok and "Your branch is ahead" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is ahead of the remote!")
            print("\nPush your changes:")
            print("  git push")
            print(f"\nThen run: invoke deploy-apprunner --region={region}")
            return 1

    print("✓ Git status clean and up to date\n")

    print(f"{'='*60}")
    print(f"Deploying PutPlace to AWS App Runner")
    print(f"{'='*60}")
    print(f"Service name: {service_name}")
    print(f"Region: {region}")
    print(f"Repository: {github_repo}")
    print(f"Branch: {github_branch}")
    print(f"Instance: {cpu}, {memory}")
    print(f"Auto-deploy: {'Enabled' if auto_deploy else 'Disabled (manual only)'}")
    print(f"{'='*60}\n")

    # Check for GitHub connection
    print("Checking GitHub connection...")
    connections_cmd = f"aws apprunner list-connections --region {region}"
    conn_result = c.run(connections_cmd, warn=True, hide=True)

    github_connection_arn = None
    if conn_result.ok:
        connections = json.loads(conn_result.stdout)
        for conn in connections.get('ConnectionSummaryList', []):
            if conn.get('ProviderType') == 'GITHUB' and conn.get('Status') == 'AVAILABLE':
                github_connection_arn = conn['ConnectionArn']
                print(f"✓ GitHub connection found: {conn['ConnectionName']}")
                print(f"  ARN: {github_connection_arn}")
                break

    if not github_connection_arn:
        print("\n⚠️  GitHub connection not configured!")
        print(f"\nRun this command for setup instructions:")
        print(f"  invoke setup-github-connection --region={region}")
        return 1

    # Check if service already exists
    print("\nChecking if service exists...")
    check_cmd = f"aws apprunner list-services --region {region}"
    check_result = c.run(check_cmd, warn=True, hide=True)

    service_exists = False
    if check_result.ok:
        import json
        services = json.loads(check_result.stdout)
        for svc in services.get('ServiceSummaryList', []):
            if svc['ServiceName'] == service_name:
                service_exists = True
                service_arn = svc['ServiceArn']
                print(f"✓ Service exists: {service_arn}")
                break

    if service_exists:
        print(f"\n⚠️  Service '{service_name}' already exists")
        print("To update the service, trigger a manual deployment:")
        print(f"  aws apprunner start-deployment --service-arn {service_arn} --region {region}")
        return 0

    # Create new service
    print("\nCreating App Runner service...")

    # Build code configuration values with secrets
    # First, get the actual secret ARNs with their random suffixes
    secrets_arns = {}
    for secret_name in ['putplace/mongodb', 'putplace/admin', 'putplace/aws-config']:
        describe_cmd = f"aws secretsmanager describe-secret --secret-id {secret_name} --region {region}"
        result = c.run(describe_cmd, hide=True, warn=True)
        if result.ok:
            secret_info = json.loads(result.stdout)
            secrets_arns[secret_name] = secret_info['ARN']

    # Format: {"ENV_VAR_NAME": "arn:aws:secretsmanager:region:account:secret:name-SUFFIX:json_key::"}
    runtime_env_secrets = {}
    # MongoDB secrets
    for key in ['MONGODB_URL', 'MONGODB_DATABASE', 'MONGODB_COLLECTION']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/mongodb']}:{key}::"
    # Admin secrets
    for key in ['PUTPLACE_ADMIN_USERNAME', 'PUTPLACE_ADMIN_EMAIL', 'PUTPLACE_ADMIN_PASSWORD']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/admin']}:{key}::"
    # AWS/API secrets
    for key in ['AWS_DEFAULT_REGION', 'API_TITLE', 'API_VERSION', 'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE']:
        runtime_env_secrets[key] = f"{secrets_arns['putplace/aws-config']}:{key}::"

    # Build source configuration with API-based configuration
    # Set PYTHONPATH as an environment variable to avoid shell quoting issues
    source_config = {
        "CodeRepository": {
            "RepositoryUrl": github_repo,
            "SourceCodeVersion": {
                "Type": "BRANCH",
                "Value": github_branch
            },
            "CodeConfiguration": {
                "ConfigurationSource": "API",
                "CodeConfigurationValues": {
                    "Runtime": "PYTHON_311",
                    "RuntimeEnvironmentSecrets": runtime_env_secrets,
                    "RuntimeEnvironmentVariables": {
                        "PYTHONPATH": "/app/packages"
                    },
                    "BuildCommand": "python3.11 -m pip install --target=/app/packages .[s3]",
                    "StartCommand": "python3.11 -m uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 2",
                    "Port": "8000"
                }
            }
        },
        "AuthenticationConfiguration": {
            "ConnectionArn": github_connection_arn
        },
        "AutoDeploymentsEnabled": auto_deploy
    }

    # Write source config to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(source_config, f)
        source_config_file = f.name

    try:
        # Get or create instance role ARN
        instance_role_arn = "arn:aws:iam::230950121080:role/AppRunnerPutPlaceInstanceRole"

        create_cmd = f"""aws apprunner create-service \\
            --service-name {service_name} \\
            --source-configuration file://{source_config_file} \\
            --instance-configuration Cpu="{cpu}",Memory="{memory}",InstanceRoleArn="{instance_role_arn}" \\
            --region {region}"""

        print("\nExecuting:")
        print(create_cmd)
        print()

        result = c.run(create_cmd, warn=True, hide=False)

        if result.ok:
            # Parse service ARN from response
            response = json.loads(result.stdout)
            service_arn = response['Service']['ServiceArn']
            service_url = response['Service'].get('ServiceUrl', 'Pending...')

            print(f"\n✓ App Runner service created successfully!")
            print(f"\nService: {service_name}")
            print(f"Region: {region}")
            print(f"Service ARN: {service_arn}")
            print(f"Service URL: https://{service_url}" if service_url != 'Pending...' else "Service URL: Pending...")

            # Monitor deployment status
            print(f"\nMonitoring deployment status...")
            print("This may take 5-10 minutes. Press Ctrl+C to stop monitoring (deployment will continue).\n")

            import time
            max_attempts = 60  # 10 minutes max
            attempt = 0

            while attempt < max_attempts:
                describe_cmd = f"aws apprunner describe-service --service-arn {service_arn} --region {region}"
                describe_result = c.run(describe_cmd, warn=True, hide=True)

                if describe_result.ok:
                    service_data = json.loads(describe_result.stdout)
                    status = service_data['Service']['Status']

                    if status == 'RUNNING':
                        service_url = service_data['Service']['ServiceUrl']
                        print(f"\n{'='*60}")
                        print(f"✓ Deployment successful!")
                        print(f"{'='*60}")
                        print(f"\nService Status: RUNNING")
                        print(f"Service URL: https://{service_url}")
                        print(f"\nTest endpoints:")
                        print(f"  Health: https://{service_url}/health")
                        print(f"  API Docs: https://{service_url}/docs")
                        print(f"\nNext steps:")
                        print(f"  1. Grant IAM role access to secrets:")
                        print(f"     Action: secretsmanager:GetSecretValue")
                        print(f"     Resource: arn:aws:secretsmanager:{region}:*:secret:putplace/*")
                        if not auto_deploy:
                            print(f"\n  2. Manual deployment mode enabled.")
                            print(f"     Trigger deployments with:")
                            print(f"     invoke trigger-apprunner-deploy --service-name={service_name}")
                        break
                    elif status in ['CREATE_FAILED', 'DELETE_FAILED']:
                        print(f"\n✗ Deployment failed with status: {status}")
                        print(f"\nCheck logs:")
                        print(f"  aws logs tail /aws/apprunner/{service_name}/service --follow --region {region}")
                        break
                    else:
                        # Show progress
                        print(f"[{attempt+1}/{max_attempts}] Status: {status}...", end='\r')
                        time.sleep(10)
                        attempt += 1
                else:
                    print(f"\n⚠️  Failed to check service status")
                    break

            if attempt >= max_attempts:
                print(f"\n⚠️  Deployment monitoring timed out after 10 minutes")
                print(f"The deployment is still in progress. Check status with:")
                print(f"  aws apprunner describe-service --service-arn {service_arn} --region {region}")
        else:
            print(f"\n✗ Failed to create service")
            print("\nCommon issues:")
            print("  - GitHub connection not configured (set up in AWS console)")
            print("  - Invalid repository URL")
            print("  - Insufficient IAM permissions")
            print("  - Service name already exists")

    finally:
        import os
        os.unlink(source_config_file)


@task
def trigger_apprunner_deploy(c, service_name="putplace-api", region="eu-west-1"):
    """Trigger a manual deployment for App Runner service.

    Use this to deploy code changes when auto-deploy is disabled.

    Args:
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)

    Examples:
        invoke trigger-apprunner-deploy
        invoke trigger-apprunner-deploy --service-name=my-service
    """
    import json

    # Check for uncommitted changes
    print("Checking git status...")
    git_status = c.run("git status --porcelain", hide=True, warn=True)

    if git_status.ok and git_status.stdout.strip():
        print("\n⚠️  You have uncommitted changes!")
        print("\nUncommitted files:")
        for line in git_status.stdout.strip().split('\n'):
            print(f"  {line}")
        print("\nPlease commit or stash your changes before deploying:")
        print("  git add .")
        print("  git commit -m 'Your commit message'")
        print("  git push")
        print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
        return 1

    # Check if local branch is up to date with remote
    print("Checking if local branch is up to date...")
    git_fetch = c.run("git fetch", hide=True, warn=True)
    if git_fetch.ok:
        git_status_remote = c.run(f"git status -uno", hide=True, warn=True)
        if git_status_remote.ok and "Your branch is behind" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is behind the remote!")
            print("\nPull the latest changes:")
            print("  git pull")
            print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
            return 1
        elif git_status_remote.ok and "Your branch is ahead" in git_status_remote.stdout:
            print("\n⚠️  Your local branch is ahead of the remote!")
            print("\nPush your changes:")
            print("  git push")
            print(f"\nThen run: invoke trigger-apprunner-deploy --service-name={service_name}")
            return 1

    print("✓ Git status clean and up to date\n")

    print(f"Triggering deployment for {service_name} in {region}...")

    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, hide=True, warn=True)

    if not result.ok:
        print("✗ Failed to list services")
        return 1

    import json
    services = json.loads(result.stdout)

    service_arn = None
    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break

    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        print(f"\nAvailable services:")
        for svc in services.get('ServiceSummaryList', []):
            print(f"  - {svc['ServiceName']}")
        return 1

    # Start deployment
    deploy_cmd = f"aws apprunner start-deployment --service-arn {service_arn} --region {region}"
    result = c.run(deploy_cmd, warn=True, hide=True)

    if result.ok:
        print(f"\n✓ Deployment triggered successfully")

        # Monitor deployment status
        print(f"\nMonitoring deployment status...")
        print("This may take 3-5 minutes. Press Ctrl+C to stop monitoring (deployment will continue).\n")

        import time
        import json
        max_attempts = 30  # 5 minutes max
        attempt = 0

        while attempt < max_attempts:
            describe_cmd = f"aws apprunner describe-service --service-arn {service_arn} --region {region}"
            describe_result = c.run(describe_cmd, warn=True, hide=True)

            if describe_result.ok:
                service_data = json.loads(describe_result.stdout)
                status = service_data['Service']['Status']

                if status == 'RUNNING':
                    service_url = service_data['Service']['ServiceUrl']
                    print(f"\n{'='*60}")
                    print(f"✓ Deployment successful!")
                    print(f"{'='*60}")
                    print(f"\nService Status: RUNNING")
                    print(f"Service URL: https://{service_url}")
                    print(f"\nTest endpoints:")
                    print(f"  Health: https://{service_url}/health")
                    print(f"  API Docs: https://{service_url}/docs")
                    break
                elif status in ['CREATE_FAILED', 'DELETE_FAILED', 'OPERATION_FAILED']:
                    print(f"\n✗ Deployment failed with status: {status}")
                    print(f"\nCheck logs:")
                    print(f"  aws logs tail /aws/apprunner/{service_name}/application --follow --region {region}")
                    break
                else:
                    # Show progress
                    print(f"[{attempt+1}/{max_attempts}] Status: {status}...", end='\r')
                    time.sleep(10)
                    attempt += 1
            else:
                print(f"\n⚠️  Failed to check service status")
                break

        if attempt >= max_attempts:
            print(f"\n⚠️  Deployment monitoring timed out after 5 minutes")
            print(f"The deployment is still in progress. Check status with:")
            print(f"  aws apprunner describe-service --service-arn {service_arn} --region {region}")
    else:
        print(f"\n✗ Failed to trigger deployment")


@task
def list_apprunner_secrets(c, region="eu-west-1", show_values=False):
    """List PutPlace secrets from AWS Secrets Manager.

    Args:
        region: AWS region (default: eu-west-1)
        show_values: Show actual secret values (default: False - only shows keys)

    Examples:
        invoke list-apprunner-secrets
        invoke list-apprunner-secrets --show-values
        invoke list-apprunner-secrets --region=us-east-1
    """
    import json

    secret_names = [
        'putplace/mongodb',
        'putplace/admin',
        'putplace/aws-config'
    ]

    print(f"Listing PutPlace secrets in {region}...\n")

    for secret_name in secret_names:
        # Check if secret exists
        describe_cmd = f"aws secretsmanager describe-secret --secret-id {secret_name} --region {region}"
        result = c.run(describe_cmd, warn=True, hide=True)

        if not result.ok:
            print(f"✗ {secret_name}: Not found")
            continue

        # Get secret metadata
        secret_info = json.loads(result.stdout)
        created_date = secret_info.get('CreatedDate', 'Unknown')
        last_changed = secret_info.get('LastChangedDate', 'Unknown')

        print(f"✓ {secret_name}")
        print(f"  Created: {created_date}")
        print(f"  Last Changed: {last_changed}")

        if show_values:
            # Get secret value
            get_cmd = f"aws secretsmanager get-secret-value --secret-id {secret_name} --region {region}"
            value_result = c.run(get_cmd, warn=True, hide=True)

            if value_result.ok:
                secret_data = json.loads(value_result.stdout)
                secret_string = json.loads(secret_data['SecretString'])

                print(f"  Values:")
                for key, value in secret_string.items():
                    # Mask passwords
                    if 'PASSWORD' in key.upper():
                        display_value = '*' * len(value) if value else '(empty)'
                    else:
                        display_value = value
                    print(f"    {key}: {display_value}")
            else:
                print(f"  Values: Unable to retrieve")
        else:
            # Get secret value to show keys only
            get_cmd = f"aws secretsmanager get-secret-value --secret-id {secret_name} --region {region}"
            value_result = c.run(get_cmd, warn=True, hide=True)

            if value_result.ok:
                secret_data = json.loads(value_result.stdout)
                secret_string = json.loads(secret_data['SecretString'])
                keys = list(secret_string.keys())
                print(f"  Keys: {', '.join(keys)}")
            else:
                print(f"  Keys: Unable to retrieve")

        print()

    print("Tip: Use --show-values to see actual secret values (passwords will be masked)")


@task
def delete_apprunner_secrets(c, region="eu-west-1", force=False):
    """Delete PutPlace secrets from AWS Secrets Manager.

    Args:
        region: AWS region (default: eu-west-1)
        force: Force delete without recovery period (default: False)

    Examples:
        invoke delete-apprunner-secrets
        invoke delete-apprunner-secrets --force
    """
    import shlex

    cmd = [
        "uv", "run", "python", "-m",
        "putplace.scripts.putplace_configure",
        "--delete-aws-secrets",
        "--aws-region", region
    ]

    if force:
        cmd.append("--force-delete")

    print(f"Deleting PutPlace secrets from {region}...")
    result = c.run(shlex.join(cmd), warn=True, pty=True)

    if not result.ok:
        print("\nTo delete secrets manually:")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/mongodb --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/admin --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/aws-config --region {region}")

@task
def configure_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Configure a custom domain for App Runner service.
    
    This will:
    1. Associate the custom domain with the App Runner service
    2. Provide DNS records to add to Route 53
    
    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)
    
    Examples:
        invoke configure-custom-domain --domain=app.putplace.org
    """
    import json
    
    print(f"\n{'='*60}")
    print(f"Configuring Custom Domain for App Runner")
    print(f"{'='*60}")
    print(f"Domain: {domain}")
    print(f"Service: {service_name}")
    print(f"Region: {region}")
    print(f"{'='*60}\n")
    
    # Get service ARN
    print("Finding App Runner service...")
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)
    
    if not result.ok:
        print("✗ Failed to list services")
        return 1
    
    services = json.loads(result.stdout)
    service_arn = None
    
    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break
    
    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1
    
    print(f"✓ Found service: {service_arn}\n")
    
    # Associate custom domain
    print(f"Associating custom domain '{domain}'...")
    associate_cmd = f"aws apprunner associate-custom-domain --service-arn {service_arn} --domain-name {domain} --region {region}"
    result = c.run(associate_cmd, warn=True, hide=False)
    
    if result.ok:
        response = json.loads(result.stdout)
        
        print(f"\n{'='*60}")
        print(f"✓ Custom domain association initiated!")
        print(f"{'='*60}\n")
        
        # Extract DNS records
        dns_target = response.get('DNSTarget', 'N/A')
        custom_domain = response.get('CustomDomain', {})
        cert_validation_records = custom_domain.get('CertificateValidationRecords', [])
        
        print(f"DNS Configuration Required:")
        print(f"{'='*60}\n")
        
        # CNAME record for the domain
        print(f"1. Add CNAME record for your domain:")
        print(f"   Type: CNAME")
        print(f"   Name: {domain}")
        print(f"   Value: {dns_target}")
        print(f"   TTL: 300 (or your preference)\n")
        
        # Certificate validation records
        if cert_validation_records:
            print(f"2. Add certificate validation records:")
            for i, record in enumerate(cert_validation_records, 1):
                print(f"\n   Record {i}:")
                print(f"   Type: {record.get('Type', 'CNAME')}")
                print(f"   Name: {record.get('Name', 'N/A')}")
                print(f"   Value: {record.get('Value', 'N/A')}")
                print(f"   Status: {record.get('Status', 'PENDING')}")
        
        print(f"\n{'='*60}")
        print(f"Route 53 Setup Commands:")
        print(f"{'='*60}\n")
        
        # Get hosted zone ID
        print("Finding Route 53 hosted zone for putplace.org...")
        zone_cmd = "aws route53 list-hosted-zones-by-name --dns-name putplace.org --max-items 1"
        zone_result = c.run(zone_cmd, warn=True, hide=True)
        
        if zone_result.ok:
            zones = json.loads(zone_result.stdout)
            hosted_zones = zones.get('HostedZones', [])
            
            if hosted_zones:
                zone_id = hosted_zones[0]['Id'].split('/')[-1]
                
                print(f"✓ Found hosted zone: {zone_id}\n")
                print(f"Run these commands to create DNS records:\n")
                
                # CNAME record for domain
                print(f"# 1. Create CNAME record for {domain}")
                print(f'cat > /tmp/change-batch-cname.json << EOF')
                print(f'{{')
                print(f'  "Changes": [{{')
                print(f'    "Action": "UPSERT",')
                print(f'    "ResourceRecordSet": {{')
                print(f'      "Name": "{domain}",')
                print(f'      "Type": "CNAME",')
                print(f'      "TTL": 300,')
                print(f'      "ResourceRecords": [{{')
                print(f'        "Value": "{dns_target}"')
                print(f'      }}]')
                print(f'    }}')
                print(f'  }}]')
                print(f'}}')
                print(f'EOF')
                print(f'\naws route53 change-resource-record-sets \\')
                print(f'  --hosted-zone-id {zone_id} \\')
                print(f'  --change-batch file:///tmp/change-batch-cname.json\n')
                
                # Certificate validation records
                if cert_validation_records:
                    for i, record in enumerate(cert_validation_records, 1):
                        print(f"# {i+1}. Create certificate validation record {i}")
                        print(f'cat > /tmp/change-batch-cert-{i}.json << EOF')
                        print(f'{{')
                        print(f'  "Changes": [{{')
                        print(f'    "Action": "UPSERT",')
                        print(f'    "ResourceRecordSet": {{')
                        print(f'      "Name": "{record.get("Name", "")}",')
                        print(f'      "Type": "{record.get("Type", "CNAME")}",')
                        print(f'      "TTL": 300,')
                        print(f'      "ResourceRecords": [{{')
                        print(f'        "Value": "{record.get("Value", "")}"')
                        print(f'      }}]')
                        print(f'    }}')
                        print(f'  }}]')
                        print(f'}}')
                        print(f'EOF')
                        print(f'\naws route53 change-resource-record-sets \\')
                        print(f'  --hosted-zone-id {zone_id} \\')
                        print(f'  --change-batch file:///tmp/change-batch-cert-{i}.json\n')
        
        print(f"{'='*60}")
        print(f"Next Steps:")
        print(f"{'='*60}")
        print(f"1. Create the DNS records shown above in Route 53")
        print(f"2. Wait for DNS propagation (5-10 minutes)")
        print(f"3. Wait for certificate validation (5-30 minutes)")
        print(f"4. Check domain status:")
        print(f"   invoke check-custom-domain --domain={domain}")
        print(f"\nOnce validated, your service will be available at:")
        print(f"  https://{domain}")
        
    else:
        print(f"\n✗ Failed to associate custom domain")
        print(f"\nCommon issues:")
        print(f"  - Domain already associated with another service")
        print(f"  - Invalid domain name format")
        print(f"  - Service not in RUNNING state")


@task
def check_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Check status of custom domain configuration.
    
    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)
    
    Examples:
        invoke check-custom-domain --domain=app.putplace.org
    """
    import json
    
    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)
    
    if not result.ok:
        print("✗ Failed to list services")
        return 1
    
    services = json.loads(result.stdout)
    service_arn = None
    
    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break
    
    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1
    
    # Describe custom domain
    describe_cmd = f"aws apprunner describe-custom-domains --service-arn {service_arn} --region {region}"
    result = c.run(describe_cmd, warn=True, hide=True)
    
    if result.ok:
        response = json.loads(result.stdout)
        custom_domains = response.get('CustomDomains', [])
        
        print(f"\n{'='*60}")
        print(f"Custom Domain Status")
        print(f"{'='*60}\n")
        
        domain_found = False
        for custom_domain in custom_domains:
            if custom_domain.get('DomainName') == domain:
                domain_found = True
                status = custom_domain.get('Status', 'UNKNOWN')
                
                print(f"Domain: {domain}")
                print(f"Status: {status}")
                print(f"DNS Target: {response.get('DNSTarget', 'N/A')}\n")
                
                # Certificate validation records
                cert_records = custom_domain.get('CertificateValidationRecords', [])
                if cert_records:
                    print(f"Certificate Validation Records:")
                    for record in cert_records:
                        print(f"  Name: {record.get('Name', 'N/A')}")
                        print(f"  Status: {record.get('Status', 'PENDING')}")
                        print()
                
                if status == 'active':
                    print(f"✓ Domain is active and ready!")
                    print(f"\nYour service is available at:")
                    print(f"  https://{domain}")
                elif status == 'pending_certificate_dns_validation':
                    print(f"⏳ Waiting for DNS validation...")
                    print(f"\nMake sure the DNS records are created in Route 53.")
                elif status == 'creating':
                    print(f"⏳ Domain configuration in progress...")
                else:
                    print(f"⚠️  Status: {status}")
                
                break
        
        if not domain_found:
            print(f"✗ Domain '{domain}' not found in service configuration")
            print(f"\nAssociated domains:")
            for custom_domain in custom_domains:
                print(f"  - {custom_domain.get('DomainName', 'N/A')}")
    else:
        print(f"✗ Failed to describe custom domains")


@task
def remove_custom_domain(c, domain, service_name="putplace-api", region="eu-west-1"):
    """Remove a custom domain from App Runner service.
    
    Args:
        domain: Custom domain name (e.g., app.putplace.org)
        service_name: App Runner service name (default: putplace-api)
        region: AWS region (default: eu-west-1)
    
    Examples:
        invoke remove-custom-domain --domain=app.putplace.org
    """
    import json
    
    # Get service ARN
    list_cmd = f"aws apprunner list-services --region {region}"
    result = c.run(list_cmd, warn=True, hide=True)
    
    if not result.ok:
        print("✗ Failed to list services")
        return 1
    
    services = json.loads(result.stdout)
    service_arn = None
    
    for svc in services.get('ServiceSummaryList', []):
        if svc['ServiceName'] == service_name:
            service_arn = svc['ServiceArn']
            break
    
    if not service_arn:
        print(f"✗ Service not found: {service_name}")
        return 1
    
    print(f"Removing custom domain '{domain}' from {service_name}...")
    
    disassociate_cmd = f"aws apprunner disassociate-custom-domain --service-arn {service_arn} --domain-name {domain} --region {region}"
    result = c.run(disassociate_cmd, warn=True, hide=False)
    
    if result.ok:
        print(f"\n✓ Custom domain removed successfully")
        print(f"\nDon't forget to remove the DNS records from Route 53 if no longer needed.")
    else:
        print(f"\n✗ Failed to remove custom domain")


@task
def setup_static_website(c, domain="putplace.org", region="us-east-1"):
    """Set up S3 + CloudFront static website hosting for putplace.org.

    This will:
    1. Create S3 bucket for static website hosting
    2. Configure bucket for public read access
    3. Create CloudFront distribution with SSL certificate
    4. Configure Route 53 DNS records

    Args:
        domain: Domain name (default: putplace.org)
        region: AWS region (default: us-east-1 for CloudFront)

    Examples:
        invoke setup-static-website
        invoke setup-static-website --domain=putplace.org
    """
    import json

    print(f"\n{'='*60}")
    print(f"Setting Up Static Website Hosting")
    print(f"{'='*60}")
    print(f"Domain: {domain}")
    print(f"Region: {region}")
    print(f"{'='*60}\n")

    bucket_name = domain  # Use domain as bucket name

    # Step 1: Create S3 bucket
    print(f"Step 1: Creating S3 bucket '{bucket_name}'...")
    create_bucket_cmd = f"aws s3api create-bucket --bucket {bucket_name} --region {region}"
    if region != "us-east-1":
        create_bucket_cmd += f" --create-bucket-configuration LocationConstraint={region}"

    result = c.run(create_bucket_cmd, warn=True, hide=True)
    if result.ok:
        print(f"✓ Bucket created: {bucket_name}")
    elif "BucketAlreadyOwnedByYou" in result.stderr:
        print(f"✓ Bucket already exists: {bucket_name}")
    else:
        print(f"✗ Failed to create bucket")
        print(result.stderr)
        return 1

    # Step 2: Configure bucket for static website hosting
    print(f"\nStep 2: Configuring static website hosting...")
    website_config = {
        "IndexDocument": {"Suffix": "index.html"},
        "ErrorDocument": {"Key": "error.html"}
    }

    config_file = "/tmp/website-config.json"
    with open(config_file, 'w') as f:
        json.dump(website_config, f)

    website_cmd = f"aws s3api put-bucket-website --bucket {bucket_name} --website-configuration file://{config_file}"
    result = c.run(website_cmd, warn=True, hide=True)
    if result.ok:
        print(f"✓ Website hosting configured")
    else:
        print(f"✗ Failed to configure website hosting")
        return 1

    # Step 3: Create bucket policy for public read access
    print(f"\nStep 3: Setting bucket policy for public read access...")
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*"
        }]
    }

    policy_file = "/tmp/bucket-policy.json"
    with open(policy_file, 'w') as f:
        json.dump(bucket_policy, f)

    # Disable block public access first
    public_access_cmd = f"aws s3api put-public-access-block --bucket {bucket_name} --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
    c.run(public_access_cmd, warn=True, hide=True)

    policy_cmd = f"aws s3api put-bucket-policy --bucket {bucket_name} --policy file://{policy_file}"
    result = c.run(policy_cmd, warn=True, hide=True)
    if result.ok:
        print(f"✓ Bucket policy configured")
    else:
        print(f"✗ Failed to set bucket policy")
        return 1

    # Step 4: Request ACM certificate for CloudFront (must be in us-east-1)
    print(f"\nStep 4: Requesting SSL certificate in us-east-1...")
    cert_cmd = f"aws acm request-certificate --domain-name {domain} --subject-alternative-names www.{domain} --validation-method DNS --region us-east-1"
    result = c.run(cert_cmd, warn=True, hide=True)

    if result.ok:
        cert_response = json.loads(result.stdout)
        cert_arn = cert_response.get('CertificateArn')
        print(f"✓ Certificate requested: {cert_arn}")

        # Get certificate validation records
        print(f"\nWaiting for certificate details...")
        import time
        time.sleep(5)  # Wait for certificate to be created

        describe_cert_cmd = f"aws acm describe-certificate --certificate-arn {cert_arn} --region us-east-1"
        result = c.run(describe_cert_cmd, warn=True, hide=True)

        if result.ok:
            cert_details = json.loads(result.stdout)
            validation_options = cert_details.get('Certificate', {}).get('DomainValidationOptions', [])

            print(f"\n{'='*60}")
            print(f"Certificate Validation Required")
            print(f"{'='*60}\n")

            # Get Route 53 hosted zone
            zone_cmd = f"aws route53 list-hosted-zones-by-name --dns-name {domain} --max-items 1"
            zone_result = c.run(zone_cmd, warn=True, hide=True)

            if zone_result.ok:
                zones = json.loads(zone_result.stdout)
                hosted_zones = zones.get('HostedZones', [])

                if hosted_zones:
                    zone_id = hosted_zones[0]['Id'].split('/')[-1]
                    print(f"Found Route 53 hosted zone: {zone_id}\n")

                    # Create validation records
                    changes = []
                    for option in validation_options:
                        if 'ResourceRecord' in option:
                            record = option['ResourceRecord']
                            changes.append({
                                "Action": "UPSERT",
                                "ResourceRecordSet": {
                                    "Name": record['Name'],
                                    "Type": record['Type'],
                                    "TTL": 300,
                                    "ResourceRecords": [{"Value": record['Value']}]
                                }
                            })

                    if changes:
                        change_batch_file = "/tmp/cert-validation-changes.json"
                        with open(change_batch_file, 'w') as f:
                            json.dump({"Changes": changes}, f)

                        route53_cmd = f"aws route53 change-resource-record-sets --hosted-zone-id {zone_id} --change-batch file://{change_batch_file}"
                        result = c.run(route53_cmd, warn=True, hide=True)

                        if result.ok:
                            print(f"✓ Certificate validation records created in Route 53")
                            print(f"\nWaiting for certificate validation (this may take 5-30 minutes)...")
                            print(f"\nYou can continue with the next steps. The certificate will be validated automatically.")
                            print(f"\nTo check certificate status:")
                            print(f"  aws acm describe-certificate --certificate-arn {cert_arn} --region us-east-1")
                        else:
                            print(f"✗ Failed to create validation records")

                    # Save certificate ARN for CloudFront setup
                    with open("/tmp/putplace-cert-arn.txt", 'w') as f:
                        f.write(cert_arn)

                    print(f"\n{'='*60}")
                    print(f"Next Steps")
                    print(f"{'='*60}")
                    print(f"1. Wait for certificate validation (~10-15 minutes)")
                    print(f"2. Run: invoke create-cloudfront-distribution")
                    print(f"3. Upload website content to S3: invoke deploy-website")
                    print(f"\nCertificate ARN saved to /tmp/putplace-cert-arn.txt")
    else:
        print(f"✗ Failed to request certificate")
        print(result.stderr)


@task
def create_cloudfront_distribution(c, domain="putplace.org", cert_arn=None):
    """Create CloudFront distribution for static website.

    Args:
        domain: Domain name (default: putplace.org)
        cert_arn: ACM certificate ARN (reads from /tmp/putplace-cert-arn.txt if not provided)

    Examples:
        invoke create-cloudfront-distribution
        invoke create-cloudfront-distribution --cert-arn=arn:aws:acm:...
    """
    import json
    import time

    # Get certificate ARN
    if not cert_arn:
        try:
            with open("/tmp/putplace-cert-arn.txt", 'r') as f:
                cert_arn = f.read().strip()
        except FileNotFoundError:
            print("✗ Certificate ARN not found. Run setup-static-website first.")
            return 1

    # Verify certificate is validated
    print(f"Checking certificate status...")
    describe_cmd = f"aws acm describe-certificate --certificate-arn {cert_arn} --region us-east-1"
    result = c.run(describe_cmd, warn=True, hide=True)

    if result.ok:
        cert_details = json.loads(result.stdout)
        cert_status = cert_details.get('Certificate', {}).get('Status')

        if cert_status != 'ISSUED':
            print(f"⏳ Certificate status: {cert_status}")
            print(f"Please wait for certificate validation to complete.")
            print(f"Current status must be 'ISSUED' to proceed.")
            return 1

        print(f"✓ Certificate validated and issued")

    bucket_name = domain

    print(f"\n{'='*60}")
    print(f"Creating CloudFront Distribution")
    print(f"{'='*60}")
    print(f"Domain: {domain}")
    print(f"S3 Bucket: {bucket_name}")
    print(f"{'='*60}\n")

    # Create CloudFront distribution configuration
    distribution_config = {
        "CallerReference": f"putplace-{int(time.time())}",
        "Comment": f"Static website for {domain}",
        "Enabled": True,
        "Origins": {
            "Quantity": 1,
            "Items": [{
                "Id": f"S3-{bucket_name}",
                "DomainName": f"{bucket_name}.s3-website-us-east-1.amazonaws.com",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only"
                }
            }]
        },
        "DefaultRootObject": "index.html",
        "DefaultCacheBehavior": {
            "TargetOriginId": f"S3-{bucket_name}",
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {
                "Quantity": 2,
                "Items": ["GET", "HEAD"],
                "CachedMethods": {
                    "Quantity": 2,
                    "Items": ["GET", "HEAD"]
                }
            },
            "ForwardedValues": {
                "QueryString": False,
                "Cookies": {"Forward": "none"}
            },
            "MinTTL": 0,
            "DefaultTTL": 86400,
            "MaxTTL": 31536000,
            "Compress": True
        },
        "Aliases": {
            "Quantity": 2,
            "Items": [domain, f"www.{domain}"]
        },
        "ViewerCertificate": {
            "ACMCertificateArn": cert_arn,
            "SSLSupportMethod": "sni-only",
            "MinimumProtocolVersion": "TLSv1.2_2021"
        }
    }

    config_file = "/tmp/cloudfront-config.json"
    with open(config_file, 'w') as f:
        json.dump(distribution_config, f, indent=2)

    create_cmd = f"aws cloudfront create-distribution --distribution-config file://{config_file}"
    result = c.run(create_cmd, warn=True, hide=True)

    if result.ok:
        distribution = json.loads(result.stdout)
        dist_id = distribution.get('Distribution', {}).get('Id')
        dist_domain = distribution.get('Distribution', {}).get('DomainName')

        print(f"✓ CloudFront distribution created")
        print(f"\nDistribution ID: {dist_id}")
        print(f"CloudFront Domain: {dist_domain}")

        # Save distribution ID
        with open("/tmp/putplace-cloudfront-id.txt", 'w') as f:
            f.write(dist_id)

        print(f"\n{'='*60}")
        print(f"Configuring Route 53 DNS")
        print(f"{'='*60}\n")

        # Get hosted zone
        zone_cmd = f"aws route53 list-hosted-zones-by-name --dns-name {domain} --max-items 1"
        zone_result = c.run(zone_cmd, warn=True, hide=True)

        if zone_result.ok:
            zones = json.loads(zone_result.stdout)
            hosted_zones = zones.get('HostedZones', [])

            if hosted_zones:
                zone_id = hosted_zones[0]['Id'].split('/')[-1]

                # Create A records for domain and www subdomain
                changes = [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": domain,
                            "Type": "A",
                            "AliasTarget": {
                                "HostedZoneId": "Z2FDTNDATAQYW2",  # CloudFront hosted zone ID
                                "DNSName": dist_domain,
                                "EvaluateTargetHealth": False
                            }
                        }
                    },
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": f"www.{domain}",
                            "Type": "A",
                            "AliasTarget": {
                                "HostedZoneId": "Z2FDTNDATAQYW2",
                                "DNSName": dist_domain,
                                "EvaluateTargetHealth": False
                            }
                        }
                    }
                ]

                change_batch_file = "/tmp/route53-cloudfront-changes.json"
                with open(change_batch_file, 'w') as f:
                    json.dump({"Changes": changes}, f)

                route53_cmd = f"aws route53 change-resource-record-sets --hosted-zone-id {zone_id} --change-batch file://{change_batch_file}"
                result = c.run(route53_cmd, warn=True, hide=True)

                if result.ok:
                    print(f"✓ Route 53 DNS records created")
                    print(f"\n{'='*60}")
                    print(f"Setup Complete!")
                    print(f"{'='*60}")
                    print(f"\nYour static website is being deployed...")
                    print(f"\nCloudFront distribution is being created (15-20 minutes)")
                    print(f"Once ready, your site will be available at:")
                    print(f"  - https://{domain}")
                    print(f"  - https://www.{domain}")
                    print(f"\nNext step: Upload website content")
                    print(f"  invoke deploy-website")
    else:
        print(f"✗ Failed to create CloudFront distribution")
        print(result.stderr)


@task
def deploy_website(c, source_dir="website", bucket=None):
    """Deploy website content to S3 bucket.

    Args:
        source_dir: Directory containing website files (default: website)
        bucket: S3 bucket name (default: putplace.org)

    Examples:
        invoke deploy-website
        invoke deploy-website --source-dir=docs/_build/html
    """
    if not bucket:
        bucket = "putplace.org"

    print(f"\n{'='*60}")
    print(f"Deploying Website to S3")
    print(f"{'='*60}")
    print(f"Source: {source_dir}")
    print(f"Bucket: s3://{bucket}")
    print(f"{'='*60}\n")

    # Check if source directory exists
    import os
    if not os.path.exists(source_dir):
        print(f"✗ Source directory not found: {source_dir}")
        print(f"\nPlease create the website content first or use the default 'website/' directory.")
        return 1

    # Upload to S3
    print(f"\nUploading files to S3...")
    sync_cmd = f"aws s3 sync {source_dir}/ s3://{bucket}/ --delete --cache-control 'max-age=300'"
    result = c.run(sync_cmd, warn=True)

    if result.ok:
        print(f"\n✓ Website deployed successfully")

        # Invalidate CloudFront cache
        print(f"\nInvalidating CloudFront cache...")

        # Try to get distribution ID from file first, then query CloudFront
        dist_id = None
        try:
            with open("/tmp/putplace-cloudfront-id.txt", 'r') as f:
                dist_id = f.read().strip()
        except FileNotFoundError:
            # Query CloudFront for distribution serving this domain
            query_cmd = f"aws cloudfront list-distributions --query \"DistributionList.Items[?Aliases.Items[0]=='{bucket}'].Id | [0]\" --output text"
            query_result = c.run(query_cmd, warn=True, hide=True)
            if query_result.ok and query_result.stdout.strip():
                dist_id = query_result.stdout.strip()

        if dist_id and dist_id != "None":
            invalidate_cmd = f"aws cloudfront create-invalidation --distribution-id {dist_id} --paths '/*'"
            result = c.run(invalidate_cmd, warn=True, hide=True)

            if result.ok:
                print(f"✓ CloudFront cache invalidated (Distribution: {dist_id})")
            else:
                print(f"⚠ Failed to invalidate cache")
        else:
            print(f"⚠ CloudFront distribution not found for {bucket}. Cache not invalidated.")

        print(f"\n{'='*60}")
        print(f"Website URL: https://putplace.org")
        print(f"{'='*60}")
    else:
        print(f"\n✗ Failed to deploy website")


@task
def toggle_registration(c, action):
    """Toggle user registration on AWS App Runner.

    Args:
        action: "enable" or "disable"

    Environment Variables:
        APPRUNNER_SERVICE_ARN: ARN of the App Runner service (required)

    Examples:
        invoke toggle-registration --action=disable
        invoke toggle-registration --action=enable

    Setup:
        export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:region:account:service/putplace/xxx"
    """
    import sys
    import os

    # Validate action
    if action not in ["enable", "disable"]:
        print(f"❌ Error: Action must be 'enable' or 'disable', got '{action}'")
        print()
        print("Usage:")
        print("  invoke toggle-registration --action=enable")
        print("  invoke toggle-registration --action=disable")
        sys.exit(1)

    # Check for service ARN
    if not os.environ.get("APPRUNNER_SERVICE_ARN"):
        print("❌ Error: APPRUNNER_SERVICE_ARN environment variable not set")
        print()
        print("Set it with:")
        print('  export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:region:account:service/putplace/xxx"')
        print()
        print("Or find it with:")
        print("  aws apprunner list-services --query 'ServiceSummaryList[?ServiceName==`putplace`].ServiceArn' --output text")
        sys.exit(1)

    # Run the Python script
    c.run(f"uv run python -m putplace.scripts.toggle_registration {action}")


@task
def atlas_clusters(c):
    """List all MongoDB Atlas clusters.

    Requires Atlas API credentials in environment or ~/.atlas/credentials file.

    Examples:
        invoke atlas-clusters
    """
    c.run("uv run python -m putplace.scripts.atlas_cluster_control list")


@task
def atlas_status(c, cluster):
    """Get status of a MongoDB Atlas cluster.

    Args:
        cluster: Cluster name

    Examples:
        invoke atlas-status --cluster=testcluster
    """
    c.run(f"uv run python -m putplace.scripts.atlas_cluster_control status --cluster {cluster}")


@task
def atlas_pause(c, cluster):
    """Pause a MongoDB Atlas cluster to save costs.

    Paused clusters cost ~10% of running cost (storage only).
    Great for dev/test environments.

    Args:
        cluster: Cluster name

    Examples:
        invoke atlas-pause --cluster=testcluster
    """
    c.run(f"uv run python -m putplace.scripts.atlas_cluster_control pause --cluster {cluster}")


@task
def setup_aws_iam(c, region="eu-west-1", skip_buckets=False):
    """Setup AWS IAM users for dev, test, and prod environments.

    Creates three IAM users with S3 and SES access:
    - putplace-dev (access to putplace-dev bucket)
    - putplace-test (access to putplace-test bucket)
    - putplace-prod (access to putplace-prod bucket)

    Args:
        region: AWS region (default: eu-west-1)
        skip_buckets: Skip S3 bucket creation if they already exist

    Examples:
        # Create all resources (users, policies, buckets, keys)
        invoke setup-aws-iam

        # Use different region
        invoke setup-aws-iam --region=us-east-1

        # Skip bucket creation (if buckets already exist)
        invoke setup-aws-iam --skip-buckets

    Output:
        Creates aws_credentials_output/ directory with:
        - .env.dev, .env.test, .env.prod (environment files)
        - aws_credentials (AWS credentials file format)
        - aws_config (AWS config file format)
        - setup_summary.json (summary of created resources)

    Prerequisites:
        - AWS CLI configured with admin permissions
        - boto3 installed (pip install boto3)
    """
    cmd = f"uv run python -m putplace.scripts.setup_aws_iam_users --region {region}"
    if skip_buckets:
        cmd += " --skip-buckets"
    c.run(cmd)


@task
def configure(
    c,
    envtype=None,
    mongodb_url="mongodb://localhost:27017",
    storage_backend="local",
    s3_bucket=None,
    aws_region="eu-west-1",
    admin_username="admin",
    admin_email="admin@example.com",
    config_file="ppserver.toml",
    setup_iam=False,
    skip_buckets=False,
):
    """Generate ppserver.toml configuration file with environment-specific settings.

    Optionally creates AWS IAM users, policies, and S3 buckets in one command.

    Args:
        envtype: Environment type (dev, test, prod) - applies environment-specific defaults
        mongodb_url: MongoDB connection string
        storage_backend: Storage backend ('local' or 's3')
        s3_bucket: S3 bucket name (required for s3 backend, auto-suffixed with -envtype)
        aws_region: AWS region
        admin_username: Admin username
        admin_email: Admin email
        config_file: Output configuration file path
        setup_iam: Create AWS IAM users, policies, and S3 buckets
        skip_buckets: Skip S3 bucket creation (use with --setup-iam if buckets exist)

    Examples:
        # ONE COMMAND SETUP: Create IAM users AND generate config for prod
        invoke configure --envtype=prod --setup-iam \\
            --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/" \\
            --storage-backend=s3 \\
            --s3-bucket=putplace

        # This creates:
        # 1. IAM users (putplace-dev, putplace-test, putplace-prod)
        # 2. S3 buckets (putplace-dev, putplace-test, putplace-prod)
        # 3. Credentials in aws_credentials_output/
        # 4. ppserver.toml with prod configuration (uses putplace-prod bucket)
        #
        # Note: The bucket name "putplace" is automatically suffixed with "-prod"
        #       to create "putplace-prod" when --envtype=prod is specified

        # Just configure dev environment (IAM already set up)
        invoke configure --envtype=dev --storage-backend=s3 --s3-bucket=putplace
        # Creates config using putplace-dev bucket

        # Configure for test environment
        invoke configure --envtype=test --storage-backend=s3 --s3-bucket=putplace
        # Creates config using putplace-test bucket

        # Configure for prod with MongoDB Atlas and S3
        invoke configure --envtype=prod \\
            --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/" \\
            --storage-backend=s3 \\
            --s3-bucket=putplace
        # Creates config using putplace-prod bucket

        # Local storage (no S3, no envtype needed)
        invoke configure --storage-backend=local

    Workflow Option 1 (Recommended - One Command):
        invoke configure --envtype=prod --setup-iam \\
            --storage-backend=s3 --s3-bucket=putplace
        # Bucket becomes: putplace-prod

    Workflow Option 2 (Separate Steps):
        1. invoke setup-aws-iam  # Creates putplace-dev, putplace-test, putplace-prod buckets
        2. invoke configure --envtype=prod --storage-backend=s3 --s3-bucket=putplace
        # Bucket becomes: putplace-prod

    AWS Credentials:
        Credentials are NOT stored in ppserver.toml. They are saved in:
        - aws_credentials_output/.env.{envtype}
        - aws_credentials_output/aws_credentials (profile format)

        On the server, configure AWS credentials using:
        - AWS_PROFILE environment variable
        - ~/.aws/credentials file
        - IAM instance role (recommended for EC2/ECS)

    Output:
        Generates ppserver.toml with:
        - Environment-specific database name (e.g., putplace_prod)
        - Environment-specific S3 bucket (e.g., putplace-prod)
        - Instructions for AWS credential configuration
        - Admin user creation
    """
    cmd = f"putplace_configure --non-interactive --skip-checks"
    cmd += f" --mongodb-url='{mongodb_url}'"
    cmd += f" --mongodb-database=putplace"
    cmd += f" --admin-username={admin_username}"
    cmd += f" --admin-email={admin_email}"
    cmd += f" --storage-backend={storage_backend}"
    cmd += f" --config-file={config_file}"
    cmd += f" --aws-region={aws_region}"

    if envtype:
        cmd += f" --envtype={envtype}"

    if setup_iam:
        cmd += " --setup-iam"
        if skip_buckets:
            cmd += " --skip-buckets"

    if storage_backend == "s3":
        if not s3_bucket:
            print("❌ Error: --s3-bucket required when --storage-backend=s3")
            return
        cmd += f" --s3-bucket={s3_bucket}"

    c.run(cmd, pty=True)


@task
def configure_dev(c, mongodb_url):
    """Configure development environment with S3 storage (shortcut).

    Hardcoded settings for dev:
    - Environment: dev
    - Storage: S3 (putplace-dev bucket)
    - AWS Region: eu-west-1
    - Setup IAM: Yes (creates AWS resources)
    - Config file: ppserver-dev.toml

    Only requires MongoDB URL.

    Args:
        mongodb_url: MongoDB connection string (Atlas or other)

    Examples:
        # One command to set up everything for dev
        invoke configure-dev --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # This creates:
        # - IAM user: putplace-dev
        # - S3 bucket: putplace-dev
        # - Config: ppserver-dev.toml
        # - Credentials: aws_credentials_output/

    Then deploy with:
        invoke deploy-do-prod --config-file=ppserver-dev.toml --create
    """
    configure(
        c,
        envtype="dev",
        mongodb_url=mongodb_url,
        storage_backend="s3",
        s3_bucket="putplace",
        aws_region="eu-west-1",
        admin_username="admin",
        admin_email="admin@example.com",
        config_file="ppserver-dev.toml",
        setup_iam=True,
        skip_buckets=False,
    )


@task
def configure_test(c, mongodb_url):
    """Configure test environment with S3 storage (shortcut).

    Hardcoded settings for test:
    - Environment: test
    - Storage: S3 (putplace-test bucket)
    - AWS Region: eu-west-1
    - Setup IAM: Yes (creates AWS resources)
    - Config file: ppserver-test.toml

    Only requires MongoDB URL.

    Args:
        mongodb_url: MongoDB connection string (Atlas or other)

    Examples:
        # One command to set up everything for test
        invoke configure-test --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # This creates:
        # - IAM user: putplace-test
        # - S3 bucket: putplace-test
        # - Config: ppserver-test.toml
        # - Credentials: aws_credentials_output/

    Then deploy with:
        invoke deploy-do-prod --config-file=ppserver-test.toml --create
    """
    configure(
        c,
        envtype="test",
        mongodb_url=mongodb_url,
        storage_backend="s3",
        s3_bucket="putplace",
        aws_region="eu-west-1",
        admin_username="admin",
        admin_email="admin@example.com",
        config_file="ppserver-test.toml",
        setup_iam=True,
        skip_buckets=False,
    )


@task
def configure_prod(c, mongodb_url):
    """Configure production environment with S3 storage (shortcut).

    Hardcoded settings for prod:
    - Environment: prod
    - Storage: S3 (putplace-prod bucket)
    - AWS Region: eu-west-1
    - Setup IAM: Yes (creates AWS resources)
    - Config file: ppserver-prod.toml

    Only requires MongoDB URL.

    Args:
        mongodb_url: MongoDB connection string (Atlas or other)

    Examples:
        # One command to set up everything for production
        invoke configure-prod --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # This creates:
        # - IAM user: putplace-prod
        # - S3 bucket: putplace-prod
        # - Config: ppserver-prod.toml
        # - Credentials: aws_credentials_output/

    Then deploy with:
        invoke deploy-do-prod  # Reads ppserver-prod.toml automatically
        # Or:
        invoke deploy-do-prod --create
    """
    configure(
        c,
        envtype="prod",
        mongodb_url=mongodb_url,
        storage_backend="s3",
        s3_bucket="putplace",
        aws_region="eu-west-1",
        admin_username="admin",
        admin_email="admin@example.com",
        config_file="ppserver-prod.toml",
        setup_iam=True,
        skip_buckets=False,
    )


@task
def atlas_resume(c, cluster):
    """Resume a paused MongoDB Atlas cluster.

    Takes 5-10 minutes for cluster to be fully operational.

    Args:
        cluster: Cluster name

    Examples:
        invoke atlas-resume --cluster=testcluster
    """
    c.run(f"uv run python -m putplace.scripts.atlas_cluster_control resume --cluster {cluster}")


@task
def setup_apprunner_fixed_ip(c, region="eu-west-1", project_name="putplace"):
    """Setup fixed IP address for AppRunner instance (for MongoDB Atlas).

    Creates VPC infrastructure with NAT Gateway to provide a static Elastic IP
    for AppRunner egress traffic. This is required for MongoDB Atlas IP whitelisting.

    Args:
        region: AWS region (default: eu-west-1)
        project_name: Project name for resource tagging (default: putplace)

    Examples:
        invoke setup-apprunner-fixed-ip
        invoke setup-apprunner-fixed-ip --region=us-east-1
        invoke setup-apprunner-fixed-ip --region=eu-west-1 --project-name=myapp

    Cost: ~$32/month for NAT Gateway + data transfer costs

    See: APPRUNNER_FIXED_IP.md for detailed documentation
    """
    c.run(f"uv run python -m putplace.scripts.setup_apprunner_fixed_ip --region {region} --project-name {project_name}")


@task
def update_apprunner_vpc(c, service, vpc_connector_arn, region="eu-west-1", wait=True):
    """Update AppRunner service to use VPC Connector for fixed IP.

    Args:
        service: AppRunner service name or ARN
        vpc_connector_arn: VPC Connector ARN to use
        region: AWS region (default: eu-west-1)
        wait: Wait for update to complete (default: True)

    Examples:
        invoke update-apprunner-vpc \\
            --service=putplace-service \\
            --vpc-connector-arn="arn:aws:apprunner:eu-west-1:xxx:vpcconnector/putplace-vpc-connector/1/xxx"

        invoke update-apprunner-vpc \\
            --service=putplace-service \\
            --vpc-connector-arn="arn:..." \\
            --region=us-east-1 \\
            --wait=False

    Prerequisites:
        Run setup-apprunner-fixed-ip first to create VPC Connector

    See: APPRUNNER_FIXED_IP.md for detailed documentation
    """
    wait_flag = "--wait" if wait else ""
    c.run(f"uv run python -m putplace.scripts.update_apprunner_vpc {service} --vpc-connector-arn '{vpc_connector_arn}' --region {region} {wait_flag}")


@task
def deploy_do(
    c,
    droplet_name="putplace-droplet",
    ip=None,
    create=False,
    region="fra1",
    size="s-1vcpu-1gb",
    domain=None,
    version="latest",
    mongodb_url="mongodb://localhost:27017",
    storage_backend="local",
    storage_path="/var/putplace/storage",
    s3_bucket=None,
    aws_region="eu-west-1",
    aws_credentials_dir="./aws_credentials_output",
    aws_profile=None,
):
    """Deploy PutPlace to Digital Ocean droplet from PyPI.

    By default, updates existing 'putplace-droplet' if it exists.
    Use --create to force new droplet creation.

    Installs PutPlace from PyPI and uses a locally-generated ppserver.toml
    configuration file. The configuration is generated based on the parameters
    you provide.

    Args:
        droplet_name: Name for the droplet (for lookup or creation)
        ip: Existing droplet IP address (skip creation)
        create: Create a new droplet (requires droplet_name)
        region: Digital Ocean region (default: fra1/Frankfurt)
        size: Droplet size (default: s-1vcpu-1gb, $6/month)
        domain: Domain name for nginx and SSL (optional)
        version: PutPlace version from PyPI (default: latest)
        mongodb_url: MongoDB connection string (default: mongodb://localhost:27017)
        storage_backend: Storage backend - 'local' or 's3' (default: local)
        storage_path: Path for local storage (default: /var/putplace/storage)
        s3_bucket: S3 bucket name (required if storage_backend=s3)
        aws_region: AWS region (default: eu-west-1)
        aws_credentials_dir: Directory with AWS credentials (default: ./aws_credentials_output)
        aws_profile: AWS profile name (e.g., putplace-prod)

    Examples:
        # FIRST TIME: Create new droplet with local storage
        invoke deploy-do --create

        # NORMAL USE: Deploy/update to existing droplet (default name)
        invoke deploy-do

        # Deploy with MongoDB Atlas and local storage
        invoke deploy-do --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

        # Deploy with MongoDB Atlas and S3 storage
        invoke deploy-do \\
            --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/" \\
            --storage-backend=s3 \\
            --s3-bucket=putplace-prod

        # Deploy with S3 and AWS credentials
        invoke deploy-do \\
            --storage-backend=s3 \\
            --s3-bucket=putplace-prod \\
            --aws-profile=putplace-prod \\
            --aws-credentials-dir=./aws_credentials_output

        # Deploy specific version
        invoke deploy-do --version=0.7.0

        # Deploy with domain
        invoke deploy-do --domain=api.example.com

        # Create with custom name
        invoke deploy-do --create --droplet-name=putplace-prod

    Prerequisites:
        - Digital Ocean API token in DIGITALOCEAN_TOKEN env var
        - SSH key added to Digital Ocean account
        - doctl CLI installed: brew install doctl
        - putplace installed locally: pip install putplace
        - For S3: AWS credentials configured (~/.aws/credentials or environment)

    Pricing:
        - Basic droplet (1GB RAM): $6/month
        - Droplet with MongoDB: $12/month recommended (2GB RAM)

    See: DIGITALOCEAN_DEPLOYMENT.md for detailed documentation
    """
    import sys

    # Check for doctl
    result = c.run("which doctl", warn=True, hide=True)
    if result.failed:
        print("❌ Error: doctl not found. Install with: brew install doctl")
        sys.exit(1)

    # Check for putplace_configure (needed to generate config)
    result = c.run("which putplace_configure", warn=True, hide=True)
    if result.failed:
        print("❌ Error: putplace not installed. Install with: pip install putplace")
        sys.exit(1)

    # Build command
    cmd = "uv run python -m putplace.scripts.deploy_digitalocean"

    if create:
        cmd += " --create-droplet"

    if droplet_name:
        cmd += f" --droplet-name={droplet_name}"

    if ip:
        cmd += f" --ip={ip}"

    if region != "fra1":
        cmd += f" --region={region}"

    if size != "s-1vcpu-1gb":
        cmd += f" --size={size}"

    if domain:
        cmd += f" --domain={domain}"

    if version != "latest":
        cmd += f" --version={version}"

    if mongodb_url != "mongodb://localhost:27017":
        cmd += f" --mongodb-url='{mongodb_url}'"

    if storage_backend != "local":
        cmd += f" --storage-backend={storage_backend}"

    if storage_path != "/var/putplace/storage":
        cmd += f" --storage-path={storage_path}"

    if s3_bucket:
        cmd += f" --s3-bucket={s3_bucket}"

    if aws_region != "eu-west-1":
        cmd += f" --aws-region={aws_region}"

    if aws_credentials_dir != "./aws_credentials_output":
        cmd += f" --aws-credentials-dir={aws_credentials_dir}"

    if aws_profile:
        cmd += f" --aws-profile={aws_profile}"

    c.run(cmd, pty=True)


def _deploy_with_config(
    c,
    config_file,
    create=False,
    domain=None,
    version="latest",
    droplet_name=None,
):
    """Internal helper to deploy using a config file.

    This is used by deploy-do-dev, deploy-do-test, and deploy-do-prod shortcuts.
    """
    import sys
    import tomllib
    from pathlib import Path

    # Read TOML config file
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"❌ Error: Config file not found: {config_file}")
        print(f"\nGenerate it with:")
        envtype = "prod" if "prod" in config_file else "dev" if "dev" in config_file else "test"
        print(f"  invoke configure-{envtype} --mongodb-url='mongodb+srv://...'")
        sys.exit(1)

    print(f"→ Reading configuration from: {config_file}")
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Extract configuration values
    mongodb_url = config.get("mongodb", {}).get("url", "mongodb://localhost:27017")
    storage_backend = config.get("storage", {}).get("backend", "local")
    s3_bucket = config.get("storage", {}).get("s3_bucket")
    aws_region = config.get("aws", {}).get("region", "eu-west-1")

    # Infer environment from filename (ppserver-prod.toml -> prod)
    if droplet_name is None:
        if "prod" in config_file:
            envtype = "prod"
        elif "dev" in config_file:
            envtype = "dev"
        elif "test" in config_file:
            envtype = "test"
        else:
            envtype = "prod"  # default
        droplet_name = f"putplace-{envtype}"

    # Infer AWS profile from droplet name
    aws_profile = droplet_name  # putplace-prod -> putplace-prod profile

    print(f"✓ Configuration loaded:")
    print(f"  Droplet: {droplet_name}")
    print(f"  MongoDB: {mongodb_url.split('@')[1] if '@' in mongodb_url else 'localhost'}")
    print(f"  Storage: {storage_backend}")
    if storage_backend == "s3":
        print(f"  S3 Bucket: {s3_bucket}")
        print(f"  AWS Profile: {aws_profile}")
    print()

    # Validate required settings for S3
    if storage_backend == "s3" and not s3_bucket:
        print(f"❌ Error: S3 backend specified but no s3_bucket in config")
        sys.exit(1)

    deploy_do(
        c,
        droplet_name=droplet_name,
        create=create,
        domain=domain,
        version=version,
        mongodb_url=mongodb_url,
        storage_backend=storage_backend,
        s3_bucket=s3_bucket,
        aws_region=aws_region,
        aws_credentials_dir="./aws_credentials_output",
        aws_profile=aws_profile,
    )


@task
def deploy_do_dev(c, create=False, domain=None, version="latest"):
    """Deploy to development environment (reads ppserver-dev.toml).

    Shortcut for deploying to dev with all config from ppserver-dev.toml.

    Args:
        create: Create new droplet (default: False)
        domain: Optional domain name for SSL
        version: PutPlace version from PyPI (default: latest)

    Examples:
        # Deploy to existing dev droplet
        invoke deploy-do-dev

        # Create new dev droplet
        invoke deploy-do-dev --create

        # With domain
        invoke deploy-do-dev --create --domain=dev.example.com

    Prerequisites:
        - Run: invoke configure-dev --mongodb-url="..."
        - This creates: ppserver-dev.toml and AWS resources
    """
    _deploy_with_config(c, "ppserver-dev.toml", create, domain, version)


@task
def deploy_do_test(c, create=False, domain=None, version="latest"):
    """Deploy to test environment (reads ppserver-test.toml).

    Shortcut for deploying to test with all config from ppserver-test.toml.

    Args:
        create: Create new droplet (default: False)
        domain: Optional domain name for SSL
        version: PutPlace version from PyPI (default: latest)

    Examples:
        # Deploy to existing test droplet
        invoke deploy-do-test

        # Create new test droplet
        invoke deploy-do-test --create

        # With domain
        invoke deploy-do-test --create --domain=test.example.com

    Prerequisites:
        - Run: invoke configure-test --mongodb-url="..."
        - This creates: ppserver-test.toml and AWS resources
    """
    _deploy_with_config(c, "ppserver-test.toml", create, domain, version)


@task
def deploy_do_prod(c, create=False, domain=None, version="latest"):
    """Deploy to production environment (reads ppserver-prod.toml).

    Shortcut for deploying to prod with all config from ppserver-prod.toml.

    Args:
        create: Create new droplet (default: False)
        domain: Optional domain name for SSL
        version: PutPlace version from PyPI (default: latest)

    Examples:
        # Deploy to existing prod droplet
        invoke deploy-do-prod

        # Create new prod droplet
        invoke deploy-do-prod --create

        # With domain
        invoke deploy-do-prod --create --domain=api.example.com

    Prerequisites:
        - Run: invoke configure-prod --mongodb-url="..."
        - This creates: ppserver-prod.toml and AWS resources
    """
    _deploy_with_config(c, "ppserver-prod.toml", create, domain, version)


@task
def deploy(c, version="latest"):
    """Quick deploy to existing putplace-droplet (most common usage).

    This is a shortcut for: invoke deploy-do --droplet-name=putplace-droplet

    Args:
        version: PutPlace version from PyPI (default: latest)

    Examples:
        # Deploy latest version to existing droplet
        invoke deploy

        # Deploy specific version
        invoke deploy --version=0.7.0

    First time setup:
        invoke deploy-do --create
    """
    deploy_do(c, droplet_name="putplace-droplet", version=version)


@task
def update_do(c, droplet_name=None, ip=None, branch="main"):
    """Quick update of PutPlace code on Digital Ocean droplet.

    Pulls latest code and restarts service. Much faster than full deployment.
    Use this for regular updates after initial deployment.

    Args:
        droplet_name: Droplet name (will lookup IP)
        ip: Droplet IP address
        branch: Git branch to deploy (default: main)

    Examples:
        # Update by droplet name (default)
        invoke update-do --droplet-name=putplace-droplet

        # Update by IP
        invoke update-do --ip=165.22.xxx.xxx

        # Update with specific branch
        invoke update-do --ip=165.22.xxx.xxx --branch=develop

    See: DIGITALOCEAN_DEPLOYMENT.md for detailed documentation
    """
    import sys

    if not droplet_name and not ip:
        print("❌ Error: Must provide either --droplet-name or --ip")
        sys.exit(1)

    cmd = "uv run python -m putplace.scripts.update_deployment"

    if droplet_name:
        cmd += f" --droplet-name={droplet_name}"
    elif ip:
        cmd += f" --ip={ip}"

    if branch != "main":
        cmd += f" --branch={branch}"

    c.run(cmd, pty=True)


@task
def ssh_do(c, droplet_name=None, ip=None):
    """SSH into Digital Ocean droplet.

    Args:
        droplet_name: Droplet name (will lookup IP)
        ip: Droplet IP address

    Examples:
        invoke ssh-do --droplet-name=putplace-droplet
        invoke ssh-do --ip=165.22.xxx.xxx
    """
    import sys

    if not droplet_name and not ip:
        print("❌ Error: Must provide either --droplet-name or --ip")
        sys.exit(1)

    if droplet_name:
        # Look up IP using doctl
        result = c.run(
            f"doctl compute droplet list --format Name,PublicIPv4 --no-header | grep '^{droplet_name}' | awk '{{print $NF}}'",
            hide=True,
        )
        ip = result.stdout.strip()
        if not ip:
            print(f"❌ Error: Could not find IP for droplet: {droplet_name}")
            sys.exit(1)
        print(f"Connecting to {droplet_name} ({ip})...")

    c.run(f"ssh -o StrictHostKeyChecking=no root@{ip}", pty=True)


@task
def logs_do(c, droplet_name=None, ip=None, follow=False, error=False):
    """View PutPlace logs on Digital Ocean droplet.

    Args:
        droplet_name: Droplet name (will lookup IP)
        ip: Droplet IP address
        follow: Follow log output (tail -f)
        error: Show error log instead of access log

    Examples:
        # View access logs
        invoke logs-do --droplet-name=putplace-droplet

        # Follow error logs
        invoke logs-do --ip=165.22.xxx.xxx --error --follow

        # View last 50 lines of access log
        invoke logs-do --ip=165.22.xxx.xxx
    """
    import sys

    if not droplet_name and not ip:
        print("❌ Error: Must provide either --droplet-name or --ip")
        sys.exit(1)

    if droplet_name:
        result = c.run(
            f"doctl compute droplet list --format Name,PublicIPv4 --no-header | grep '^{droplet_name}' | awk '{{print $NF}}'",
            hide=True,
        )
        ip = result.stdout.strip()
        if not ip:
            print(f"❌ Error: Could not find IP for droplet: {droplet_name}")
            sys.exit(1)

    log_file = "/var/log/putplace/error.log" if error else "/var/log/putplace/access.log"
    tail_cmd = "tail -f" if follow else "tail -50"

    c.run(
        f"ssh -o StrictHostKeyChecking=no root@{ip} '{tail_cmd} {log_file}'",
        pty=True,
    )
