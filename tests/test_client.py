"""Tests for ppclient.py functionality."""

import tempfile
from pathlib import Path

import pytest

import ppclient


def test_get_hostname():
    """Test that hostname detection works."""
    hostname = ppclient.get_hostname()
    assert hostname is not None
    assert isinstance(hostname, str)
    assert len(hostname) > 0


def test_get_ip_address():
    """Test that IP address detection works."""
    ip = ppclient.get_ip_address()
    assert ip is not None
    assert isinstance(ip, str)
    # Should be valid IP format
    parts = ip.split(".")
    assert len(parts) == 4


def test_calculate_sha256_valid_file():
    """Test SHA256 calculation for a valid file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Hello World")
        temp_path = Path(f.name)

    try:
        sha256 = ppclient.calculate_sha256(temp_path)
        assert sha256 is not None
        assert len(sha256) == 64
        # Verify it's a valid hex string
        assert all(c in "0123456789abcdef" for c in sha256)

        # Known SHA256 for "Hello World"
        expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
        assert sha256 == expected
    finally:
        temp_path.unlink()


def test_calculate_sha256_nonexistent_file():
    """Test SHA256 calculation for non-existent file."""
    nonexistent = Path("/nonexistent/file.txt")
    sha256 = ppclient.calculate_sha256(nonexistent)
    assert sha256 is None


def test_calculate_sha256_empty_file():
    """Test SHA256 calculation for empty file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        # Write nothing
        temp_path = Path(f.name)

    try:
        sha256 = ppclient.calculate_sha256(temp_path)
        assert sha256 is not None
        assert len(sha256) == 64

        # Known SHA256 for empty file
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert sha256 == expected
    finally:
        temp_path.unlink()


def test_calculate_sha256_large_file():
    """Test SHA256 calculation for large file (tests chunked reading)."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        # Write more than 8KB (the chunk size)
        f.write("x" * 10000)
        temp_path = Path(f.name)

    try:
        sha256 = ppclient.calculate_sha256(temp_path)
        assert sha256 is not None
        assert len(sha256) == 64
    finally:
        temp_path.unlink()


def test_get_file_stats_valid_file():
    """Test getting file stats for a valid file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("Test content")
        temp_path = Path(f.name)

    try:
        stats = ppclient.get_file_stats(temp_path)
        assert stats is not None
        assert isinstance(stats, dict)

        # Check all required fields are present
        assert "file_size" in stats
        assert "file_mode" in stats
        assert "file_uid" in stats
        assert "file_gid" in stats
        assert "file_mtime" in stats
        assert "file_atime" in stats
        assert "file_ctime" in stats

        # Verify types and values
        assert isinstance(stats["file_size"], int)
        assert stats["file_size"] >= 0
        assert isinstance(stats["file_mode"], int)
        assert isinstance(stats["file_uid"], int)
        assert isinstance(stats["file_gid"], int)
        assert isinstance(stats["file_mtime"], float)
        assert isinstance(stats["file_atime"], float)
        assert isinstance(stats["file_ctime"], float)
    finally:
        temp_path.unlink()


def test_get_file_stats_nonexistent_file():
    """Test getting file stats for non-existent file."""
    nonexistent = Path("/nonexistent/file.txt")
    stats = ppclient.get_file_stats(nonexistent)
    assert stats is None


def test_matches_exclude_pattern_exact_match(temp_test_dir):
    """Test exclude pattern with exact directory name."""
    git_dir = temp_test_dir / ".git"
    assert ppclient.matches_exclude_pattern(git_dir, temp_test_dir, [".git"])


def test_matches_exclude_pattern_wildcard(temp_test_dir):
    """Test exclude pattern with wildcards."""
    log_file = temp_test_dir / "file2.log"
    assert ppclient.matches_exclude_pattern(log_file, temp_test_dir, ["*.log"])

    txt_file = temp_test_dir / "file1.txt"
    assert not ppclient.matches_exclude_pattern(txt_file, temp_test_dir, ["*.log"])


