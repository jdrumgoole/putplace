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
