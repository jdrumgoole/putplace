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

    result = c.run(shlex.join(cmd), warn=True)

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
def deploy_apprunner(
    c,
    service_name="putplace-api",
    region="eu-west-1",
    github_repo=None,
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
        github_repo: GitHub repository URL (e.g., https://github.com/user/repo)
        github_branch: Git branch to deploy (default: main)
        cpu: CPU allocation (default: 1 vCPU)
        memory: Memory allocation (default: 2 GB)
        auto_deploy: Enable automatic deployment on git push (default: False - manual only)

    Examples:
        # Deploy with manual trigger (recommended)
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

    if not github_repo:
        github_repo = input("GitHub repository URL: ").strip()

    if not github_repo:
        print("Error: GitHub repository URL is required")
        return 1

    print(f"\n{'='*60}")
    print(f"Deploying PutPlace to AWS App Runner")
    print(f"{'='*60}")
    print(f"Service name: {service_name}")
    print(f"Region: {region}")
    print(f"Repository: {github_repo}")
    print(f"Branch: {github_branch}")
    print(f"Instance: {cpu}, {memory}")
    print(f"Auto-deploy: {'Enabled' if auto_deploy else 'Disabled (manual only)'}")
    print(f"{'='*60}\n")

    # Check if service already exists
    print("Checking if service exists...")
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
    print("Note: You may need to connect GitHub in the AWS console first")

    # Build source configuration
    source_config = {
        "CodeRepository": {
            "RepositoryUrl": github_repo,
            "SourceCodeVersion": {
                "Type": "BRANCH",
                "Value": github_branch
            },
            "CodeConfiguration": {
                "ConfigurationSource": "REPOSITORY"
            }
        },
        "AutoDeploymentsEnabled": auto_deploy
    }

    # Write source config to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(source_config, f)
        source_config_file = f.name

    try:
        create_cmd = f"""aws apprunner create-service \\
            --service-name {service_name} \\
            --source-configuration file://{source_config_file} \\
            --instance-configuration Cpu="{cpu}",Memory="{memory}" \\
            --region {region}"""

        print("\nExecuting:")
        print(create_cmd)
        print()

        result = c.run(create_cmd, warn=True)

        if result.ok:
            print(f"\n✓ App Runner service created successfully!")
            print(f"\nService: {service_name}")
            print(f"Region: {region}")
            print(f"\nNext steps:")
            print(f"  1. Check deployment status:")
            print(f"     aws apprunner list-services --region {region}")
            print(f"  2. View service in console:")
            print(f"     https://console.aws.amazon.com/apprunner/")
            print(f"  3. Grant IAM role access to secrets:")
            print(f"     Action: secretsmanager:GetSecretValue")
            print(f"     Resource: arn:aws:secretsmanager:{region}:*:secret:putplace/*")

            if not auto_deploy:
                print(f"\n  Manual deployment mode enabled.")
                print(f"  Trigger deployments with:")
                print(f"     invoke trigger-apprunner-deploy --service-name={service_name}")
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
    result = c.run(deploy_cmd, warn=True)

    if result.ok:
        print(f"\n✓ Deployment triggered successfully")
        print(f"\nMonitor deployment:")
        print(f"  aws apprunner describe-service --service-arn {service_arn} --region {region}")
    else:
        print(f"\n✗ Failed to trigger deployment")


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
    result = c.run(shlex.join(cmd), warn=True)

    if not result.ok:
        print("\nTo delete secrets manually:")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/mongodb --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/admin --region {region}")
        print(f"  aws secretsmanager delete-secret --secret-id putplace/aws-config --region {region}")
