# Deployment Guide

Complete guide to deploying PutPlace in production environments.

## Overview

This guide covers:
- Production server setup
- HTTPS/TLS configuration
- Reverse proxy setup (nginx, traefik)
- Container deployment (Docker, Docker Compose, Kubernetes)
- Monitoring and logging
- Backup strategies
- High availability

## Prerequisites

Before deploying to production:

- [ ] PutPlace installed and tested locally
- [ ] MongoDB configured and accessible
- [ ] Storage backend configured (local or S3)
- [ ] API keys created
- [ ] Domain name (for HTTPS)
- [ ] SSL certificate (Let's Encrypt recommended)

## Production Architecture

### Simple Deployment

```
┌─────────┐
│ Internet│
└────┬────┘
     │
┌────▼────────┐
│   nginx     │  (Reverse proxy, TLS termination)
│  Port 443   │
└────┬────────┘
     │
┌────▼────────┐
│  PutPlace   │  (Gunicorn + Uvicorn workers)
│  Port 8000  │
└────┬────────┘
     │
┌────▼────────┐
│  MongoDB    │
│  Port 27017 │
└─────────────┘
```

### High Availability Deployment

```
┌───────────┐
│  Internet │
└─────┬─────┘
      │
┌─────▼──────┐
│Load Balancer│
└─────┬──────┘
      │
   ┌──┴──┐
   │     │
   ▼     ▼
┌────┐ ┌────┐
│App1│ │App2│  (Multiple PutPlace instances)
└─┬──┘ └─┬──┘
  │      │
  └───┬──┘
      │
┌─────▼─────┐
│ MongoDB   │  (Replica set)
│ Cluster   │
└───────────┘
      │
┌─────▼─────┐
│    S3     │  (Shared storage)
└───────────┘
```

## Method 1: systemd Service (Recommended for VPS/Bare Metal)

### Step 1: Create Service User

```bash
# Create dedicated user
sudo useradd -r -s /bin/false -d /opt/putplace putplace

# Create installation directory
sudo mkdir -p /opt/putplace
sudo chown putplace:putplace /opt/putplace
```

### Step 2: Install PutPlace

```bash
# Switch to putplace user
sudo -u putplace -s

# Navigate to directory
cd /opt/putplace

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install PutPlace
pip install putplace[s3]  # Include s3 if using S3 storage

# Or from source
git clone https://github.com/jdrumgoole/putplace.git .
pip install -e ".[s3]"
```

### Step 3: Create Configuration

```bash
# Create .env file
sudo -u putplace nano /opt/putplace/.env
```

**Production .env:**
```bash
# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace

# Storage Configuration
STORAGE_BACKEND=s3
S3_BUCKET_NAME=putplace-production
S3_REGION_NAME=us-east-1

# Use IAM role if on EC2/ECS, otherwise:
# AWS_PROFILE=putplace

# API Configuration
API_TITLE=PutPlace API
API_VERSION=0.3.0

# Logging
LOG_LEVEL=WARNING
```

**Set permissions:**
```bash
sudo chmod 600 /opt/putplace/.env
sudo chown putplace:putplace /opt/putplace/.env
```

### Step 4: Create systemd Service

```bash
sudo nano /etc/systemd/system/putplace.service
```

**Service file:**
```ini
[Unit]
Description=PutPlace File Metadata Service
Documentation=https://github.com/jdrumgoole/putplace
After=network.target mongodb.service
Wants=mongodb.service

[Service]
Type=simple
User=putplace
Group=putplace
WorkingDirectory=/opt/putplace

# Load environment variables
EnvironmentFile=/opt/putplace/.env

# Run with Gunicorn (production ASGI server)
ExecStart=/opt/putplace/.venv/bin/gunicorn putplace.main:app \
  --workers 9 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --timeout 120 \
  --access-logfile /var/log/putplace/access.log \
  --error-logfile /var/log/putplace/error.log \
  --log-level warning

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/putplace /var/putplace/files

[Install]
WantedBy=multi-user.target
```

**Worker count formula:**
- CPU-bound: `(2 × CPU cores) + 1`
- I/O-bound: `(4 × CPU cores) + 1`

For 2 CPU cores: `(4 × 2) + 1 = 9` workers

### Step 5: Create Log Directory

```bash
# Create log directory
sudo mkdir -p /var/log/putplace
sudo chown putplace:putplace /var/log/putplace
sudo chmod 755 /var/log/putplace
```

### Step 6: Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable putplace

# Start service
sudo systemctl start putplace

# Check status
sudo systemctl status putplace
```

**Expected output:**
```
● putplace.service - PutPlace File Metadata Service
     Loaded: loaded (/etc/systemd/system/putplace.service; enabled)
     Active: active (running) since ...
```

### Step 7: Test Service

```bash
# Test locally
curl http://localhost:8000/health

# Check logs
sudo journalctl -u putplace -f
```

## Method 2: Docker

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml setup.py ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[s3]"

# Create non-root user
RUN useradd -m -u 1000 putplace && \
    chown -R putplace:putplace /app
USER putplace

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run with Gunicorn
CMD ["gunicorn", "putplace.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### Build and Run

```bash
# Build image
docker build -t putplace:latest .

# Run container
docker run -d \
  --name putplace \
  -p 8000:8000 \
  -e MONGODB_URL=mongodb://mongodb:27017 \
  -e MONGODB_DATABASE=putplace \
  -e STORAGE_BACKEND=s3 \
  -e S3_BUCKET_NAME=putplace-production \
  -e S3_REGION_NAME=us-east-1 \
  -e AWS_ACCESS_KEY_ID=... \
  -e AWS_SECRET_ACCESS_KEY=... \
  --restart unless-stopped \
  putplace:latest

# Check logs
docker logs -f putplace
```

## Method 3: Docker Compose

### docker-compose.yml

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:6
    container_name: putplace-mongodb
    volumes:
      - mongodb-data:/data/db
    environment:
      MONGO_INITDB_DATABASE: putplace
    networks:
      - putplace-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

  putplace:
    image: putplace:latest
    container_name: putplace-api
    depends_on:
      mongodb:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      MONGODB_URL: mongodb://mongodb:27017
      MONGODB_DATABASE: putplace
      STORAGE_BACKEND: s3
      S3_BUCKET_NAME: putplace-production
      S3_REGION_NAME: us-east-1
    env_file:
      - .env  # For AWS credentials
    networks:
      - putplace-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: putplace-nginx
    depends_on:
      - putplace
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - nginx-cache:/var/cache/nginx
    networks:
      - putplace-network
    restart: unless-stopped

volumes:
  mongodb-data:
  nginx-cache:

networks:
  putplace-network:
    driver: bridge
```

### Start Services

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Update services
docker-compose pull
docker-compose up -d
```

## HTTPS Configuration

### Option 1: Let's Encrypt with Certbot

#### Install Certbot

```bash
# Ubuntu/Debian
sudo apt install certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install certbot python3-certbot-nginx
```

#### Obtain Certificate

```bash
# Automatic nginx configuration
sudo certbot --nginx -d putplace.example.com

# Or manual certificate only
sudo certbot certonly --standalone -d putplace.example.com
```

#### Auto-renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Certbot automatically adds cron job for renewal
```

### Option 2: Manual nginx Configuration

#### nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/putplace
```

**Complete nginx config:**

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name putplace.example.com;

    # ACME challenge for Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other requests to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name putplace.example.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/putplace.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/putplace.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/putplace-access.log;
    error_log /var/log/nginx/putplace-error.log;

    # Proxy to PutPlace
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for large file uploads
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        send_timeout 300s;

        # Max body size for file uploads
        client_max_body_size 100M;

        # Buffer settings
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

#### Enable Site

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/putplace /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Monitoring and Logging

### Application Logs

**View logs:**
```bash
# systemd service
sudo journalctl -u putplace -f

# Docker
docker logs -f putplace

# Docker Compose
docker-compose logs -f putplace
```

**Log rotation:**

Create `/etc/logrotate.d/putplace`:

```
/var/log/putplace/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 putplace putplace
    sharedscripts
    postrotate
        systemctl reload putplace > /dev/null 2>&1 || true
    endscript
}
```

### System Monitoring

#### Prometheus + Grafana

**Install Prometheus exporter:**

```bash
pip install prometheus-fastapi-instrumentator
```

**Update main.py:**

```python
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(...)

