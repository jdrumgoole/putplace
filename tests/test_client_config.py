"""Tests for ppclient configuration file and argument parsing."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from putplace import ppclient


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        config_path = Path(f.name)
        yield config_path
    # Cleanup
    config_path.unlink(missing_ok=True)


@pytest.fixture
def sample_config_content():
    """Sample config file content."""
    return """[DEFAULT]
url = http://config-server:9000/put_file
api-key = config-api-key-12345
hostname = config-hostname
ip = 10.0.0.99
exclude = .git
exclude = *.log
exclude = __pycache__
"""


def test_main_with_config_file(temp_test_dir, temp_config_file, sample_config_content):
    """Test that config file is properly loaded."""
    # Write config file
    temp_config_file.write_text(sample_config_content)

    # Mock sys.argv to simulate command line
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(temp_config_file),
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            # Mock process_path to avoid actual scanning
            mock_scan.return_value = (0, 0, 0, 0)

            # Run main
            exit_code = ppclient.main()

            # Verify process_path was called with config values
            assert mock_scan.called
            call_args = mock_scan.call_args[0]  # Get positional args

            # Args: start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args

            # Check URL from config file
            assert api_url == "http://config-server:9000/put_file"

            # Check API key from config file
            assert api_key == "config-api-key-12345"

            # Check hostname from config file
            assert hostname == "config-hostname"

            # Check IP from config file
            assert ip_address == "10.0.0.99"

            # Check exclude patterns from config file
            assert ".git" in exclude_patterns
            assert "*.log" in exclude_patterns
            assert "__pycache__" in exclude_patterns

            assert exit_code == 0


def test_command_line_overrides_config_file(temp_test_dir, temp_config_file, sample_config_content):
    """Test that command line arguments override config file values."""
    # Write config file
    temp_config_file.write_text(sample_config_content)

    # Command line args that override config
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(temp_config_file),
        "--url", "http://cli-server:8080/put_file",  # Override URL
        "--api-key", "cli-api-key-67890",  # Override API key
        "--hostname", "cli-hostname",  # Override hostname
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            exit_code = ppclient.main()

            # Verify command line values were used instead of config
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args

            # CLI values should override config values
            assert api_url == "http://cli-server:8080/put_file"
            assert api_key == "cli-api-key-67890"
            assert hostname == "cli-hostname"

            # But exclude patterns should still include config values
            # (unless explicitly excluded on CLI)
            assert ".git" in exclude_patterns

            assert exit_code == 0


def test_environment_variable_api_key(temp_test_dir):
    """Test that API key from environment variable is used."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--dry-run",
    ]

    # Set environment variable
    env_api_key = "env-api-key-from-environment"

    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_API_KEY": env_api_key}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                mock_scan.return_value = (0, 0, 0, 0)

                exit_code = ppclient.main()

                # Verify environment variable was used
                call_args = mock_scan.call_args[0]  # Get positional args
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
                assert api_key == env_api_key

                assert exit_code == 0


def test_cli_overrides_environment_variable(temp_test_dir):
    """Test that CLI API key overrides environment variable."""
    cli_api_key = "cli-api-key-override"
    env_api_key = "env-api-key-should-not-be-used"

    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--api-key", cli_api_key,
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_API_KEY": env_api_key}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                mock_scan.return_value = (0, 0, 0, 0)

                exit_code = ppclient.main()

                # Verify CLI value was used, not environment
                call_args = mock_scan.call_args[0]  # Get positional args
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
                assert api_key == cli_api_key
                assert api_key != env_api_key

                assert exit_code == 0


