# PutPlace Configuration Guide

PutPlace supports multiple configuration methods with a clear priority order.

## Configuration Priority

Settings are loaded in this order (highest priority first):

1. **Environment Variables** - Override everything
2. **ppserver.toml** - Main server configuration file
3. **Default Values** - Built-in defaults

## Using ppserver.toml (Recommended)

### Quick Start

1. Copy the example configuration:
   ```bash
   cp ppserver.toml.example ppserver.toml
   ```

2. Edit `ppserver.toml` with your settings:
   ```toml
   [database]
   mongodb_url = "mongodb://localhost:27017"
   mongodb_database = "putplace"

   [storage]
   backend = "local"
   path = "./storage/files"
   ```

3. Restart the server - settings are automatically loaded!

### Configuration File Locations

PutPlace searches for `ppserver.toml` in these locations (in order):

1. `./ppserver.toml` - Current directory (project root)
2. `~/.config/putplace/ppserver.toml` - User configuration
3. `/etc/putplace/ppserver.toml` - System-wide configuration

The first file found is used.

## Configuration Sections

### [database]

MongoDB connection settings:

```toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"
mongodb_collection = "file_metadata"
```

### [api]

API server settings:

```toml
[api]
title = "PutPlace API"
description = "File metadata storage API"
```

### [storage]

Storage backend configuration:

#### Local Storage

```toml
[storage]
backend = "local"
path = "./storage/files"
```

#### S3 Storage

```toml
[storage]
backend = "s3"
s3_bucket_name = "my-putplace-bucket"
s3_region_name = "us-east-1"
s3_prefix = "files/"
```

### [aws]

AWS credentials (optional - uses AWS credential chain if not specified):

```toml
[aws]
# Option 1: Use AWS profile (recommended)
profile = "my-aws-profile"

# Option 2: Direct credentials (NOT recommended for production)
# access_key_id = "AKIAIOSFODNN7EXAMPLE"
# secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

**Security Note**: It's recommended to use AWS credential chain (IAM roles, AWS CLI config) instead of hardcoding credentials.

## Environment Variable Override

Any setting can be overridden with environment variables. Use uppercase with underscores:

```bash
# Override storage backend
export STORAGE_BACKEND=s3
export S3_BUCKET_NAME=my-bucket

# Override database
export MONGODB_URL=mongodb://prod-server:27017

# Start server with overrides
python -m putplace.ppserver start
```

## Example Configurations

### Development Setup (Local Storage)

```toml
# ppserver.toml
[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace_dev"

[storage]
backend = "local"
path = "./storage/files"
```

### Production Setup (S3 Storage)

```toml
# ppserver.toml
[database]
mongodb_url = "mongodb://prod-db-server:27017"
mongodb_database = "putplace"

[storage]
backend = "s3"
s3_bucket_name = "company-putplace-prod"
s3_region_name = "us-east-1"
s3_prefix = "files/"

[aws]
# Use IAM role in production - no credentials needed!
# Or use AWS profile:
profile = "production"
```

### Multi-Environment Setup

Use different config files per environment:

```bash
# Development
cp ppserver.toml.example ppserver.dev.toml
# Edit ppserver.dev.toml...

# Production
cp ppserver.toml.example ppserver.prod.toml
# Edit ppserver.prod.toml...

# Use symbolic link to switch environments
ln -sf ppserver.dev.toml ppserver.toml   # Dev
ln -sf ppserver.prod.toml ppserver.toml  # Prod
```

Or use environment-specific directories:

```bash
# Dev uses ./ppserver.toml
cd /path/to/dev && ppserver start

# Prod uses /etc/putplace/ppserver.toml
sudo cp ppserver.prod.toml /etc/putplace/ppserver.toml
ppserver start  # Uses system config
```

## Migrating from .env

**Note**: As of version 0.2.0, `.env` files are no longer supported. Use `ppserver.toml` instead.

If you're currently using a `.env` file:

1. Create `ppserver.toml` from the example:
   ```bash
   cp ppserver.toml.example ppserver.toml
   ```

2. Transfer your settings from `.env` to `ppserver.toml`:

   **Before (.env):**
   ```bash
   STORAGE_BACKEND=local
   STORAGE_PATH=./storage/files
   MONGODB_URL=mongodb://localhost:27017
   ```

   **After (ppserver.toml):**
   ```toml
   [database]
   mongodb_url = "mongodb://localhost:27017"

   [storage]
   backend = "local"
   path = "./storage/files"
   ```

3. Test the configuration:
   ```bash
   uv run python -c "from putplace.config import settings; print(settings.storage_backend)"
   ```

4. Remove `.env` file

## Troubleshooting

### Configuration not loading

Check which config file is being used:

```python
from putplace.config import find_config_file
config_file = find_config_file()
print(f"Using config: {config_file}")
```

### Check current settings

View all loaded settings:

```python
from putplace.config import settings
print(f"Storage backend: {settings.storage_backend}")
print(f"Storage path: {settings.storage_path}")
print(f"MongoDB URL: {settings.mongodb_url}")
```

### TOML syntax errors

Validate your TOML file:

```bash
uv run python -c "import tomli; tomli.load(open('ppserver.toml', 'rb'))"
```

## Security Best Practices

1. **Never commit ppserver.toml to git** - It's in `.gitignore` by default
2. **Use ppserver.toml.example as a template** - This IS committed for reference
3. **Use environment variables in CI/CD** - Override sensitive values
4. **Use AWS IAM roles in production** - Avoid hardcoding credentials
5. **Restrict file permissions**:
   ```bash
   chmod 600 ppserver.toml  # Only owner can read/write
   ```

## Complete Example

```toml
# ppserver.toml - Complete configuration example

[database]
mongodb_url = "mongodb://localhost:27017"
mongodb_database = "putplace"
mongodb_collection = "file_metadata"

[api]
title = "PutPlace API"
description = "File metadata storage API"

[storage]
backend = "s3"
s3_bucket_name = "my-company-putplace"
s3_region_name = "us-west-2"
s3_prefix = "uploads/"

[aws]
profile = "putplace-production"
```

## Reference: All Available Settings

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| database | mongodb_url | mongodb://localhost:27017 | MongoDB connection string |
| database | mongodb_database | putplace | Database name |
| database | mongodb_collection | file_metadata | Collection name |
| api | title | PutPlace API | API title |
| api | description | File metadata storage API | API description |
| storage | backend | local | Storage backend: "local" or "s3" |
| storage | path | /var/putplace/files | Local storage directory path |
| storage | s3_bucket_name | null | S3 bucket name |
| storage | s3_region_name | us-east-1 | S3 region |
| storage | s3_prefix | files/ | S3 key prefix |
| aws | profile | null | AWS profile name |
| aws | access_key_id | null | AWS access key |
| aws | secret_access_key | null | AWS secret key |
