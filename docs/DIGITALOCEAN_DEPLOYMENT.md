# Digital Ocean Deployment Guide

Complete guide for deploying PutPlace to Digital Ocean droplets with automated provisioning, deployment, and management.

## Overview

This deployment method provides:
- **Simple setup**: Single command deployment
- **Cost-effective**: Starting at $6/month
- **Full control**: Root access to your server
- **No vendor lock-in**: Standard Ubuntu + Python stack
- **MongoDB included**: Runs on the same droplet or use Atlas
- **S3 storage support**: Optional AWS S3 for file storage with automatic credentials deployment
- **SSL/HTTPS ready**: Certbot integration for Let's Encrypt

### Cost Comparison

| Platform | Monthly Cost | Notes |
|----------|--------------|-------|
| **Digital Ocean (1GB)** | $6 | Good for testing/development |
| **Digital Ocean (2GB)** | $12 | Recommended for production |
| **Digital Ocean (4GB)** | $24 | High traffic production |
| AWS AppRunner | $25+ | + NAT Gateway ($32) if using Atlas |
| Heroku | $25+ | Hobby tier |

## Quick Start

### Prerequisites

1. **Digital Ocean account**: Sign up at https://www.digitalocean.com/
2. **Digital Ocean CLI (`doctl`)**: Install and authenticate
3. **SSH key**: Add to your Digital Ocean account
4. **API token**: Create in Digital Ocean dashboard

### Installation

```bash
# Install doctl (macOS)
brew install doctl

# Authenticate doctl
doctl auth init

# Add your SSH key to Digital Ocean (if not already done)
doctl compute ssh-key list
# If empty, create one:
ssh-keygen -t ed25519 -C "your_email@example.com"
doctl compute ssh-key import my-key --public-key-file ~/.ssh/id_ed25519.pub

# Set Digital Ocean API token
export DIGITALOCEAN_TOKEN="your_token_here"
```

### Simplified Deployment (Recommended)

The easiest way to deploy with environment-specific shortcuts:

```bash
# Step 1: Configure production environment (one-time setup)
invoke configure-prod --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

# This creates:
# - IAM user: putplace-prod
# - S3 bucket: putplace-prod
# - Config file: ppserver-prod.toml
# - AWS credentials in: aws_credentials_output/

# Step 2: Deploy to Digital Ocean
invoke deploy-do-prod --create

# This will:
# 1. Create a 1GB droplet (putplace-prod) in Frankfurt
# 2. Wait for it to boot (~60 seconds)
# 3. Install Python, nginx, uv (skips MongoDB - using Atlas)
# 4. Install PutPlace from PyPI
# 5. Copy AWS credentials to droplet
# 6. Set up systemd service with AWS profile
# 7. Configure nginx reverse proxy
# 8. Start the application
#
# Total time: ~5 minutes (faster without MongoDB!)
```

**Available environment shortcuts:**
- `configure-dev` / `deploy-do-dev` - Development
- `configure-test` / `deploy-do-test` - Testing
- `configure-prod` / `deploy-do-prod` - Production

### Manual Deployment (Full Control)

For advanced use cases with full parameter control:

```bash
# Configure manually
invoke configure --envtype=prod --setup-iam \
    --storage-backend=s3 --s3-bucket=putplace \
    --mongodb-url="mongodb+srv://..."

# Deploy manually
invoke deploy-do --create --droplet-name=putplace-prod \
    --storage-backend=s3 --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod --mongodb-url="..."
```

**Output:**
```
=== PutPlace Digital Ocean Deployment ===

Creating droplet: putplace-prod
  Region: fra1
  Size: s-1vcpu-1gb
  Image: ubuntu-22-04-x64
  Using SSH keys: 12345678

✓ Droplet created successfully!
  ID: 334455667
  IP: 165.22.123.45

Waiting for SSH to be available on 165.22.123.45...
✓ SSH is ready

Provisioning server at 165.22.123.45...
  Running provisioning script (this may take 5-10 minutes)...
✓ Server provisioned successfully

Deploying application from https://github.com/jdrumgoole/putplace.git...
✓ Application deployed successfully

Setting up systemd service...
✓ Systemd service configured and started

Setting up nginx reverse proxy...
✓ Nginx configured successfully

=== Deployment Complete! ===

Application URL: http://165.22.123.45
API Docs: http://165.22.123.45/docs
SSH Access: ssh root@165.22.123.45

Next steps:
1. Configure admin user and API keys
2. Set up SSL certificate (if using domain)
3. Configure firewall rules
4. Set up monitoring and backups
```

