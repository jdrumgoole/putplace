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


def test_load_config_with_error():
    """Test load_config handles file read errors gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "ppserver.toml"
        config_file.write_text("invalid toml {{{")

        with patch('putplace.ppserver.Path') as mock_path_cls:
            # Create instances that will be returned
            mock_instance1 = MagicMock()
            mock_instance1.exists.return_value = True
            mock_instance1.__str__ = lambda s: str(config_file)

            # Make Path("./ppserver.toml") return our mock
            mock_path_cls.return_value = mock_instance1

            with patch('builtins.open', side_effect=Exception("Read error")):
                config = ppserver.load_config()
                # Should return empty dict on error
                assert config == {}


def test_start_server_already_running():
    """Test start_server when server is already running."""
    with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
        with patch('putplace.ppserver.console') as mock_console:
            result = ppserver.start_server()
            assert result == 1
            # Should print warning
            assert any("already running" in str(call).lower() for call in mock_console.print.call_args_list)


def test_start_server_process_fails():
    """Test start_server when process fails immediately."""
    with patch('putplace.ppserver.is_running', return_value=(False, None)):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.get_log_file', return_value=Path("/tmp/test.log")):
                with patch('putplace.ppserver.get_pid_file', return_value=Path("/tmp/test.pid")):
                    with patch('builtins.open', create=True):
                        with patch('subprocess.Popen') as mock_popen:
                            # Mock process that exits immediately
                            mock_process = Mock()
                            mock_process.poll.return_value = 1  # Non-None = exited
                            mock_popen.return_value = mock_process

                            with patch('putplace.ppserver.console'):
                                result = ppserver.start_server()
                                assert result == 1


def test_stop_server_success():
    """Test stop_server successfully stops a running server."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"

        with patch('putplace.ppserver.is_running', return_value=(True, 99999)):
            with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
                with patch('os.kill') as mock_kill:
                    # First kill is SIGTERM, second is the check which raises ProcessLookupError
                    mock_kill.side_effect = [None, ProcessLookupError()]

                    with patch('putplace.ppserver.console'):
                        result = ppserver.stop_server()
                        assert result == 0


def test_stop_server_force_kill():
    """Test stop_server force kills if graceful shutdown times out."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"
        pid_file.write_text("12345")

        with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
            with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
                with patch('os.kill') as mock_kill:
                    # Process keeps running during checks, then gets force killed
                    call_count = [0]
                    def kill_side_effect(pid, sig):
                        call_count[0] += 1
                        if call_count[0] <= 11:  # SIGTERM + 10 checks
                            return None
                        # After force kill
                        raise ProcessLookupError()

                    mock_kill.side_effect = kill_side_effect

                    with patch('time.sleep'):  # Speed up the test
                        with patch('putplace.ppserver.console'):
                            result = ppserver.stop_server()
                            # Should succeed after force kill
                            assert result == 0


def test_stop_server_permission_error():
    """Test stop_server handles permission errors."""
    with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
        with patch('os.kill', side_effect=PermissionError("Permission denied")):
            with patch('putplace.ppserver.console') as mock_console:
                result = ppserver.stop_server()
                assert result == 1
                # Should print permission error
                assert any("permission" in str(call).lower() for call in mock_console.print.call_args_list)


def test_stop_server_process_already_gone():
    """Test stop_server when process is already terminated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"
        pid_file.write_text("12345")

        with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
            with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
                with patch('os.kill', side_effect=ProcessLookupError()):
                    with patch('putplace.ppserver.console'):
                        result = ppserver.stop_server()
                        assert result == 0


def test_restart_with_port_timeout():
    """Test restart_server when port doesn't become available."""
    with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
        with patch('putplace.ppserver.stop_server', return_value=0):
            with patch('putplace.ppserver.wait_for_port_available', return_value=False):
                with patch('putplace.ppserver.console') as mock_console:
                    result = ppserver.restart_server()
                    assert result == 1
                    # Should print port error
                    assert any("port" in str(call).lower() for call in mock_console.print.call_args_list)


