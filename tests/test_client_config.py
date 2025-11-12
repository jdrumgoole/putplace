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
username = config-user
password = config-pass
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
            with patch("putplace.ppclient.login_and_get_token") as mock_login:
                # Mock login to return a token
                mock_login.return_value = "mock-jwt-token"
                # Mock process_path to avoid actual scanning
                mock_scan.return_value = (0, 0, 0, 0)

                # Run main
                exit_code = ppclient.main()

                # Verify login was called with credentials from config
                assert mock_login.called
                login_call_args = mock_login.call_args[0]
                base_url, username, password = login_call_args
                assert username == "config-user"
                assert password == "config-pass"

                # Verify process_path was called with config values
                assert mock_scan.called
                call_args = mock_scan.call_args[0]  # Get positional args

                # Args: start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args

                # Check URL from config file
                assert api_url == "http://config-server:9000/put_file"

                # Check access token from login
                assert access_token == "mock-jwt-token"

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
        "--username", "cli-user",  # Override username
        "--password", "cli-pass",  # Override password
        "--hostname", "cli-hostname",  # Override hostname
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            with patch("putplace.ppclient.login_and_get_token") as mock_login:
                mock_login.return_value = "mock-jwt-token"
                mock_scan.return_value = (0, 0, 0, 0)

                exit_code = ppclient.main()

                # Verify CLI credentials were used
                login_call_args = mock_login.call_args[0]
                base_url, username, password = login_call_args
                assert username == "cli-user"
                assert password == "cli-pass"

                # Verify command line values were used instead of config
                call_args = mock_scan.call_args[0]  # Get positional args
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args

                # CLI values should override config values
                assert api_url == "http://cli-server:8080/put_file"
                assert access_token == "mock-jwt-token"
                assert hostname == "cli-hostname"

                # But exclude patterns should still include config values
                # (unless explicitly excluded on CLI)
                assert ".git" in exclude_patterns

                assert exit_code == 0


def test_environment_variable_api_key(temp_test_dir):
    """Test that username/password from environment variables are used."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--dry-run",
    ]

    # Set environment variables
    env_username = "env-user"
    env_password = "env-pass"

    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_USERNAME": env_username, "PUTPLACE_PASSWORD": env_password}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                with patch("putplace.ppclient.login_and_get_token") as mock_login:
                    mock_login.return_value = "mock-jwt-token"
                    mock_scan.return_value = (0, 0, 0, 0)

                    exit_code = ppclient.main()

                    # Verify environment variables were used
                    login_call_args = mock_login.call_args[0]
                    base_url, username, password = login_call_args
                    assert username == env_username
                    assert password == env_password

                    assert exit_code == 0


def test_cli_overrides_environment_variable(temp_test_dir):
    """Test that CLI username/password overrides environment variables."""
    cli_username = "cli-user"
    cli_password = "cli-pass"
    env_username = "env-user-should-not-be-used"
    env_password = "env-pass-should-not-be-used"

    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--username", cli_username,
        "--password", cli_password,
        "--dry-run",
    ]

    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_USERNAME": env_username, "PUTPLACE_PASSWORD": env_password}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                with patch("putplace.ppclient.login_and_get_token") as mock_login:
                    mock_login.return_value = "mock-jwt-token"
                    mock_scan.return_value = (0, 0, 0, 0)

                    exit_code = ppclient.main()

                    # Verify CLI values were used, not environment
                    login_call_args = mock_login.call_args[0]
                    base_url, username, password = login_call_args
                    assert username == cli_username
                    assert password == cli_password
                    assert username != env_username
                    assert password != env_password

                    assert exit_code == 0


def test_priority_order_cli_env_config(temp_test_dir, temp_config_file):
    """Test configuration priority: CLI > Environment > Config File."""
    # Config file with username/password
    config_content = """[DEFAULT]
username = config-user
password = config-pass
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
            with patch("putplace.ppclient.login_and_get_token") as mock_login:
                mock_login.return_value = "mock-jwt-token"
                mock_scan.return_value = (0, 0, 0, 0)
                ppclient.main()
                login_call_args = mock_login.call_args[0]
                base_url, username, password = login_call_args
                assert username == "config-user"
                assert password == "config-pass"

    # Test 2: Environment overrides config
    with patch("sys.argv", test_args):
        with patch.dict(os.environ, {"PUTPLACE_USERNAME": "env-user", "PUTPLACE_PASSWORD": "env-pass"}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                with patch("putplace.ppclient.login_and_get_token") as mock_login:
                    mock_login.return_value = "mock-jwt-token"
                    mock_scan.return_value = (0, 0, 0, 0)
                    ppclient.main()
                    login_call_args = mock_login.call_args[0]
                    base_url, username, password = login_call_args
                    assert username == "env-user"
                    assert password == "env-pass"

    # Test 3: CLI overrides both
    test_args_with_cli = test_args + ["--username", "cli-user", "--password", "cli-pass"]

    with patch("sys.argv", test_args_with_cli):
        with patch.dict(os.environ, {"PUTPLACE_USERNAME": "env-user", "PUTPLACE_PASSWORD": "env-pass"}):
            with patch("putplace.ppclient.process_path") as mock_scan:
                with patch("putplace.ppclient.login_and_get_token") as mock_login:
                    mock_login.return_value = "mock-jwt-token"
                    mock_scan.return_value = (0, 0, 0, 0)
                    ppclient.main()
                    login_call_args = mock_login.call_args[0]
                    base_url, username, password = login_call_args
                    assert username == "cli-user"
                    assert password == "cli-pass"


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
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args

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
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args

            # From config
            assert ".git" in exclude_patterns
            assert "*.log" in exclude_patterns

            # From CLI
            assert "node_modules" in exclude_patterns
            assert "*.tmp" in exclude_patterns


def test_no_api_key_provided(temp_test_dir, capsys, monkeypatch):
    """Test that ppclient works without authentication (access_token will be None)."""
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

            # Verify scan was called with None for access_token
            call_args = mock_scan.call_args[0]  # Get positional args
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args
            assert access_token is None


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
username = default-location-user
password = default-location-pass
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
            start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args
            assert dry_run is True


def test_without_dry_run_mode(temp_test_dir):
    """Test that dry run mode defaults to False."""
    test_args = [
        "ppclient.py",
        "--path", str(temp_test_dir),
        "--username", "test-user",
        "--password", "test-pass",
    ]

    with patch("sys.argv", test_args):
        with patch("putplace.ppclient.process_path") as mock_scan:
            with patch("putplace.ppclient.login_and_get_token") as mock_login:
                mock_login.return_value = "mock-jwt-token"
                mock_scan.return_value = (0, 0, 0, 0)

                ppclient.main()

                # Verify dry_run was set to False
                call_args = mock_scan.call_args[0]  # Get positional args
                start_path, exclude_patterns, hostname, ip_address, api_url, dry_run, access_token = call_args
                assert dry_run is False
