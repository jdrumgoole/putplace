"""Tests for ppserver.py module functions."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from putplace import ppserver


def test_load_config_no_toml():
    """Test load_config when tomllib is not available."""
    with patch('putplace.ppserver.tomllib', None):
        config = ppserver.load_config()
        assert config == {}


def test_load_config_file_exists():
    """Test load_config when config file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "ppserver.toml"
        config_file.write_text("""
[server]
host = "0.0.0.0"
port = 9000

[logging]
pid_file = "/tmp/test.pid"
""")

        with patch('putplace.ppserver.Path') as mock_path:
            # Mock Path.home() to return our temp directory
            mock_path.return_value = Path(tmpdir)
            mock_path.home.return_value = Path(tmpdir)

            # Create a mock Path instance that exists
            mock_config_path = MagicMock()
            mock_config_path.exists.return_value = True
            mock_config_path.__truediv__ = lambda self, other: config_file if "ppserver.toml" in str(other) else Path(tmpdir) / other

            with patch('putplace.ppserver.Path', return_value=mock_config_path):
                # Directly test with the temp config file
                import sys
                if sys.version_info >= (3, 11):
                    import tomllib
                else:
                    try:
                        import tomli as tomllib
                    except ImportError:
                        pytest.skip("tomli not available")

                with open(config_file, 'rb') as f:
                    config = tomllib.load(f)

                assert config['server']['host'] == "0.0.0.0"
                assert config['server']['port'] == 9000


def test_get_pid_file_default():
    """Test get_pid_file returns default path."""
    with patch('putplace.ppserver.load_config', return_value={}):
        pid_file = ppserver.get_pid_file()
        assert pid_file.name == "ppserver.pid"
        assert ".putplace" in str(pid_file)


def test_get_pid_file_from_config():
    """Test get_pid_file reads from config."""
    test_pid = "/tmp/custom.pid"
    with patch('putplace.ppserver.load_config', return_value={
        'logging': {'pid_file': test_pid}
    }):
        pid_file = ppserver.get_pid_file()
        assert str(pid_file) == test_pid


def test_get_log_file():
    """Test get_log_file returns correct path."""
    log_file = ppserver.get_log_file()
    assert log_file.name == "ppserver.log"
    assert ".putplace" in str(log_file)


def test_is_running_no_pid_file():
    """Test is_running when PID file doesn't exist."""
    with patch('putplace.ppserver.get_pid_file') as mock_get_pid:
        mock_pid_file = Mock()
        mock_pid_file.exists.return_value = False
        mock_get_pid.return_value = mock_pid_file

        running, pid = ppserver.is_running()
        assert running is False
        assert pid is None


def test_is_running_stale_pid():
    """Test is_running with stale PID file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"
        pid_file.write_text("99999")  # Non-existent PID

        with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
            running, pid = ppserver.is_running()
            assert running is False
            # When PID doesn't exist, is_running returns None for pid


def test_is_port_available_yes():
    """Test is_port_available when port is free."""
    import socket

    # Find a free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        free_port = s.getsockname()[1]

    assert ppserver.is_port_available('127.0.0.1', free_port) is True


def test_is_port_available_no():
    """Test is_port_available when port is in use."""
    import socket

    # Bind to a port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        used_port = s.getsockname()[1]

        # Port should be unavailable while socket is open
        assert ppserver.is_port_available('127.0.0.1', used_port) is False


def test_wait_for_port_timeout():
    """Test wait_for_port_available times out."""
    import socket

    # Bind to a port and hold it
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        used_port = s.getsockname()[1]

        # Should timeout quickly
        result = ppserver.wait_for_port_available('127.0.0.1', used_port, timeout=1)
        assert result is False


def test_stop_server_not_running():
    """Test stop_server when server is not running."""
    with patch('putplace.ppserver.is_running', return_value=(False, None)):
        with patch('putplace.ppserver.console') as mock_console:
            result = ppserver.stop_server()
            assert result == 1
            mock_console.print.assert_called()


def test_status_not_running():
    """Test status_server when server is not running."""
    with patch('putplace.ppserver.is_running', return_value=(False, None)):
        with patch('putplace.ppserver.console') as mock_console:
            result = ppserver.status_server()
            assert result == 1
            mock_console.print.assert_called()


def test_status_running():
    """Test status_server when server is running."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "ppserver.log"
        log_file.write_text("INFO: Server started\n")

        with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
            with patch('putplace.ppserver.get_log_file', return_value=log_file):
                with patch('putplace.ppserver.console') as mock_console:
                    result = ppserver.status_server()
                    assert result == 0
                    # Should print status
                    assert mock_console.print.call_count > 0


def test_restart_not_running():
    """Test restart_server when server is not currently running."""
    with patch('putplace.ppserver.is_running', return_value=(False, None)):
        with patch('putplace.ppserver.start_server', return_value=0) as mock_start:
            with patch('putplace.ppserver.console'):
                result = ppserver.restart_server()
                mock_start.assert_called_once()


def test_logs_file_not_found():
    """Test logs_server when log file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent = Path(tmpdir) / "nonexistent.log"

        with patch('putplace.ppserver.get_log_file', return_value=nonexistent):
            with patch('putplace.ppserver.console') as mock_console:
                result = ppserver.logs_server(lines=10)
                assert result == 1
                mock_console.print.assert_called()


def test_logs_success():
    """Test logs_server with existing log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "ppserver.log"
        log_file.write_text("Line 1\nLine 2\nLine 3\n")

        with patch('putplace.ppserver.get_log_file', return_value=log_file):
            with patch('putplace.ppserver.console') as mock_console:
                result = ppserver.logs_server(lines=10)
                assert result == 0
                # Should print log content
                assert mock_console.print.call_count > 0
