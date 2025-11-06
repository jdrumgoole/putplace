# Configuration Reference

This document covers all configuration options for PutPlace server and client.

## Server Configuration

### Configuration Methods

PutPlace server supports multiple configuration methods (in priority order):

1. **Environment variables** - Highest priority, override everything
2. **ppserver.toml** - Recommended configuration file
3. **Default values** - Lowest priority

**Important:** As of version 0.5.1, environment variables correctly take precedence over `ppserver.toml` settings. Prior versions had a bug where TOML values would override environment variables.

**Note:** `.env` files are no longer supported as of version 0.2.0. Use `ppserver.toml` instead.

**Recommendation:** Use `ppserver.toml` for structured configuration. Environment variables are useful for overrides in production and testing.

### Environment Variables

All configuration can be set via environment variables. The format is uppercase with underscores.

#### Core Settings

```bash
# API Configuration
API_TITLE="PutPlace API"
API_VERSION="0.2.0"
API_DESCRIPTION="Distributed file metadata storage and content deduplication"

# Server Configuration
HOST="0.0.0.0"
PORT=8000
WORKERS=4  # Number of worker processes (for production with gunicorn)
```

#### MongoDB Configuration

```bash
# MongoDB Connection
MONGODB_URL="mongodb://localhost:27017"
MONGODB_DATABASE="putplace"
MONGODB_COLLECTION="file_metadata"

# MongoDB Connection Options
MONGODB_TIMEOUT_MS=5000
MONGODB_MAX_POOL_SIZE=10
MONGODB_MIN_POOL_SIZE=1
```

**MongoDB URL Examples:**

```bash
# Local MongoDB (default)
MONGODB_URL="mongodb://localhost:27017"

# Remote MongoDB with authentication
MONGODB_URL="mongodb://username:password@mongodb.example.com:27017"

# MongoDB Atlas
MONGODB_URL="mongodb+srv://username:password@cluster.mongodb.net/"

# MongoDB replica set
MONGODB_URL="mongodb://host1:27017,host2:27017,host3:27017/?replicaSet=myReplicaSet"
```

#### Storage Configuration

```bash
# Storage Backend Type
STORAGE_BACKEND="local"  # Options: "local" or "s3"

# Local Storage Settings
STORAGE_PATH="/var/putplace/files"

# AWS S3 Storage Settings
S3_BUCKET_NAME="my-putplace-bucket"
S3_REGION_NAME="us-east-1"
S3_PREFIX="files/"  # Optional prefix for S3 keys
S3_STORAGE_CLASS="STANDARD"  # STANDARD, STANDARD_IA, GLACIER, etc.

# AWS Credentials (optional - uses default credential chain if not set)
AWS_PROFILE="putplace"
AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

#### CORS Configuration

```bash
# CORS Settings (for browser-based clients)
CORS_ALLOW_ORIGINS="*"  # Comma-separated list or "*" for all
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS="GET,POST,PUT,DELETE"
CORS_ALLOW_HEADERS="*"
```

### ppserver.toml Configuration (Recommended)

The recommended way to configure PutPlace is using a TOML configuration file.

#### Quick Start

```bash
# Copy the example configuration
cp ppserver.toml.example ppserver.toml

# Edit with your settings
nano ppserver.toml
```

#### Configuration File Locations

PutPlace searches for `ppserver.toml` in these locations (in order):

1. `./ppserver.toml` - Current directory (project root)
2. `~/.config/putplace/ppserver.toml` - User configuration
3. `/etc/putplace/ppserver.toml` - System-wide configuration

The first file found is used.

#### Complete ppserver.toml Example

```toml
# PutPlace Server Configuration

