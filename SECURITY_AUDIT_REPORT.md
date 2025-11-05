# PutPlace Security Audit Report

**Date:** 2025-11-05
**Auditor:** Claude Code Security Review
**Version:** 0.5.0
**Repository:** https://github.com/jdrumgoole/putplace

## Executive Summary

This security audit identified **9 security issues** across various severity levels, ranging from critical vulnerabilities to medium-priority concerns. The most critical issue is a **hardcoded JWT secret key** that must be addressed immediately before production deployment.

**Overall Security Posture:** ⚠️ **REQUIRES IMMEDIATE ATTENTION**

### Quick Stats
- 🔴 **Critical Issues:** 1
- 🟠 **High Priority:** 3
- 🟡 **Medium Priority:** 5
- ✅ **Good Practices Found:** 7

---

## Critical Issues (Must Fix Immediately)

### 1. 🔴 CRITICAL: Hardcoded JWT Secret Key

**Location:** `src/putplace/user_auth.py:14`

**Issue:**
```python
SECRET_KEY = "your-secret-key-change-this-in-production"  # TODO: Move to config
```

**Impact:**
- JWT tokens can be forged by anyone who has access to the source code
- All authentication can be bypassed
- User sessions can be hijacked
- This is a **critical security vulnerability** that makes JWT authentication completely ineffective

**Risk Level:** 🔴 **CRITICAL** - Severity: 10/10

**Recommendation:**
1. Immediately move the JWT secret to an environment variable
2. Generate a strong random secret key (at least 32 bytes)
3. Never commit the secret key to version control

**Fix:**
```python
# In src/putplace/user_auth.py
import os
import secrets

# Generate a secure secret key if not provided
SECRET_KEY = os.getenv("PUTPLACE_JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "PUTPLACE_JWT_SECRET_KEY environment variable must be set. "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
```

**Add to .env.example:**
```bash
# JWT Authentication Secret (REQUIRED - generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))')
PUTPLACE_JWT_SECRET_KEY=your-randomly-generated-secret-key-here
```

---

## High Priority Issues

### 2. 🟠 No CORS Middleware Configured

**Location:** `src/putplace/main.py`

**Issue:**
The FastAPI application does not configure CORS (Cross-Origin Resource Sharing) middleware, which means:
- The API cannot be safely accessed from browser-based clients
- No control over which origins can access the API
- Potential for unauthorized cross-origin requests

**Impact:**
- Limited functionality for web-based clients
- No protection against CSRF attacks from malicious websites
- Cannot restrict API access to specific domains

**Risk Level:** 🟠 **HIGH** - Severity: 7/10

**Recommendation:**
Add CORS middleware with appropriate configuration for production environments.

**Fix:**
```python
# In src/putplace/main.py
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins.split(",") if settings.cors_allow_origins else ["*"],
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods.split(",") if settings.cors_allow_methods else ["*"],
    allow_headers=settings.cors_allow_headers.split(",") if settings.cors_allow_headers else ["*"],
)
```

**Add to config.py:**
```python
# CORS settings
cors_allow_origins: str = "*"  # Comma-separated list or "*" for all (use specific domains in production)
cors_allow_credentials: bool = True
cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
cors_allow_headers: str = "*"
```

**Production recommendation:** Set `cors_allow_origins` to specific domains, not `"*"`.

---

### 3. 🟠 No Rate Limiting Protection

**Location:** All API endpoints

**Issue:**
The API has no rate limiting configured, making it vulnerable to:
- Brute force attacks on authentication endpoints
- API key enumeration attacks
- Denial of Service (DoS) through excessive requests
- Resource exhaustion

**Impact:**
- Attackers can make unlimited login attempts
- API can be overwhelmed by malicious requests
- Resource costs can spike unexpectedly
- No protection against automated attacks

**Risk Level:** 🟠 **HIGH** - Severity: 7/10

**Recommendation:**
Implement rate limiting using `slowapi` or similar middleware.

**Fix:**
```bash
# Add to dependencies
uv pip install slowapi
```

