"""Tests for file scanner."""

from pathlib import Path

import pytest

from putplace_assist.scanner import (
    collect_files,
    get_file_stats,
    matches_exclude_pattern,
)


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
