# Development Guide

Guide for contributing to PutPlace development.

## Getting Started

### Prerequisites

- Python 3.10 - 3.14
- MongoDB 4.4 or higher
- Git
- uv (recommended) or pip

### Clone Repository

```bash
git clone https://github.com/jdrumgoole/putplace.git
cd putplace
```

### Set Up Development Environment

#### Using uv (Recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with all dependencies
uv pip install -e ".[dev]"
```

#### Using pip

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install in development mode
pip install -e ".[dev]"
```

### Start MongoDB

```bash
# Ubuntu/Debian
sudo systemctl start mongod

# macOS (Homebrew)
brew services start mongodb-community

# Docker
docker run -d --name putplace-mongodb -p 27017:27017 mongo:6
```

### Create Configuration

```bash
# Copy example configuration
cp ppserver.toml.example ppserver.toml

# Edit configuration
nano ppserver.toml
```

**Development ppserver.toml:**
```toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace_dev"

[storage]
backend = "local"
path = "/tmp/putplace-dev"

[api]
title = "PutPlace API (Development)"
```

**Note:** You can also use environment variables for development:
```bash
export LOG_LEVEL=DEBUG
```

### Run Server

```bash
# Run with auto-reload
uvicorn putplace.main:app --reload --host 127.0.0.1 --port 8000

# Or use the development script
python -m putplace.main
```

Server will be available at: http://localhost:8000

### Create First API Key

```bash
# In another terminal
python -m putplace.scripts.create_api_key --name "dev-key"

# Save the displayed API key
export PUTPLACE_API_KEY="your-api-key-here"
```

### Test Client

```bash
# Test with dry run
python ppclient.py /tmp --dry-run

# Test actual upload
echo "test" > /tmp/test.txt
python ppclient.py /tmp/test.txt
```

## Project Structure

```
putplace/
├── src/
│   └── putplace/
│       ├── __init__.py
│       ├── main.py              # FastAPI application
│       ├── config.py            # Configuration (Pydantic settings)
│       ├── models.py            # Pydantic models
│       ├── database.py          # MongoDB interface
│       ├── auth.py              # API key authentication
│       ├── storage.py           # Storage backends
│       └── scripts/
│           └── create_api_key.py
├── tests/
│   ├── __init__.py
│   ├── test_api.py              # API endpoint tests
│   ├── test_client.py           # Client tests
│   ├── test_database.py         # Database tests
│   ├── test_auth.py             # Authentication tests
│   └── test_storage.py          # Storage backend tests
├── docs/                        # Documentation
├── ppclient.py                  # Command-line client
├── pyproject.toml               # Project metadata & dependencies
├── setup.py                     # Setup script
├── ppserver.toml.example        # Example server configuration
├── .gitignore
├── LICENSE
└── README.md
```

## Running Tests

### Run All Tests

```bash
# Run all tests (parallel execution by default via invoke)
invoke test-all

# Run all tests with pytest directly
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=putplace --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Parallel Test Execution

PutPlace supports parallel test execution using pytest-xdist for faster test runs:

```bash
# Run tests in parallel with 4 workers (default via invoke)
invoke test-all

# Run serially (most stable, useful for debugging)
invoke test-all --parallel=False

# Run with more workers
invoke test-all --workers=8

# Run directly with pytest-xdist
pytest -n 4 --dist loadscope
```

**Per-Worker Database Isolation:**
- Each worker gets its own isolated database (e.g., `putplace_test_gw0`, `putplace_test_gw1`)
- Prevents race conditions in parallel execution
- ~40% faster than serial execution with 4 workers
- Databases are automatically cleaned up after test session

### Run Specific Tests

```bash
# Run single test file
pytest tests/test_api.py

# Run single test function
pytest tests/test_api.py::test_put_file

# Run tests matching pattern
pytest -k "test_api"

# Run tests with specific marker
pytest -m "slow"
```

### Test Coverage

PutPlace aims for 100% test coverage.

```bash
# Check current coverage
pytest --cov=putplace --cov-report=term-missing

# Generate HTML report
pytest --cov=putplace --cov-report=html
```

### Writing Tests

**Example test:**

```python
import pytest
from fastapi.testclient import TestClient
from putplace.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
async def api_key(db):
    """Create test API key."""
    from putplace.auth import APIKeyAuth
    auth = APIKeyAuth(db)
    key, metadata = await auth.create_api_key("test-key")
    return key