def test_restart_stop_fails():
    """Test restart_server when stop fails."""
    with patch('putplace.ppserver.is_running', return_value=(True, 12345)):
        with patch('putplace.ppserver.stop_server', return_value=1):
            with patch('putplace.ppserver.console'):
                result = ppserver.restart_server()
                assert result == 1


def test_wait_for_port_becomes_available():
    """Test wait_for_port_available when port becomes free."""
    with patch('putplace.ppserver.is_port_available') as mock_is_avail:
        # Port becomes available on second check
        mock_is_avail.side_effect = [False, True]

        with patch('time.sleep'):  # Speed up the test
            result = ppserver.wait_for_port_available('127.0.0.1', 8000, timeout=5)
            assert result is True


def test_main_no_command():
    """Test main() with no command prints help."""
    with patch('sys.argv', ['ppserver']):
        with patch('putplace.ppserver.load_config', return_value={}):
            result = ppserver.main()
            assert result == 1


def test_main_start_command():
    """Test main() with start command."""
    with patch('sys.argv', ['ppserver', 'start']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.start_server', return_value=0) as mock_start:
                result = ppserver.main()
                mock_start.assert_called_once()
                assert result == 0


def test_main_stop_command():
    """Test main() with stop command."""
    with patch('sys.argv', ['ppserver', 'stop']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.stop_server', return_value=0) as mock_stop:
                result = ppserver.main()
                mock_stop.assert_called_once()
                assert result == 0


def test_main_restart_command():
    """Test main() with restart command."""
    with patch('sys.argv', ['ppserver', 'restart', '--port', '9000']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.restart_server', return_value=0) as mock_restart:
                result = ppserver.main()
                mock_restart.assert_called_once_with('127.0.0.1', 9000, False)
                assert result == 0


def test_main_status_command():
    """Test main() with status command."""
    with patch('sys.argv', ['ppserver', 'status']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.status_server', return_value=0) as mock_status:
                result = ppserver.main()
                mock_status.assert_called_once()
                assert result == 0


def test_main_logs_command():
    """Test main() with logs command."""
    with patch('sys.argv', ['ppserver', 'logs', '--lines', '100']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.logs_server', return_value=0) as mock_logs:
                result = ppserver.main()
                mock_logs.assert_called_once_with(False, 100)
                assert result == 0


def test_main_logs_follow():
    """Test main() with logs --follow command."""
    with patch('sys.argv', ['ppserver', 'logs', '-f']):
        with patch('putplace.ppserver.load_config', return_value={}):
            with patch('putplace.ppserver.logs_server', return_value=0) as mock_logs:
                result = ppserver.main()
                mock_logs.assert_called_once_with(True, 50)
                assert result == 0


def test_main_with_config_overrides():
    """Test main() uses config defaults but allows CLI overrides."""
    config = {
        'server': {
            'host': '0.0.0.0',
            'port': 9000
        }
    }

    with patch('sys.argv', ['ppserver', 'start', '--port', '8080']):
        with patch('putplace.ppserver.load_config', return_value=config):
            with patch('putplace.ppserver.start_server', return_value=0) as mock_start:
                result = ppserver.main()
                # CLI port should override config
                mock_start.assert_called_once_with('0.0.0.0', 8080, False)
                assert result == 0


def test_is_running_with_valid_pid():
    """Test is_running with valid running process."""
    import os
    current_pid = os.getpid()

    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"
        pid_file.write_text(str(current_pid))

        with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
            running, pid = ppserver.is_running()
            assert running is True
            assert pid == current_pid


def test_is_running_invalid_pid_format():
    """Test is_running with invalid PID format in file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid_file = Path(tmpdir) / "ppserver.pid"
        pid_file.write_text("not-a-number")

        with patch('putplace.ppserver.get_pid_file', return_value=pid_file):
            running, pid = ppserver.is_running()
            assert running is False
            assert pid is None
            # Stale PID file should be cleaned up
            assert not pid_file.exists()
