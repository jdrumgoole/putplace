# putplace

A FastAPI-based file metadata storage service using MongoDB. Store and retrieve file metadata including filepath, hostname, IP address, and SHA256 hash.

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

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

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
- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

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

## PutPlace Client

The `ppclient.py` tool scans directories, generates SHA256 hashes, and automatically sends file metadata to the server.

### Basic Usage

```bash
# Scan current directory
python ppclient.py .

# Scan specific directory
python ppclient.py /var/log

# After installation, you can also use:
ppclient /var/log
```

### Exclude Patterns

```bash
# Exclude .git directories
python ppclient.py /home/user --exclude .git

# Exclude multiple patterns
python ppclient.py /var/log --exclude .git --exclude "*.log" --exclude __pycache__

# Wildcard patterns
python ppclient.py /app --exclude "*.pyc" --exclude "test_*"
```

### Advanced Options

```bash
# Dry run (scan without sending to server)
python ppclient.py /var/log --dry-run

# Use custom server URL
python ppclient.py /var/log --url http://remote-server:8000/put_file

# Override hostname and IP
python ppclient.py /var/log --hostname myserver --ip 10.0.0.5

# Verbose output
python ppclient.py /var/log --verbose
```

### Configuration Files

The client supports configuration files to avoid repeating command-line options. The client automatically looks for config files in these locations:

1. `~/.ppclient.conf` (user home directory)
2. `.ppclient.conf` (current directory)

You can also specify a custom config file:

```bash
python ppclient.py /var/log --config myconfig.conf
```

**Config file format (INI style):**

```ini
# .ppclient.conf
[DEFAULT]
# API endpoint URL
url = http://localhost:8000/put_file

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

# Now you can run the client without specifying options
python ppclient.py /var/log

# Command-line options override config file settings
python ppclient.py /var/log --url http://different-server:8000/put_file
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
python ppclient.py --help
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

```bash
# Run all tests with coverage
invoke test

# Run tests without coverage
invoke test --no-coverage

# Run specific test file
invoke test-one tests/test_models.py

# Run specific test function
invoke test-one tests/test_api.py::test_put_file_valid

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
│   └── config.py        # Application configuration
├── tests/               # Test suite
│   ├── __init__.py
│   ├── conftest.py      # Pytest fixtures
│   ├── test_models.py   # Model tests
│   ├── test_api.py      # API endpoint tests
│   ├── test_database.py # Database tests
│   ├── test_client.py   # Client tests
│   ├── test_e2e.py      # End-to-end integration tests
│   └── README.md        # Test documentation
├── docs/                # Documentation
├── ppclient.py          # Client tool for scanning directories
├── tasks.py             # Invoke tasks
├── pyproject.toml       # Project configuration
├── .env.example         # Environment variables template
└── README.md
```

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /put_file` - Store file metadata
- `GET /get_file/{sha256}` - Retrieve file by SHA256 hash
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation

## Configuration

Environment variables (configure in `.env`):

- `MONGODB_URL` - MongoDB connection string (default: `mongodb://localhost:27017`)
- `MONGODB_DATABASE` - Database name (default: `putplace`)
- `MONGODB_COLLECTION` - Collection name (default: `file_metadata`)
- `API_TITLE` - API title for documentation
- `API_VERSION` - API version
- `API_DESCRIPTION` - API description

Files:
- **pyproject.toml**: Project metadata, dependencies, and tool configurations
- **tasks.py**: Development task definitions for invoke
- **tests/conftest.py**: Shared pytest fixtures
- **src/putplace/config.py**: Pydantic settings for configuration management
