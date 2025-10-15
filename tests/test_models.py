"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from putplace.models import FileMetadata, FileMetadataResponse


def test_file_metadata_valid(sample_file_metadata):
    """Test creating valid FileMetadata."""
    metadata = FileMetadata(**sample_file_metadata)

    assert metadata.filepath == sample_file_metadata["filepath"]
    assert metadata.hostname == sample_file_metadata["hostname"]
    assert metadata.ip_address == sample_file_metadata["ip_address"]
    assert metadata.sha256 == sample_file_metadata["sha256"]
    assert metadata.file_size == sample_file_metadata["file_size"]
    assert metadata.file_mode == sample_file_metadata["file_mode"]
    assert metadata.file_uid == sample_file_metadata["file_uid"]
    assert metadata.file_gid == sample_file_metadata["file_gid"]
    assert metadata.file_mtime == sample_file_metadata["file_mtime"]
    assert metadata.file_atime == sample_file_metadata["file_atime"]
    assert metadata.file_ctime == sample_file_metadata["file_ctime"]
    assert isinstance(metadata.created_at, datetime)


def test_file_metadata_sha256_validation():
    """Test SHA256 hash validation."""
    # Valid SHA256 (64 characters)
    valid_data = {
        "filepath": "/test",
        "hostname": "host",
        "ip_address": "127.0.0.1",
        "sha256": "a" * 64,
        "file_size": 1024,
        "file_mode": 33188,
        "file_uid": 1000,
        "file_gid": 1000,
        "file_mtime": 1609459200.0,
        "file_atime": 1609459200.0,
        "file_ctime": 1609459200.0,
    }
    metadata = FileMetadata(**valid_data)
    assert len(metadata.sha256) == 64

    # Invalid: too short
    invalid_short = valid_data.copy()
    invalid_short["sha256"] = "a" * 63
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**invalid_short)
    assert "sha256" in str(exc_info.value)

    # Invalid: too long
    invalid_long = valid_data.copy()
    invalid_long["sha256"] = "a" * 65
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**invalid_long)
    assert "sha256" in str(exc_info.value)


def test_file_metadata_missing_fields():
    """Test that all required fields must be present."""
    valid_data = {
        "filepath": "/test",
        "hostname": "host",
        "ip_address": "127.0.0.1",
        "sha256": "a" * 64,
        "file_size": 1024,
        "file_mode": 33188,
        "file_uid": 1000,
        "file_gid": 1000,
        "file_mtime": 1609459200.0,
        "file_atime": 1609459200.0,
        "file_ctime": 1609459200.0,
    }

    # Missing filepath
    data = valid_data.copy()
    del data["filepath"]
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**data)
    assert "filepath" in str(exc_info.value)

    # Missing hostname
    data = valid_data.copy()
    del data["hostname"]
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**data)
    assert "hostname" in str(exc_info.value)

    # Missing ip_address
    data = valid_data.copy()
    del data["ip_address"]
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**data)
    assert "ip_address" in str(exc_info.value)

    # Missing sha256
    data = valid_data.copy()
    del data["sha256"]
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**data)
    assert "sha256" in str(exc_info.value)

    # Missing file_size
    data = valid_data.copy()
    del data["file_size"]
    with pytest.raises(ValidationError) as exc_info:
        FileMetadata(**data)
    assert "file_size" in str(exc_info.value)


def test_file_metadata_response_with_id(sample_file_metadata):
    """Test FileMetadataResponse includes MongoDB ID."""
    metadata = FileMetadataResponse(**sample_file_metadata, _id="507f1f77bcf86cd799439011")

    assert metadata.id == "507f1f77bcf86cd799439011"
    assert metadata.filepath == sample_file_metadata["filepath"]


def test_file_metadata_response_dict_conversion(sample_file_metadata):
    """Test converting response to dict includes _id."""
    metadata = FileMetadataResponse(**sample_file_metadata, _id="507f1f77bcf86cd799439011")

    # Check that model can be dumped
    data = metadata.model_dump()
    assert "sha256" in data


def test_file_metadata_created_at_auto():
    """Test that created_at is automatically set."""
    before = datetime.utcnow()
    metadata = FileMetadata(
        filepath="/test",
        hostname="host",
        ip_address="127.0.0.1",
        sha256="a" * 64,
        file_size=1024,
        file_mode=33188,
        file_uid=1000,
        file_gid=1000,
        file_mtime=1609459200.0,
        file_atime=1609459200.0,
        file_ctime=1609459200.0,
    )
    after = datetime.utcnow()

    assert before <= metadata.created_at <= after


def test_file_metadata_example_schema():
    """Test that example schema is valid."""
    example = FileMetadata.model_config["json_schema_extra"]["example"]

    # Should be valid
    metadata = FileMetadata(**example)
    assert metadata.filepath == example["filepath"]
    assert metadata.hostname == example["hostname"]
    assert metadata.ip_address == example["ip_address"]
    assert metadata.sha256 == example["sha256"]