def test_matches_exclude_pattern_subdirectory(temp_test_dir):
    """Test exclude pattern in subdirectories."""
    nested_file = temp_test_dir / "subdir" / "file3.txt"

    # Should match if subdirectory is in pattern
    assert ppclient.matches_exclude_pattern(nested_file, temp_test_dir, ["subdir"])


def test_matches_exclude_pattern_no_patterns(temp_test_dir):
    """Test that no patterns means nothing is excluded."""
    any_file = temp_test_dir / "file1.txt"
    assert not ppclient.matches_exclude_pattern(any_file, temp_test_dir, [])


def test_matches_exclude_pattern_multiple_patterns(temp_test_dir):
    """Test multiple exclude patterns."""
    patterns = [".git", "*.log", "__pycache__"]

    git_file = temp_test_dir / ".git" / "config"
    assert ppclient.matches_exclude_pattern(git_file, temp_test_dir, patterns)

    log_file = temp_test_dir / "file2.log"
    assert ppclient.matches_exclude_pattern(log_file, temp_test_dir, patterns)

    pycache_file = temp_test_dir / "__pycache__" / "module.pyc"
    assert ppclient.matches_exclude_pattern(pycache_file, temp_test_dir, patterns)

    txt_file = temp_test_dir / "file1.txt"
    assert not ppclient.matches_exclude_pattern(txt_file, temp_test_dir, patterns)


def test_matches_exclude_pattern_prefix_wildcard(temp_test_dir):
    """Test wildcard prefix patterns."""
    # Create test file
    test_file = temp_test_dir / "test_something.py"
    test_file.write_text("test")

    assert ppclient.matches_exclude_pattern(test_file, temp_test_dir, ["test_*"])

    normal_file = temp_test_dir / "file1.txt"
    assert not ppclient.matches_exclude_pattern(normal_file, temp_test_dir, ["test_*"])


def test_scan_directory_counts_files(temp_test_dir):
    """Test that scan_directory correctly counts files."""
    total, successful, failed = ppclient.scan_directory(
        temp_test_dir,
        exclude_patterns=[],
        hostname="testhost",
        ip_address="127.0.0.1",
        api_url="http://test/put_file",
        dry_run=True,
    )

    # Should find file1.txt, file2.log, subdir/file3.txt, .git/config, __pycache__/module.pyc
    assert total == 5
    assert successful == 5
    assert failed == 0


def test_scan_directory_with_excludes(temp_test_dir):
    """Test that scan_directory respects exclude patterns."""
    total, successful, failed = ppclient.scan_directory(
        temp_test_dir,
        exclude_patterns=[".git", "__pycache__"],
        hostname="testhost",
        ip_address="127.0.0.1",
        api_url="http://test/put_file",
        dry_run=True,
    )

    # Should exclude .git/config and __pycache__/module.pyc
    # Remaining: file1.txt, file2.log, subdir/file3.txt
    assert total == 3
    assert successful == 3
    assert failed == 0


def test_scan_directory_nonexistent_path():
    """Test scanning non-existent directory."""
    nonexistent = Path("/nonexistent/directory")
    total, successful, failed = ppclient.scan_directory(
        nonexistent,
        exclude_patterns=[],
        hostname="testhost",
        ip_address="127.0.0.1",
        api_url="http://test/put_file",
        dry_run=True,
    )

    assert total == 0
    assert successful == 0
    assert failed == 0


def test_scan_directory_file_not_directory():
    """Test scanning a file instead of directory."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_file = Path(f.name)

    try:
        total, successful, failed = ppclient.scan_directory(
            temp_file,
            exclude_patterns=[],
            hostname="testhost",
            ip_address="127.0.0.1",
            api_url="http://test/put_file",
            dry_run=True,
        )

        assert total == 0
        assert successful == 0
        assert failed == 0
    finally:
        temp_file.unlink()


def test_scan_directory_empty_directory():
    """Test scanning empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = Path(tmpdir)

        total, successful, failed = ppclient.scan_directory(
            empty_dir,
            exclude_patterns=[],
            hostname="testhost",
            ip_address="127.0.0.1",
            api_url="http://test/put_file",
            dry_run=True,
        )

        assert total == 0
        assert successful == 0
        assert failed == 0
