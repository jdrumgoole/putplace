# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PutPlace is a FastAPI-based file metadata storage service using MongoDB. It provides REST API endpoints to store and retrieve file metadata (filepath, hostname, IP address, SHA256 hash).

**Tech Stack:**
- **FastAPI**: Async REST API framework
- **MongoDB (PyMongo Async)**: Native async MongoDB driver (PyMongo 4.10+)
- **uv**: Fast Python package installer and virtual environment manager
- **invoke**: Task automation (replaces Makefiles)
- **pytest**: Testing framework with coverage reporting
- **ruff**: Fast linter and formatter
- **mypy**: Static type checker

**Note on MongoDB Driver:**
This project uses PyMongo's native async support (introduced in PyMongo 4.9+), which provides better performance than the deprecated Motor library. PyMongo async implements asyncio support directly rather than using a thread pool, resulting in improved latency and throughput.

## Setup

### Prerequisites
- Python 3.10+
- Docker (for MongoDB container)

### Quick Setup (Automated)
```bash
# Complete setup: venv, dependencies, .env file
invoke setup

# Activate virtual environment
source .venv/bin/activate

# Start MongoDB and run server
invoke quickstart
```

### Manual Setup
```bash
# Create virtual environment
invoke setup-venv
source .venv/bin/activate

# Install dependencies
invoke install

# Create .env file
invoke setup-env

# Start MongoDB
invoke mongo-start

# Run server
invoke serve
```

## Authentication & Initial Setup

### Automatic Admin User Creation

PutPlace automatically creates an admin user on first startup using a **hybrid approach**:

**Method 1: Environment Variables (Production)**
```bash
# Add to .env file
PUTPLACE_ADMIN_USERNAME=admin
PUTPLACE_ADMIN_PASSWORD=your-secure-password
PUTPLACE_ADMIN_EMAIL=admin@example.com
```

**Method 2: Random Password Generation (Development)**

If no environment variables are set, PutPlace will:
- Generate a secure random password on first startup
- Display credentials once in server logs
- Write credentials to `/tmp/putplace_initial_creds.txt`

**Important:**
- Admin user is only created if no users exist
- Generated passwords are 21+ characters (cryptographically secure)
- Password must be at least 8 characters when using environment variables
- Delete the credentials file after saving the password

### API Keys

Create API keys for programmatic access:
```bash
# Bootstrap first API key
python -m putplace.scripts.create_api_key --name "admin-key"

# After admin user exists, can create via API
curl -X POST http://localhost:8000/api_keys \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"name": "my-key"}'
```

### Configuration Wizard

Use the configuration wizard to set up PutPlace after installation:

```bash
# Interactive configuration
invoke configure
# Or: uv run python -m putplace.scripts.putplace_configure

# Non-interactive (for automation)
uv run python -m putplace.scripts.putplace_configure --non-interactive \
  --admin-username admin \
  --admin-email admin@example.com \
  --storage-backend local

# Standalone AWS tests (v0.5.2+)
uv run python -m putplace.scripts.putplace_configure S3   # Test S3 access
uv run python -m putplace.scripts.putplace_configure SES  # Test SES access
invoke configure --test-mode=S3                  # Via invoke
invoke configure --test-mode=SES                 # Via invoke

# Test in specific region
uv run python -m putplace.scripts.putplace_configure S3 --aws-region us-west-2
```

**What it does:**
- Creates admin user with secure password
- Tests MongoDB connection
- Checks AWS S3/SES access (optional)
- Configures storage backend (local or S3)
- Generates `ppserver.toml` configuration file

**Note:** The configure script uses `pty=True` in the invoke task to properly handle readline/terminal input for better backspace behavior.

## Common Commands

All development tasks are managed through `invoke` (see tasks.py):

### Quick Start
- `invoke setup` - Complete project setup (venv, deps, .env)
- `invoke quickstart` - Start MongoDB and run dev server

### MongoDB Management
- `invoke mongo-start` - Start MongoDB in Docker (creates container if needed)
- `invoke mongo-stop` - Stop MongoDB container
- `invoke mongo-status` - Check MongoDB container status
- `invoke mongo-logs` - View MongoDB logs
- `invoke mongo-logs --follow` - Follow MongoDB logs
- `invoke mongo-remove` - Remove MongoDB container

