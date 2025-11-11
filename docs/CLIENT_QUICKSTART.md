# PutPlace Client Quick Start

This guide shows you how to quickly start using the PutPlace client to scan and upload files.

## Prerequisites

1. **PutPlace server running** (see main README.md for setup)
2. **User account** (get credentials from server administrator)

## Getting Account Credentials

### Option 1: Ask Server Administrator

Request a username and password from your PutPlace server administrator.

### Option 2: Use Admin Account (if you have server access)

The admin account is automatically created on first server startup. Check the server logs or `/tmp/putplace_initial_creds.txt` for the auto-generated credentials.

### Option 3: Register New User (if registration is enabled)

```bash
# Register via API
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "email": "user@example.com", "password": "secure-password"}'
```

## Using the Client

The client supports **three ways** to provide your credentials:

### Method 1: Command Line (Quick Testing)

```bash
python ppclient.py /path/to/scan --username "admin" --password "your-password"
```

**Pros:** Quick and easy for testing
**Cons:** Credentials visible in shell history and process list

### Method 2: Environment Variable (Recommended for Scripts)

```bash
# Set environment variables
export PUTPLACE_USERNAME="admin"
export PUTPLACE_PASSWORD="your-password"

# Run client (no need to specify --username/--password)
python ppclient.py /path/to/scan
```

**Add to your `.bashrc` or `.zshrc` for persistence:**
```bash
echo 'export PUTPLACE_USERNAME="admin"' >> ~/.bashrc
echo 'export PUTPLACE_PASSWORD="your-password"' >> ~/.bashrc
source ~/.bashrc
```

**Pros:** Not in command history, works across all commands
**Cons:** Visible in environment, need to set in each shell

### Method 3: Config File (Recommended for Production)

```bash
# Create config file
cat > ~/ppclient.conf << 'EOF'
[DEFAULT]
username = admin
password = your-password
EOF

# Set secure permissions (IMPORTANT!)
chmod 600 ~/ppclient.conf

# Run client (automatically reads from ~/ppclient.conf)
python ppclient.py /path/to/scan
```

**Pros:** Most secure, persistent, supports all settings
**Cons:** Requires file setup

## Configuration Priority

If you specify credentials in multiple places, the priority is:

1. **Command line** (`--username`/`--password`) - Highest priority
2. **Environment variables** (`PUTPLACE_USERNAME`/`PUTPLACE_PASSWORD`)
3. **Config file** (`~/ppclient.conf` or `ppclient.conf`) - Lowest priority

## Complete Examples

### Example 1: Scan Local Directory

```bash
# Using environment variables
export PUTPLACE_USERNAME="admin"
export PUTPLACE_PASSWORD="your-password"
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
  --username "admin" \
  --password "production-password"
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
username = admin
password = your-password
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

1. **Protect your credentials**
   ```bash
   # Config file permissions
   chmod 600 ~/ppclient.conf

   # Never commit passwords
   # ppclient.conf is already in .gitignore
   ```

2. **Use separate accounts per client**
   - One account per server
   - One account per application
   - Easier to manage access

3. **Use strong passwords**
   - At least 8 characters
   - Mix of letters, numbers, symbols
   - Use password manager to generate

### ❌ DON'T:

1. **Don't commit passwords to version control**
   - ppclient.conf is in .gitignore
   - Never put passwords in code

2. **Don't share passwords**
   - Create separate accounts for each user/server

3. **Don't use command line in production**
   - Credentials visible in process list
   - Use config file or environment variable

## Troubleshooting

### "Both username and password are required"

```
✗ Both username and password are required for authentication
```

**Solution:** Provide both credentials via:
- `--username` and `--password` flags
- `PUTPLACE_USERNAME` and `PUTPLACE_PASSWORD` environment variables
- `username` and `password` in ~/ppclient.conf

### "Login failed: 401"

```
✗ Login failed: 401
  Incorrect username or password
```

**Possible causes:**
1. No credentials provided
2. Invalid username or password
3. User account disabled

**Solution:**
```bash
# Test your credentials
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# If you forgot password, contact server admin to reset
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
# 1. Get credentials from server admin
export PUTPLACE_USERNAME="dev-user"
export PUTPLACE_PASSWORD="dev-password"

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
username = prod-user
password = production-password
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
username = dev-user
password = dev-password
EOF

# Production
cat > ~/ppclient.conf.prod << 'EOF'
url = https://putplace.example.com/put_file
username = prod-user
password = prod-password
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

- 📖 Read [Authentication Guide](AUTHENTICATION.md) for JWT token management
- 📚 Check [Client Guide](client-guide.md) for comprehensive usage
- 🔒 Review [Security Guide](../SECURITY.md) for best practices
