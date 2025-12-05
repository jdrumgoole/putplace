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
    """Install both packages in development mode using uv."""
    c.run("uv pip install -e './packages/putplace-client[dev]'")
    c.run("uv pip install -e './packages/putplace-server[dev]'")
    print("\n✓ Both packages installed")
    print("\nIMPORTANT: Activate the virtual environment to use console scripts:")
    print("  source .venv/bin/activate")
    print("\nThen you can use:")
    print("  ppclient --help")
    print("  ppserver --help")


@task
def install_client(c):
    """Install putplace-client package in development mode."""
    c.run("uv pip install -e './packages/putplace-client[dev]'")
    print("\n✓ putplace-client installed")
    print("Use: ppclient --help")


@task
def install_server(c):
    """Install putplace-server package in development mode."""
    c.run("uv pip install -e './packages/putplace-server[dev]'")
    print("\n✓ putplace-server installed")
    print("Use: ppserver --help")


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
    """Run all tests for both client and server packages.

    Tests include:
        - Client tests (ppclient functionality)
        - Server tests (API, database, auth, storage, integration)

    Args:
        verbose: Show verbose test output (default: True)
        coverage: Generate coverage report (default: True)
        parallel: Run tests in parallel (default: True, ~40% faster)
        workers: Number of parallel workers (default: 4)

    Examples:
        invoke test-all                     # Run all tests
        invoke test-all --workers=8         # Use 8 workers
        invoke test-all --parallel=False    # Run serially
    """
    print("Testing putplace-client...")
    test_client(c, verbose=verbose, coverage=False)

    print("\nTesting putplace-server...")
    test_server(c, verbose=verbose, coverage=coverage, parallel=parallel, workers=workers)

    if coverage:
        print("\n✓ All tests passed!")
        print("Coverage report: packages/putplace-server/htmlcov/index.html")


@task
def test_client(c, verbose=True, coverage=False):
    """Run tests for putplace-client package."""
    cmd = "uv run python -m pytest packages/putplace-client/tests/ -v --tb=short"
    if not coverage:
        cmd += " --no-cov"
    c.run(cmd)
    print("\n✓ Client tests passed!")


@task
def test_server(c, verbose=True, coverage=True, parallel=True, workers=4):
    """Run tests for putplace-server package."""
    import os
    # Add both package src directories to PYTHONPATH
    pythonpath = f"{os.getcwd()}/packages/putplace-client/src:{os.getcwd()}/packages/putplace-server/src:{os.environ.get('PYTHONPATH', '')}"

    cmd = f"PYTHONPATH={pythonpath} uv run python -m pytest packages/putplace-server/tests/ -v --tb=short"

    if parallel:
        cmd += f" -n {workers} --dist loadscope"

    if not coverage:
        cmd += " --no-cov"

    c.run(cmd)
    print("\n✓ Server tests passed!")


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
    """Run ruff linter on both packages."""
    cmd = "uv run ruff check packages/putplace-client/src packages/putplace-client/tests packages/putplace-server/src packages/putplace-server/tests"
    if fix:
        cmd += " --fix"
    c.run(cmd)


@task
def format(c, check=False):
    """Format code with ruff for both packages."""
    cmd = "uv run ruff format packages/putplace-client/src packages/putplace-client/tests packages/putplace-server/src packages/putplace-server/tests"
    if check:
        cmd += " --check"
    c.run(cmd)


@task
def typecheck(c):
    """Run mypy type checker on both packages."""
    c.run("uv run mypy packages/putplace-client/src packages/putplace-server/src")


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
    """Build both packages."""
    clean(c)
    build_client(c)
    build_server(c)
    print("\n✓ Both packages built successfully")


@task
def build_client(c):
    """Build putplace-client package."""
    c.run("cd packages/putplace-client && uv build")
    print("\n✓ putplace-client built")
    print("  Distribution files in: packages/putplace-client/dist/")


@task
def build_server(c):
    """Build putplace-server package."""
    c.run("cd packages/putplace-server && uv build")
    print("\n✓ putplace-server built")
    print("  Distribution files in: packages/putplace-server/dist/")


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
    cmd = "uv run python -m putplace_server.scripts.putplace_configure"

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


@task
def reset_password(c, email=None, password=None, mongodb_url=None, database=None, list_users=False):
    """Reset a user's password in the database.

    If email and password are not provided, runs in interactive mode
    with password confirmation.

    Args:
        email: User's email address
        password: New password (will prompt if not provided)
        mongodb_url: MongoDB URL (default: mongodb://localhost:27017)
        database: Database name (default: putplace)
        list_users: List all users and exit

    Examples:
        invoke reset-password --list-users
        invoke reset-password --email admin@localhost
        invoke reset-password --email admin@localhost --password newpass123
    """
    cmd = "uv run python -m putplace_server.scripts.reset_password"

    if list_users:
        cmd += " --list-users"
    else:
        if email:
            cmd += f" --email {email}"
        if password:
            cmd += f" --password {password}"

    if mongodb_url:
        cmd += f" --mongodb-url {mongodb_url}"
    if database:
        cmd += f" --database {database}"

    c.run(cmd, pty=True)


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
        "putplace_server.scripts.send_ses_email",
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
    c.run(f"uv run python -m putplace_server.scripts.toggle_registration {action}")


