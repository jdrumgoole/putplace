# Test Suite

This directory contains comprehensive tests for the PutPlace application.

## Test Organization

- **test_models.py** - Pydantic model validation tests
- **test_api.py** - FastAPI endpoint tests
- **test_database.py** - MongoDB database operation tests
- **test_client.py** - ppclient.py functionality tests
- **test_e2e.py** - End-to-end integration tests
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
