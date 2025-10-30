# Installation Guide

This guide covers installing PutPlace server and client components.

## Prerequisites

### System Requirements
- **Python**: 3.10 or higher
- **MongoDB**: 4.4 or higher
- **Operating System**: Linux, macOS, or Windows
- **RAM**: 1GB minimum, 2GB+ recommended
- **Disk**: Depends on storage backend (local) or minimal (S3)

### Network Requirements
- Server: Inbound port 8000 (or configured port)
- Client: Outbound HTTPS to server
- MongoDB: Port 27017 (default) or configured port

## Installing MongoDB

### Ubuntu/Debian

```bash
# Import MongoDB GPG key
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -

# Add MongoDB repository
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list

# Install MongoDB
sudo apt-get update
sudo apt-get install -y mongodb-org

# Start MongoDB
sudo systemctl start mongod
sudo systemctl enable mongod
```

### macOS (Homebrew)

```bash
# Install MongoDB
brew tap mongodb/brew
brew install mongodb-community

# Start MongoDB
brew services start mongodb-community
```

### Docker

```bash
# Run MongoDB in Docker
docker run -d \
  --name putplace-mongodb \
  -p 27017:27017 \
  -v putplace-mongodb-data:/data/db \
  mongo:6
```

## Installing PutPlace

### Method 1: From Source (Development)

```bash
# Clone repository
git clone https://github.com/jdrumgoole/putplace.git
cd putplace

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in development mode
uv pip install -e ".[dev]"

# For S3 support, install optional dependencies
uv pip install -e ".[s3]"
```

### Method 2: From PyPI (Production)

```bash
# Install via pip
pip install putplace

# For S3 support
pip install putplace[s3]
```

### Method 3: Using Docker

```bash
# Pull image
docker pull putplace/putplace:latest

# Run container
docker run -d \
  --name putplace \
  -p 8000:8000 \
  -e MONGODB_URL=mongodb://mongodb:27017 \
  --link putplace-mongodb:mongodb \
  putplace/putplace:latest
```

## Initial Configuration

### 1. Create Configuration File

```bash
# Copy example configuration
cp .env.example .env

# Edit configuration
nano .env
```

**Minimal `.env` file:**

```bash
# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace
MONGODB_COLLECTION=file_metadata

# Storage Backend
STORAGE_BACKEND=local
STORAGE_PATH=/var/putplace/files

# API Configuration
API_TITLE=PutPlace API
API_VERSION=0.3.0
```

### 2. Create Storage Directory

```bash
# For local storage
sudo mkdir -p /var/putplace/files
sudo chown $USER:$USER /var/putplace/files
chmod 755 /var/putplace/files
```

### 3. Configure Initial Admin User (Optional)

PutPlace automatically creates an admin user on first startup. You can control this behavior:

**Option A: Use Environment Variables (Recommended for Production)**

Add to your `.env` file:
```bash
# Admin user credentials
PUTPLACE_ADMIN_USERNAME=admin
PUTPLACE_ADMIN_PASSWORD=your-secure-password-here
PUTPLACE_ADMIN_EMAIL=admin@example.com
```

**Option B: Let PutPlace Generate Credentials (Development)**

If you don't set the environment variables, PutPlace will:
- Generate a secure random password
- Display credentials once in the server logs on first startup
- Save credentials to `/tmp/putplace_initial_creds.txt`

**Important:**
- ⚠️ Save the generated credentials immediately - they're shown only once
- ⚠️ Delete `/tmp/putplace_initial_creds.txt` after saving the password
- ✅ Admin user is only created if no users exist in the database

### 4. Initialize Database

```bash
# Start the server (this will create indexes automatically)
uvicorn putplace.main:app

# Or run directly with Python
python -m uvicorn putplace.main:app
```

The database indexes and admin user will be created automatically on first startup.

**First Startup Output:**
```
INFO:     Application startup: Database connected successfully
WARNING:  ================================================================================
WARNING:  🔐 INITIAL ADMIN CREDENTIALS GENERATED
WARNING:  ================================================================================
WARNING:     Username: admin
WARNING:     Password: AbCdEf1234567890XyZ
WARNING:
WARNING:  ⚠️  SAVE THESE CREDENTIALS NOW - They won't be shown again!
WARNING:  ================================================================================
```

### 5. Create First API Key

```bash
# Create administrative API key
python -m putplace.scripts.create_api_key --name "admin-key" --description "Administrative API key"

# Save the displayed API key securely!
```

## Installing the Client

The client (`ppclient.py`) is included in the repository.

### System-Wide Installation

```bash
# Make client executable
chmod +x ppclient.py

# Create symbolic link (optional)
sudo ln -s $(pwd)/ppclient.py /usr/local/bin/ppclient

# Now you can run from anywhere
ppclient --help
```

### Client Configuration

```bash
# Create client config
cp ppclient.conf.example ~/ppclient.conf

# Edit and add your API key
nano ~/ppclient.conf

# Set secure permissions
chmod 600 ~/ppclient.conf
```

