# Client Guide

Complete guide to using the PutPlace client (`ppclient.py`).

## Overview

The PutPlace client is a command-line tool that scans directories, calculates file metadata, and uploads it to a PutPlace server. It features:

- 📁 Recursive directory scanning
- 🔐 API key authentication
- 🎯 Pattern-based file exclusion
- 🚀 Automatic file deduplication
- 🎨 Rich console output
- ⚙️ Flexible configuration (CLI/env/file)

## Installation

The client is included in the PutPlace repository:

```bash
# Clone repository
git clone https://github.com/jdrumgoole/putplace.git
cd putplace

# Install dependencies
pip install -e .

# Or install required packages directly
pip install httpx rich configargparse
```

## Quick Start

### Get an API Key

You need an API key to use the client. Get one from your server administrator or create your own:

```bash
# On the server
python -m putplace.scripts.create_api_key --name "my-client"

# Save the displayed API key!
```

### First Scan

```bash
# Set your API key
export PUTPLACE_API_KEY="your-api-key-here"

# Test scan (dry run)
python ppclient.py /tmp --dry-run

# Real scan
python ppclient.py /tmp
```

## Usage

### Basic Syntax

```bash
python ppclient.py [OPTIONS] PATH
```

### Options

#### Required Options

**`PATH`** (positional)
- Path to scan (file or directory)
- Supports absolute and relative paths

```bash
python ppclient.py /var/www
python ppclient.py ~/Documents
python ppclient.py .
```

**`--api-key KEY` or `-k KEY`**
- API key for authentication
- Can also use `PUTPLACE_API_KEY` environment variable
- Can also set in config file

```bash
python ppclient.py /tmp --api-key "your-api-key"
python ppclient.py /tmp -k "your-api-key"
```

#### Optional Options

**`--url URL`**
- PutPlace server API endpoint
- Default: `http://localhost:8000/put_file`

```bash
python ppclient.py /tmp --url "https://putplace.example.com/put_file"
```

**`--hostname HOSTNAME`**
- Override auto-detected hostname
- Useful for custom naming

```bash
python ppclient.py /tmp --hostname "web-server-01"
```

**`--ip IP`**
- Override auto-detected IP address
- Useful when multiple IPs exist

```bash
python ppclient.py /tmp --ip "192.168.1.100"
```

**`--exclude PATTERN`**
- Exclude files matching pattern
- Can be used multiple times
- Supports wildcards

```bash
python ppclient.py /tmp --exclude "*.log" --exclude ".git"
```

**`--dry-run`**
- Scan files but don't send to server
- Useful for testing

```bash
python ppclient.py /tmp --dry-run
```

**`--verbose` or `-v`**
- Enable verbose output
- Shows detailed progress

```bash
python ppclient.py /tmp --verbose
python ppclient.py /tmp -v
```

**`--config PATH`**
- Path to configuration file
- Default: `ppclient.conf` or `~/ppclient.conf`

```bash
python ppclient.py /tmp --config ~/my-config.conf
```

**`--help` or `-h`**
- Show help message

```bash
python ppclient.py --help
```

## Configuration

### Configuration Priority

Settings are applied in this order (highest to lowest priority):

1. **Command-line arguments** (highest)
2. **Environment variables**
3. **Configuration file** (lowest)

Example:
```bash
# Config file has: api-key = file-key
# Environment has: PUTPLACE_API_KEY=env-key
# Command line has: --api-key cli-key

# Result: cli-key is used
```

### Configuration File

Create a configuration file to avoid repeating options:

**~/ppclient.conf:**
```ini
[DEFAULT]
url = http://localhost:8000/put_file
api-key = your-api-key-here
exclude = .git
exclude = __pycache__
exclude = *.log
```

**Set secure permissions:**
```bash
chmod 600 ~/ppclient.conf
```

**Use:**
```bash
# All settings from config file
python ppclient.py /var/www
```

