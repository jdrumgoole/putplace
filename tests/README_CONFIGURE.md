# Using putplace_configure for Programmatic Test Setup

This document demonstrates how to use `putplace_configure` in non-interactive mode to set up test environments programmatically.

## Overview

The `putplace_configure` script can be used in non-interactive mode to automatically configure PutPlace server environments. This is particularly useful for:

- Setting up isolated test environments
- Parallel test execution with pytest-xdist
- CI/CD pipelines
- Automated deployment scripts

## Helper Function

The `run_configure()` helper function in `conftest.py` provides a convenient way to run the configure script:

```python
from tests.conftest import run_configure
from pathlib import Path

success, message = run_configure(
    db_name="my_test_db",
    storage_path=Path("/tmp/storage"),
    config_path=Path("/tmp/ppserver.toml"),
    admin_username="admin",
    admin_email="admin@test.com",
    admin_password="secure_password",
    storage_backend="local",
)
```

## Examples

### Example 1: Local Storage Configuration

```python
import tempfile
from pathlib import Path
from tests.conftest import run_configure

with tempfile.TemporaryDirectory() as tmpdir:
    storage_path = Path(tmpdir) / "storage"
    config_path = Path(tmpdir) / "ppserver.toml"

    success, message = run_configure(
        db_name="test_local_db",
        storage_path=storage_path,
        config_path=config_path,
        admin_username="test_admin",
        admin_email="test@example.com",
        admin_password="test123",
        storage_backend="local",
        skip_checks=True,  # Skip MongoDB/AWS validation
    )

    if success:
        print(f"Configuration created at {config_path}")
        # Use the config...
```

### Example 2: S3 Storage Configuration

```python
success, message = run_configure(
    db_name="test_s3_db",
    storage_path=storage_path,
    config_path=config_path,
    admin_username="s3_admin",
    admin_email="s3@example.com",
    admin_password="s3_password",
    storage_backend="s3",
    s3_bucket="my-putplace-bucket",
    aws_region="eu-west-1",
    skip_checks=True,  # Skip AWS validation for testing
)
```

### Example 3: Multiple Worker Environments (pytest-xdist)

The `test_settings` fixture in `conftest.py` demonstrates how to create isolated configurations for parallel test workers:

```python
@pytest.fixture
def test_settings(worker_id: str, tmp_path_factory):
    """Configure isolated environment for each test worker."""
    db_name = f"putplace_test_{worker_id}"
    storage_path = tmp_path_factory.mktemp(f"storage_{worker_id}")
    config_path = tmp_path_factory.mktemp(f"config_{worker_id}") / "ppserver.toml"

    success, message = run_configure(
        db_name=db_name,
        storage_path=storage_path,
        config_path=config_path,
        admin_username=f"test_admin_{worker_id}",
        admin_email=f"test_admin_{worker_id}@test.local",
        admin_password="test_password_123",
        storage_backend="local",
        skip_checks=True,
    )

    return Settings(
        mongodb_url="mongodb://localhost:27017",
        mongodb_database=db_name,
        storage_path=str(storage_path),
    )
```

## Command Line Usage

You can also call `putplace_configure` directly from the command line:

```bash
# Local storage
putplace_configure --non-interactive \
  --skip-checks \
  --mongodb-url mongodb://localhost:27017 \
  --mongodb-database test_db \
  --admin-username test_admin \
  --admin-email test@test.com \
  --admin-password test123 \
  --storage-backend local \
  --storage-path /tmp/storage \
  --config-file /tmp/ppserver.toml

# S3 storage
putplace_configure --non-interactive \
  --skip-checks \
  --mongodb-url mongodb://localhost:27017 \
  --mongodb-database test_db \
  --admin-username s3_admin \
  --admin-email s3@test.com \
  --admin-password s3pass \
  --storage-backend s3 \
  --s3-bucket my-bucket \
  --aws-region eu-west-1 \
  --config-file /tmp/ppserver.toml
```

## Parameters

### Required Parameters
- `db_name`: MongoDB database name
- `storage_path`: Path to storage directory
- `config_path`: Path to output configuration file

### Optional Parameters
- `admin_username`: Admin username (default: "test_admin")
- `admin_email`: Admin email (default: "test@test.local")
- `admin_password`: Admin password (default: "test_password_123")
- `storage_backend`: "local" or "s3" (default: "local")
- `s3_bucket`: S3 bucket name (required if storage_backend="s3")
- `aws_region`: AWS region (default: "eu-west-1")
- `skip_checks`: Skip MongoDB/AWS validation (default: True for tests)

## Generated Configuration

The configure script creates a `ppserver.toml` file with secure defaults:

```toml
[server]
host = "127.0.0.1"  # Localhost only for security
port = 8000
workers = 1

[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "test_db"
mongodb_collection = "file_metadata"

[storage]
backend = "local"
path = "/tmp/storage"

# For S3:
# backend = "s3"
# s3_bucket_name = "my-bucket"
# s3_region_name = "eu-west-1"
```

## Test Examples

See `tests/test_configure_helper.py` for comprehensive examples:

- `test_configure_local_storage()` - Basic local storage setup
- `test_configure_s3_storage()` - S3 storage configuration
- `test_configure_multiple_workers()` - Parallel worker setup
- `test_configure_generates_valid_toml()` - TOML validation

## Benefits

1. **Consistency**: Same configuration process for tests and production
2. **Isolation**: Each test worker gets independent configuration
3. **Reproducibility**: Deterministic test environments
4. **Speed**: `--skip-checks` flag bypasses slow validation
5. **Flexibility**: Easy to switch between local and S3 storage

## Notes

- The configure script creates admin users automatically
- Storage directories are created on application startup if they don't exist
- Use `--skip-checks` in tests to avoid MongoDB/AWS validation delays
- Each pytest-xdist worker should have a unique database name to avoid conflicts