## Deployment Options

### Deploy to Existing Droplet

If you already have a droplet:

```bash
# Deploy by droplet name
invoke deploy-do --droplet-name=putplace-prod

# Deploy by IP address
invoke deploy-do --ip=165.22.123.45
```

### Deploy with Custom Domain

```bash
# Deploy with domain name
invoke deploy-do --create --droplet-name=putplace-prod --domain=api.example.com

# After deployment, point your domain's A record to the droplet IP
# Then enable SSL:
ssh root@165.22.123.45 'certbot --nginx -d api.example.com'
```

### Custom Droplet Size and Region

```bash
# Deploy with 2GB RAM (recommended for production)
invoke deploy-do --create --droplet-name=putplace-prod --size=s-1vcpu-2gb

# Deploy in a different region
invoke deploy-do --create --droplet-name=putplace-prod --region=nyc1

# Common regions:
#   fra1  - Frankfurt, Germany
#   lon1  - London, UK
#   nyc1  - New York, USA
#   sfo3  - San Francisco, USA
#   sgp1  - Singapore
#   tor1  - Toronto, Canada

# Common sizes:
#   s-1vcpu-1gb   - $6/month  (512 MB transfer)
#   s-1vcpu-2gb   - $12/month (2 TB transfer) ← Recommended
#   s-2vcpu-4gb   - $24/month (4 TB transfer)
#   s-4vcpu-8gb   - $48/month (5 TB transfer)
```

### Deploy with AWS S3 Storage

**Recommended: Use environment shortcuts**

```bash
# Configure production with S3 (one-time setup)
invoke configure-prod --mongodb-url="mongodb://localhost:27017"

# Deploy to production
invoke deploy-do-prod --create
```

**Manual approach with full control:**

```bash
# First, generate AWS credentials (one-time setup)
invoke configure --envtype=prod --setup-iam \
    --storage-backend=s3 \
    --s3-bucket=putplace

# Deploy with S3 storage and AWS credentials
invoke deploy-do --create \
    --droplet-name=putplace-prod \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod

# Deploy to existing droplet with S3
invoke deploy-do \
    --droplet-name=putplace-prod \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod
```

See the "Using AWS S3 for File Storage" section below for detailed configuration.

### Deploy with MongoDB Atlas and S3 Storage

**Recommended: Use environment shortcuts**

```bash
# Configure production with Atlas and S3 (one-time setup)
invoke configure-prod --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

# Deploy to production (skips MongoDB installation)
invoke deploy-do-prod --create
```

**Manual approach with full control:**

```bash
# Complete cloud deployment (no local storage)
invoke deploy-do --create \
    --droplet-name=putplace-prod \
    --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/" \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod
```

## Quick Updates

After initial deployment, use the update command for fast code updates:

```bash
# Update by droplet name
invoke update-do --droplet-name=putplace-prod

# Update by IP
invoke update-do --ip=165.22.123.45

# Update specific branch
invoke update-do --ip=165.22.123.45 --branch=develop
```

This pulls the latest code, updates dependencies, and restarts the service. Takes ~30 seconds vs ~10 minutes for full deployment.

## Management Commands

### SSH Access

```bash
# SSH by droplet name
invoke ssh-do --droplet-name=putplace-prod

# SSH by IP
invoke ssh-do --ip=165.22.123.45
```

### View Logs

