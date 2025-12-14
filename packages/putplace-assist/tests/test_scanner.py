"""Tests for file scanner."""

from pathlib import Path

import pytest

from putplace_assist.scanner import (
    calculate_sha256,
    collect_files,
    get_file_stats,
    matches_exclude_pattern,
    scan_file,
)


class TestSHA256:
    """Tests for SHA256 calculation."""

    def test_calculate_sha256(self, temp_test_dir: Path):
        """Test SHA256 calculation."""
        file_path = temp_test_dir / "file1.txt"
        sha256 = calculate_sha256(file_path)

        assert sha256 is not None
        assert len(sha256) == 64
        assert all(c in "0123456789abcdef" for c in sha256)

    def test_calculate_sha256_nonexistent(self, tmp_path: Path):
        """Test SHA256 of nonexistent file."""
        sha256 = calculate_sha256(tmp_path / "nonexistent")
        assert sha256 is None

    def test_calculate_sha256_consistent(self, temp_test_dir: Path):
        """Test SHA256 is consistent for same content."""
        file_path = temp_test_dir / "file1.txt"
        sha256_1 = calculate_sha256(file_path)
        sha256_2 = calculate_sha256(file_path)

        assert sha256_1 == sha256_2


class TestFileStats:
    """Tests for file stat retrieval."""

    def test_get_file_stats(self, temp_test_dir: Path):
        """Test getting file stats."""
        file_path = temp_test_dir / "file1.txt"
        stats = get_file_stats(file_path)

        assert stats is not None
        assert stats["file_size"] == len("Hello, World!")
        assert "file_mode" in stats
        assert "file_mtime" in stats

    def test_get_file_stats_nonexistent(self, tmp_path: Path):
        """Test stats of nonexistent file."""
        stats = get_file_stats(tmp_path / "nonexistent")
        assert stats is None


class TestExcludePatterns:
    """Tests for exclude pattern matching."""

    def test_no_patterns(self, temp_test_dir: Path):
        """Test with no patterns."""
        result = matches_exclude_pattern(
            temp_test_dir / "file1.txt",
            temp_test_dir,
            [],
        )
        assert result is False

    def test_exact_match(self, temp_test_dir: Path):
        """Test exact pattern match."""
        result = matches_exclude_pattern(
            temp_test_dir / "file1.txt",
            temp_test_dir,
            ["file1.txt"],
        )
        assert result is True

    def test_directory_match(self, temp_test_dir: Path):
        """Test directory pattern match."""
        result = matches_exclude_pattern(
            temp_test_dir / "subdir" / "file3.txt",
            temp_test_dir,
            ["subdir"],
        )
        assert result is True

    def test_wildcard_match(self, temp_test_dir: Path):
        """Test wildcard pattern match."""
        result = matches_exclude_pattern(
            temp_test_dir / "file1.txt",
            temp_test_dir,
            ["*.txt"],
        )
        assert result is True

    def test_wildcard_no_match(self, temp_test_dir: Path):
        """Test wildcard pattern no match."""
        (temp_test_dir / "test.log").write_text("log")
        result = matches_exclude_pattern(
            temp_test_dir / "test.log",
            temp_test_dir,
            ["*.txt"],
        )
        assert result is False

    def test_hidden_file_pattern(self, temp_test_dir: Path):
        """Test hidden file pattern."""
        result = matches_exclude_pattern(
            temp_test_dir / ".hidden",
            temp_test_dir,
            [".*"],
        )
        assert result is True


class TestCollectFiles:
    """Tests for file collection."""

    def test_collect_files_recursive(self, temp_test_dir: Path):
        """Test recursive file collection."""
        files = collect_files(temp_test_dir, recursive=True, exclude_patterns=[])
        assert len(files) == 4  # file1.txt, file2.txt, subdir/file3.txt, .hidden

    def test_collect_files_non_recursive(self, temp_test_dir: Path):
        """Test non-recursive file collection."""
        files = collect_files(temp_test_dir, recursive=False, exclude_patterns=[])
        assert len(files) == 3  # file1.txt, file2.txt, .hidden

    def test_collect_files_with_excludes(self, temp_test_dir: Path):
        """Test file collection with excludes."""
        files = collect_files(temp_test_dir, recursive=True, exclude_patterns=[".*"])
        assert len(files) == 3  # Excludes .hidden


@pytest.mark.asyncio
class TestScanFile:
    """Tests for async file scanning."""

    async def test_scan_file(self, temp_test_dir: Path):
        """Test scanning a single file."""
        file_path = temp_test_dir / "file1.txt"
        scanned = await scan_file(file_path)

        assert scanned is not None
        assert scanned.filepath == file_path
        assert scanned.file_size == len("Hello, World!")
        assert len(scanned.sha256) == 64

    async def test_scan_file_nonexistent(self, tmp_path: Path):
        """Test scanning nonexistent file."""
        scanned = await scan_file(tmp_path / "nonexistent")
        assert scanned is None
