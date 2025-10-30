# PutPlace

[![Documentation Status](https://readthedocs.org/projects/putplace/badge/?version=latest)](https://putplace.readthedocs.io/en/latest/?badge=latest)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10-3.14](https://img.shields.io/badge/python-3.10--3.14-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4.4+-green.svg)](https://www.mongodb.com/)

A distributed file metadata storage and content deduplication system with SHA256-based clone detection, epoch file tracking, and multiple storage backends.

## Tech Stack

- **FastAPI** - Modern async web framework
- **MongoDB (PyMongo Async)** - Native async MongoDB driver (PyMongo 4.10+)
- **Argon2** - Modern password hashing algorithm
- **JWT** - JSON Web Tokens for authentication
- **uv** - Fast Python package manager
- **pytest** - Comprehensive test suite with 125+ tests

**Note:** This project uses PyMongo's native async support (introduced in PyMongo 4.9+) which provides better performance than the deprecated Motor library through direct asyncio implementation.

## Features

- 📁 **File Metadata Tracking** - Store file metadata with SHA256 hashes across your infrastructure
- 🔄 **Content Deduplication** - Upload files only once, deduplicated by SHA256
- 👥 **Clone Detection** - Track duplicate files across all users with epoch file identification
- 💾 **Multiple Storage Backends** - Local filesystem or AWS S3 for file content
- 🔐 **Dual Authentication** - API key (for clients) and JWT (for web UI)
- 🌐 **Interactive Web UI** - Tree-based file browser with clone visualization
- 🚀 **Production Ready** - Comprehensive tests, TOML configuration, graceful interrupt handling

## Documentation

**📖 Full documentation:** https://putplace.readthedocs.io/

- [Installation Guide](https://putplace.readthedocs.io/en/latest/installation.html)
- [Quick Start Guide](https://putplace.readthedocs.io/en/latest/quickstart.html)
- [Client Usage Guide](https://putplace.readthedocs.io/en/latest/client-guide.html)
- [API Reference](https://putplace.readthedocs.io/en/latest/api-reference.html)
- [Deployment Guide](https://putplace.readthedocs.io/en/latest/deployment.html)
- [Architecture Overview](https://putplace.readthedocs.io/en/latest/architecture.html)

## Quick Start

### Prerequisites

- Python 3.10 - 3.14
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- Docker (for MongoDB container)

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/jdrumgoole/putplace.git
cd putplace

# Complete setup (venv + dependencies + MongoDB)
invoke setup
source .venv/bin/activate

# Start MongoDB and server
invoke quickstart
```

The server will be available at http://localhost:8000

### Using the Client

#### Command-Line Interface (CLI)

```bash
# Scan a directory and upload metadata
ppclient --path /var/log

# Dry run (no upload)
ppclient --path /var/log --dry-run

# With API key
ppclient --path /var/log --api-key your-api-key-here
```

#### Graphical User Interface (GUI)

```bash
# Install with GUI support
pip install putplace[gui]

# Launch GUI client
ppgui
```

The GUI provides:
- 📁 Visual directory picker
- ⚙️ Settings panel (API key, server URL, hostname, IP)
- 📋 Exclude patterns manager
- 📊 Real-time upload progress
- 📝 Log output viewer

See the [Client Guide](https://putplace.readthedocs.io/en/latest/client-guide.html) for more details.

## Development

### Project Structure

```
putplace/
├── src/putplace/        # Main application code
│   ├── main.py          # FastAPI application
│   ├── models.py        # Pydantic models
│   ├── database.py      # MongoDB operations
│   ├── storage.py       # Storage backends (local/S3)
│   ├── auth.py          # API key authentication
│   ├── ppclient.py      # Client tool
│   └── ppserver.py      # Server manager
├── tests/               # Test suite (125+ tests, parallel execution)
├── docs/                # Documentation (Sphinx)
├── tasks.py             # Invoke task automation
└── pyproject.toml       # Project configuration
```

### Development Tasks

This project uses [invoke](https://www.pyinvoke.org/) for task automation:

```bash
# Setup
invoke setup              # Complete project setup
invoke setup-venv         # Create virtual environment only
invoke install            # Install dependencies

# MongoDB
invoke mongo-start        # Start MongoDB in Docker
invoke mongo-stop         # Stop MongoDB
invoke mongo-status       # Check MongoDB status

# Running
invoke serve              # Development server (auto-reload)
invoke serve-prod         # Production server (4 workers)
invoke quickstart         # Start MongoDB + dev server

# Testing
invoke test-all           # Run all tests (parallel, 4 workers, ~40% faster)
invoke test-all --parallel=False  # Run serially (most stable)
invoke test               # Run tests with coverage
invoke test-one tests/test_api.py  # Run specific test file
pytest -m "not integration"  # Skip integration tests
pytest -m integration     # Run only integration tests

# Code Quality
invoke lint               # Run ruff linter
invoke lint --fix         # Auto-fix linting issues
invoke format             # Format code with black
invoke typecheck          # Run mypy type checker
invoke check              # Run all checks (format, lint, typecheck, test)

# Other
invoke build              # Build package
invoke clean              # Clean build artifacts
invoke --list             # List all tasks
```

### Testing

The project includes 125+ comprehensive tests covering:
- Unit tests for models, API endpoints, database operations
- Integration tests with real server and MongoDB
- End-to-end tests including file upload and deduplication
- Console script installation tests
- Parallel test execution with isolated databases (4 workers, ~40% faster)

```bash
# Run all tests with coverage (parallel by default, ~40% faster)
invoke test-all

# Run tests serially (most stable)
invoke test-all --parallel=False

# Run with more workers
invoke test-all --workers=8

# Run specific test file
invoke test-one tests/test_models.py

# Run specific test function
invoke test-one tests/test_api.py::test_put_file_valid

# Skip integration tests (faster, no MongoDB required)
pytest -m "not integration"

# View coverage report
open htmlcov/index.html
```

**Parallel Testing:** Tests run in parallel by default using pytest-xdist with isolated databases per worker, preventing race conditions while providing significant speed improvements.

See [tests/README.md](tests/README.md) for detailed testing documentation.

### Server Manager (ppserver)

```bash
ppserver start            # Start server
ppserver start --port 8080  # Custom port
ppserver status           # Check status
ppserver stop             # Stop server
ppserver restart          # Restart server
ppserver logs             # View logs
ppserver logs --follow    # Follow logs
```

Files are stored in `~/.putplace/`:
- `ppserver.pid` - Process ID
- `ppserver.log` - Server logs

## Configuration

PutPlace uses TOML configuration files. Copy the example and customize:

```bash
cp ppserver.toml.example ppserver.toml
nano ppserver.toml
```

The server looks for `ppserver.toml` in:
1. `./ppserver.toml` (current directory)
2. `~/.config/putplace/ppserver.toml` (user config)
3. `/etc/putplace/ppserver.toml` (system config)

Environment variables override all settings. See [Configuration Guide](https://putplace.readthedocs.io/en/latest/configuration.html) for details.

## API Endpoints

Once the server is running:

- **Home**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **Health Check**: http://localhost:8000/health

### Key Endpoints

**File Operations:**
- `POST /put_file` - Store file metadata (requires API key)
- `GET /get_file/{sha256}` - Retrieve file by SHA256 (requires API key)
- `POST /upload_file/{sha256}` - Upload file content (requires API key)
- `GET /api/clones/{sha256}` - Get all file clones (requires JWT)
- `GET /api/my_files` - Get user's files (requires JWT)

**Authentication:**
- `POST /api/register` - Register new user
- `POST /api/login` - Login and get JWT token
- `POST /api_keys` - Create API key (requires JWT)
- `GET /api_keys` - List API keys (requires JWT)

See [API Reference](https://putplace.readthedocs.io/en/latest/api-reference.html) for complete endpoint documentation.

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Client    │         │   Client    │         │   Client    │
│  (Server A) │         │  (Server B) │         │  (Server C) │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │    X-API-Key Auth     │                        │
       └───────────┬───────────┴────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  PutPlace API   │
         │   (FastAPI)     │
         └────────┬────────┘
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼
   ┌────────────┐   ┌────────────┐
   │  MongoDB   │   │  Storage   │
   │ (Metadata) │   │  Backend   │
   └────────────┘   └────────────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
            ┌──────────┐  ┌──────────┐
            │  Local   │  │   AWS    │
            │   FS     │  │    S3    │
            └──────────┘  └──────────┘
```

See [Architecture Guide](https://putplace.readthedocs.io/en/latest/architecture.html) for detailed design documentation.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`invoke check`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

See [Development Guide](https://putplace.readthedocs.io/en/latest/development.html) for more details.

## License

See [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: https://putplace.readthedocs.io/
- **Issues**: https://github.com/jdrumgoole/putplace/issues
- **Source**: https://github.com/jdrumgoole/putplace

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.