## Verification

### Verify Server Installation

```bash
# Check server health
curl http://localhost:8000/health

# Expected output:
# {"status":"healthy","database":{"status":"connected","type":"mongodb"}}
```

### Verify Client Installation

```bash
# Set API key
export PUTPLACE_API_KEY="your-api-key-here"

# Test client (dry run)
python ppclient.py /tmp --dry-run

# Expected output:
# PutPlace Client
#   Path: /tmp
#   Hostname: your-hostname
#   ...
```

### Verify Authentication

```bash
# Test API key
curl -H "X-API-Key: your-api-key-here" http://localhost:8000/api_keys

# Should return list of API keys (JSON array)
```

## Platform-Specific Installation

### Linux (systemd)

Create a systemd service for PutPlace:

```bash
# Create service file
sudo nano /etc/systemd/system/putplace.service
```

**Service file content:**

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
EnvironmentFile=/opt/putplace/.env
ExecStart=/opt/putplace/.venv/bin/uvicorn putplace.main:app --host 0.0.0.0 --port 8000
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

### macOS (launchd)

Create a launch agent:

```bash
# Create plist file
nano ~/Library/LaunchAgents/com.putplace.server.plist
```

**Plist content:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.putplace.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uvicorn</string>
        <string>putplace.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/putplace</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

**Load service:**

```bash
launchctl load ~/Library/LaunchAgents/com.putplace.server.plist
launchctl start com.putplace.server
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:6
    container_name: putplace-mongodb
    volumes:
      - mongodb-data:/data/db
    ports:
      - "27017:27017"
    restart: always

  putplace:
    image: putplace/putplace:latest
    container_name: putplace-api
    depends_on:
      - mongodb
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URL=mongodb://mongodb:27017
      - MONGODB_DATABASE=putplace
      - STORAGE_BACKEND=local
      - STORAGE_PATH=/var/putplace/files
    volumes:
      - putplace-files:/var/putplace/files
      - ./env:/app/.env
    restart: always

volumes:
  mongodb-data:
  putplace-files:
```

**Start services:**

```bash
docker-compose up -d
```

## Post-Installation Steps

### 1. Create Additional API Keys

```bash
# For each client server
curl -X POST http://localhost:8000/api_keys \
  -H "X-API-Key: ADMIN_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "server-01",
    "description": "API key for server 01"
  }'
```

### 2. Configure Firewall

```bash
# Allow PutPlace API port
sudo ufw allow 8000/tcp

# Or for specific IP
sudo ufw allow from 192.168.1.0/24 to any port 8000
```

### 3. Set Up TLS/HTTPS (Production)

See [Deployment Guide](deployment.md) for TLS configuration.

### 4. Configure Backup

```bash
# MongoDB backup script
mongodump --db putplace --out /backup/putplace-$(date +%Y%m%d)

# Add to cron
echo "0 2 * * * mongodump --db putplace --out /backup/putplace-\$(date +\%Y\%m\%d)" | crontab -
```

## Upgrading

### Upgrade from Source

```bash
cd putplace
git pull
uv pip install -e ".[dev]"
sudo systemctl restart putplace
```

### Upgrade from PyPI

```bash
pip install --upgrade putplace
sudo systemctl restart putplace
```

### Database Migrations

PutPlace automatically creates/updates database indexes on startup. No manual migration required.

## Uninstallation

### Remove PutPlace

```bash
# Stop service
sudo systemctl stop putplace
sudo systemctl disable putplace

# Remove service file
sudo rm /etc/systemd/system/putplace.service

# Remove installation
pip uninstall putplace

# Or if from source
rm -rf /opt/putplace
```

### Remove MongoDB Data

```bash
# Backup first!
mongodump --db putplace --out /backup/putplace-final

# Drop database
mongo putplace --eval "db.dropDatabase()"
```

### Remove Storage Files

```bash
# For local storage (BE CAREFUL!)
sudo rm -rf /var/putplace/files
```

## Troubleshooting Installation

### MongoDB Connection Failed

```
pymongo.errors.ServerSelectionTimeoutError: localhost:27017: [Errno 111] Connection refused
```

**Solution:**
```bash
# Check MongoDB is running
sudo systemctl status mongod

# Start if not running
sudo systemctl start mongod

# Check MongoDB is listening
sudo netstat -tlnp | grep 27017
```

### Permission Denied on Storage Path

```
PermissionError: [Errno 13] Permission denied: '/var/putplace/files'
```

**Solution:**
```bash
# Fix ownership
sudo chown -R $USER:$USER /var/putplace/files

# Fix permissions
chmod 755 /var/putplace/files
```

### Module Not Found

```
ModuleNotFoundError: No module named 'putplace'
```

**Solution:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Reinstall
pip install -e .
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get started using PutPlace
- [Configuration Reference](configuration.md) - Detailed configuration options
- [Authentication Guide](AUTHENTICATION.md) - Set up API keys
- [Deployment Guide](deployment.md) - Production deployment strategies