```bash
# View access logs (last 50 lines)
invoke logs-do --droplet-name=putplace-prod

# View error logs
invoke logs-do --ip=165.22.123.45 --error

# Follow logs in real-time
invoke logs-do --ip=165.22.123.45 --error --follow

# Manual log viewing via SSH
ssh root@165.22.123.45 'tail -f /var/log/putplace/error.log'
ssh root@165.22.123.45 'tail -f /var/log/putplace/access.log'
```

### Service Management

```bash
# SSH into droplet
invoke ssh-do --droplet-name=putplace-prod

# Check service status
systemctl status putplace

# Restart service
systemctl restart putplace

# View systemd logs
journalctl -u putplace -f

# Check nginx status
systemctl status nginx

# Test nginx configuration
nginx -t
```

## Post-Deployment Configuration

### 1. Create Admin User

The application creates an admin user automatically on first startup. Check the credentials:

```bash
ssh root@165.22.123.45 'cat /tmp/putplace_initial_creds.txt'
```

Or set custom credentials before first startup:

```bash
ssh root@165.22.123.45

# Edit .env file
cd /opt/putplace/putplace
nano .env

# Add:
PUTPLACE_ADMIN_USERNAME=admin
PUTPLACE_ADMIN_PASSWORD=your-secure-password
PUTPLACE_ADMIN_EMAIL=admin@example.com

# Restart service
systemctl restart putplace
```

### 2. Enable SSL/HTTPS (Recommended)

If you have a domain pointed to your droplet:

```bash
ssh root@165.22.123.45

# Run certbot (interactive)
certbot --nginx -d api.example.com

# Follow prompts to:
# 1. Enter email address
# 2. Agree to terms
# 3. Choose redirect HTTP to HTTPS (recommended)

# Auto-renewal is configured automatically
# Test renewal:
certbot renew --dry-run
```

Your API will now be available at `https://api.example.com`.

### 3. Configure Firewall (UFW)

```bash
ssh root@165.22.123.45

# Enable firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable

# Check status
ufw status
```

### 4. Configure Environment Variables

Edit `/opt/putplace/putplace/.env`:

```bash
ssh root@165.22.123.45
cd /opt/putplace/putplace
nano .env
```

Important settings:
```bash
# MongoDB (local)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace

# Or use MongoDB Atlas
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/putplace

# Registration
ALLOW_REGISTRATION=false  # Disable public registration

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

After changes:
```bash
systemctl restart putplace
```

## Architecture

### Server Layout

```
/opt/putplace/
  └── ppserver.toml          # Application configuration

/var/putplace/
  └── storage/               # Local file storage (if not using S3)

/root/.aws/                  # AWS credentials (if using S3)
  ├── credentials            # AWS access keys
  └── config                 # AWS region/profile config

/var/log/putplace/
  ├── access.log             # Application access logs
  └── error.log              # Application error logs

/etc/systemd/system/
  └── putplace.service       # Systemd service file

/etc/nginx/
  └── sites-available/
      └── putplace           # Nginx configuration
```

### Services

1. **MongoDB** (`mongod.service`)
   - Port: 27017 (localhost only)
   - Data: `/var/lib/mongodb`
   - Logs: `/var/log/mongodb`

2. **PutPlace** (`putplace.service`)
   - Port: 8000 (localhost only)
   - Workers: 4 (uvicorn)
   - Logs: `/var/log/putplace/`

3. **Nginx** (`nginx.service`)
   - Ports: 80 (HTTP), 443 (HTTPS)
   - Reverse proxy to port 8000
   - SSL termination

### Network Flow

```
Internet
  ↓
Nginx (port 80/443)
  ↓
PutPlace (ppserver, port 8000)
  ↓
  ├─→ MongoDB (port 27017, localhost or Atlas)
  └─→ File Storage (Local disk or AWS S3)
```

## Using MongoDB Atlas Instead

If you prefer MongoDB Atlas over local MongoDB:

### 1. Create Atlas Cluster

1. Sign up at https://www.mongodb.com/cloud/atlas
2. Create a free M0 cluster or paid cluster
3. Add droplet IP to IP whitelist
4. Create database user
5. Get connection string

### 2. Update Configuration

```bash
ssh root@165.22.123.45
cd /opt/putplace/putplace