See [Configuration Reference](configuration.md#client-configuration) for all options.

## API Key Authentication

### Three Methods

#### 1. Command Line (Quick Testing)

```bash
python ppclient.py /tmp --api-key "your-api-key"
```

**Pros:** Quick for testing
**Cons:** Visible in shell history and process list

#### 2. Environment Variable (Recommended for Scripts)

```bash
export PUTPLACE_API_KEY="your-api-key"
python ppclient.py /tmp
```

**Pros:** Not in command history, works across commands
**Cons:** Visible in environment

**Make persistent:**
```bash
# For bash
echo 'export PUTPLACE_API_KEY="your-api-key"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export PUTPLACE_API_KEY="your-api-key"' >> ~/.zshrc
source ~/.zshrc
```

#### 3. Config File (Recommended for Production)

```bash
# Create config
cat > ~/ppclient.conf << 'EOF'
[DEFAULT]
api-key = your-api-key
EOF

chmod 600 ~/ppclient.conf

# Use
python ppclient.py /tmp
```

**Pros:** Most secure, persistent
**Cons:** Requires file setup

### Security Best Practices

**DO:**
- Use separate API keys per client/server
- Set file permissions to 600 on config files
- Rotate keys regularly
- Use environment variables or config files in production

**DON'T:**
- Commit API keys to version control
- Share API keys between users
- Use command-line API keys in production
- Use overly permissive file permissions

## File Exclusion

### Exclude Patterns

Use `--exclude` to skip files:

**File extensions:**
```bash
--exclude "*.log"      # All .log files
--exclude "*.tmp"      # All .tmp files
--exclude "*.pyc"      # Compiled Python files
```

**Directories:**
```bash
--exclude ".git"           # Git repositories
--exclude "node_modules"   # Node.js dependencies
--exclude "__pycache__"    # Python cache
--exclude ".venv"          # Virtual environments
```

**Wildcards:**
```bash
--exclude "test_*"     # Files starting with test_
--exclude "*~"         # Backup files
--exclude ".*.swp"     # Vim swap files
```

### Common Exclude Patterns

**Python projects:**
```bash
python ppclient.py /project \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".venv" \
  --exclude "venv" \
  --exclude ".pytest_cache" \
  --exclude "*.egg-info"
```

**Node.js projects:**
```bash
python ppclient.py /project \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude "dist" \
  --exclude "build" \
  --exclude "*.log"
```

**Web servers:**
```bash
python ppclient.py /var/www \
  --exclude ".git" \
  --exclude "*.log" \
  --exclude "cache" \
  --exclude "tmp" \
  --exclude ".DS_Store"
```

### Config File Exclusions

Put common exclusions in config file:

```ini
[DEFAULT]
# Universal exclusions
exclude = .git
exclude = .DS_Store
exclude = Thumbs.db

# Python
exclude = __pycache__
exclude = *.pyc
exclude = .venv
exclude = venv

# Node.js
exclude = node_modules

# Logs and temporary files
exclude = *.log
exclude = *.tmp
exclude = tmp
exclude = cache
```

## Examples

### Example 1: Simple Scan

Scan a directory with default settings:

```bash
export PUTPLACE_API_KEY="your-api-key"
python ppclient.py /var/www
```

Output:
```
PutPlace Client
  Path: /var/www
  Hostname: web-server-01
  IP: 192.168.1.100
  URL: http://localhost:8000/put_file
  API Key: ********a1b2c3d4

Found 150 files to process
Processing files... ━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:05
✓ Processing complete

Summary:
  Total files: 150
  Successful: 148
  Failed: 2
  Files uploaded: 35
```

### Example 2: Dry Run

Test without sending data:

```bash
python ppclient.py /tmp --dry-run
```

Output shows what would be sent but doesn't actually send.

### Example 3: Remote Server

Scan and send to remote server:

```bash
python ppclient.py /var/www \
  --url "https://putplace.example.com/put_file" \
  --api-key "production-api-key"
```

### Example 4: Custom Hostname

Override auto-detected hostname:

```bash
python ppclient.py /var/www \
  --hostname "web-prod-01" \
  --ip "10.0.1.50"
```

### Example 5: Multiple Exclusions

Exclude multiple patterns:

```bash
python ppclient.py /home/user \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude "__pycache__" \
  --exclude "*.log" \
  --exclude "*.tmp" \
  --exclude ".venv"
```

### Example 6: Verbose Output

See detailed progress:

```bash
python ppclient.py /tmp --verbose
```

Output:
```
PutPlace Client
  Path: /tmp
  ...

Scanning directory: /tmp
Found file: /tmp/file1.txt (1234 bytes)
Found file: /tmp/file2.txt (5678 bytes)
...

Processing: /tmp/file1.txt
  SHA256: abc123...
  Sending metadata... ✓
  Upload required: No (file already exists)

Processing: /tmp/file2.txt
  SHA256: def456...
  Sending metadata... ✓
  Upload required: Yes
  Uploading content... ✓
```

## Workflows

### Development Workflow

```bash
# 1. Get API key from server admin
export PUTPLACE_API_KEY="dev-api-key"

# 2. Test connection with dry run
python ppclient.py /tmp --dry-run

# 3. Scan development directory
python ppclient.py ~/projects/myapp \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude ".venv"
```

### Production Workflow

```bash
# 1. Create config file
cat > ~/ppclient.conf << 'EOF'
[DEFAULT]
url = https://putplace.example.com/put_file
api-key = production-api-key
exclude = .git
exclude = *.log
exclude = tmp
EOF

chmod 600 ~/ppclient.conf

# 2. Test with dry run
python ppclient.py /var/www --dry-run

# 3. Run actual scan
python ppclient.py /var/www

# 4. Set up cron job for daily scans
echo "0 2 * * * /usr/bin/python3 /path/to/ppclient.py /var/www" | crontab -
```

### Multi-Environment Workflow

```bash
# Development config
cat > ~/ppclient.conf.dev << 'EOF'
url = http://dev-putplace:8000/put_file
api-key = dev-key
EOF

# Staging config
cat > ~/ppclient.conf.staging << 'EOF'
url = https://staging-putplace.example.com/put_file
api-key = staging-key
EOF

# Production config
cat > ~/ppclient.conf.prod << 'EOF'
url = https://putplace.example.com/put_file
api-key = prod-key
EOF

# Use with --config flag
python ppclient.py /var/www --config ~/ppclient.conf.dev
python ppclient.py /var/www --config ~/ppclient.conf.staging
python ppclient.py /var/www --config ~/ppclient.conf.prod
```

## Automated Scanning

### Cron Jobs

#### Daily Scan at 2 AM

```bash
# Edit crontab
crontab -e

# Add line
0 2 * * * /usr/bin/python3 /path/to/ppclient.py /var/www
```

#### Hourly Scan

```bash
0 * * * * /usr/bin/python3 /path/to/ppclient.py /var/www
```

#### Weekly Scan (Sundays at 3 AM)

```bash
0 3 * * 0 /usr/bin/python3 /path/to/ppclient.py /var/www
```

#### With Logging

```bash
0 2 * * * /usr/bin/python3 /path/to/ppclient.py /var/www >> /var/log/ppclient.log 2>&1
```

### systemd Timer

**Create service: /etc/systemd/system/ppclient.service**

```ini
[Unit]
Description=PutPlace Client Scan
After=network.target

[Service]
Type=oneshot
User=www-data
Group=www-data
Environment="PUTPLACE_API_KEY=your-api-key"
ExecStart=/usr/bin/python3 /path/to/ppclient.py /var/www
StandardOutput=journal
StandardError=journal
```

**Create timer: /etc/systemd/system/ppclient.timer**

```ini
[Unit]
Description=PutPlace Client Daily Scan
Requires=ppclient.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable ppclient.timer
sudo systemctl start ppclient.timer

# Check status
sudo systemctl status ppclient.timer
sudo systemctl list-timers
```

## Output and Progress

### Console Output

The client provides rich console output with:

- ✅ Configuration summary
- 📊 Progress bar during scanning
- 📈 Real-time counters
- ✓ Success/failure indicators
- 📋 Final summary

### Exit Codes

```bash
0   # Success - all files processed
1   # Partial failure - some files failed
2   # Complete failure - no files processed
```

**Use in scripts:**
```bash
python ppclient.py /var/www
if [ $? -eq 0 ]; then
    echo "All files processed successfully"
elif [ $? -eq 1 ]; then
    echo "Some files failed"
else
    echo "Complete failure"
fi
```

## Troubleshooting

### API Key Issues

**Problem: "No API key provided"**

```
Warning: No API key provided (authentication may fail)
```

**Solution:** Provide API key via:
- `--api-key` flag
- `PUTPLACE_API_KEY` environment variable
- `api-key` in config file

---

**Problem: "401 Unauthorized"**

```
Failed to send file.txt: Client error '401 Unauthorized'
```

**Causes:**
1. Invalid API key
2. Revoked API key
3. Wrong server URL

**Solution:**
```bash
# Test API key
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/api_keys

# If invalid, create new key
python -m putplace.scripts.create_api_key --name "new-key"
```

### Connection Issues

**Problem: "Connection refused"**

```
Failed to send file.txt: Cannot connect to host localhost:8000
```

**Causes:**
1. Server not running
2. Wrong URL
3. Firewall blocking

**Solution:**
```bash
# Check server is running
curl http://localhost:8000/health

# Check URL
python ppclient.py /tmp --url "http://correct-server:8000/put_file"

# Check firewall
telnet localhost 8000
```

### File Access Issues

**Problem: "Permission denied"**

```
Error scanning /var/www/private: Permission denied
```

**Solution:**
```bash
# Run with appropriate user
sudo -u www-data python ppclient.py /var/www

# Or fix permissions
sudo chmod -R +r /var/www
```

### Large Directory Scans

**Problem: Scan is slow**

**Solutions:**
1. Use exclusions to skip unnecessary files
2. Scan subdirectories separately
3. Use `--verbose` to monitor progress

```bash
# Exclude large directories
python ppclient.py /var/www \
  --exclude "cache" \
  --exclude "tmp" \
  --exclude "*.log"

# Scan subdirectories separately
python ppclient.py /var/www/app
python ppclient.py /var/www/static
```

## Advanced Usage

### Custom Scripts

Integrate client into your scripts:

```bash
#!/bin/bash
# backup-and-scan.sh

# Backup directories
DIRS="/var/www /etc /opt/myapp"

for dir in $DIRS; do
    echo "Scanning $dir..."
    python ppclient.py "$dir" \
        --url "https://putplace.example.com/put_file" \
        --api-key "$PUTPLACE_API_KEY" \
        --exclude ".git" \
        --exclude "*.log"

    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to scan $dir"
        exit 1
    fi
done

echo "All directories scanned successfully"
```

### Monitoring Integration

**Send results to monitoring system:**

```bash
#!/bin/bash
# scan-with-monitoring.sh

OUTPUT=$(python ppclient.py /var/www 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    # Send success metric to monitoring
    curl -X POST https://monitoring.example.com/metric \
        -d "service=ppclient&status=success"
else
    # Send failure metric and alert
    curl -X POST https://monitoring.example.com/metric \
        -d "service=ppclient&status=failure"

    # Send alert
    echo "$OUTPUT" | mail -s "PutPlace scan failed" ops@example.com
fi
```

### Parallel Scanning

Scan multiple directories in parallel:

```bash
#!/bin/bash
# parallel-scan.sh

python ppclient.py /var/www &
python ppclient.py /etc &
python ppclient.py /opt &

wait

echo "All scans complete"
```

## Performance Tips

1. **Use exclusions** - Skip unnecessary files
   ```bash
   --exclude "*.log" --exclude "cache" --exclude "tmp"
   ```

2. **Scan subdirectories separately** - For very large directories
   ```bash
   for dir in /var/www/*; do
       python ppclient.py "$dir"
   done
   ```

3. **Use dry run for testing** - Verify setup without sending
   ```bash
   python ppclient.py /var/www --dry-run
   ```

4. **Run during off-peak hours** - Use cron for scheduled scans
   ```bash
   0 2 * * * /usr/bin/python3 /path/to/ppclient.py /var/www
   ```

5. **Monitor progress** - Use verbose mode for long scans
   ```bash
   python ppclient.py /large/directory --verbose
   ```

## Next Steps

- [Authentication Guide](AUTHENTICATION.md) - API key management
- [Configuration Reference](configuration.md) - All configuration options
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [API Reference](api-reference.md) - REST API documentation
