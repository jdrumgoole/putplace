# PutPlace Server

A FastAPI-based file metadata storage service using MongoDB.

## Installation

```bash
pip install putplace-server
```

## Quick Start

```bash
# Start MongoDB (using Docker)
docker run -d --name mongodb -p 27017:27017 mongo:latest

# Configure the server (creates admin user, tests connections)
putplace_configure

# Start the server
ppserver start

# Check server status
ppserver status

# View logs
ppserver logs
```

## Features

- REST API for storing and retrieving file metadata
- MongoDB backend with async support
- JWT and API key authentication
- User registration with email confirmation
- Admin dashboard for user management
- S3 storage backend support (optional)
- Google OAuth integration (optional)

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /put_file` - Store file metadata
- `GET /get_file/{sha256}` - Retrieve file by SHA256 hash
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation

## Configuration

Configuration via environment variables or `.env` file:

```bash
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=putplace
API_TITLE=PutPlace API
API_VERSION=0.8.1

# Admin user (created on first startup)
PUTPLACE_ADMIN_EMAIL=admin@example.com
PUTPLACE_ADMIN_PASSWORD=your-secure-password
```

Or via `ppserver.toml`:

```toml
[server]
host = "0.0.0.0"
port = 8000

[mongodb]
url = "mongodb://localhost:27017"
database = "putplace"
```

## Server Management

```bash
# Start server (background)
ppserver start

# Start with custom options
ppserver start --host 0.0.0.0 --port 8080

# Stop server
ppserver stop

# Restart server
ppserver restart

# Check status
ppserver status

# View logs
ppserver logs
ppserver logs --follow
```

## User Management

```bash
# List all users
pp_manage_users list

# Add a new user
pp_manage_users add --email user@example.com

# Delete a user
pp_manage_users delete --email user@example.com

# Reset password
pp_manage_users reset-password --email user@example.com

# Set/unset admin privileges
pp_manage_users setadmin --email user@example.com
pp_manage_users unsetadmin --email user@example.com

# List pending registrations
pp_manage_users pending

# Approve pending user
pp_manage_users approve --email user@example.com
```

## Related

- [putplace-client](https://pypi.org/project/putplace-client/) - CLI tool for scanning directories and uploading file metadata

## License

Apache-2.0
