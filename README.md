# putplace

A FastAPI-based file metadata storage service using MongoDB. Store and retrieve file metadata including filepath, hostname, IP address, and SHA256 hash.

## Features

- **File Metadata Storage** - Track file locations across your infrastructure with SHA256 hashes
- **Multiple Storage Backends** - Local filesystem or AWS S3 storage for file content
- **User Authentication** - JWT-based authentication with secure password hashing
- **API Key Management** - Create, list, revoke, and delete API keys via web interface
- **TOML Configuration** - Clean, structured configuration using `ppserver.toml`
- **Automatic Validation** - Server validates storage directory on startup with clear error messages
- **Client Tool** - `ppclient` for scanning directories and uploading metadata
- **Server Manager** - `ppserver` for easy server lifecycle management
- **Web Interface** - Beautiful web UI for authentication and API key management
- **Comprehensive Testing** - 115+ tests with full coverage of all features

## Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- Docker (for MongoDB container)

## Installation

Install uv if you haven't already:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Quick Setup (Recommended)

```bash
# Complete automated setup
invoke setup

# IMPORTANT: Activate virtual environment to use console scripts
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Verify console scripts are available
ppclient --help
ppserver --help

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

# Start MongoDB in Docker
invoke mongo-start

# Run the server
invoke serve
```

## Using the API

Once the server is running (`invoke quickstart` or `invoke serve`), the API will be available at:
- **Home Page**: http://localhost:8000 - Welcome page with quick start guide
- **Interactive Docs**: http://localhost:8000/docs - Swagger UI
- **Alternative Docs**: http://localhost:8000/redoc - ReDoc UI
- **Health Check**: http://localhost:8000/health

### Example Usage

Store file metadata:

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

Retrieve file metadata by SHA256:

```bash
curl http://localhost:8000/get_file/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## PutPlace Server Manager

The `ppserver` command provides an easy way to start, stop, and manage the PutPlace server.

### Basic Commands

```bash
# Start the server (default: localhost:8000)
ppserver start

# Start on custom port
ppserver start --port 8080

# Start on all interfaces (for remote access)
ppserver start --host 0.0.0.0

# Start with auto-reload (development)
ppserver start --reload

# Check server status
ppserver status

# Stop the server
ppserver stop

# Restart the server
ppserver restart

# Show server logs
ppserver logs

# Follow server logs in real-time
ppserver logs --follow
```

### Server Management

```bash
# Start server in background
ppserver start

# Check if running
ppserver status
# Output:
# ✓ Server is running (PID: 12345)
#   Log file: ~/.putplace/ppserver.log
#   PID file: ~/.putplace/ppserver.pid

# View recent logs
ppserver logs --lines 50

# Stop when done
ppserver stop
```

### Files and Locations

- **PID file**: `~/.putplace/ppserver.pid` - Stores server process ID
- **Log file**: `~/.putplace/ppserver.log` - Server output and errors

### Help

```bash
ppserver --help
ppserver start --help
```

## PutPlace Client

The `ppclient` tool scans directories or individual files, generates SHA256 hashes, and automatically sends file metadata to the server.

### Basic Usage

```bash
# Scan a directory
ppclient --path /var/log

# Scan a single file
ppclient --path /var/log/app.log

# Scan current directory
ppclient --path .

# Or using short form
ppclient -p /var/log
```

### Exclude Patterns

```bash
# Exclude .git directories
ppclient --path /home/user --exclude .git

# Exclude multiple patterns
ppclient --path /var/log --exclude .git --exclude "*.log" --exclude __pycache__

# Wildcard patterns
ppclient --path /app --exclude "*.pyc" --exclude "test_*"
```

### Advanced Options

```bash
# Dry run (scan without sending to server)
ppclient --path /var/log --dry-run

# Use custom server URL
ppclient --path /var/log --url http://remote-server:8000/put_file

# Use API key from command line
ppclient --path /var/log --api-key your-api-key-here

# Override hostname and IP
ppclient --path /var/log --hostname myserver --ip 10.0.0.5

# Verbose output
ppclient --path /var/log --verbose
```

### Configuration Files

The client supports configuration files to avoid repeating command-line options. The client automatically looks for config files in these locations:

1. `~/.ppclient.conf` (user home directory)
2. `.ppclient.conf` (current directory)

You can also specify a custom config file:

```bash
ppclient /var/log --config myconfig.conf
```

**Config file format (INI style):**

```ini
# .ppclient.conf
[DEFAULT]
# API endpoint URL
url = http://localhost:8000/put_file

# API key for authentication
api-key = your-api-key-here