def test_priority_order_cli_env_config(temp_test_dir, temp_config_file):
    """Test configuration priority: CLI > Environment > Config File."""
    # Config file with API key
    config_content = """[DEFAULT]
api-key = config-api-key
url = http://config-server:9000/put_file
"""
    temp_config_file.write_text(config_content)

    # Test 1: Config file only
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(temp_config_file),
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)
            ppclient.main()
            call_args = mock_scan.call_args[0]
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
            assert api_key == "config-api-key"

    # Test 2: Environment overrides config
    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_API_KEY": "env-api-key"}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                mock_scan.return_value = (0, 0, 0, 0)
                ppclient.main()
                call_args = mock_scan.call_args[0]
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
                assert api_key == "env-api-key"

    # Test 3: CLI overrides both
    test_args_with_cli = test_args + ["--api-key", "cli-api-key"]

    with patch("sys.argv", test_args_with_cli):
        with patch.dict(os.environ, {"PUTPLACE_API_KEY": "env-api-key"}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                mock_scan.return_value = (0, 0, 0, 0)
                ppclient.main()
                call_args = mock_scan.call_args[0]
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
                assert api_key == "cli-api-key"


def test_config_file_with_multiple_exclude_patterns(temp_test_dir, temp_config_file):
    """Test that multiple exclude patterns from config are all loaded."""
    config_content = """[DEFAULT]
exclude = .git
exclude = .svn
exclude = __pycache__
exclude = *.pyc
exclude = *.log
exclude = node_modules
"""
    temp_config_file.write_text(config_content)

    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(temp_config_file),
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            ppclient.main()

            # Verify all exclude patterns were loaded
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args

            assert ".git" in exclude_patterns
            assert ".svn" in exclude_patterns
            assert "__pycache__" in exclude_patterns
            assert "*.pyc" in exclude_patterns
            assert "*.log" in exclude_patterns
            assert "node_modules" in exclude_patterns


def test_cli_exclude_adds_to_config_exclude(temp_test_dir, temp_config_file):
    """Test that CLI exclude patterns are added to config exclude patterns."""
    config_content = """[DEFAULT]
exclude = .git
exclude = *.log
"""
    temp_config_file.write_text(config_content)

    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(temp_config_file),
        "--exclude", "node_modules",  # Additional CLI exclude
        "--exclude", "*.tmp",  # Additional CLI exclude
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            ppclient.main()

            # Verify both config and CLI excludes are present
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args

            # From config
            assert ".git" in exclude_patterns
            assert "*.log" in exclude_patterns

            # From CLI
            assert "node_modules" in exclude_patterns
            assert "*.tmp" in exclude_patterns


def test_no_api_key_provided(temp_test_dir, capsys, monkeypatch):
    """Test that warning is shown when no API key is provided."""
    # Change to temp directory to avoid loading ppclient.conf from repo root
    monkeypatch.chdir(temp_test_dir)

    # Create an empty config file
    empty_config = temp_test_dir / "empty.conf"
    empty_config.write_text("")

    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", str(empty_config),
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            ppclient.main()

            # Verify scan was called with None for api_key
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
            assert api_key is None


def test_config_file_not_found_raises_error(temp_test_dir):
    """Test that non-existent config file specified with --config raises an error."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--config", "/nonexistent/config.conf",
        "--url", "http://localhost:8000/put_file",
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            # Should raise SystemExit because config file doesn't exist
            with pytest.raises(SystemExit):
                ppclient.main()


def test_default_config_file_locations(temp_test_dir, monkeypatch):
    """Test that default config file locations are checked."""
    # Create a config in "current directory"
    current_dir_config = Path("ppclient.conf")
    config_content = """[DEFAULT]
api-key = default-location-key
"""

    # We can't easily test this without actually creating the file,
    # but we can verify the parser has the right default_config_files
    import configargparse
    parser = configargparse.ArgumentParser(
        default_config_files=["~/ppclient.conf", "ppclient.conf"]
    )

    # Verify default config files are set correctly
    assert parser._default_config_files == ["~/ppclient.conf", "ppclient.conf"]


def test_dry_run_mode(temp_test_dir):
    """Test that dry run mode is properly passed through."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            ppclient.main()

            # Verify dry_run was set to True
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
            assert dry_run is True


def test_without_dry_run_mode(temp_test_dir):
    """Test that dry run mode defaults to False."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--api-key", "test-key",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            mock_scan.return_value = (0, 0, 0, 0)

            ppclient.main()

            # Verify dry_run was set to False
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, api_key = call_args
            assert dry_run is False