```python
# In src/putplace/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to sensitive endpoints
@app.post("/api/login")
@limiter.limit("5/minute")  # 5 attempts per minute
async def login(...):
    ...

@app.post("/put_file")
@limiter.limit("100/minute")  # 100 uploads per minute
async def put_file(...):
    ...
```

---

### 4. 🟠 No Account Lockout Mechanism

**Location:** `src/putplace/user_auth.py`, `src/putplace/main.py`

**Issue:**
Failed login attempts are not tracked or limited, allowing unlimited password guessing attempts.

**Impact:**
- Attackers can perform brute force attacks indefinitely
- No protection against credential stuffing attacks
- User accounts vulnerable to unauthorized access

**Risk Level:** 🟠 **HIGH** - Severity: 6/10

**Recommendation:**
Implement failed login tracking with temporary account lockout.

**Fix:**
```python
# Track failed login attempts in MongoDB
# Add collection: login_attempts
# After 5 failed attempts in 15 minutes, lock account for 15 minutes
# Send email notification to user about suspicious activity
```

---

## Medium Priority Issues

### 5. 🟡 Potential NoSQL Injection Vulnerabilities

**Location:** `src/putplace/database.py` (multiple methods)

**Issue:**
While PyMongo provides some protection against NoSQL injection, user input is used directly in database queries without explicit sanitization in some cases.

**Example:**
```python
# In database.py:159
return await self.collection.find_one({"sha256": sha256})
```

If `sha256` parameter contains MongoDB operators (e.g., `{"$ne": ""}"`), it could lead to unintended query behavior.

**Impact:**
- Potential for NoSQL injection attacks
- Unauthorized data access
- Query manipulation

**Risk Level:** 🟡 **MEDIUM** - Severity: 5/10

**Recommendation:**
1. Add input validation for all user-provided fields
2. Use Pydantic models to validate input before database queries
3. Never allow dictionary/object inputs directly to database queries
4. Sanitize or reject special MongoDB operators in user input

**Fix:**
```python
# Add validation to ensure sha256 is a string (already done via Pydantic)
# Add additional check:
if not isinstance(sha256, str) or len(sha256) != 64:
    raise ValueError("Invalid SHA256 hash")
```

**Note:** Current implementation using Pydantic models provides good protection, but additional validation wouldn't hurt.

---

### 6. 🟡 Information Disclosure in Error Messages

**Location:** Various error handlers throughout `src/putplace/main.py`

**Issue:**
Some error messages include detailed internal information that could aid attackers.

**Examples:**
```python
detail=f"Failed to store file metadata: {str(e)}"  # Exposes internal error details
detail=f"File content SHA256 ({calculated_hash}) does not match provided hash ({sha256})"  # Good
```

**Impact:**
- Information leakage about internal system structure
- Stack traces may reveal file paths, database details
- Helps attackers understand the system better

**Risk Level:** 🟡 **MEDIUM** - Severity: 4/10

**Recommendation:**
- Log detailed errors server-side
- Return generic error messages to clients in production
- Use DEBUG mode flag to control error verbosity

**Fix:**
```python
# Add to config.py
debug_mode: bool = False

# In error handlers
if settings.debug_mode:
    detail = f"Failed to store file metadata: {str(e)}"
else:
    detail = "Failed to store file metadata"
logger.error(f"File metadata storage error: {e}", exc_info=True)
```

---

### 7. 🟡 Weak Password Requirements

**Location:** `src/putplace/models.py:125`, `src/putplace/main.py:64`

**Issue:**
Password minimum length is only 8 characters. Modern security standards recommend stronger requirements.

**Current:**
```python
password: str = Field(..., description="Password", min_length=8)
```

**Impact:**
- Weak passwords more susceptible to brute force
- Users may choose easily guessable passwords
- Does not meet some compliance standards (NIST, PCI-DSS recommend 12-15 characters)

**Risk Level:** 🟡 **MEDIUM** - Severity: 4/10

**Recommendation:**
Increase minimum password length to 12 characters and add complexity requirements.

