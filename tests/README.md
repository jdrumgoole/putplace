# Test Suite

This directory contains comprehensive tests for the PutPlace application.

## Test Organization

- **test_models.py** - Pydantic model validation tests
- **test_api.py** - FastAPI endpoint tests
- **test_database.py** - MongoDB database operation tests
- **test_client.py** - ppclient.py functionality tests
- **test_auth.py** - Authentication and authorization tests
- **test_storage.py** - Storage backend tests (local and S3)
- **test_admin_creation.py** - Admin user creation tests
- **test_console_scripts.py** - CLI script installation tests
- **test_e2e.py** - End-to-end integration tests
- **test_electron_gui.py** - Electron desktop GUI tests (macOS only)
- **conftest.py** - Shared pytest fixtures

## Running Tests

### All Tests

```bash
# Run all tests with coverage
invoke test

# Or directly with pytest
pytest
```

### Unit Tests Only (Skip Integration)

```bash
# Skip integration tests (don't require MongoDB running)
pytest -m "not integration"
```

### Integration Tests Only

```bash
# Run only integration tests (requires MongoDB running)
pytest -m integration
```

### Specific Test Files

```bash
# Test models only
pytest tests/test_models.py

# Test API endpoints only
pytest tests/test_api.py

# Test client only
pytest tests/test_client.py

# Test Electron GUI only (macOS only, requires packaged app)
pytest tests/test_electron_gui.py
```

### Specific Test Functions

```bash
# Run single test
pytest tests/test_models.py::test_file_metadata_valid

# Run tests matching pattern
pytest -k "sha256"
```

### With Verbose Output

```bash
pytest -v
pytest -vv  # Even more verbose
```

## Test Requirements

### Unit Tests
- No external dependencies (except Python packages)
- Can run without MongoDB

### Integration Tests
- **Require MongoDB** running on localhost:27017
- Use test database: `putplace_test`
- Tests automatically clean up after themselves

Start MongoDB for integration tests:

```bash
# Using invoke
invoke mongo-start

# Or using Docker directly
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

## Test Coverage

View coverage report:

```bash
# Generate and view HTML coverage report
invoke test
open htmlcov/index.html  # macOS
# Or: xdg-open htmlcov/index.html  # Linux
```

## Test Fixtures

### Common Fixtures (conftest.py)

- **test_settings** - Test configuration
- **test_db** - Test MongoDB instance (auto-cleanup)
- **client** - FastAPI test client
- **sample_file_metadata** - Sample metadata for testing
- **temp_test_dir** - Temporary directory with test files

### Example Usage

```python
def test_example(sample_file_metadata, temp_test_dir):
    # Use fixtures in your tests
    metadata = sample_file_metadata
    test_files = list(temp_test_dir.glob("*"))
```

## Markers

- **integration** - Tests requiring external services (MongoDB, running server)

## Electron GUI Tests

The Electron GUI tests (`test_electron_gui.py`) verify the desktop application functionality:

### Prerequisites

1. **macOS only** - Tests automatically skip on other platforms
2. **Packaged app required** - Run `invoke gui-electron-package` before testing

```bash
# Package the Electron app first
invoke gui-electron-package

# Then run the tests
pytest tests/test_electron_gui.py -v
```

### What's Tested

- ✅ DMG package creation
- ✅ App bundle structure (Contents, MacOS, Info.plist)
- ✅ Info.plist product name verification
- ✅ TypeScript compilation (dist/ files)
- ✅ npm dependencies installation
- ✅ Complete install → launch → quit → uninstall flow

### Test Flow

The main integration test (`test_electron_app_install_launch_uninstall`) performs:

1. **Install**: Copies app bundle to /Applications
2. **Launch**: Opens the installed app using `open -a`
3. **Verify**: Checks app is running via process ID
4. **Quit**: Programmatically quits app via AppleScript
5. **Cleanup**: Removes app and support files

### Notes

- Tests use fixtures for automatic cleanup
- Safe to run multiple times - cleans up after each run
- Uses subprocess for isolated command execution
- Skips gracefully if app not packaged

## Continuous Integration

For CI environments, ensure MongoDB is available:

```bash
# Start MongoDB
docker run -d -p 27017:27017 mongo:latest

# Run tests
pytest

# Or skip integration tests if MongoDB unavailable
pytest -m "not integration"
```