# Exclude patterns (can be specified multiple times)
exclude = .git
exclude = __pycache__
exclude = *.pyc
exclude = node_modules

# Override hostname (optional)
hostname = myserver

# Override IP address (optional)
ip = 192.168.1.100
```

**Example usage with config file:**

```bash
# Copy the example config file
cp .ppclient.conf.example ~/.ppclient.conf

# Edit the config file with your settings
nano ~/.ppclient.conf

# Now you can run the client without specifying most options
ppclient --path /var/log

# Command-line options override config file settings
ppclient --path /var/log --url http://different-server:8000/put_file
```

**Note:** Command-line arguments take precedence over config file settings, allowing you to override specific options when needed.

### Example Output

```
PutPlace Client
  Path: /var/log
  Hostname: server01
  IP Address: 192.168.1.100
  API URL: http://localhost:8000/put_file
  Exclude patterns: .git, *.log

Scanning directory: /var/log
Found 42 files to process
Processing files... ━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 42/42

Results:
  Total files: 42
  Successful: 40
  Failed: 2
```

### Help

```bash
ppclient --help
```

## Development

This project uses [invoke](https://www.pyinvoke.org/) for task automation. Available tasks:

### Quick Start Tasks

```bash
# Complete project setup (venv, deps, .env)
invoke setup

# Start MongoDB and run dev server
invoke quickstart
```

### MongoDB Management

```bash
# Start MongoDB in Docker
invoke mongo-start

# Stop MongoDB
invoke mongo-stop

# Check MongoDB status
invoke mongo-status

# View MongoDB logs
invoke mongo-logs

# Follow MongoDB logs in real-time
invoke mongo-logs --follow

# Remove MongoDB container
invoke mongo-remove
```

### Running the Server

```bash
# Development server (with auto-reload)
invoke serve

# Custom host/port
invoke serve --host 0.0.0.0 --port 8080

# Production server (4 workers)
invoke serve-prod
```

### Testing

The project includes comprehensive tests:
- **Unit tests**: Models, API endpoints, database operations, client functions
- **Integration tests**: End-to-end tests with real server and MongoDB
- **Installation tests**: Console script installation and execution

```bash
# Run all tests with coverage
invoke test

# Run tests without coverage
invoke test --no-coverage

# Run specific test file
invoke test-one tests/test_models.py

# Run specific test function
invoke test-one tests/test_api.py::test_put_file_valid

# Run console script installation tests
pytest tests/test_console_scripts.py -v

# Skip integration tests (faster, no MongoDB required)
pytest -m "not integration"

# Run only integration tests (requires MongoDB)
pytest -m integration

# View coverage report
open htmlcov/index.html  # After running tests with coverage
```

**Test Files:**
- `test_models.py` - Pydantic model validation
- `test_api.py` - FastAPI endpoint tests
- `test_database.py` - MongoDB operations
- `test_client.py` - ppclient.py functionality
- `test_client_config.py` - Configuration file and argument parsing
- `test_console_scripts.py` - Installed console scripts (ppserver, ppclient)
- `test_e2e.py` - End-to-end integration tests

See [tests/README.md](tests/README.md) for detailed testing documentation.

### Code Quality

```bash
# Run linter
invoke lint

# Run linter and auto-fix issues
invoke lint --fix

# Format code
invoke format

# Check formatting without changes
invoke format --check

# Run type checker
invoke typecheck

# Run all checks (format, lint, typecheck, test)
invoke check
```

### Other Tasks

```bash
# Build the package
invoke build

# Clean build artifacts and caches
invoke clean

