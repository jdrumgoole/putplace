"""End-to-end integration tests for the complete system."""

import asyncio
from pathlib import Path

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from putplace.config import Settings
from putplace.database import MongoDB

import ppclient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_file_metadata_stored(client, test_db, temp_test_dir):
    """Test that file metadata is properly stored and retrieved."""
    # Calculate hash and stats for a test file
    test_file = temp_test_dir / "file1.txt"
    sha256 = ppclient.calculate_sha256(test_file)
    file_stats = ppclient.get_file_stats(test_file)

    # Send file metadata via API
    metadata = {
        "filepath": str(test_file),
        "hostname": "e2e-test-host",
        "ip_address": "10.0.0.1",
        "sha256": sha256,
        **file_stats,
    }

    response = await client.post("/put_file", json=metadata)
    assert response.status_code == 201

    # Retrieve via API
    get_response = await client.get(f"/get_file/{sha256}")
    assert get_response.status_code == 200

    data = get_response.json()
    assert data["sha256"] == sha256
    assert data["hostname"] == "e2e-test-host"
    assert data["ip_address"] == "10.0.0.1"
    assert data["file_size"] == file_stats["file_size"]
    assert data["file_mode"] == file_stats["file_mode"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_multiple_files_different_hosts(client, test_db, temp_test_dir):
    """Test storing metadata from multiple files and hosts."""
    files_to_process = [
        (temp_test_dir / "file1.txt", "host1", "10.0.0.1"),
        (temp_test_dir / "file2.log", "host2", "10.0.0.2"),
        (temp_test_dir / "subdir" / "file3.txt", "host1", "10.0.0.1"),
    ]

    for file_path, hostname, ip_address in files_to_process:
        sha256 = ppclient.calculate_sha256(file_path)
        file_stats = ppclient.get_file_stats(file_path)
        metadata = {
            "filepath": str(file_path),
            "hostname": hostname,
            "ip_address": ip_address,
            "sha256": sha256,
            **file_stats,
        }
        response = await client.post("/put_file", json=metadata)
        assert response.status_code == 201

    # Verify we can query by hostname
    count = await test_db.collection.count_documents({"hostname": "host1"})
    assert count == 2  # file1.txt and file3.txt

    count = await test_db.collection.count_documents({"hostname": "host2"})
    assert count == 1  # file2.log


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_client_sha256_calculation(temp_test_dir):
    """Test that client correctly calculates SHA256 hashes."""
    # Test with known content
    test_file = temp_test_dir / "file1.txt"
    sha256 = ppclient.calculate_sha256(test_file)

    # Verify it's a valid SHA256 (64 hex characters)
    assert sha256 is not None
    assert len(sha256) == 64
    assert all(c in "0123456789abcdef" for c in sha256)

    # Known SHA256 for "Hello World"
    expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
    assert sha256 == expected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_duplicate_files_different_hosts(client, test_db, temp_test_dir):
    """Test that same file from different hosts creates multiple records."""
    test_file = temp_test_dir / "file1.txt"
    sha256 = ppclient.calculate_sha256(test_file)
    file_stats = ppclient.get_file_stats(test_file)

    # Store same file from two different hosts
    for hostname, ip_address in [("host1", "10.0.0.1"), ("host2", "10.0.0.2")]:
        metadata = {
            "filepath": str(test_file),
            "hostname": hostname,
            "ip_address": ip_address,
            "sha256": sha256,
            **file_stats,
        }
        response = await client.post("/put_file", json=metadata)
        assert response.status_code == 201

    # Both records should exist
    count = await test_db.collection.count_documents({"sha256": sha256})
    assert count == 2