# Add Prometheus metrics
Instrumentator().instrument(app).expose(app)
```

**Access metrics:**
```
http://localhost:8000/metrics
```

#### Health Check Monitoring

**Create monitoring script:**

```bash
#!/bin/bash
# /usr/local/bin/check-putplace-health.sh

URL="https://putplace.example.com/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $URL)

if [ "$RESPONSE" != "200" ]; then
    echo "PutPlace health check failed: HTTP $RESPONSE"
    # Send alert (email, Slack, PagerDuty, etc.)
    exit 1
fi

echo "PutPlace health check passed"
exit 0
```

**Add to cron:**

```bash
*/5 * * * * /usr/local/bin/check-putplace-health.sh
```

## Backup Strategy

### MongoDB Backup

**Automated backup script:**

```bash
#!/bin/bash
# /usr/local/bin/backup-putplace-mongodb.sh

BACKUP_DIR="/backup/putplace/mongodb"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup
mongodump --db putplace --out "$BACKUP_DIR/$DATE"

# Compress backup
tar -czf "$BACKUP_DIR/$DATE.tar.gz" -C "$BACKUP_DIR" "$DATE"
rm -rf "$BACKUP_DIR/$DATE"

# Remove old backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_DIR/$DATE.tar.gz"
```

**Add to cron:**

```bash
0 2 * * * /usr/local/bin/backup-putplace-mongodb.sh
```

### Storage Backup

**Local storage:**
```bash
rsync -av /var/putplace/files/ /backup/putplace/files/
```

**S3 storage:**

S3 is already highly durable. Enable versioning and cross-region replication for additional protection.

## High Availability

### Load Balancing

**nginx upstream configuration:**

```nginx
upstream putplace_backend {
    least_conn;
    server putplace-01:8000 max_fails=3 fail_timeout=30s;
    server putplace-02:8000 max_fails=3 fail_timeout=30s;
    server putplace-03:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name putplace.example.com;

    location / {
        proxy_pass http://putplace_backend;
        ...
    }
}
```

### MongoDB Replica Set

**Configure replica set:**

```bash
# On each MongoDB node
mongod --replSet rs0 --bind_ip_all