# List all available tasks
invoke --list
```

## Project Structure

```
putplace/
├── src/putplace/
│   ├── __init__.py      # Package initialization
│   ├── main.py          # FastAPI application and endpoints
│   ├── models.py        # Pydantic data models
│   ├── database.py      # MongoDB connection and operations
│   ├── config.py        # Application configuration
│   ├── auth.py          # API key authentication
│   ├── storage.py       # Storage backends (local/S3)
│   ├── ppclient.py      # Client tool for scanning directories
│   ├── ppserver.py      # Server management tool
│   └── scripts/
│       └── create_api_key.py  # Bootstrap API key creation
├── tests/               # Test suite
│   ├── __init__.py
│   ├── conftest.py      # Pytest fixtures
│   ├── test_models.py   # Model tests
│   ├── test_api.py      # API endpoint tests
│   ├── test_database.py # Database tests
│   ├── test_auth.py     # Authentication tests
│   ├── test_storage.py  # Storage backend tests
│   ├── test_client.py   # Client tests
│   ├── test_e2e.py      # End-to-end integration tests
│   └── README.md        # Test documentation
├── docs/                # Comprehensive documentation
│   ├── index.md         # Documentation index
│   ├── installation.md  # Installation guide
│   ├── quickstart.md    # Quick start guide
│   ├── api-reference.md # API documentation
│   ├── client-guide.md  # Client usage guide
│   ├── deployment.md    # Production deployment
│   └── ...              # More documentation
├── tasks.py             # Invoke tasks
├── pyproject.toml       # Project configuration
├── .env.example         # Environment variables template
└── README.md
```

## API Endpoints

### File Operations
- `POST /put_file` - Store file metadata (requires API key)
- `GET /get_file/{sha256}` - Retrieve file by SHA256 hash (requires API key)
- `POST /upload_file/{sha256}` - Upload file content (requires API key)

### Authentication & API Keys
- `POST /api/register` - Register a new user account
- `POST /api/login` - Login and get JWT token
- `POST /api_keys` - Create API key (requires JWT)
- `GET /api_keys` - List your API keys (requires JWT)
- `DELETE /api_keys/{key_id}` - Delete API key (requires JWT)
- `PUT /api_keys/{key_id}/revoke` - Revoke API key (requires JWT)

### Web Pages
- `GET /` - Home page with quick start guide
- `GET /login` - Login page
- `GET /register` - User registration page
- `GET /api_keys_page` - API key management interface
- `GET /health` - Health check endpoint

### Documentation
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## Troubleshooting

### Console Scripts Not Found

If you get `command not found: ppclient` or `command not found: ppserver`:

1. **Make sure you've activated the virtual environment:**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Verify the package is installed:**
   ```bash
   uv pip list | grep putplace
   ```

   If not installed, run:
   ```bash
   invoke install
   ```

3. **Check that the scripts are in your venv:**
   ```bash
   ls .venv/bin/ppclient .venv/bin/ppserver
   ```

4. **If using pyenv without a virtual environment**, you'll need to:
   ```bash
   pip install -e .
   pyenv rehash
   ```

### Import Errors

If you get import errors when running tests or the application, make sure:
- The virtual environment is activated
- All dependencies are installed: `invoke install`

## Configuration

### Using ppserver.toml (Recommended)

PutPlace uses TOML configuration files for better structure and clarity. The server looks for `ppserver.toml` in these locations:

1. `./ppserver.toml` (current directory)
2. `~/.config/putplace/ppserver.toml` (user config)
3. `/etc/putplace/ppserver.toml` (system config)

**Quick start:**

```bash
# Copy the example configuration
cp ppserver.toml.example ppserver.toml

# Edit with your settings
nano ppserver.toml
```

**Example ppserver.toml:**

```toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"
mongodb_collection = "file_metadata"

[storage]
# Storage backend: "local" or "s3"
backend = "local"
path = "./storage/files"

# For S3 storage:
# backend = "s3"
# s3_bucket_name = "my-bucket"
# s3_region_name = "us-east-1"

[aws]
# Optional: Use AWS profile or credentials
# profile = "default"
```

See [CONFIG.md](CONFIG.md) for comprehensive configuration documentation.

### Configuration Priority

Settings are loaded in this order (highest to lowest):

1. **Environment variables** - Override everything
2. **ppserver.toml** - Main configuration file
3. **.env file** - Legacy support (still works)
4. **Default values** - Built-in defaults

### Storage Backends

PutPlace supports multiple storage backends:

- **Local Storage** - Store files on local filesystem
- **S3 Storage** - Store files in AWS S3 buckets

The server validates storage configuration on startup and will fail fast with clear error messages if there are issues.

**Test AWS S3 setup:**

```bash
# Test S3 bucket creation and file upload
uv run python test_aws_s3.py

# Keep bucket for inspection
uv run python test_aws_s3.py --keep-bucket
```

See [test_aws_s3_README.md](test_aws_s3_README.md) for details.

### Environment Variables

You can override any configuration setting with environment variables:

```bash
# Override storage backend
export STORAGE_BACKEND=s3
export S3_BUCKET_NAME=my-bucket

# Override database
export MONGODB_URL=mongodb://prod-server:27017

ppserver start
```

Files:
- **ppserver.toml**: Server configuration (gitignored)
- **ppserver.toml.example**: Configuration template (committed)
- **CONFIG.md**: Comprehensive configuration guide
- **pyproject.toml**: Project metadata, dependencies, and tool configurations
- **tasks.py**: Development task definitions for invoke
- **tests/conftest.py**: Shared pytest fixtures
- **src/putplace/config.py**: Configuration loader with TOML support