### Running the API Server
- `invoke serve` - Run development server (auto-reload enabled)
- `invoke serve --host 0.0.0.0 --port 8080` - Custom host/port
- `invoke serve-prod` - Run production server (4 workers)

**API Endpoints:**
- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /put_file` - Store file metadata
- `GET /get_file/{sha256}` - Retrieve file by SHA256 hash
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation

### Testing
- `invoke test-all` - Run all tests with coverage (parallel, 4 workers, ~40% faster)
- `invoke test-all --parallel=False` - Run tests serially (most stable)
- `invoke test-all --workers=8` - Run with 8 parallel workers (faster)
- `invoke test` - Run all tests with coverage (uses pytest defaults)
- `invoke test --no-coverage` - Run tests without coverage
- `invoke test-one <path>` - Run specific test file/function
  - Example: `invoke test-one tests/test_models.py::test_file_metadata_valid`
- `pytest -m "not integration"` - Skip integration tests (no MongoDB needed)
- `pytest -m integration` - Run only integration tests

**Parallel Testing:**
- Tests run in parallel by default (4 workers) using pytest-xdist
- Each worker gets isolated database (e.g., `putplace_test_gw0`, `putplace_test_gw1`)
- Prevents database race conditions during parallel execution
- ~40% faster than serial execution (16s vs 26s)
- Test databases automatically cleaned up after test session

**Test Organization:**
- `test_models.py` - Pydantic model validation tests
- `test_api.py` - FastAPI endpoint tests (async)
- `test_database.py` - MongoDB operation tests (async)
- `test_client.py` - ppclient.py unit tests
- `test_admin_creation.py` - Admin user creation tests
- `test_e2e.py` - End-to-end integration tests (marked with @pytest.mark.integration)
- `conftest.py` - Shared fixtures (test_db, client, sample_file_metadata, temp_test_dir)

### Code Quality
- `invoke lint` - Run ruff linter
- `invoke lint --fix` - Auto-fix linting issues
- `invoke format` - Format code with ruff
- `invoke format --check` - Check formatting without changes
- `invoke typecheck` - Run mypy type checker
- `invoke check` - Run all checks (format, lint, typecheck, test)

### Build & Clean
- `invoke build` - Build the package
- `invoke clean` - Remove build artifacts and caches

## Project Structure

```
src/putplace/
  ├── __init__.py          Package initialization
  ├── main.py              FastAPI application and endpoints
  ├── models.py            Pydantic data models
  ├── database.py          MongoDB connection and operations
  └── config.py            Application configuration
tests/                     Test suite (comprehensive unit and integration tests)
  ├── __init__.py
  ├── conftest.py          Pytest fixtures
  ├── test_models.py       Pydantic model tests
  ├── test_api.py          FastAPI endpoint tests
  ├── test_database.py     MongoDB operation tests
  ├── test_client.py       Client functionality tests
  ├── test_e2e.py          End-to-end integration tests
  └── README.md            Test documentation
docs/                      Documentation
ppclient.py                Client tool for directory scanning
tasks.py                   Invoke task definitions
pyproject.toml             Project config, dependencies, tool settings
.env.example               Environment variables template
```

## API Usage

### Store File Metadata
```bash
curl -X POST http://localhost:8000/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/var/log/app.log",
    "hostname": "server01",
    "ip_address": "192.168.1.100",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'
```

### Retrieve File Metadata
```bash
curl http://localhost:8000/get_file/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## PutPlace Client (ppclient.py)

The `ppclient.py` is a command-line tool for scanning directories and sending file metadata to the server.

### Key Features
- Recursively scans directories
- Calculates SHA256 hashes for each file
- Auto-detects hostname and IP address
- Supports exclude patterns (wildcards, directory names)
- Progress bars and colored output (using rich library)
- Dry-run mode for testing
- Parallel processing with progress tracking

