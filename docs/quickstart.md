# Quick Start Guide

Get PutPlace up and running in 5 minutes!

## Prerequisites

- Python 3.10 - 3.14
- MongoDB running on localhost:27017
- Terminal/command line access

## Step 1: Install PutPlace (2 minutes)

```bash
# Clone the repository
git clone https://github.com/jdrumgoole/putplace.git
cd putplace

# Install dependencies
pip install -e .

# Verify installation
python -c "import putplace; print('✓ PutPlace installed')"
```

## Step 2: Start the Server (1 minute)

```bash
# Start PutPlace server
uvicorn putplace.main:app --reload

# You should see:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup: Database connected successfully
```

Keep this terminal open. Open a new terminal for the next steps.

## Step 3: Get Admin Credentials (1 minute)

The admin user is automatically created on first server startup. Check the server logs or the credentials file:

```bash
# Check credentials file (created on first startup)
cat /tmp/putplace_initial_creds.txt

# Example output:
# PutPlace Admin User Created
# ===========================
# Username: admin
# Password: Xy9K3mP#vL2nQ@8sW4tR
#
# ⚠️  Save these credentials securely and delete this file!
```

**⚠️ IMPORTANT:** Copy and save these credentials! Delete the file after saving:
```bash
rm /tmp/putplace_initial_creds.txt
```

## Step 4: Use the Client (1 minute)

```bash
# Set your credentials
export PUTPLACE_USERNAME="admin"
export PUTPLACE_PASSWORD="paste-your-password-here"

# Scan a directory (dry run first)
python ppclient.py /tmp --dry-run

# If that works, scan for real
python ppclient.py /tmp

# You should see:
# Logging in as admin...
# ✓ Login successful
# PutPlace Client
#   Path: /tmp
#   ...
# Found X files to process
# ✓ Processing complete
```

## Step 5: Verify It Worked

```bash
# Test login
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$PUTPLACE_USERNAME\", \"password\": \"$PUTPLACE_PASSWORD\"}"

# You should see JSON output with an access_token
```

## 🎉 Success!

You now have:
- ✅ PutPlace server running
- ✅ Admin user created
- ✅ Client scanning files
- ✅ Metadata stored in MongoDB

## What's Next?

### Explore the API

```bash
# View API documentation
open http://localhost:8000/docs

# Or manually:
# - Swagger UI: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

### Configure Storage Backend

**Local Storage (Default):**
```bash
# Already configured! Files stored in /var/putplace/files
```

**AWS S3 Storage:**
```bash
# Install S3 dependencies
pip install putplace[s3]

# Configure S3 in ppserver.toml
cat > ppserver.toml << EOF
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"

[storage]
backend = "s3"
s3_bucket_name = "my-putplace-bucket"
s3_region_name = "us-east-1"

[aws]
# Use AWS profile or IAM role (recommended)
profile = "default"
EOF

# Restart server
# Ctrl+C the uvicorn process, then:
uvicorn putplace.main:app --reload
```

### Scan More Directories

```bash
# Scan with exclusions
python ppclient.py /var/log --exclude "*.log" --exclude ".git"

# Scan different server
python ppclient.py /var/log --url http://remote-server:8000/put_file

# Use config file
cat > ~/ppclient.conf << EOF
[DEFAULT]
username = admin
password = your-password
EOF
chmod 600 ~/ppclient.conf
python ppclient.py /var/log
```

### Create More Users

```bash
# Register a new user via API
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "newuser", "email": "user@example.com", "password": "secure-password"}'

# User can now login and use the client
```

## Common First-Time Issues

### "Database not connected"

**Problem:** MongoDB not running

**Solution:**
```bash
# Start MongoDB
sudo systemctl start mongod  # Linux
brew services start mongodb-community  # macOS
```

### "Permission denied: /var/putplace/files"

**Problem:** No permission to create storage directory

**Solution:**
```bash
# Create directory with your user
sudo mkdir -p /var/putplace/files
sudo chown $USER:$USER /var/putplace/files
```

### "Login failed: 401"

**Problem:** Forgot credentials or incorrect password

**Solution:**
```bash
# Set environment variables
export PUTPLACE_USERNAME="admin"
export PUTPLACE_PASSWORD="your-password"

# Or use command line
python ppclient.py /tmp --username "admin" --password "your-password"

# If you lost the admin password, check the server logs from first startup
```

## Quick Reference Commands

```bash
# Start server
uvicorn putplace.main:app --reload

# Register new user
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "email": "user@example.com", "password": "password"}'

# Login and get token
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# Scan directory
python ppclient.py /path/to/scan

# Scan with credentials
python ppclient.py /path --username "admin" --password "your-password"

# Scan remote server
python ppclient.py /path --url http://server:8000/put_file

# Dry run (test without sending)
python ppclient.py /path --dry-run

# Health check
curl http://localhost:8000/health
```

## Example Workflow

Here's a complete example workflow:

```bash
# 1. Start server (Terminal 1)
uvicorn putplace.main:app

# 2. Get admin credentials (Terminal 2)
cat /tmp/putplace_initial_creds.txt
# Username: admin
# Password: Xy9K3mP#vL2nQ@8sW4tR

# 3. Create config file
cat > ~/ppclient.conf << EOF
[DEFAULT]
url = http://localhost:8000/put_file
username = admin
password = Xy9K3mP#vL2nQ@8sW4tR
exclude = .git
exclude = node_modules
exclude = __pycache__
EOF
chmod 600 ~/ppclient.conf

# 4. Scan your home directory
python ppclient.py ~/Documents

# 5. Check results
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Xy9K3mP#vL2nQ@8sW4tR"}'
```

## Architecture at a Glance

```
[Your Files] → [ppclient.py] → [PutPlace API] → [MongoDB + Storage]
                    ↓                              ↓
              JWT Bearer Auth           Metadata + File Content
```

**Flow:**
1. Client logs in with username/password, gets JWT token
2. Client scans files, calculates SHA256
3. Sends metadata to API (with JWT token)
4. API checks if file already exists (deduplication!)
5. If new file: client uploads content
6. If duplicate: skip upload (saved bandwidth!)

## Development Mode

Want to develop PutPlace?

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Check coverage
pytest --cov=putplace --cov-report=html
open htmlcov/index.html

# Run linter
ruff check .

# Format code
ruff format .
```

## Production Deployment (Preview)

For production deployment:

```bash
# Use production ASGI server
pip install gunicorn

# Run with workers
gunicorn putplace.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# See full deployment guide
# docs/deployment.md
```

## Next Steps

Now that you have PutPlace running, explore these guides:

- **[Client Guide](client-guide.md)** - Learn all client features
- **[API Reference](api-reference.md)** - Explore the REST API
- **[Authentication](AUTHENTICATION.md)** - User authentication and JWT tokens
- **[Configuration](configuration.md)** - Customize PutPlace
- **[Storage Backends](storage.md)** - Configure S3 or local storage
- **[Deployment](deployment.md)** - Production deployment
- **[Security](SECURITY.md)** - Security best practices

## Getting Help

- 📖 **Documentation**: [docs/](.)
- 🐛 **Issues**: [GitHub Issues](https://github.com/jdrumgoole/putplace/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/jdrumgoole/putplace/discussions)

Happy file tracking! 🎉
