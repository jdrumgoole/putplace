# Security Tests Documentation

This directory contains comprehensive tests for all security fixes implemented in PutPlace.

## Test Files

### Unit Tests (No MongoDB Required)

#### `test_security_password.py` - Password Strength Validation
Tests the enhanced password requirements (12+ chars, complexity rules):
- Tests for minimum length (12 characters)
- Tests for uppercase letter requirement
- Tests for lowercase letter requirement
- Tests for digit requirement
- Tests for special character requirement
- Tests edge cases (exactly 12 chars, very long passwords, max length)
- Tests that other validations still work (username, email)

**Total Tests:** 13
**Run:** `pytest tests/test_security_password.py`

---

#### `test_security_lockout.py` - Account Lockout Mechanism
Tests the account lockout functionality that prevents brute force attacks:
- Recording failed login attempts
- Account locking after max attempts (5 in 15 minutes)
- Lockout time calculation
- Clearing attempts after successful login
- Automatic cleanup of old attempts
- Multi-user isolation
- Lockout expiration

**Total Tests:** 12
**Run:** `pytest tests/test_security_lockout.py`

---

#### `test_security_jwt.py` - JWT Secret Key Security
Tests the JWT authentication security enhancements:
- JWT secret loaded from environment variable
- Error when JWT secret is missing
- Token creation with configured secret
- Token decoding with configured secret
- Token validation fails with wrong secret
- Token expiration handling
- Invalid token format handling

**Total Tests:** 8
**Run:** `pytest tests/test_security_jwt.py`

---

#### `test_security_config.py` - Configuration Security
Tests the security configuration and MongoDB URL sanitization:
- MongoDB URL password sanitization
- Handling special characters in passwords (including @ symbols)
- URLs without authentication
- Replica set URLs
- Query parameter preservation
- Default security settings (CORS, rate limiting, JWT)

**Total Tests:** 12
**Run:** `pytest tests/test_security_config.py`

---

### Integration Tests (MongoDB Required)

#### `test_security_api.py` - API Endpoint Security
Integration tests for security features in actual API endpoints:

**Security Headers Tests:**
- X-Content-Type-Options header
- X-Frame-Options header
- X-XSS-Protection header
- Content-Security-Policy header
- HSTS header (production mode)

**CORS Tests:**
- CORS preflight requests (OPTIONS)
- CORS headers on actual requests
- Credentials support

**Rate Limiting Tests:**
- Login endpoint rate limiting (5/minute)
- Registration endpoint rate limiting (5/minute)
- File upload rate limiting (100/minute)

**Account Lockout Tests:**
- Account locks after 5 failed attempts
- Successful login clears failed attempts
- Lockout error messages

**Password Validation Tests:**
- Weak passwords rejected at API level
- Strong passwords accepted
- Clear validation error messages

**Total Tests:** 16
**Run:** `pytest tests/test_security_api.py -m integration`
**Requires:** MongoDB running on localhost:27017

---

## Running Tests

### Run All Security Tests (Unit Only)
```bash
pytest tests/test_security_*.py -v -m "not integration"
```

### Run All Security Tests (Including Integration)
```bash
# Start MongoDB first
docker run -d -p 27017:27017 mongo:latest

# Run tests
pytest tests/test_security_*.py -v
```

### Run Specific Test File
```bash
pytest tests/test_security_password.py -v
```

### Run Specific Test
```bash
pytest tests/test_security_password.py::test_password_too_short -v
```

### Run with Coverage
```bash
pytest tests/test_security_*.py --cov=putplace.lockout --cov=putplace.user_auth --cov=putplace.config
```

---

## Test Coverage Summary

| Security Feature | Tests | Coverage |
|------------------|-------|----------|
| Password Strength | 13 | 100% |
| Account Lockout | 12 | 100% |
| JWT Secret Key | 8 | 100% |
| Config & Sanitization | 12 | 100% |
| API Security Headers | 3 | Integration |
| CORS Middleware | 3 | Integration |
| Rate Limiting | 3 | Integration |
| API Lockout | 2 | Integration |
| API Password Validation | 5 | Integration |
| **Total** | **61** | **Comprehensive** |