### Basic Usage
```bash
# Scan directory and send to server
python ppclient.py /path/to/scan

# With exclude patterns
python ppclient.py /path --exclude .git --exclude "*.log" --exclude __pycache__

# Dry run (don't send to server)
python ppclient.py /path --dry-run

# Custom server URL
python ppclient.py /path --url http://remote-server:8000/put_file
```

### Implementation Details
- **File scanning**: Uses `Path.rglob("*")` for recursive traversal
- **SHA256 calculation**: Chunked reading (8KB) to handle large files
- **Pattern matching**: Supports wildcards via `fnmatch` module
- **Relative path matching**: Patterns match against paths relative to start directory
- **HTTP client**: Uses `httpx` library for async-compatible requests
- **Progress display**: Rich library for terminal UI
- **Error handling**: Continues on file read errors, reports at end

### Exclude Pattern Logic
Patterns are matched against:
1. Full relative path from start directory
2. Individual path components (directory/file names)
3. Wildcard patterns using fnmatch syntax

Examples:
- `.git` - Excludes any .git directory
- `*.log` - Excludes all .log files
- `test_*` - Excludes files/dirs starting with test_
- `__pycache__` - Excludes Python cache directories

### Command-line Arguments
- `path` (required): Starting directory to scan
- `--exclude`, `-e`: Exclude pattern (repeatable)
- `--url`: API endpoint (default: http://localhost:8000/put_file)
- `--hostname`: Override auto-detected hostname
- `--ip`: Override auto-detected IP address
- `--dry-run`: Scan without sending to server
- `--verbose`, `-v`: Verbose output

## Development Conventions

### Testing
- **Test files**: `test_*.py` in `tests/` directory
- **Test functions**: Must start with `test_`
- **Async tests**: Use `@pytest.mark.asyncio` decorator
- **Integration tests**: Use `@pytest.mark.integration` marker
- **Fixtures**: Defined in `tests/conftest.py`
  - `test_db` - MongoDB test instance (auto-cleanup)
  - `client` - FastAPI test client
  - `sample_file_metadata` - Example metadata dict
  - `temp_test_dir` - Temporary directory with test files
- **Coverage**: Configured in pyproject.toml, reports in `htmlcov/`
- **Running tests**:
  - All tests: `invoke test` or `pytest`
  - Skip integration: `pytest -m "not integration"`
  - Integration only: `pytest -m integration` (requires MongoDB)
- **Test database**: Uses `putplace_test` database, automatically cleaned up

### Code Style
- Line length: 100 characters
- Python 3.10+ required
- Ruff handles linting and formatting
- Type hints required (mypy strict mode enabled)
- Tests exempt from type checking strictness

### Adding Dependencies
Add to `[project.dependencies]` in pyproject.toml, then:
```bash
uv pip install -e '.[dev]'
```

### Adding New Invoke Tasks
Edit `tasks.py` and add decorated functions:
```python
@task
def mytask(c, arg=None):
    """Task description."""
    c.run("command")
```

## Database Schema

### MongoDB Collection: `file_metadata`

**Document Structure:**
```json
{
  "_id": "ObjectId",
  "filepath": "string",
  "hostname": "string",
  "ip_address": "string",
  "sha256": "string (64 chars)",
  "created_at": "datetime"
}
```

**Indexes:**
- `sha256` - Single field index for efficient lookups
- `hostname + filepath` - Compound index for host-based queries

## Configuration

Environment variables (see .env.example):
- `MONGODB_URL` - MongoDB connection string (default: mongodb://localhost:27017)
- `MONGODB_DATABASE` - Database name (default: putplace)
- `MONGODB_COLLECTION` - Collection name (default: file_metadata)
- `API_TITLE` - API title for docs
- `API_VERSION` - API version
- `API_DESCRIPTION` - API description

Configuration is managed via Pydantic Settings in `src/putplace/config.py`
- Use uv run to run python and other program inside the uv enviroment
- when you update the docs update both the README.md and the ./docs directory
- when running tests use uv invoke test-all
- when you bump versions and commit changes, add a git tag at the same time
- when you use uv run you don't need to set the python path before hand
- use the invoke targets to start and stop the sever rather than doing it manually
- the default region for AWS us eu-west-1