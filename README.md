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
- **AWS SES** - Email service for user registration confirmation
- **boto3** - AWS SDK for Python (SES integration)
- **uv** - Fast Python package manager
- **pytest** - Comprehensive test suite with 125+ tests

**Note:** This project uses PyMongo's native async support (introduced in PyMongo 4.9+) which provides better performance than the deprecated Motor library through direct asyncio implementation.

## Features

- 📁 **File Metadata Tracking** - Store file metadata with SHA256 hashes across your infrastructure
- 🔄 **Content Deduplication** - Upload files only once, deduplicated by SHA256
- 👥 **Clone Detection** - Track duplicate files across all users with epoch file identification
- 💾 **Multiple Storage Backends** - Local filesystem or AWS S3 for file content
- 🔐 **Flexible Authentication** - Username/password login with JWT tokens and Google OAuth
- 📧 **Email Confirmation** - Secure email verification for new user registrations via AWS SES
- 🌐 **Google Sign-In Integration** - One-click authentication with Google accounts
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

# Complete setup (venv + dependencies)
invoke setup

# Configure the server (create admin user, check AWS, set storage backend)
source .venv/bin/activate
invoke configure
# Or directly: putplace_configure

# Start MongoDB and server
invoke quickstart
```

The server will be available at http://localhost:8000

### Configuration Tool

PutPlace includes a configuration wizard to set up your server after installation:

```bash
# Interactive configuration (recommended for first-time setup)
putplace_configure

# Non-interactive configuration (for automation/CI/CD)
putplace_configure --non-interactive \
  --admin-username admin \
  --admin-email admin@example.com \
  --storage-backend local

# With S3 storage
putplace_configure --non-interactive \
  --admin-username admin \
  --admin-email admin@example.com \
  --storage-backend s3 \
  --s3-bucket my-putplace-bucket \
  --aws-region us-west-2

# Skip validation checks (useful for testing)
putplace_configure --skip-checks

# Standalone AWS tests (new in v0.5.2)
putplace_configure S3                        # Test S3 access
putplace_configure SES                       # Test SES access
putplace_configure S3 --aws-region us-west-2 # Test in specific region

# Via invoke task
invoke configure --test-mode=S3
invoke configure --test-mode=SES
```

**Features:**
- ✅ **Creates admin user** with secure password generation
- ✅ **Tests MongoDB connection** before configuration
- ✅ **Checks AWS S3 and SES access** (optional)
- ✅ **Standalone S3/SES tests** - Test AWS credentials independently
- ✅ **Configures storage backend** (local or S3)
- ✅ **Generates `ppserver.toml`** configuration file
- ✅ **Non-interactive mode** for automation
- ✅ **Beautiful terminal UI** with rich formatting (when available)

**Interactive Mode:**
- Step-by-step wizard with prompts
- Automatic password generation option
- AWS connectivity checks
- Storage backend selection based on availability

**Non-Interactive Mode:**
- Perfect for automation and CI/CD pipelines
- All configuration via command-line flags
- Optional validation checks can be skipped
- Secure password auto-generation

### Using the Client

#### Command-Line Interface (CLI)

```bash
# Scan a directory and upload metadata
ppclient --path /var/log

# Dry run (no upload)
ppclient --path /var/log --dry-run

# With authentication
ppclient --path /var/log --username admin --password your-password
```

#### Graphical User Interface (GUI)

Cross-platform desktop application built with Electron and TypeScript:

```bash
# Run the packaged app (recommended - correct menu names)
invoke gui-electron

# Or run in development mode with DevTools
invoke gui-electron --dev

# Package the app into a distributable .app bundle
invoke gui-electron-package

# Test installation/uninstallation flow (manual)
invoke gui-electron-test-install

# Test installation/uninstallation flow (automated)
invoke gui-electron-test-install --automated

# Build only (compile TypeScript)
invoke gui-electron-build

# Run unpacked development version (menu shows "Electron")
invoke gui-electron --packaged=False
```

The Electron GUI provides:
- 🖥️ Native cross-platform desktop application (Windows, macOS, Linux)
- 📁 Native OS directory picker
- 🔐 **Dual authentication**: Username/password OR Google Sign-In
- 🌐 **Google OAuth integration**: One-click sign-in with Google accounts
- 👁️ Password visibility toggle
- ⚙️ Settings panel with persistence (server URL, hostname, IP)
- 📋 Exclude patterns manager with wildcards support
- 📊 Real-time progress tracking with statistics
- 📝 Color-coded log output (success, error, warning, info)
- 💾 Settings saved between sessions (localStorage)
- 🔐 Secure IPC communication
- 🎨 Custom menu bar with proper branding

See the [Client Guide](https://putplace.readthedocs.io/en/latest/client-guide.html) and [OAuth Setup Guide](OAUTH_SETUP.md) for more details.

## Development

### Project Structure

```
putplace/
├── src/putplace/        # Main application code
│   ├── main.py          # FastAPI application
│   ├── models.py        # Pydantic models
│   ├── database.py      # MongoDB operations
│   ├── storage.py       # Storage backends (local/S3)
│   ├── auth.py          # Authentication (JWT & API keys)
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
invoke setup              # Complete project setup (venv + dependencies)
invoke configure          # Configure server (interactive wizard)
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