[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"
mongodb_collection = "file_metadata"

[api]
title = "PutPlace API"
description = "File metadata storage API"

[storage]
# Storage backend: "local" or "s3"
backend = "local"

# Local storage settings (used when backend = "local")
path = "/var/putplace/files"

# S3 storage settings (used when backend = "s3")
# Uncomment and configure if using S3:
# s3_bucket_name = "your-bucket-name"
# s3_region_name = "us-east-1"
# s3_prefix = "files/"

[aws]
# AWS credentials (optional - will use AWS credential chain if not specified)
# Recommended: Use IAM roles or AWS CLI config instead of hardcoding credentials
# profile = "your-aws-profile"
# access_key_id = "your-access-key"
# secret_access_key = "your-secret-key"
```

**Security Note:**
- `ppserver.toml` is gitignored by default - never commit it!
- `ppserver.toml.example` is the template (safe to commit)
- Set restrictive permissions: `chmod 600 ppserver.toml`

#### Development vs Production

**Development (ppserver.toml):**
```toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace_dev"

[storage]
backend = "local"
path = "./storage/files"
```

**Production (ppserver.toml):**
```toml
[database]
mongodb_url = "mongodb://prod-server:27017"
mongodb_database = "putplace"

[storage]
backend = "s3"
s3_bucket_name = "company-putplace-prod"
s3_region_name = "us-east-1"

[aws]
# Use IAM role (recommended) or AWS profile
profile = "production"
```

#### Logging Configuration

```bash
# Logging Level
LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Log Format
LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### .env File (No Longer Supported)

**Note:** As of version 0.2.0, `.env` files are no longer supported. This section is kept for reference only. Please migrate to `ppserver.toml` (see examples above).

**Legacy `.env` file format (for reference only):**

```bash
# PutPlace Server Configuration

# ============================================================================
# MongoDB Configuration
# ============================================================================
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace
MONGODB_COLLECTION=file_metadata

# ============================================================================
# Storage Backend
# ============================================================================

# Use local filesystem storage (default)
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files

# OR use AWS S3 storage
# STORAGE_BACKEND=s3
# S3_BUCKET_NAME=my-putplace-bucket
# S3_REGION_NAME=us-east-1
# S3_PREFIX=files/
# AWS_PROFILE=putplace

# ============================================================================
# API Configuration
# ============================================================================
API_TITLE=PutPlace API
API_VERSION=0.1.0
HOST=0.0.0.0
PORT=8000

# ============================================================================
# Logging
# ============================================================================
LOG_LEVEL=INFO
```

### Storage Backend Selection

#### Local Filesystem Storage

**When to use:**
- Simple deployment
- Single server
- Fast local access needed
- No cloud dependencies

**Configuration:**
```bash
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files
```

**Directory Structure:**
```
/var/putplace/files/
├── 00/
│   └── 00a1b2c3...  # SHA256 hash starting with 00
├── 01/
│   └── 01d4e5f6...  # SHA256 hash starting with 01
├── ...
└── ff/
    └── ffa7b8c9...  # SHA256 hash starting with ff
```

Files are distributed across 256 subdirectories (00-ff) based on the first two characters of their SHA256 hash.

**Permissions:**
```bash
# Create storage directory
sudo mkdir -p /var/putplace/files
sudo chown $USER:$USER /var/putplace/files
chmod 755 /var/putplace/files
```

#### AWS S3 Storage

**When to use:**
- Cloud deployment
- Multiple servers
- Scalability needed
- Durability requirements (99.999999999% durability)

**Configuration:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
S3_PREFIX=files/
AWS_PROFILE=putplace  # Optional: use credentials from ~/.aws/credentials
```

**S3 Key Structure:**
```
s3://my-putplace-bucket/
└── files/
    ├── 00/
    │   └── 00a1b2c3...
    ├── 01/
    │   └── 01d4e5f6...
    └── ...
```

**S3 Bucket Policy Example:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/putplace-server"
      },
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-putplace-bucket/files/*",
        "arn:aws:s3:::my-putplace-bucket"
      ]
    }
  ]
}
```

**Storage Classes:**
```bash
# Standard (default) - Frequent access
S3_STORAGE_CLASS=STANDARD

# Standard-IA - Infrequent access, lower cost
S3_STORAGE_CLASS=STANDARD_IA

# Glacier - Archive, lowest cost
S3_STORAGE_CLASS=GLACIER
```

### AWS Credentials Configuration

See [SECURITY.md](../SECURITY.md) for detailed AWS credentials setup.

**Priority order:**
1. IAM roles (if running on AWS)
2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
3. AWS credentials file (~/.aws/credentials) with profile
4. AWS credentials file (default profile)

**Using IAM Role (recommended for EC2/ECS):**
```bash
# No credentials needed - automatic!
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
```

**Using AWS Profile:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
AWS_PROFILE=putplace
```

**Using Environment Variables:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=my-putplace-bucket
S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

## Client Configuration

### Configuration Methods

The PutPlace client (`ppclient.py`) supports three configuration methods (in priority order):

1. **Command-line arguments** - Highest priority
2. **Environment variables** - Middle priority
3. **Configuration file** - Lowest priority

### Command-Line Arguments

```bash
python ppclient.py [options] PATH

# Positional Arguments:
  PATH                  Path to scan

# Required Options:
  --url URL            API endpoint URL
                       Default: http://localhost:8000/put_file

  --api-key KEY        API key for authentication
                       Can also use: PUTPLACE_API_KEY env var or config file

# Optional Arguments:
  --hostname HOSTNAME  Override detected hostname
  --ip IP             Override detected IP address
  --exclude PATTERN   Exclude files matching pattern (can be used multiple times)
  --dry-run           Scan files but don't send to server
  --verbose, -v       Verbose output
  --config PATH       Path to config file
                      Default: ppclient.conf or ~/ppclient.conf
  --help, -h          Show help message
```

### Environment Variables

```bash
# API Configuration
export PUTPLACE_API_KEY="your-api-key-here"
export PUTPLACE_URL="http://localhost:8000/put_file"

# Run client
python ppclient.py /path/to/scan
```

**Add to shell profile for persistence:**

```bash
# For bash
echo 'export PUTPLACE_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export PUTPLACE_API_KEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Configuration File

**File locations (checked in order):**
1. Path specified with `--config`
2. `ppclient.conf` (current directory)
3. `~/ppclient.conf` (home directory)

**Example: ~/ppclient.conf**

```ini
[DEFAULT]
# =============================================================================
# API Configuration
# =============================================================================

# API endpoint URL
url = http://localhost:8000/put_file

# API Key (REQUIRED)
# IMPORTANT: Set file permissions to 600 to protect API key!
api-key = your-api-key-here

# =============================================================================
# Host Configuration
# =============================================================================

# Override hostname (optional, auto-detected if not specified)
# hostname = myserver

# Override IP address (optional, auto-detected if not specified)
# ip = 192.168.1.100

# =============================================================================
# Exclude Patterns
# =============================================================================

# Patterns to exclude from scanning (can be specified multiple times)
exclude = .git
exclude = __pycache__
exclude = *.pyc
exclude = *.log
exclude = node_modules
exclude = .DS_Store
exclude = .venv
exclude = venv

# =============================================================================
# Options
# =============================================================================

# Dry run mode - scan files but don't send to server
# dry-run = false

# Verbose output
# verbose = false
```

**Set secure permissions:**
```bash
chmod 600 ~/ppclient.conf
```

### Exclude Patterns

Exclude patterns support wildcards:

**File extensions:**
```bash
--exclude "*.log"      # All .log files
--exclude "*.tmp"      # All .tmp files
--exclude "*.pyc"      # All compiled Python files
```

**Directories:**
```bash
--exclude ".git"       # Git directories
--exclude "node_modules"  # Node.js dependencies
--exclude "__pycache__"   # Python cache
--exclude ".venv"      # Python virtual environments
```

**Wildcards:**
```bash
--exclude "test_*"     # Files starting with test_
--exclude "*~"         # Backup files
--exclude ".*.swp"     # Vim swap files
```

**In config file:**
```ini
[DEFAULT]
exclude = .git
exclude = node_modules
exclude = __pycache__
exclude = *.log
exclude = *.tmp
exclude = .DS_Store
```

### Client Examples

#### Example 1: Quick Test with API Key

```bash
python ppclient.py /tmp \
  --api-key "your-api-key-here" \
  --dry-run
```

#### Example 2: Production Scan with Environment Variable

```bash
export PUTPLACE_API_KEY="production-api-key"
export PUTPLACE_URL="https://putplace.example.com/put_file"

python ppclient.py /var/www \
  --exclude "*.log" \
  --exclude ".git" \
  --exclude "node_modules"
```

#### Example 3: Using Config File

```bash
# Create config file once
cat > ~/ppclient.conf << 'EOF'
[DEFAULT]
url = https://putplace.example.com/put_file
api-key = production-api-key
exclude = .git
exclude = *.log
EOF

chmod 600 ~/ppclient.conf

# Run with all settings from config
python ppclient.py /var/www
```

#### Example 4: Multi-Environment Setup

```bash
# Development config
cat > ~/ppclient.conf.dev << 'EOF'
url = http://dev-putplace:8000/put_file
api-key = dev-api-key
EOF

# Production config
cat > ~/ppclient.conf.prod << 'EOF'
url = https://putplace.example.com/put_file
api-key = prod-api-key
EOF

# Use with --config flag
python ppclient.py /var/www --config ~/ppclient.conf.prod
```

## Production Configuration

### Using Gunicorn

For production deployments, use Gunicorn with Uvicorn workers:

```bash
# Install Gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn putplace.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile /var/log/putplace/access.log \
  --error-logfile /var/log/putplace/error.log
```

**Worker Count Recommendation:**
```bash
# CPU-bound: (2 x CPU cores) + 1
# I/O-bound: (4 x CPU cores) + 1

# For 4 CPU cores:
--workers 17  # I/O-bound (typical for PutPlace)
```

### systemd Service Configuration

**Example: /etc/systemd/system/putplace.service**

```ini
[Unit]
Description=PutPlace File Metadata Service
After=network.target mongodb.service

[Service]
Type=simple
User=putplace
Group=putplace
WorkingDirectory=/opt/putplace
Environment="PATH=/opt/putplace/.venv/bin"
# Configuration loaded from ppserver.toml in WorkingDirectory or /etc/putplace/ppserver.toml
ExecStart=/opt/putplace/.venv/bin/gunicorn putplace.main:app \
  --workers 17 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile /var/log/putplace/access.log \
  --error-logfile /var/log/putplace/error.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable putplace
sudo systemctl start putplace
sudo systemctl status putplace
```

### HTTPS/TLS Configuration

Use a reverse proxy (nginx or traefik) for TLS termination:

**Example: nginx configuration**

```nginx
server {
    listen 80;
    server_name putplace.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name putplace.example.com;

    ssl_certificate /etc/letsencrypt/live/putplace.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/putplace.example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;

    # Proxy to PutPlace
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Increase timeouts for large file uploads
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
        send_timeout 300;

        # Increase max body size for large files
        client_max_body_size 100M;
    }
}
```

### Environment-Specific Configurations

#### Development

```toml
# ppserver.toml or ppserver.dev.toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace_dev"

[storage]
backend = "local"
path = "/tmp/putplace-dev"
```

#### Staging

```toml
# ppserver.staging.toml
[database]
mongodb_url = "mongodb://staging-mongo:27017"
mongodb_database = "putplace_staging"

[storage]
backend = "s3"
s3_bucket_name = "putplace-staging"
s3_region_name = "us-east-1"

[aws]
profile = "staging"
```

#### Production

```toml
# ppserver.toml or /etc/putplace/ppserver.toml
[database]
mongodb_url = "mongodb+srv://username:password@cluster.mongodb.net/"
mongodb_database = "putplace"

[storage]
backend = "s3"
s3_bucket_name = "putplace-production"
s3_region_name = "us-east-1"

[aws]
profile = "production"
```

## Configuration Validation

PutPlace validates configuration on startup and will fail fast with clear error messages:

**Missing MongoDB connection:**
```
ERROR: MONGODB_URL is required
```

**Invalid storage backend:**
```
ERROR: STORAGE_BACKEND must be 'local' or 's3', got: 'invalid'
```

**Missing S3 configuration:**
```
ERROR: S3_BUCKET_NAME is required when STORAGE_BACKEND=s3
```

## Configuration Best Practices

1. **Use environment-specific configurations**
   - Separate ppserver.toml files for dev/staging/prod
   - Never commit production credentials

2. **Protect sensitive values**
   - Use ppserver.toml with restrictive permissions (600)
   - Never commit ppserver.toml to version control
   - Use secret managers in production
   - Override sensitive values with environment variables in CI/CD

3. **Use IAM roles in AWS**
   - Avoid hardcoding AWS credentials
   - Let AWS handle credential rotation

4. **Set appropriate log levels**
   - DEBUG: Development only
   - INFO: Default for most environments
   - WARNING: Production

5. **Configure proper timeouts**
   - Increase for large file uploads
   - Consider network latency

6. **Monitor configuration drift**
   - Use configuration management tools
   - Document all changes

## Troubleshooting Configuration

### Check Current Configuration

```bash
# Server: Check environment variables
env | grep -E "(MONGODB|STORAGE|S3|AWS)"

# Client: Test configuration
python ppclient.py /tmp --dry-run --verbose
```

### Common Configuration Issues

**Issue: Can't connect to MongoDB**
```bash
# Check MongoDB URL
echo $MONGODB_URL

# Test connection
mongo $MONGODB_URL
```

**Issue: S3 authentication failed**
```bash
# Check AWS credentials
aws sts get-caller-identity --profile putplace

# Test S3 access
aws s3 ls s3://my-putplace-bucket --profile putplace
```

**Issue: API key not recognized**
```bash
# Check API key
echo $PUTPLACE_API_KEY

# Test API key
curl -H "X-API-Key: $PUTPLACE_API_KEY" http://localhost:8000/api_keys
```

## Next Steps

- [Deployment Guide](deployment.md) - Production deployment strategies
- [Security Guide](../SECURITY.md) - Security best practices
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