---

## Test Requirements

### Environment Setup
The tests automatically set up a test JWT secret via the `setup_test_jwt_secret` fixture in `conftest.py`:
- Test JWT secret: `test-secret-key-for-testing-only-do-not-use-in-production`
- Automatically configured before any tests run
- No manual environment setup needed for unit tests

### Dependencies
All test dependencies are included in the `[dev]` extras:
```bash
pip install -e '.[dev]'
```

Key testing packages:
- `pytest>=8.0.0`
- `pytest-asyncio>=0.23.0`
- `pytest-cov>=4.1.0`
- `httpx` (for API tests)

---

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

### Unit Tests (Fast)
```bash
# No MongoDB required - can run anywhere
pytest tests/test_security_*.py -v -m "not integration" --cov
```

### Integration Tests (Requires MongoDB)
```bash
# Requires MongoDB service
pytest tests/test_security_*.py -v -m integration
```

### GitHub Actions Example
```yaml
- name: Run Security Unit Tests
  run: |
    pytest tests/test_security_*.py -v -m "not integration"

- name: Start MongoDB
  run: |
    docker run -d -p 27017:27017 mongo:latest

- name: Run Security Integration Tests
  run: |
    pytest tests/test_security_*.py -v -m integration
```

---

## Test Markers

Tests use pytest markers for categorization:

- `@pytest.mark.integration` - Requires MongoDB (marked on entire `test_security_api.py` module)

Skip integration tests:
```bash
pytest -m "not integration"
```

Run only integration tests:
```bash
pytest -m integration
```

---

## Troubleshooting

### Issue: JWT Secret Key Error
**Error:** `RuntimeError: JWT secret key not configured`

**Solution:** The `setup_test_jwt_secret` fixture in `conftest.py` should handle this automatically. If you see this error, ensure you're running tests via pytest, not importing modules directly.

### Issue: MongoDB Connection Errors
**Error:** `ServerSelectionTimeoutError: localhost:27017`

**Solution:** This is expected for unit tests. Either:
1. Skip integration tests: `pytest -m "not integration"`
2. Start MongoDB: `docker run -d -p 27017:27017 mongo:latest`

### Issue: Cleanup Errors
**Error:** Error during test teardown with MongoDB

**Solution:** The `cleanup_test_databases` fixture now catches and ignores these errors. They're harmless when MongoDB isn't running.

---

## Adding New Security Tests

When adding new security features, follow this pattern:

1. **Unit Tests First**
   - Create focused unit tests for the core functionality
   - No external dependencies (MongoDB, etc.)
   - Fast execution

2. **Integration Tests Second**
   - Test the feature in actual API endpoints
   - Mark with `@pytest.mark.integration`
   - Test realistic scenarios

3. **Update This README**
   - Document the new test file
   - Update the coverage table
   - Add running instructions

### Example Test Structure
```python
"""Tests for new security feature."""

import pytest
from putplace.module import feature


def test_feature_basic():
    """Test basic functionality."""
    assert feature() == expected


def test_feature_edge_case():
    """Test edge case."""
    with pytest.raises(ValueError):
        feature(invalid_input)


@pytest.mark.integration
async def test_feature_api(client):
    """Test feature via API."""
    response = await client.get("/endpoint")
    assert response.status_code == 200
```

---

## Related Documentation

- `SECURITY_AUDIT_REPORT.md` - Full security audit with identified issues
- `SECURITY_FIXES_SUMMARY.md` - Summary of all security fixes
- `tests/README.md` - General testing documentation

---

## Test Status

✅ **45 Unit Tests Passing** (No MongoDB required)
✅ **16 Integration Tests** (Require MongoDB)
✅ **Zero Warnings** (All deprecations fixed)
✅ **100% Coverage** of security-critical code

Last Updated: 2025-11-05