# Edit .env
nano .env

# Update MongoDB URL
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/putplace

# Restart service
systemctl restart putplace

# Optional: Disable local MongoDB to save resources
systemctl stop mongod
systemctl disable mongod
```

This saves ~200MB RAM by not running MongoDB locally.

## Using AWS S3 for File Storage

PutPlace supports storing file content in AWS S3 instead of local disk storage. This section shows how to configure S3 storage with automatic AWS credentials deployment.

### Prerequisites

1. **AWS Account** with S3 access
2. **IAM Users Created**: Use `putplace_configure` with `--setup-iam` to create IAM users and S3 buckets
3. **Credentials Generated**: Located in `./aws_credentials_output/` directory

### 1. Generate AWS Credentials (One-Time Setup)

On your local machine, create AWS IAM users, S3 buckets, and credentials for your environment.

**Recommended: Use environment shortcuts**

```bash
# Production environment (creates putplace-prod IAM user and bucket)
invoke configure-prod --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"

# Development environment (creates putplace-dev IAM user and bucket)
invoke configure-dev --mongodb-url="mongodb://localhost:27017"

# Test environment (creates putplace-test IAM user and bucket)
invoke configure-test --mongodb-url="mongodb://localhost:27017"
```

**Manual approach with full control:**

```bash
# Generate IAM users, S3 buckets, and credentials
invoke configure --envtype=prod --setup-iam \
    --storage-backend=s3 \
    --s3-bucket=putplace \
    --aws-region=eu-west-1 \
    --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"
```

**Both approaches create:**
- IAM user: `putplace-{envtype}` (e.g., putplace-prod)
- S3 bucket: `putplace-{envtype}` (e.g., putplace-prod)
- Credentials in: `./aws_credentials_output/`
  - `aws_credentials` (AWS credentials format)
  - `aws_config` (AWS config format)
  - `.env.{envtype}` (environment variable format)

**What gets created:**
```
aws_credentials_output/
├── aws_credentials          # Multi-profile credentials file
│   [putplace-dev]
│   aws_access_key_id = AKIAIOSFODNN7EXAMPLE
│   aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
│   [putplace-prod]
│   ...
├── aws_config              # Multi-profile config file
│   [profile putplace-dev]
│   region = eu-west-1
│   ...
├── .env.dev                # Environment-specific credentials
├── .env.prod
└── .env.test
```

### 2. Deploy with S3 Storage and AWS Credentials

The deployment script automatically copies AWS credentials to the droplet and configures the application to use them.

**Recommended: Use environment shortcuts**

```bash
# Deploy to new production droplet (reads ppserver-prod.toml)
invoke deploy-do-prod --create

# Deploy to existing production droplet
invoke deploy-do-prod

# Deploy to dev/test environments
invoke deploy-do-dev --create
invoke deploy-do-test --create
```

**Manual approach with full control:**

```bash
# Deploy to new droplet with S3 storage
invoke deploy-do --create \
    --droplet-name=putplace-prod \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod

# Deploy to existing droplet with S3 storage
invoke deploy-do \
    --droplet-name=putplace-prod \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod \
    --aws-credentials-dir=./aws_credentials_output
```

**What happens during deployment:**

1. **Generates `ppserver.toml`** locally with S3 configuration
2. **Copies AWS credentials** from `./aws_credentials_output/` to droplet:
   - `aws_credentials` → `/root/.aws/credentials`
   - `aws_config` → `/root/.aws/config`
   - Sets proper permissions (600) for security
3. **Configures systemd service** with `AWS_PROFILE=putplace-prod` environment variable
4. **Application automatically uses** S3 for file storage with the specified profile

### 3. Verify S3 Configuration

After deployment, verify S3 is working:

```bash
# Check AWS credentials are configured
ssh root@165.22.123.45 'cat /root/.aws/credentials'
ssh root@165.22.123.45 'aws s3 ls s3://putplace-prod/'