@task
def atlas_clusters(c):
    """List all MongoDB Atlas clusters.

    Requires Atlas API credentials in environment or ~/.atlas/credentials file.

    Examples:
        invoke atlas-clusters
    """
    c.run("uv run python -m putplace_server.scripts.atlas_cluster_control list")


@task
def atlas_status(c, cluster):
    """Get status of a MongoDB Atlas cluster.

    Args:
        cluster: Cluster name

    Examples:
        invoke atlas-status --cluster=testcluster
    """
    c.run(f"uv run python -m putplace_server.scripts.atlas_cluster_control status --cluster {cluster}")


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
    c.run(f"uv run python -m putplace_server.scripts.atlas_cluster_control pause --cluster {cluster}")


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
    cmd = f"uv run python -m putplace_server.scripts.setup_aws_iam_users --region {region}"
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
    c.run(f"uv run python -m putplace_server.scripts.atlas_cluster_control resume --cluster {cluster}")


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
    config_file=None,
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

    # Check for putplace-server (needed to generate config)
    result = c.run("uv run python -c 'import putplace_server'", warn=True, hide=True)
    if result.failed:
        print("❌ Error: putplace-server not installed. Install with: pip install putplace-server")
        sys.exit(1)

    # Build command
    cmd = "uv run python -m putplace_server.scripts.deploy_digitalocean"

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

    if config_file:
        cmd += f" --config-output={config_file}"

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
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # Python < 3.11 fallback
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
    mongodb_url = config.get("database", {}).get("mongodb_url", "mongodb://localhost:27017")
    storage_backend = config.get("storage", {}).get("backend", "local")
    s3_bucket = config.get("storage", {}).get("s3_bucket_name")
    aws_region = config.get("aws", {}).get("region", "eu-west-1")

    # Read domain from config if not provided as argument
    if domain is None:
        domain = config.get("server", {}).get("domain")

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
    if domain:
        print(f"  Domain: {domain} (SSL will be configured)")
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
        config_file=config_file,  # Pass the environment-specific config file
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

    cmd = "uv run python -m putplace_server.scripts.update_deployment"

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


@task
def install_awscli_do(c, droplet_name=None, ip=None):
    """Install AWS CLI v2 on a Digital Ocean droplet.

    Installs the latest AWS CLI v2 on a remote droplet running Ubuntu/Debian.
    Uses the official AWS installation method.

    Args:
        droplet_name: Droplet name (will lookup IP via doctl)
        ip: Droplet IP address

    Examples:
        # Install by droplet name
        invoke install-awscli-do --droplet-name=putplace-droplet

        # Install by IP
        invoke install-awscli-do --ip=165.22.xxx.xxx

    Prerequisites:
        - doctl CLI installed (if using droplet_name): brew install doctl
        - SSH key added to the droplet
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
        print(f"Installing AWS CLI on {droplet_name} ({ip})...")
    else:
        print(f"Installing AWS CLI on {ip}...")

    # AWS CLI v2 installation commands for Ubuntu/Debian
    install_commands = """
        set -e
        echo "==> Updating package list..."
        apt-get update -qq

        echo "==> Installing dependencies..."
        apt-get install -y -qq unzip curl

        echo "==> Downloading AWS CLI v2..."
        cd /tmp
        curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

        echo "==> Extracting..."
        unzip -q -o awscliv2.zip

        echo "==> Installing AWS CLI..."
        ./aws/install --update

        echo "==> Cleaning up..."
        rm -rf awscliv2.zip aws

        echo "==> Verifying installation..."
        aws --version
    """

    result = c.run(
        f"ssh -o StrictHostKeyChecking=no root@{ip} '{install_commands}'",
        pty=True,
        warn=True,
    )

    if result.ok:
        print(f"\n✓ AWS CLI installed successfully on {droplet_name or ip}")
    else:
        print(f"\n❌ Failed to install AWS CLI on {droplet_name or ip}")
        sys.exit(1)


@task
def flush_dns(c):
    """Flush the local DNS cache (macOS only).

    Clears the DNS resolver cache to pick up recent DNS changes.
    Useful after updating Route53 or other DNS records.

    Examples:
        invoke flush-dns
    """
    import platform

    if platform.system() != "Darwin":
        print("❌ This command only works on macOS")
        return

    print("Flushing DNS cache...")
    result = c.run(
        "sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder",
        pty=True,
        warn=True,
    )

    if result.ok:
        print("✓ DNS cache flushed")
    else:
        print("❌ Failed to flush DNS cache")
