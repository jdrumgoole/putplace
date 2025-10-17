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

## Step 3: Create API Key (1 minute)

```bash
# In a new terminal, create your first API key
python -m putplace.scripts.create_api_key --name "my-first-key"

# Save the API key that's displayed!
# Example output:
# API Key: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6...
```

**⚠️ IMPORTANT:** Copy and save the API key! You'll need it for the next step.

## Step 4: Use the Client (1 minute)

```bash
# Set your API key
export PUTPLACE_API_KEY="paste-your-api-key-here"

# Scan a directory (dry run first)
python ppclient.py /tmp --dry-run

# If that works, scan for real
python ppclient.py /tmp

# You should see:
# PutPlace Client
#   Path: /tmp
#   ...
# Found X files to process
# ✓ Processing complete
```

## Step 5: Verify It Worked

```bash
# List your API keys
curl -H "X-API-Key: $PUTPLACE_API_KEY" http://localhost:8000/api_keys

# You should see JSON output with your API key metadata
```

## 🎉 Success!

You now have:
- ✅ PutPlace server running
- ✅ API key created
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
cp ppclient.conf.example ~/ppclient.conf
nano ~/ppclient.conf  # Add your API key
python ppclient.py /var/log
```

### Create More API Keys

```bash
# Create key for another server
curl -X POST http://localhost:8000/api_keys \
  -H "X-API-Key: $PUTPLACE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "server-02", "description": "Production server 02"}'

# Save the returned API key!
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

### "API key required"

**Problem:** Forgot to set API key

**Solution:**
```bash
# Set environment variable
export PUTPLACE_API_KEY="your-api-key-here"

# Or use command line
python ppclient.py /tmp --api-key "your-api-key-here"
```

## Quick Reference Commands

```bash
# Start server
uvicorn putplace.main:app --reload

# Create API key
python -m putplace.scripts.create_api_key --name "KEY_NAME"

# Scan directory
python ppclient.py /path/to/scan

# Scan with API key
python ppclient.py /path --api-key "YOUR_KEY"

# Scan remote server
python ppclient.py /path --url http://server:8000/put_file

# Dry run (test without sending)
python ppclient.py /path --dry-run

# Health check
curl http://localhost:8000/health

# List API keys
curl -H "X-API-Key: KEY" http://localhost:8000/api_keys
```

## Example Workflow

Here's a complete example workflow:

```bash
# 1. Start server (Terminal 1)
uvicorn putplace.main:app

# 2. Create API key (Terminal 2)
python -m putplace.scripts.create_api_key --name "laptop"
# Save the key: a1b2c3d4e5f6...

# 3. Create config file
cat > ~/ppclient.conf << EOF
[DEFAULT]
url = http://localhost:8000/put_file
api-key = a1b2c3d4e5f6...
exclude = .git
exclude = node_modules
exclude = __pycache__
EOF
chmod 600 ~/ppclient.conf

# 4. Scan your home directory
python ppclient.py ~/Documents

# 5. Check results
curl -H "X-API-Key: a1b2c3d4e5f6..." http://localhost:8000/api_keys
```

## Architecture at a Glance

```
[Your Files] → [ppclient.py] → [PutPlace API] → [MongoDB + Storage]
                    ↓                              ↓
              X-API-Key Auth            Metadata + File Content
```

**Flow:**
1. Client scans files, calculates SHA256
2. Sends metadata to API (with API key)
3. API checks if file already exists (deduplication!)
4. If new file: client uploads content
5. If duplicate: skip upload (saved bandwidth!)

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
- **[Authentication](AUTHENTICATION.md)** - Manage API keys
- **[Configuration](configuration.md)** - Customize PutPlace
- **[Storage Backends](storage.md)** - Configure S3 or local storage
- **[Deployment](deployment.md)** - Production deployment
- **[Security](SECURITY.md)** - Security best practices

## Getting Help

- 📖 **Documentation**: [docs/](.)
- 🐛 **Issues**: [GitHub Issues](https://github.com/jdrumgoole/putplace/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/jdrumgoole/putplace/discussions)

Happy file tracking! 🎉