# Check service environment
ssh root@165.22.123.45 'systemctl show putplace | grep AWS_PROFILE'

# Upload a test file via API
curl -X POST http://165.22.123.45/put_file \
  -H "Content-Type: application/json" \
  -d '{
    "filepath": "/test/file.txt",
    "hostname": "test-host",
    "ip_address": "192.168.1.1",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'

# Verify file is in S3
ssh root@165.22.123.45 'aws s3 ls s3://putplace-prod/e3/b0/'
```

### 4. Alternative: Manual AWS Credentials Setup

If you prefer to configure AWS credentials manually without using `--setup-iam`:

```bash
# SSH into droplet
ssh root@165.22.123.45

# Create AWS credentials directory
mkdir -p /root/.aws

# Create credentials file
cat > /root/.aws/credentials << 'EOF'
[putplace-prod]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
EOF

# Create config file
cat > /root/.aws/config << 'EOF'
[profile putplace-prod]
region = eu-west-1
output = json
EOF

# Set proper permissions
chmod 600 /root/.aws/credentials /root/.aws/config

# Update systemd service to use profile
nano /etc/systemd/system/putplace.service

# Add under [Service]:
Environment="AWS_PROFILE=putplace-prod"

# Reload and restart
systemctl daemon-reload
systemctl restart putplace
```

### 5. Environment-Specific Deployments

Deploy different environments with appropriate credentials.

**Recommended: Use environment shortcuts**

The shortcut tasks automatically configure the correct IAM user, S3 bucket, and droplet name for each environment:

```bash
# Development environment
invoke configure-dev --mongodb-url="mongodb://localhost:27017"
invoke deploy-do-dev --create

# Test environment
invoke configure-test --mongodb-url="mongodb://localhost:27017"
invoke deploy-do-test --create

# Production environment
invoke configure-prod --mongodb-url="mongodb+srv://user:pass@cluster.mongodb.net/"
invoke deploy-do-prod --create
```

**Manual approach with full control:**

```bash
# Development environment
invoke deploy-do --create \
    --droplet-name=putplace-dev \
    --storage-backend=s3 \
    --s3-bucket=putplace-dev \
    --aws-profile=putplace-dev

# Production environment
invoke deploy-do --create \
    --droplet-name=putplace-prod \
    --storage-backend=s3 \
    --s3-bucket=putplace-prod \
    --aws-profile=putplace-prod
```

### S3 Storage Benefits

**Advantages:**
- **Unlimited storage**: No disk space limits
- **Durability**: 99.999999999% (11 nines) durability
- **Redundancy**: Automatic replication across availability zones
- **Cost-effective**: Pay only for what you use (~$0.023/GB/month)
- **Scalability**: Handles any number of files
- **Security**: Encryption at rest and in transit

**When to use S3:**
- Storing large amounts of file content
- Multi-region deployments (shared storage)
- High durability requirements
- Compliance/audit requirements

**When to use local storage:**
- Small deployments with limited file storage needs
- Lower latency requirements (files on same server)
- Cost optimization for very small datasets (<10GB)
- Development/testing environments

### S3 Cost Estimation

For PutPlace file storage:

| Storage Amount | Monthly Cost (S3 Standard) |
|----------------|---------------------------|
| 1 GB | $0.023 |
| 10 GB | $0.23 |
| 100 GB | $2.30 |
| 1 TB | $23.00 |

**Additional costs:**
- PUT requests: $0.005 per 1,000 requests
- GET requests: $0.0004 per 1,000 requests
- Data transfer out: $0.09/GB (first 10 TB/month)

**Example**: Storing 50GB with 10,000 PUT and 100,000 GET requests per month:
- Storage: 50 GB × $0.023 = $1.15
- PUT: 10,000 ÷ 1,000 × $0.005 = $0.05
- GET: 100,000 ÷ 1,000 × $0.0004 = $0.04
- **Total: ~$1.24/month**

### Troubleshooting S3 Storage

**Check AWS credentials are configured:**
```bash
ssh root@165.22.123.45
aws configure list --profile putplace-prod
```

**Test S3 access:**
```bash
ssh root@165.22.123.45
aws s3 ls --profile putplace-prod
aws s3 ls s3://putplace-prod/ --profile putplace-prod
```

**Check service environment variables:**
```bash
ssh root@165.22.123.45
systemctl show putplace | grep -E 'AWS|Environment'
```

**View application logs for S3 errors:**
```bash
ssh root@165.22.123.45
tail -f /var/log/putplace/error.log | grep -i s3
```

**Common S3 errors:**

1. **"Unable to locate credentials"**
   - Check `/root/.aws/credentials` exists and has correct permissions
   - Verify `AWS_PROFILE` is set in systemd service
   - Restart service: `systemctl restart putplace`

2. **"Access Denied" errors**
   - Verify IAM user has S3 permissions
   - Check bucket name matches IAM policy
   - Verify bucket exists: `aws s3 ls s3://putplace-prod/`