def test_put_file(client, api_key):
    """Test file metadata upload."""
    metadata = {
        "filepath": "/tmp/test.txt",
        "hostname": "test-host",
        "ip_address": "127.0.0.1",
        "sha256": "a" * 64,
        "file_size": 1234,
        "file_mode": 33188,  # Regular file with rw-r--r-- (0644)
        "file_uid": 1000,
        "file_gid": 1000,
        "file_mtime": 1609459200.0,  # Unix timestamp
        "file_atime": 1609459200.0,
        "file_ctime": 1609459200.0,
    }

    response = client.post(
        "/put_file",
        json=metadata,
        headers={"X-API-Key": api_key},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filepath"] == "/tmp/test.txt"
    assert data["upload_required"] in [True, False]
```

## Code Quality

### Linting and Formatting

PutPlace uses Ruff for linting and formatting.

```bash
# Check code style
ruff check .

# Fix auto-fixable issues
ruff check . --fix

# Format code
ruff format .

# Check without modifying
ruff format . --check
```

### Type Checking

```bash
# Install mypy
pip install mypy

# Run type checking
mypy src/putplace
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

**Create .pre-commit-config.yaml:**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
```

## Development Workflow

### 1. Create Feature Branch

```bash
# Update main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/my-new-feature
```

### 2. Make Changes

```bash
# Make your changes
nano src/putplace/main.py

# Test changes
pytest

# Format code
ruff format .

# Check code style
ruff check .
```

### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "Add feature: Description of feature

- Detail 1
- Detail 2
- Detail 3"
```

### 4. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=putplace

# Ensure 100% coverage for new code
```

### 5. Push and Create PR

```bash
# Push to GitHub
git push origin feature/my-new-feature

# Create pull request on GitHub
# Include description of changes
# Reference any related issues
```

## Adding New Features

### Adding New API Endpoint

1. **Define Pydantic model** (if needed):

   ```python
   # src/putplace/models.py
   from pydantic import BaseModel, Field

   class MyNewModel(BaseModel):
       name: str = Field(..., min_length=1)
       value: int = Field(..., ge=0)
   ```

2. **Add database method** (if needed):

   ```python
   # src/putplace/database.py
   async def my_new_operation(self, data: dict) -> str:
       """Perform new database operation."""
       result = await self.collection.insert_one(data)
       return str(result.inserted_id)
   ```

3. **Add endpoint**:

   ```python
   # src/putplace/main.py
   @app.post("/my_endpoint", response_model=MyNewModel)
   async def my_endpoint(
       data: MyNewModel,
       db: MongoDB = Depends(get_db),
       api_key: dict = Depends(get_current_api_key),
   ):
       """My new endpoint."""
       # Implementation
       return data
   ```

4. **Write tests**:

   ```python
   # tests/test_my_feature.py
   def test_my_endpoint(client, api_key):
       response = client.post(
           "/my_endpoint",
           json={"name": "test", "value": 42},
           headers={"X-API-Key": api_key},
       )
       assert response.status_code == 200
   ```

5. **Update documentation**:

   ```bash
   # docs/api-reference.md
   # Add endpoint documentation
   ```

### Adding New Storage Backend

1. **Implement storage backend**:

   ```python
   # src/putplace/storage.py
   class MyStorageBackend(StorageBackend):
       """My custom storage backend."""

       def __init__(self, config: str):
           self.config = config

       async def store(self, sha256: str, content: bytes) -> bool:
           # Implementation
           return True

       async def retrieve(self, sha256: str) -> Optional[bytes]:
           # Implementation
           return None

       async def exists(self, sha256: str) -> bool:
           # Implementation
           return False

       async def delete(self, sha256: str) -> bool:
           # Implementation
           return True
   ```

2. **Update factory**:

   ```python
   # src/putplace/storage.py
   def get_storage_backend(storage_type: str, **kwargs) -> StorageBackend:
       if storage_type == "my_storage":
           return MyStorageBackend(**kwargs)
       # ...
   ```

3. **Add configuration**:

   ```python
   # src/putplace/config.py
   my_storage_config: Optional[str] = None
   ```

4. **Write tests**:

   ```python
   # tests/test_storage.py
   class TestMyStorageBackend:
       async def test_store_and_retrieve(self):
           storage = MyStorageBackend(config="test")
           # Test implementation
   ```

5. **Update documentation**:

   ```bash
   # docs/storage.md
   # Add new storage backend documentation
   ```

## Debugging

### Debug Server

```bash
# Run with debug logging
LOG_LEVEL=DEBUG uvicorn putplace.main:app --reload

# Or use Python debugger
python -m pdb -m uvicorn putplace.main:app --reload
```

### Debug Tests

```bash
# Run tests with print statements visible
pytest -s

# Run with Python debugger
pytest --pdb

# Drop into debugger on failure
pytest --pdb -x
```

### VS Code Debug Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.3.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "putplace.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000"
      ],
      "jinja": true,
      "justMyCode": false
    },
    {
      "name": "Python: Current Test File",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v"
      ],
      "console": "integratedTerminal"
    }
  ]
}
```

## Documentation

### Building Documentation

```bash
# Install Sphinx
pip install sphinx myst-parser sphinx-rtd-theme

# Build HTML documentation
cd docs
make html

# View documentation
open _build/html/index.html  # macOS
xdg-open _build/html/index.html  # Linux
```

### Writing Documentation

- Use Markdown format (MyST)
- Follow existing documentation structure
- Include code examples
- Add cross-references to related documentation

### API Documentation

FastAPI automatically generates API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Performance Testing

### Load Testing with Locust

```bash
# Install Locust
pip install locust

# Create locustfile.py
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class PutPlaceUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.api_key = "your-api-key"

    @task
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def put_file(self):
        metadata = {
            "filepath": "/tmp/test.txt",
            "hostname": "test",
            "ip_address": "127.0.0.1",
            "sha256": "a" * 64,
            "file_size": 1234,
            "file_mode": 33188,  # Regular file with rw-r--r-- (0644)
            "file_uid": 1000,
            "file_gid": 1000,
            "file_mtime": 1609459200.0,  # Unix timestamp
            "file_atime": 1609459200.0,
            "file_ctime": 1609459200.0,
        }
        self.client.post(
            "/put_file",
            json=metadata,
            headers={"X-API-Key": self.api_key},
        )
EOF

# Run load test
locust -f locustfile.py --host http://localhost:8000
```

Open http://localhost:8089 to configure and start test.

### Profiling

```bash
# Install py-spy
pip install py-spy

# Profile running server
py-spy record -o profile.svg --pid $(pgrep -f "uvicorn putplace.main")

# View profile
open profile.svg
```

## Release Process

### Version Numbering

PutPlace follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Creating a Release

1. **Update version**:

   ```bash
   # Edit pyproject.toml
   nano pyproject.toml
   # Change version = "0.2.0" to version = "0.3.0"
   ```

2. **Update CHANGELOG**:

   ```bash
   # Edit CHANGELOG.md
   nano CHANGELOG.md
   # Add release notes
   ```

3. **Commit changes**:

   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release version 0.2.0"
   ```

4. **Create tag**:

   ```bash
   git tag -a v0.3.0 -m "Release version 0.3.0"
   ```

5. **Push to GitHub**:

   ```bash
   git push origin main
   git push origin v0.3.0
   ```

6. **Create GitHub release**:

   - Go to GitHub repository
   - Click "Releases" → "Create a new release"
   - Select tag v0.3.0
   - Add release notes
   - Publish release

7. **Build and publish to PyPI** (if applicable):

   ```bash
   # Build package
   python -m build

   # Upload to PyPI
   python -m twine upload dist/*
   ```

## Contributing Guidelines

### Pull Request Checklist

Before submitting a pull request:

- [ ] Tests pass (`pytest`)
- [ ] Code coverage maintained (100%)
- [ ] Code formatted (`ruff format .`)
- [ ] No linting errors (`ruff check .`)
- [ ] Documentation updated
- [ ] CHANGELOG updated
- [ ] Commit messages are descriptive
- [ ] No merge conflicts

### Code Review Process

1. Submit pull request with description
2. Automated checks run (tests, linting)
3. Code review by maintainers
4. Address feedback
5. Approved and merged

### Reporting Bugs

When reporting bugs, include:

1. **Description**: What happened vs. what should happen
2. **Steps to reproduce**: Exact steps to reproduce the issue
3. **Environment**: OS, Python version, PutPlace version
4. **Logs**: Relevant error messages and logs
5. **Configuration**: ppserver.toml file (redact secrets!) or relevant environment variables

### Suggesting Features

When suggesting features, include:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Other approaches considered
4. **Impact**: Who would benefit from this feature?

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [PyMongo Async Documentation](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/index.html)
- [pytest Documentation](https://docs.pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)

## Getting Help

- **Documentation**: Read the [docs](.)
- **Issues**: [GitHub Issues](https://github.com/jdrumgoole/putplace/issues)
- **Discussions**: [GitHub Discussions](https://github.com/jdrumgoole/putplace/discussions)
