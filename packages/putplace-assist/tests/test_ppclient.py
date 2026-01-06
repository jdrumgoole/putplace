"""Tests for ppclient.py pp_assist daemon client functionality."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from putplace_assist import ppclient


def test_signal_handler():
    """Test signal handler sets interrupted flag."""
    import importlib
    # Reload module to reset global state
    importlib.reload(ppclient)

    # Initially not interrupted
    assert ppclient.interrupted is False

    # Call signal handler
    ppclient.signal_handler(None, None)

    # Should set interrupted flag
    assert ppclient.interrupted is True

    # Reset for other tests
    ppclient.interrupted = False


def test_check_daemon_running_success():
    """Test checking if daemon is running - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "running"}
        mock_get.return_value = mock_response

        result = ppclient.check_daemon_running("http://localhost:8765")

        assert result is True
        mock_get.assert_called_once_with(
            "http://localhost:8765/health",
            timeout=5.0
        )


def test_check_daemon_running_failure():
    """Test checking if daemon is running - connection failure."""
    with patch('httpx.get') as mock_get:
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = ppclient.check_daemon_running("http://localhost:8765")

        assert result is False


def test_get_daemon_status_success():
    """Test getting daemon status - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "running",
            "uptime": 123.45,
            "version": "0.1.0"
        }
        mock_get.return_value = mock_response

        result = ppclient.get_daemon_status("http://localhost:8765")

        assert result is not None
        assert result["status"] == "running"
        assert result["uptime"] == 123.45


def test_get_daemon_status_failure():
    """Test getting daemon status - connection failure."""
    with patch('httpx.get') as mock_get:
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = ppclient.get_daemon_status("http://localhost:8765")

        assert result is None


def test_register_path_success():
    """Test registering a path with daemon - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "path": "/test/path",
            "recursive": True
        }
        mock_post.return_value = mock_response

        result = ppclient.register_path(
            "http://localhost:8765",
            Path("/test/path"),
            recursive=True
        )

        assert result is not None
        assert result["id"] == 1
        assert result["path"] == "/test/path"


def test_register_path_failure():
    """Test registering a path with daemon - failure case."""
    with patch('httpx.post') as mock_post:
        import httpx
        mock_post.side_effect = httpx.RequestError("Connection error")

        result = ppclient.register_path(
            "http://localhost:8765",
            Path("/test/path")
        )

        assert result is None


def test_add_exclude_pattern_success():
    """Test adding exclude pattern - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = ppclient.add_exclude_pattern(
            "http://localhost:8765",
            "*.log"
        )

        assert result is True


def test_add_exclude_pattern_failure():
    """Test adding exclude pattern - failure case."""
    with patch('httpx.post') as mock_post:
        import httpx
        mock_post.side_effect = httpx.RequestError("Connection error")

        result = ppclient.add_exclude_pattern(
            "http://localhost:8765",
            "*.log"
        )

        assert result is False


def test_configure_server_success():
    """Test configuring server - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = ppclient.configure_server(
            "http://localhost:8765",
            name="test-server",
            url="http://server:8100",
            username="testuser",
            password="testpass"
        )

        assert result is True


def test_login_success():
    """Test login - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Login successful"
        }
        mock_post.return_value = mock_response

        result = ppclient.login(
            "http://localhost:8765",
            "test@example.com",
            "password123"
        )

        assert result is True


def test_login_failure():
    """Test login - invalid credentials."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid credentials"}
        mock_post.return_value = mock_response

        result = ppclient.login(
            "http://localhost:8765",
            "test@example.com",
            "wrongpassword"
        )

        assert result is False


def test_register_user_success():
    """Test user registration - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Registration successful"
        }
        mock_post.return_value = mock_response

        result = ppclient.register(
            "http://localhost:8765",
            username="newuser",
            email="new@example.com",
            password="password123",
            full_name="New User"
        )

        assert result is True


def test_trigger_scan_success():
    """Test triggering scan - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = ppclient.trigger_scan("http://localhost:8765", path_id=1)

        assert result is True


def test_trigger_uploads_success():
    """Test triggering uploads - success case."""
    with patch('httpx.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "queued": 10,
            "already_queued": 0
        }
        mock_post.return_value = mock_response

        result = ppclient.trigger_uploads(
            "http://localhost:8765",
            upload_content=True
        )

        assert result is not None
        assert result["queued"] == 10


def test_get_queue_status_success():
    """Test getting queue status - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_pending": 10,
            "uploading": 2,
            "completed": 5,
            "failed": 0
        }
        mock_get.return_value = mock_response

        result = ppclient.get_queue_status("http://localhost:8765")

        assert result is not None
        assert result["total_pending"] == 10
        assert result["uploading"] == 2


def test_get_sha256_status_success():
    """Test getting SHA256 status - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_files": 100,
            "calculated": 75,
            "pending": 25,
            "calculating": True
        }
        mock_get.return_value = mock_response

        result = ppclient.get_sha256_status("http://localhost:8765")

        assert result is not None
        assert result["total_files"] == 100
        assert result["calculated"] == 75


def test_get_file_stats_success():
    """Test getting file stats - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_files": 100,
            "total_bytes": 1024000
        }
        mock_get.return_value = mock_response

        result = ppclient.get_file_stats("http://localhost:8765")

        assert result is not None
        assert result["total_files"] == 100
        assert result["total_bytes"] == 1024000


def test_format_bytes():
    """Test byte formatting utility."""
    assert ppclient.format_bytes(0) == "0 B"
    assert ppclient.format_bytes(1023) == "1023.0 B"
    assert ppclient.format_bytes(1024) == "1.0 KB"
    assert ppclient.format_bytes(1024 * 1024) == "1.0 MB"
    assert ppclient.format_bytes(1024 * 1024 * 1024) == "1.0 GB"
    assert ppclient.format_bytes(1024 * 1024 * 1024 * 1024) == "1.0 TB"


def test_get_servers_success():
    """Test getting configured servers - success case."""
    with patch('httpx.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "servers": [
                {"id": 1, "url": "http://server1:8100", "is_default": True},
                {"id": 2, "url": "http://server2:8100", "is_default": False}
            ]
        }
        mock_get.return_value = mock_response

        result = ppclient.get_servers("http://localhost:8765")

        assert len(result) == 2
        assert result[0]["url"] == "http://server1:8100"
        assert result[0]["is_default"] is True