3. **"No such bucket"**
   - Create bucket: `aws s3 mb s3://putplace-prod --region eu-west-1`
   - Or re-run `invoke configure --setup-iam`

## Monitoring and Backups

### Health Checks

```bash
# Check application health
curl http://your-droplet-ip/health

# Check service status
ssh root@165.22.123.45 'systemctl is-active putplace'

# Check MongoDB
ssh root@165.22.123.45 'systemctl is-active mongod'
```

### MongoDB Backups

```bash
ssh root@165.22.123.45

# Create backup
mongodump --db putplace --out /root/backups/$(date +%Y%m%d)

# Restore backup
mongorestore --db putplace /root/backups/20250113/putplace
```

### Automated Backups

Add to crontab:

```bash
ssh root@165.22.123.45
crontab -e

# Daily backup at 3 AM
0 3 * * * mongodump --db putplace --out /root/backups/$(date +\%Y\%m\%d) && find /root/backups -mtime +7 -delete
```

### Digital Ocean Backups

Enable droplet backups in Digital Ocean dashboard:
- Settings → Backups → Enable
- Cost: 20% of droplet price
- Weekly automated snapshots

## Scaling

### Vertical Scaling (Resize Droplet)

```bash
# Power off droplet
doctl compute droplet-action shutdown <droplet-id>

# Resize (this may take several minutes)
doctl compute droplet-action resize <droplet-id> --size s-2vcpu-4gb --resize-disk

# Power on
doctl compute droplet-action power-on <droplet-id>
```

### Horizontal Scaling (Multiple Droplets + Load Balancer)

1. Create multiple droplets with same app
2. Set up Digital Ocean Load Balancer
3. Use MongoDB Atlas (shared database)
4. Point domain to load balancer

## Troubleshooting

### Application Won't Start

```bash
# Check service status
systemctl status putplace

# Check logs
journalctl -u putplace -n 50

# Check application logs
tail -50 /var/log/putplace/error.log

# Test manually
cd /opt/putplace/putplace
source .venv/bin/activate
uvicorn putplace.main:app --host 0.0.0.0 --port 8000
```

### MongoDB Connection Issues

```bash
# Check MongoDB status
systemctl status mongod

# Check MongoDB logs
tail -50 /var/log/mongodb/mongod.log

# Test MongoDB connection
mongosh --eval "db.adminCommand('ping')"

# Check if MongoDB is listening
netstat -tlnp | grep 27017
```

### Nginx Issues

```bash
# Check nginx status
systemctl status nginx

# Test nginx configuration
nginx -t

# Check nginx logs
tail -50 /var/log/nginx/error.log

# Restart nginx
systemctl restart nginx
```

### Out of Memory

```bash
# Check memory usage
free -h

# Check top processes
top

# Add swap space (if needed)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### SSL Certificate Issues

```bash
# Check certificate status
certbot certificates

# Renew certificate
certbot renew

# Test auto-renewal
certbot renew --dry-run
```

## Security Best Practices

### 1. Change SSH Port (Optional)

```bash
# Edit SSH config
nano /etc/ssh/sshd_config

# Change port (e.g., to 2222)
Port 2222