# GUI Client
invoke gui-electron-build # Build Electron desktop app
invoke gui-electron       # Run Electron desktop app
invoke gui-electron --dev # Run Electron app with DevTools

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

You can also use `invoke configure` or `putplace_configure` for guided setup. Environment variables can override TOML settings if needed. See [Configuration Guide](https://putplace.readthedocs.io/en/latest/configuration.html) for details.

## API Endpoints

Once the server is running:

- **Home**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **Health Check**: http://localhost:8000/health

### Key Endpoints

**File Operations:**
- `POST /put_file` - Store file metadata (requires JWT or API key)
- `GET /get_file/{sha256}` - Retrieve file by SHA256 (requires JWT or API key)
- `POST /upload_file/{sha256}` - Upload file content (requires JWT or API key)
- `GET /api/clones/{sha256}` - Get all file clones (requires JWT)
- `GET /api/my_files` - Get user's files (requires JWT)

**Authentication:**
- `POST /api/register` - Register new user (sends email confirmation)
- `GET /api/confirm-email?token=...` - Confirm email address
- `POST /api/login` - Login and get JWT token
- `POST /api/auth/google` - Google Sign-In authentication
- `GET /api/oauth/config` - Get OAuth configuration
- `POST /api_keys` - Create API key (requires JWT)
- `GET /api_keys` - List API keys (requires JWT)

**Email Confirmation:**

PutPlace uses email confirmation for user registration via AWS SES:

1. **Registration**: Users register with username, email, and password
2. **Email Sent**: Confirmation email sent with secure 24-hour link
3. **Confirmation**: User clicks link to activate account
4. **Cleanup**: Unconfirmed registrations auto-deleted after 24 hours

Configure email settings in `ppserver.toml`:
```toml
[email]
sender_email = "noreply@putplace.org"  # SES verified sender
base_url = "http://localhost:8000"     # Server base URL for confirmation links
aws_region = "eu-west-1"               # AWS SES region

[server]
registration_enabled = true  # Set to false to disable new user registration
```

Or via environment variables:
```bash
PUTPLACE_SENDER_EMAIL=noreply@putplace.org
PUTPLACE_BASE_URL=https://putplace.example.com
PUTPLACE_EMAIL_AWS_REGION=eu-west-1
PUTPLACE_REGISTRATION_ENABLED=true  # false to disable registration
```

**Disabling Registration:**

To disable new user registration (e.g., in production), you can:
- Set `registration_enabled = false` in `ppserver.toml` under `[server]` section
- Set environment variable `PUTPLACE_REGISTRATION_ENABLED=false`
- No redeployment needed - just edit the config file and restart the server

**For AWS App Runner:**

Use the provided Python script to toggle registration without redeployment:

```bash
# Set your service ARN (one time)
export APPRUNNER_SERVICE_ARN="arn:aws:apprunner:region:account:service/putplace/xxx"

# Disable registration
invoke toggle-registration --action=disable

# Re-enable registration later
invoke toggle-registration --action=enable

# Or use the script directly
uv run python -m putplace.scripts.toggle_registration disable
uv run python -m putplace.scripts.toggle_registration enable
```

The script will:
- Update the `PUTPLACE_REGISTRATION_ENABLED` environment variable
- Trigger an automatic redeployment (2-3 minutes)
- Preserve all other environment variables

**Note**: AWS SES must be out of sandbox mode to send to any email address.

**Google Sign-In Setup:**

To enable Google Sign-In in the Electron client and web interface, see [GOOGLE_OAUTH_SETUP.md](GOOGLE_OAUTH_SETUP.md) for detailed configuration instructions.

Quick summary:
1. Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/)
2. Add Client ID to `ppserver.toml` or set `GOOGLE_CLIENT_ID` environment variable
3. Restart the server
4. Google Sign-In button will appear automatically in the Electron client

See [API Reference](https://putplace.readthedocs.io/en/latest/api-reference.html) for complete endpoint documentation.

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Client    │         │   Client    │         │   Client    │
│  (Server A) │         │  (Server B) │         │  (Server C) │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │    JWT Bearer Auth    │                        │
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