**Fix:**
```python
# In src/putplace/models.py
password: str = Field(..., description="Password", min_length=12, max_length=128)

# Add password strength validation
from typing import ClassVar
import re

class UserCreate(BaseModel):
    ...

    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password meets security requirements."""
        if len(v) < 12:
            raise ValueError('Password must be at least 12 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v
```

---

### 8. 🟡 No HTTPS Enforcement

**Location:** Server configuration

**Issue:**
The application doesn't enforce HTTPS connections, allowing sensitive data (passwords, API keys, JWT tokens) to be transmitted in plaintext.

**Impact:**
- Credentials can be intercepted via man-in-the-middle attacks
- API keys exposed in transit
- JWT tokens can be stolen
- Violates security best practices

**Risk Level:** 🟡 **MEDIUM** - Severity: 6/10

**Recommendation:**
1. Add HTTPS redirect middleware for production
2. Set secure cookie flags
3. Add HSTS headers
4. Document TLS/SSL certificate requirements

**Fix:**
```python
# Add HTTPS redirect middleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if not settings.debug_mode:
    app.add_middleware(HTTPSRedirectMiddleware)

# Add security headers
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts.split(","))

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
```

---

### 9. 🟡 MongoDB Connection String Exposure Risk

**Location:** `.env.example:8`, logging statements

**Issue:**
MongoDB connection strings are logged during startup, which could expose credentials if logging is misconfigured.

**Example:**
```python
logger.info(f"Connecting to MongoDB at {settings.mongodb_url}")  # May contain credentials
```

**Impact:**
- Database credentials could be exposed in logs
- Logs may be accessible to unauthorized users
- Credentials could leak in monitoring systems

**Risk Level:** 🟡 **MEDIUM** - Severity: 5/10

**Recommendation:**
Sanitize connection strings before logging.

**Fix:**
```python
def sanitize_mongodb_url(url: str) -> str:
    """Remove credentials from MongoDB URL for safe logging."""
    import re
    # Replace password in mongodb://user:pass@host/db with mongodb://user:****@host/db
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', url)

logger.info(f"Connecting to MongoDB at {sanitize_mongodb_url(settings.mongodb_url)}")
```

---

## Good Security Practices Found ✅

The following security best practices were identified in the codebase:

1. ✅ **Argon2 Password Hashing** - Using modern, secure password hashing algorithm (`src/putplace/user_auth.py:11`)
2. ✅ **API Key Hashing** - API keys are hashed with SHA256 before storage (`src/putplace/auth.py:39-48`)
3. ✅ **.env in .gitignore** - Environment files properly excluded from version control
4. ✅ **Secure Credential Generation** - Random passwords use `secrets.token_urlsafe()` (`src/putplace/main.py:90`)
5. ✅ **File SHA256 Verification** - Uploaded files are verified against provided hash (`src/putplace/main.py:841-847`)
6. ✅ **AWS Credentials Handled Securely** - Multiple secure fallback methods, IAM roles preferred (`src/putplace/storage.py`, `SECURITY.md`)
7. ✅ **Proper File Permissions** - Credentials file permissions set to 600 (`src/putplace/main.py:137`)

---

## Priority Recommendations

### Immediate Actions (Before Production Deployment)

