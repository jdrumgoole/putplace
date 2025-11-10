"""Tests for installed console scripts (ppserver and ppclient).

These tests verify that the package can be installed and the console scripts
work correctly from the command line.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def install_package():
    """Install the package in editable mode, then uninstall after tests."""
    # Get the project root directory (parent of tests/)
    project_root = Path(__file__).parent.parent

    # Install package in editable mode using uv
    print("\n[SETUP] Installing package in editable mode...")
    result = subprocess.run(
        ["uv", "pip", "install", "-e", str(project_root)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to install package:\n{result.stderr}")

    print("[SETUP] Package installed successfully")

    yield

    # Uninstall package after all tests using uv
    print("\n[TEARDOWN] Uninstalling package...")
    subprocess.run(
        ["uv", "pip", "uninstall", "-y", "putplace"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print("[TEARDOWN] Package uninstalled")


def test_ppclient_help(install_package):
    """Test that ppclient --help works after installation."""
    result = subprocess.run(
        ["ppclient", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"ppclient --help failed:\n{result.stderr}"
    assert "PutPlace" in result.stdout or "Scan directories" in result.stdout
    assert "--exclude" in result.stdout
    assert "--url" in result.stdout
    assert "--dry-run" in result.stdout


def test_ppclient_version_exists(install_package):
    """Test that ppclient command exists and can be executed."""
    result = subprocess.run(
        ["which", "ppclient"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, "ppclient command not found in PATH"
    assert "ppclient" in result.stdout


def test_ppclient_runs_dry_run(install_package):
    """Test that ppclient can scan a directory in dry-run mode."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("test content")

        result = subprocess.run(
            ["ppclient", "--path", temp_dir, "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # ppclient returns 0 on success
        assert result.returncode == 0, f"ppclient failed:\n{result.stderr}\n{result.stdout}"
        assert "DRY RUN" in result.stdout
        assert "Results:" in result.stdout


def test_ppserver_help(install_package):
    """Test that ppserver --help works after installation."""
    result = subprocess.run(
        ["ppserver", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"ppserver --help failed:\n{result.stderr}"
    assert "PutPlace" in result.stdout or "server" in result.stdout.lower()


def test_ppserver_version_exists(install_package):
    """Test that ppserver command exists and can be executed."""
    result = subprocess.run(
        ["which", "ppserver"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, "ppserver command not found in PATH"
    assert "ppserver" in result.stdout


def test_ppserver_start_stop(install_package, tmp_path):
    """Test that ppserver can start and stop successfully."""
    import os

    # Create test environment with temporary storage directory
    test_env = os.environ.copy()
    test_env["STORAGE_PATH"] = str(tmp_path / "storage")

    # Make sure server is not already running
    subprocess.run(
        ["ppserver", "stop"],
        capture_output=True,
        timeout=10,
        env=test_env,
    )
    time.sleep(1)

    try:
        # Start server on a non-default port to avoid conflicts
        result = subprocess.run(
            ["ppserver", "start", "--port", "8765"],
            capture_output=True,
            text=True,
            timeout=30,
            env=test_env,
        )

        assert result.returncode == 0, f"ppserver start failed:\n{result.stderr}\n{result.stdout}"
        assert "started" in result.stdout.lower() or "running" in result.stdout.lower()

        # Wait for server to start
        time.sleep(2)

        # Check status
        result = subprocess.run(
            ["ppserver", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            env=test_env,
        )

        assert result.returncode == 0, f"ppserver status failed:\n{result.stderr}"
        assert "running" in result.stdout.lower()

    finally:
        # Always try to stop server, even if test fails
        result = subprocess.run(
            ["ppserver", "stop"],
            capture_output=True,
            text=True,
            timeout=10,
            env=test_env,
        )

        # Verify stop succeeded
        assert result.returncode == 0, f"ppserver stop failed:\n{result.stderr}"


def test_ppserver_status_not_running(install_package):
    """Test that ppserver status reports when server is not running."""
    # Make sure server is stopped
    subprocess.run(
        ["ppserver", "stop"],
        capture_output=True,
        timeout=10,
    )
    time.sleep(1)

    result = subprocess.run(
        ["ppserver", "status"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Status command returns 1 when server is not running
    assert result.returncode == 1
    assert "not running" in result.stdout.lower() or "stopped" in result.stdout.lower()


def test_ppclient_with_config_file(install_package):
    """Test that ppclient works with a config file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        (temp_path / "test.txt").write_text("test")
        (temp_path / "test.log").write_text("log")

        # Create config file
        config_file = temp_path / "test.conf"
        config_file.write_text("""[DEFAULT]
url = http://localhost:8000/put_file
exclude = *.log
""")

        result = subprocess.run(
            ["ppclient", "--path", str(temp_path), "--config", str(config_file), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"ppclient with config failed:\n{result.stderr}\n{result.stdout}"
        assert "DRY RUN" in result.stdout
        # Config file should be loaded (exclude pattern should appear)
        assert "*.log" in result.stdout


def test_ppclient_with_exclude_patterns(install_package):
    """Test that ppclient exclude patterns work correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files and directories
        (temp_path / "included.txt").write_text("include me")
        (temp_path / "excluded.log").write_text("exclude me")
        git_dir = temp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")

        result = subprocess.run(
            [
                "ppclient",
                "--path", str(temp_path),
                "--exclude", "*.log",
                "--exclude", ".git",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"ppclient with excludes failed:\n{result.stderr}\n{result.stdout}"
        assert "DRY RUN" in result.stdout
        # Verify exclude patterns appear in output
        assert "*.log" in result.stdout
        assert ".git" in result.stdout


def test_ppserver_restart(install_package, tmp_path):
    """Test that ppserver restart command works."""
    import os

    # Create test environment with temporary storage directory
    test_env = os.environ.copy()
    test_env["STORAGE_PATH"] = str(tmp_path / "storage")

    # Make sure server is not running
    subprocess.run(
        ["ppserver", "stop"],
        capture_output=True,
        timeout=10,
        env=test_env,
    )
    time.sleep(1)

    try:
        # Start server
        subprocess.run(
            ["ppserver", "start", "--port", "8766"],
            capture_output=True,
            timeout=30,
            env=test_env,
        )
        time.sleep(2)

        # Restart server on the same port
        result = subprocess.run(
            ["ppserver", "restart", "--port", "8766"],
            capture_output=True,
            text=True,
            timeout=30,
            env=test_env,
        )

        assert result.returncode == 0, f"ppserver restart failed:\n{result.stderr}\n{result.stdout}"

        # Wait for restart to complete
        time.sleep(2)

        # Verify it's running
        status_result = subprocess.run(
            ["ppserver", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            env=test_env,
        )

        assert "running" in status_result.stdout.lower()

    finally:
        # Clean up
        subprocess.run(
            ["ppserver", "stop"],
            capture_output=True,
            timeout=10,
            env=test_env,
        )


def test_ppserver_logs_command(install_package):
    """Test that ppserver logs command works."""
    # Make sure server is stopped (logs command should work even when stopped)
    subprocess.run(
        ["ppserver", "stop"],
        capture_output=True,
        timeout=10,
    )

    result = subprocess.run(
        ["ppserver", "logs", "--lines", "10"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Logs command should succeed (may show empty or previous logs)
    # Return code of 0 or 1 is acceptable (1 if no log file exists)
    assert result.returncode in [0, 1], f"ppserver logs failed unexpectedly:\n{result.stderr}"
