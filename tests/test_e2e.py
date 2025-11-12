"""End-to-end integration tests for the complete system."""

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from pymongo import AsyncMongoClient

from putplace.config import Settings
from putplace.database import MongoDB
from putplace import ppclient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_file_metadata_stored(client, test_db, temp_test_dir, test_user_token: str):
    """Test that file metadata is properly stored and retrieved."""
    # Calculate hash and stats for a test file
    test_file = temp_test_dir / "file1.txt"
    sha256 = ppclient.calculate_sha256(test_file)
    file_stats = ppclient.get_file_stats(test_file)

    # Send file metadata via API with API key
    metadata = {
        "filepath": str(test_file),
        "hostname": "e2e-test-host",
        "ip_address": "10.0.0.1",
        "sha256": sha256,
        **file_stats,
    }

    response = await client.post(
        "/put_file",
        json=metadata,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 201

    # Retrieve via API (also requires API key)
    get_response = await client.get(
        f"/get_file/{sha256}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_response.status_code == 200

    data = get_response.json()
    assert data["sha256"] == sha256
    assert data["hostname"] == "e2e-test-host"
    assert data["ip_address"] == "10.0.0.1"
    assert data["file_size"] == file_stats["file_size"]
    assert data["file_mode"] == file_stats["file_mode"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_multiple_files_different_hosts(client, test_db, temp_test_dir, test_user_token: str):
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
        response = await client.post(
            "/put_file",
            json=metadata,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
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
async def test_e2e_duplicate_files_different_hosts(client, test_db, temp_test_dir, test_user_token: str):
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
        response = await client.post(
            "/put_file",
            json=metadata,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 201

    # Both records should exist
    count = await test_db.collection.count_documents({"sha256": sha256})
    assert count == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_file_content_upload_and_deduplication(client, test_db, temp_test_dir, test_user_token: str):
    """Test complete workflow including file content upload and deduplication.

    This test:
    1. Uploads file metadata
    2. Uploads file content when upload_required=True
    3. Tests deduplication (same content from different location)
    """
    # Create test files with known content
    test_file1 = temp_test_dir / "upload_test1.txt"
    test_file1.write_text("Test content for upload 1")

    test_file2 = temp_test_dir / "upload_test2.txt"
    test_file2.write_text("Test content for upload 2")

    # Calculate SHA256 hashes
    sha256_file1 = ppclient.calculate_sha256(test_file1)
    sha256_file2 = ppclient.calculate_sha256(test_file2)

    # Test 1: Upload first file metadata
    file_stats1 = ppclient.get_file_stats(test_file1)
    metadata1 = {
        "filepath": str(test_file1),
        "hostname": "e2e-test-host",
        "ip_address": "10.0.0.1",
        "sha256": sha256_file1,
        **file_stats1,
    }

    response1 = await client.post(
        "/put_file",
        json=metadata1,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response1.status_code == 201
    data1 = response1.json()
    assert data1["upload_required"] is True
    assert data1["upload_url"] == f"/upload_file/{sha256_file1}"

    # Upload file content
    with open(test_file1, "rb") as f:
        upload_response = await client.post(
            f"/upload_file/{sha256_file1}?hostname=e2e-test-host&filepath={test_file1}",
            files={"file": ("upload_test1.txt", f, "application/octet-stream")},
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
    assert upload_response.status_code == 200
    upload_data = upload_response.json()
    assert upload_data["status"] == "uploaded"
    assert upload_data["sha256"] == sha256_file1

    # Test 2: Upload second file
    file_stats2 = ppclient.get_file_stats(test_file2)
    metadata2 = {
        "filepath": str(test_file2),
        "hostname": "e2e-test-host",
        "ip_address": "10.0.0.1",
        "sha256": sha256_file2,
        **file_stats2,
    }

    response2 = await client.post(
        "/put_file",
        json=metadata2,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["upload_required"] is True

    with open(test_file2, "rb") as f:
        upload_response2 = await client.post(
            f"/upload_file/{sha256_file2}?hostname=e2e-test-host&filepath={test_file2}",
            files={"file": ("upload_test2.txt", f, "application/octet-stream")},
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
    assert upload_response2.status_code == 200

    # Test 3: Deduplication - upload same content from different location
    duplicate_file = temp_test_dir / "upload_test1_duplicate.txt"
    duplicate_file.write_text("Test content for upload 1")  # Same content as test_file1

    file_stats_dup = ppclient.get_file_stats(duplicate_file)
    metadata_dup = {
        "filepath": str(duplicate_file),
        "hostname": "e2e-test-host-2",
        "ip_address": "10.0.0.2",
        "sha256": sha256_file1,  # Same SHA256 as file1
        **file_stats_dup,
    }

    response_dup = await client.post(
        "/put_file",
        json=metadata_dup,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response_dup.status_code == 201
    data_dup = response_dup.json()
    # Should NOT require upload because content already exists
    assert data_dup["upload_required"] is False

    # Verify both metadata records exist
    count = await test_db.collection.count_documents({"sha256": sha256_file1})
    assert count == 2  # Original and duplicate


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_real_server_and_client_with_upload(worker_id):
    """Test complete workflow with real server and client subprocess.

    This test:
    1. Starts a real uvicorn server
    2. Creates test files
    3. Runs ppclient as subprocess to upload files
    4. Verifies metadata stored in database
    5. Verifies file content stored in storage backend
    6. Tests deduplication

    Note: Uses worker_id to ensure unique database names in parallel execution.
    """
    # Use worker_id to create unique database name for this test worker
    worker_suffix = worker_id if worker_id != "master" else "serial"
    # Setup: Create temporary directories for storage and test files
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        storage_path = temp_path / "storage"
        storage_path.mkdir()
        test_files_path = temp_path / "test_files"
        test_files_path.mkdir()

        # Create test files with known content
        test_file1 = test_files_path / "test1.txt"
        test_file1.write_text("Hello from PutPlace test file 1")

        test_file2 = test_files_path / "test2.txt"
        test_file2.write_text("Hello from PutPlace test file 2")

        # Calculate expected SHA256 hashes
        sha256_file1 = ppclient.calculate_sha256(test_file1)
        sha256_file2 = ppclient.calculate_sha256(test_file2)

        # Setup test database with unique name based on worker_id to avoid parallel test conflicts
        test_db_name = f"putplace_test_e2e_real_{worker_suffix}"
        test_collection = "file_metadata_test_e2e"
        mongo_client = AsyncMongoClient("mongodb://localhost:27017")
        test_db_instance = mongo_client[test_db_name]
        test_collection_obj = test_db_instance[test_collection]

        # Clean up database before test
        await test_collection_obj.drop()

        # Create test database instance for user creation
        test_db = MongoDB()
        test_db.client = mongo_client
        test_db.collection = test_collection_obj
        # Important: Use "users" collection (not "users_test") - this is what the server will use
        test_db.users_collection = test_db_instance["users"]

        # Create a test user with username/password
        from putplace.user_auth import get_password_hash
        from datetime import datetime
        test_username = "e2e_test_user"
        test_password = "e2e_test_password"
        hashed_password = get_password_hash(test_password)

        await test_db.users_collection.insert_one({
            "username": test_username,
            "email": "e2e_test@example.com",
            "hashed_password": hashed_password,
            "full_name": "E2E Test User",
            "is_active": True,
            "created_at": datetime.utcnow()
        })

        # Verify user was created
        user_doc = await test_db.users_collection.find_one({"username": test_username})
        assert user_doc is not None, "Test user not found in database after creation"

        # Start uvicorn server in subprocess
        # Find an available port dynamically to avoid conflicts in parallel testing
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            server_port = s.getsockname()[1]

        # Copy current environment and override with test settings
        env = os.environ.copy()
        env.update({
            "MONGODB_URL": "mongodb://localhost:27017",
            "MONGODB_DATABASE": test_db_name,
            "MONGODB_COLLECTION": test_collection,
            "STORAGE_BACKEND": "local",
            "STORAGE_PATH": str(storage_path),
        })

        # Create log files for server output
        server_stdout_file = temp_path / "server_stdout.log"
        server_stderr_file = temp_path / "server_stderr.log"

        with open(server_stdout_file, "w") as stdout_f, open(server_stderr_file, "w") as stderr_f:
            server_process = subprocess.Popen(
                ["uv", "run", "uvicorn", "putplace.main:app",
                 "--host", "127.0.0.1", "--port", str(server_port)],
                env=env,
                stdout=stdout_f,
                stderr=stderr_f,
                text=True,
            )

        try:
            # Wait for server to be ready
            server_ready = False
            for i in range(30):  # Try for 30 seconds
                try:
                    response = httpx.get(f"http://127.0.0.1:{server_port}/health", timeout=1.0)
                    if response.status_code == 200:
                        server_ready = True
                        break
                except (httpx.ConnectError, httpx.TimeoutException):
                    time.sleep(1)

            if not server_ready:
                # Server failed to start - get logs
                server_stdout = server_stdout_file.read_text() if server_stdout_file.exists() else ""
                server_stderr = server_stderr_file.read_text() if server_stderr_file.exists() else ""
                print(f"\n=== SERVER START FAILURE ===")
                print(f"\n=== SERVER STDOUT ===\n{server_stdout}")
                print(f"\n=== SERVER STDERR ===\n{server_stderr}")
            assert server_ready, "Server failed to start within 30 seconds"

            # Give server a moment to fully initialize
            time.sleep(1)

            # Verify server can see the API key
            health_response = httpx.get(f"http://127.0.0.1:{server_port}/health", timeout=5.0)
            assert health_response.status_code == 200, f"Server health check failed: {health_response.text}"

            # Debug: Check what settings the server is using
            settings_response = httpx.get(f"http://127.0.0.1:{server_port}/health", timeout=5.0)
            print(f"\n=== SERVER INFO ===")
            print(f"Health check response: {settings_response.json()}")

            # Test username/password authentication with server - login to get JWT token
            login_response = httpx.post(
                f"http://127.0.0.1:{server_port}/api/login",
                json={"username": test_username, "password": test_password},
                timeout=5.0,
            )
            if login_response.status_code != 200:
                print(f"\n=== LOGIN TEST FAILED ===")
                print(f"Status: {login_response.status_code}")
                print(f"Response: {login_response.text}")
                # Check if user is still in database
                check_user = await test_db.users_collection.find_one({"username": test_username})
                print(f"User still in DB: {check_user is not None}")
                if check_user:
                    print(f"User doc: {check_user}")

            assert login_response.status_code == 200, f"Login failed: {login_response.text}"
            jwt_token = login_response.json()["access_token"]

            # Test JWT authentication with put_file endpoint
            test_metadata = {
                "filepath": "/test/path.txt",
                "hostname": "test-host",
                "ip_address": "127.0.0.1",
                "sha256": "a" * 64,
                "file_size": 100,
                "file_mode": 33188,
                "file_uid": 1000,
                "file_gid": 1000,
                "file_mtime": 1000.0,
                "file_atime": 1000.0,
                "file_ctime": 1000.0,
            }
            auth_test_response = httpx.post(
                f"http://127.0.0.1:{server_port}/put_file",
                json=test_metadata,
                headers={"Authorization": f"Bearer {jwt_token}"},
                timeout=5.0,
            )
            if auth_test_response.status_code != 201:
                print(f"\n=== AUTH TEST FAILED ===")
                print(f"Status: {auth_test_response.status_code}")
                print(f"Response: {auth_test_response.text}")
                print(f"JWT Token: {jwt_token[:20]}...")

            assert auth_test_response.status_code == 201, f"JWT authentication failed: {auth_test_response.text}"

            # Test 1: Upload first file via client
            result = subprocess.run(
                [
                    "uv", "run", "python", "-m", "putplace.ppclient",
                    "--path", str(test_file1),
                    "--url", f"http://127.0.0.1:{server_port}/put_file",
                    "--username", test_username,
                    "--password", test_password,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Print client output for debugging
            print(f"\n=== CLIENT STDOUT ===\n{result.stdout}")
            print(f"\n=== CLIENT STDERR ===\n{result.stderr}")

            if result.returncode != 0:
                # Get server logs for debugging
                server_stdout = server_stdout_file.read_text() if server_stdout_file.exists() else ""
                server_stderr = server_stderr_file.read_text() if server_stderr_file.exists() else ""
                print(f"\n=== SERVER STDOUT ===\n{server_stdout}\n=== SERVER STDERR ===\n{server_stderr}")

            assert result.returncode == 0, f"Client failed with status {result.returncode}"

            # Verify metadata was stored in database
            await asyncio.sleep(1)  # Give database a moment to write
            doc1 = await test_collection_obj.find_one({"sha256": sha256_file1})
            assert doc1 is not None, "File metadata not found in database"
            assert doc1["sha256"] == sha256_file1
            assert doc1["file_size"] == test_file1.stat().st_size

            # Verify file content was stored in storage backend
            # Storage backend uses first 2 chars as subdirectory: storage/37/SHA256
            stored_file_path = storage_path / sha256_file1[:2] / sha256_file1
            assert stored_file_path.exists(), "File content not stored in storage backend"
            assert stored_file_path.read_text() == "Hello from PutPlace test file 1"

            # Test 2: Upload second file
            result2 = subprocess.run(
                [
                    "uv", "run", "python", "-m", "putplace.ppclient",
                    "--path", str(test_file2),
                    "--url", f"http://127.0.0.1:{server_port}/put_file",
                    "--username", test_username,
                    "--password", test_password,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert result2.returncode == 0, f"Client failed: {result2.stderr}"

            # Verify second file metadata
            await asyncio.sleep(1)
            doc2 = await test_collection_obj.find_one({"sha256": sha256_file2})
            assert doc2 is not None, "Second file metadata not found"
            assert doc2["sha256"] == sha256_file2

            # Verify second file content
            stored_file_path2 = storage_path / sha256_file2[:2] / sha256_file2
            assert stored_file_path2.exists(), "Second file content not stored"
            assert stored_file_path2.read_text() == "Hello from PutPlace test file 2"

            # Test 3: Deduplication - upload first file again from different location
            duplicate_file = test_files_path / "test1_duplicate.txt"
            duplicate_file.write_text("Hello from PutPlace test file 1")  # Same content as test1.txt

            result3 = subprocess.run(
                [
                    "uv", "run", "python", "-m", "putplace.ppclient",
                    "--path", str(duplicate_file),
                    "--url", f"http://127.0.0.1:{server_port}/put_file",
                    "--username", test_username,
                    "--password", test_password,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert result3.returncode == 0, f"Client failed on duplicate: {result3.stderr}"

            # Verify deduplication: should have 2 metadata records (file1 and duplicate)
            # but only one stored file content
            await asyncio.sleep(1)
            count = await test_collection_obj.count_documents({"sha256": sha256_file1})
            assert count == 2, f"Expected 2 metadata records for duplicate file, got {count}"

            # Storage should still have only one copy
            assert stored_file_path.exists(), "Original stored file should still exist"
            # Verify content hasn't changed
            assert stored_file_path.read_text() == "Hello from PutPlace test file 1"

        finally:
            # Cleanup: Stop server
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

            # Cleanup: Drop test database
            await test_collection_obj.drop()
            await test_db.users_collection.drop()
            await mongo_client.close()
