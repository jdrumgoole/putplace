# PutPlace Client Quick Start

This guide shows you how to quickly start using the PutPlace client to scan and upload files.

## Prerequisites

1. **PutPlace server running** (see main README.md for setup)
2. **API key** (get from server administrator or create your own)

## Getting an API Key

### Option 1: Ask Server Administrator

Request an API key from your PutPlace server administrator.

### Option 2: Create Your Own (if you have server access)

```bash
# On the server
python -m putplace.scripts.create_api_key --name "my-client-$(hostname)"

# Save the API key that's displayed (it's shown only once!)
```

## Using the Client

The client supports **three ways** to provide your API key:

### Method 1: Command Line (Quick Testing)

```bash
python ppclient.py /path/to/scan --api-key "YOUR_API_KEY_HERE"
```

**Pros:** Quick and easy for testing
**Cons:** API key visible in shell history and process list

### Method 2: Environment Variable (Recommended for Scripts)

```bash
# Set environment variable
export PUTPLACE_API_KEY="YOUR_API_KEY_HERE"

# Run client (no need to specify --api-key)
python ppclient.py /path/to/scan
```

**Add to your `.bashrc` or `.zshrc` for persistence:**
```bash
echo 'export PUTPLACE_API_KEY="YOUR_API_KEY_HERE"' >> ~/.bashrc
source ~/.bashrc
```

**Pros:** Not in command history, works across all commands
**Cons:** Visible in environment, need to set in each shell

### Method 3: Config File (Recommended for Production)

```bash
# Create config file
cp ppclient.conf.example ~/ppclient.conf

# Edit and add your API key
nano ~/ppclient.conf
# Change: api-key = your-api-key-here

# Set secure permissions (IMPORTANT!)
chmod 600 ~/ppclient.conf

# Run client (automatically reads from ~/ppclient.conf)
python ppclient.py /path/to/scan
```

**Pros:** Most secure, persistent, supports all settings
**Cons:** Requires file setup

## Configuration Priority

If you specify the API key in multiple places, the priority is:

1. **Command line** (`--api-key`) - Highest priority
2. **Environment variable** (`PUTPLACE_API_KEY`)
3. **Config file** (`~/ppclient.conf` or `ppclient.conf`) - Lowest priority

## Complete Examples

### Example 1: Scan Local Directory

```bash
# Using environment variable
export PUTPLACE_API_KEY="a1b2c3d4e5f6..."
python ppclient.py /var/log
```

### Example 2: Scan with Exclusions

```bash
python ppclient.py /home/user \
  --exclude ".git" \
  --exclude "node_modules" \
  --exclude "*.log"
```

### Example 3: Scan Remote Server

```bash
python ppclient.py /var/www \
  --url "https://putplace.example.com/put_file" \
  --api-key "your-production-api-key"
```

### Example 4: Dry Run (Test Without Sending)

```bash
# See what would be sent without actually sending
python ppclient.py /path/to/scan --dry-run
```

### Example 5: Using Config File

**~/ppclient.conf:**
```ini
[DEFAULT]
url = https://putplace.example.com/put_file
api-key = your-api-key-here
exclude = .git
exclude = node_modules
exclude = *.log
```

**Run:**
```bash
# All settings loaded from config file
python ppclient.py /var/www
```

## Security Best Practices

### ✅ DO:

1. **Protect your API key**
   ```bash
   # Config file permissions
   chmod 600 ~/ppclient.conf

   # Never commit API keys
   # ppclient.conf is already in .gitignore
   ```

2. **Use separate keys per client**
   - One key per server
   - One key per application
   - Easier to revoke if compromised

3. **Rotate keys regularly**
   ```bash
   # Create new key on server
   python -m putplace.scripts.create_api_key --name "client-$(hostname)-$(date +%Y%m%d)"

   # Update client config
   nano ~/ppclient.conf

   # Revoke old key on server
   curl -X PUT "https://putplace.example.com/api_keys/OLD_KEY_ID/revoke" \
     -H "X-API-Key: NEW_API_KEY"
   ```

### ❌ DON'T:

1. **Don't commit API keys to version control**
   - ppclient.conf is in .gitignore
   - Never put keys in code

2. **Don't share API keys**
   - Create separate keys for each user/server

3. **Don't use command line in production**
   - API key visible in process list
   - Use config file or environment variable

## Troubleshooting

### "Warning: No API key provided"

```
Warning: No API key provided (authentication may fail)
```

**Solution:** Provide API key via:
- `--api-key` flag
- `PUTPLACE_API_KEY` environment variable
- `api-key` in ~/ppclient.conf

### "Failed to send: 401 Unauthorized"

```
Failed to send file.txt: Client error '401 Unauthorized'
```

**Possible causes:**
1. No API key provided
2. Invalid API key
3. Revoked API key

**Solution:**
```bash
# Check your API key works
curl -H "X-API-Key: YOUR_KEY" https://putplace.example.com/api_keys

# If it fails, create a new key
python -m putplace.scripts.create_api_key --name "new-client-key"
```

### "Config file not found"

The client looks for config files in this order:
1. `ppclient.conf` (current directory)
2. `~/ppclient.conf` (home directory)
3. Path specified with `--config`

Create one:
```bash
cp ppclient.conf.example ~/ppclient.conf
chmod 600 ~/ppclient.conf
nano ~/ppclient.conf
```

## Common Workflows

### Development Setup

```bash
# 1. Get API key from server admin
export PUTPLACE_API_KEY="dev-api-key-here"

# 2. Test connection
python ppclient.py /tmp --dry-run

# 3. Scan actual directory
python ppclient.py /home/user/projects
```

### Production Server Setup

```bash
# 1. Create config file
cat > ~/ppclient.conf << 'EOF'
[DEFAULT]
url = https://putplace.example.com/put_file
api-key = production-api-key-here
exclude = .git
exclude = *.log
exclude = tmp
EOF

# 2. Set secure permissions
chmod 600 ~/ppclient.conf

# 3. Test
python ppclient.py /var/www --dry-run

# 4. Run for real
python ppclient.py /var/www

# 5. Set up cron job
echo "0 2 * * * /usr/bin/python3 /path/to/ppclient.py /var/www" | crontab -
```

### Multi-Environment Setup

```bash
# Development
cat > ~/ppclient.conf.dev << 'EOF'
url = http://dev-putplace:8000/put_file
api-key = dev-key-here
EOF

# Production
cat > ~/ppclient.conf.prod << 'EOF'
url = https://putplace.example.com/put_file
api-key = prod-key-here
EOF

# Use with --config flag
python ppclient.py /var/www --config ~/ppclient.conf.prod
```

## Getting Help

```bash
# Show all options
python ppclient.py --help

# Check version and settings
python ppclient.py --version
```

## Next Steps

- 📖 Read [Authentication Guide](AUTHENTICATION.md) for API key management
- 🔒 Review [Security Guide](../SECURITY.md) for best practices
- 📚 Check [API Documentation](API.md) for advanced usage