# Initialize replica set (on primary)
mongosh
> rs.initiate({
    _id: "rs0",
    members: [
      { _id: 0, host: "mongo-01:27017" },
      { _id: 1, host: "mongo-02:27017" },
      { _id: 2, host: "mongo-03:27017" }
    ]
  })
```

**Update connection string:**

```bash
MONGODB_URL=mongodb://mongo-01:27017,mongo-02:27017,mongo-03:27017/?replicaSet=rs0
```

## Security Hardening

### Firewall Configuration

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow MongoDB (from app servers only)
sudo ufw allow from 10.0.1.0/24 to any port 27017

# Enable firewall
sudo ufw enable
```

### Rate Limiting

**nginx rate limiting:**

```nginx
# Define rate limit zone
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    ...

    location /put_file {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### Fail2ban

**Install:**
```bash
sudo apt install fail2ban
```

**Configure for nginx:**

Create `/etc/fail2ban/filter.d/nginx-4xx.conf`:

```ini
[Definition]
failregex = ^<HOST> .* "(GET|POST|PUT) .* HTTP.*" 4\d{2}
ignoreregex =
```

Create `/etc/fail2ban/jail.local`:

```ini
[nginx-4xx]
enabled = true
filter = nginx-4xx
logpath = /var/log/nginx/putplace-access.log
maxretry = 100
findtime = 60
bantime = 3600
```

## Troubleshooting Production Issues

### Service Won't Start

```bash
# Check service status
sudo systemctl status putplace

# Check logs
sudo journalctl -u putplace -n 100 --no-pager

# Check configuration
/opt/putplace/.venv/bin/python -m putplace.main:app
```

### High Memory Usage

```bash
# Check memory usage
ps aux | grep gunicorn

# Reduce worker count
# Edit /etc/systemd/system/putplace.service
# Change --workers value

# Restart service
sudo systemctl restart putplace
```

### Slow Response Times

```bash
# Check MongoDB performance
mongosh --eval "db.serverStatus()"

# Check application logs
sudo journalctl -u putplace -f

# Check nginx access logs
sudo tail -f /var/log/nginx/putplace-access.log

# Add indexes if needed
mongosh putplace --eval "db.file_metadata.getIndexes()"
```

## Next Steps

- [Monitoring Setup](https://prometheus.io/docs/guides/node-exporter/)
- [Security Hardening](../SECURITY.md)
- [Troubleshooting Guide](troubleshooting.md)
- [Configuration Reference](configuration.md)