# Restart SSH
systemctl restart sshd

# Update firewall
ufw allow 2222/tcp
ufw delete allow 22/tcp
```

### 2. Disable Root SSH Login

```bash
# Create non-root user first
adduser deploy
usermod -aG sudo deploy

# Copy SSH keys
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# Disable root login
nano /etc/ssh/sshd_config
# Set: PermitRootLogin no

systemctl restart sshd
```

### 3. Set Up Fail2Ban

```bash
apt-get install fail2ban

# Configure
nano /etc/fail2ban/jail.local

# Add:
[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

systemctl restart fail2ban
```

### 4. Regular Updates

```bash
# Set up automatic security updates
apt-get install unattended-upgrades
dpkg-reconfigure --priority=low unattended-upgrades
```

## Cleanup and Removal

### Remove Droplet

```bash
# List droplets
doctl compute droplet list

# Delete droplet
doctl compute droplet delete <droplet-id>

# Or by name
doctl compute droplet delete putplace-prod
```

### Remove from Digital Ocean Dashboard

1. Go to https://cloud.digitalocean.com/droplets
2. Click on droplet
3. Click "Destroy" in the menu
4. Confirm deletion

## Advanced Configuration

### Custom Systemd Service Settings

Edit `/etc/systemd/system/putplace.service`:

```ini
[Service]
# More workers for high traffic
ExecStart=/opt/putplace/putplace/.venv/bin/uvicorn putplace.main:app --host 0.0.0.0 --port 8000 --workers 8

# Memory limits
MemoryMax=1G
MemoryHigh=800M

# Process limits
LimitNOFILE=65536
```

Reload and restart:
```bash
systemctl daemon-reload
systemctl restart putplace
```

### Nginx Performance Tuning

Edit `/etc/nginx/sites-available/putplace`:

```nginx
server {
    listen 80;
    server_name api.example.com;

    # Increase client body size for large uploads
    client_max_body_size 100M;

    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    # Buffering
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;

    # Compression
    gzip on;
    gzip_types application/json;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Using Postgres Instead of MongoDB

The deployment script currently installs MongoDB, but you can modify it to use Postgres:

1. Edit deployment script to install Postgres instead
2. Update application to use SQLAlchemy + Postgres
3. Update connection string in `.env`

## Cost Optimization

### Resize Droplet Based on Usage

Start with 1GB ($6/month), monitor for a week, then resize if needed:

```bash
# Check memory usage
ssh root@IP 'free -h'

# Check CPU usage
ssh root@IP 'top -bn1 | head -20'

# If consistently using >80% memory, resize to 2GB
```

### Use Monitoring

Enable Digital Ocean monitoring (free):
- Dashboard → Droplet → Enable Monitoring
- View CPU, memory, disk, and network graphs

### Snapshots vs Backups

- **Backups**: Automatic, weekly, 20% of droplet cost
- **Snapshots**: Manual, cheaper for occasional use

## Support

- **Digital Ocean Docs**: https://docs.digitalocean.com/
- **Community**: https://www.digitalocean.com/community
- **Support**: https://www.digitalocean.com/support

## Comparison with Other Deployment Methods

| Feature | Digital Ocean | AWS AppRunner | Heroku |
|---------|--------------|---------------|--------|
| Cost | $6-12/month | $25+/month | $25+/month |
| Setup Time | ~10 minutes | ~5 minutes | ~5 minutes |
| Flexibility | Full control | Limited | Limited |
| Scaling | Manual resize | Auto-scale | Auto-scale |
| MongoDB | Included | Separate ($9+) | Addon ($15+) |
| SSL | Free (Let's Encrypt) | Included | Included |
| SSH Access | Yes | No | Limited |
| Custom Software | Yes | No | Limited |

**Digital Ocean is best for:**
- Cost-sensitive deployments
- Full control requirements
- Learning/understanding the stack
- Custom software needs

**AppRunner/Heroku are best for:**
- Zero-maintenance deployments
- Auto-scaling requirements
- Quick prototypes
- Teams without DevOps expertise