1. **Fix the hardcoded JWT secret key** (Critical Issue #1)
2. **Add CORS middleware** (High Priority Issue #2)
3. **Implement rate limiting** (High Priority Issue #3)
4. **Add HTTPS enforcement** (Medium Priority Issue #8)

### Short-term Improvements (Within 2-4 weeks)

5. **Implement account lockout mechanism** (High Priority Issue #4)
6. **Strengthen password requirements** (Medium Priority Issue #7)
7. **Add security headers middleware** (Medium Priority Issue #8)
8. **Sanitize MongoDB connection strings in logs** (Medium Priority Issue #9)

### Long-term Enhancements

9. **Add comprehensive input validation** (Medium Priority Issue #5)
10. **Implement error message sanitization** (Medium Priority Issue #6)
11. **Add security monitoring and alerting**
12. **Implement session management improvements**
13. **Add API request signing for additional security**
14. **Consider adding Web Application Firewall (WAF)**

---

## Compliance Considerations

### GDPR / Data Protection
- ⚠️ No data retention policies documented
- ⚠️ No user data deletion mechanism
- ⚠️ No consent tracking for data collection
- ⚠️ No privacy policy or terms of service

### OWASP Top 10 Coverage

| OWASP Risk | Status | Notes |
|------------|--------|-------|
| A01: Broken Access Control | ⚠️ Partial | API keys required, but no role-based access |
| A02: Cryptographic Failures | 🔴 Critical | Hardcoded JWT secret |
| A03: Injection | 🟡 Medium | NoSQL injection risk, Pydantic helps |
| A04: Insecure Design | 🟡 Medium | No rate limiting, no account lockout |
| A05: Security Misconfiguration | 🟠 High | No CORS, no HTTPS enforcement |
| A06: Vulnerable Components | ✅ Good | Dependencies appear up to date |
| A07: Auth Failures | 🔴 Critical | JWT secret issue, no account lockout |
| A08: Software/Data Integrity | ✅ Good | File SHA256 verification |
| A09: Logging/Monitoring | 🟡 Medium | Logs may expose credentials |
| A10: SSRF | ✅ Good | No external URL fetching |

---

## Testing Recommendations

### Security Testing to Perform

1. **Penetration Testing**
   - Test authentication bypass attempts
   - Test NoSQL injection vectors
   - Test API rate limiting after implementation
   - Test CORS policy after implementation

2. **Static Analysis**
   - Run `bandit` security scanner: `pip install bandit && bandit -r src/`
   - Run `safety` for dependency vulnerabilities: `pip install safety && safety check`
   - Run `semgrep` for security patterns: `semgrep --config=auto src/`

3. **Dynamic Testing**
   - Use OWASP ZAP or Burp Suite for API security testing
   - Test with intentionally malformed inputs
   - Test with SQL/NoSQL injection payloads
   - Test authentication bypass techniques

---

## Monitoring and Alerting Recommendations

### Security Monitoring to Implement

1. **Failed Authentication Attempts**
   - Alert on >5 failed logins from same IP
   - Alert on >10 failed logins for same user
   - Monitor for credential stuffing patterns

2. **API Abuse Detection**
   - Monitor for unusually high request rates
   - Track failed API key validations
   - Alert on suspicious file upload patterns

3. **Database Security**
   - Monitor for unusual query patterns
   - Track failed database authentication
   - Alert on direct database access attempts

---

## Conclusion

The PutPlace application demonstrates several good security practices, particularly in password hashing and API key management. However, the **critical JWT secret key vulnerability must be addressed immediately** before any production deployment.

The application would benefit significantly from implementing:
- CORS middleware configuration
- Rate limiting protection
- Account lockout mechanisms
- HTTPS enforcement
- Security monitoring and alerting

**Overall Risk Assessment:** 🔴 **HIGH RISK** (due to hardcoded JWT secret)
**After fixes:** 🟡 **MEDIUM RISK** (acceptable for production with continued improvements)

---

## Appendix: Security Checklist

Use this checklist to track remediation progress:

- [ ] Fix hardcoded JWT secret key
- [ ] Add CORS middleware
- [ ] Implement rate limiting
- [ ] Add account lockout mechanism
- [ ] Strengthen password requirements
- [ ] Add HTTPS enforcement
- [ ] Add security headers
- [ ] Sanitize MongoDB URLs in logs
- [ ] Review and sanitize error messages
- [ ] Add input validation checks
- [ ] Set up security monitoring
- [ ] Document security policies
- [ ] Perform penetration testing
- [ ] Run static analysis tools
- [ ] Create incident response plan
- [ ] Add data retention policies
- [ ] Implement user data deletion

---

**Report End**

For questions or clarifications about this security audit, please consult with your security team or contact a security professional.
