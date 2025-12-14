"""Invoke tasks for putplace-assist."""

from invoke import task


@task
def install(c):
    """Install dependencies."""
    c.run("uv pip install -e '.[dev]'")


@task
def test(c, verbose=False, coverage=True):
    """Run tests."""
    cmd = "uv run python -m pytest tests/"
    if verbose:
        cmd += " -v"
    if coverage:
        cmd += " --cov=putplace_assist --cov-report=term-missing"
    c.run(cmd)


@task
def lint(c, fix=False):
    """Run linter."""
    cmd = "uv run ruff check src/"
    if fix:
        cmd += " --fix"
    c.run(cmd)


@task
def format(c, check=False):
    """Format code."""
    cmd = "uv run ruff format src/"
    if check:
        cmd += " --check"
    c.run(cmd)


@task
def typecheck(c):
    """Run type checker."""
    c.run("uv run mypy src/")


@task
def check(c):
    """Run all checks (format, lint, typecheck, test)."""
    format(c, check=True)
    lint(c)
    typecheck(c)
    test(c)


@task
def build(c):
    """Build the package."""
    c.run("uv build")


@task
def clean(c):
    """Clean build artifacts."""
    c.run("rm -rf build/ dist/ *.egg-info src/*.egg-info")
    c.run("find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true")
    c.run("find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true")
    c.run("find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true")
    c.run("find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true")


@task
def serve(c, host="127.0.0.1", port=8765):
    """Run the development server."""
    c.run(
        f"uv run uvicorn putplace_assist.main:app --reload --host {host} --port {port}",
        pty=True,
    )


@task
def start(c, foreground=False):
    """Start the daemon."""
    cmd = "uv run ppassist start"
    if foreground:
        cmd += " --foreground"
    c.run(cmd, pty=True)


@task
def stop(c):
    """Stop the daemon."""
    c.run("uv run ppassist stop")


@task
def status(c):
    """Check daemon status."""
    c.run("uv run ppassist status")


@task
def restart(c, foreground=False):
    """Restart the daemon."""
    cmd = "uv run ppassist restart"
    if foreground:
        cmd += " --foreground"
    c.run(cmd, pty=True)
