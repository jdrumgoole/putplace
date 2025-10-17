# PutPlace Documentation

**PutPlace** is a distributed file metadata storage and content deduplication system built with FastAPI and MongoDB.

## Overview

PutPlace allows you to:

- 📁 **Track file metadata** across multiple servers
- 🔄 **Deduplicate file content** using SHA256 hashing
- 👥 **Detect file clones** across all users with epoch file tracking
- 🌐 **Browse files interactively** via web interface
- 💾 **Store file content** in local filesystem or AWS S3
- 🔐 **Secure access** with API key and JWT authentication
- 🚀 **Scale horizontally** with MongoDB and object storage

## Quick Links

### Getting Started
- [Installation Guide](installation.md) - Install PutPlace server and client
- [Quick Start Guide](quickstart.md) - Get up and running in 5 minutes
- [Client Quick Start](CLIENT_QUICKSTART.md) - Using the command-line client

### Configuration
- [Configuration Reference](configuration.md) - All configuration options
- [Authentication Guide](AUTHENTICATION.md) - Setting up API keys
- [Storage Backends](storage.md) - Local and S3 storage configuration

### Usage
- [Client Guide](client-guide.md) - Complete client documentation
- [API Reference](api-reference.md) - REST API documentation
- [File Upload Workflow](FILE_UPLOAD_WORKFLOW.md) - Understanding the upload process

### Security & Deployment
- [Security Guide](SECURITY.md) - AWS credentials and security best practices
- [Deployment Guide](deployment.md) - Production deployment strategies
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

### Development
- [Development Guide](development.md) - Contributing to PutPlace
- [Architecture](architecture.md) - System architecture and design

## Features

### File Metadata Tracking
Track comprehensive file information across your infrastructure:
- File path, size, permissions, ownership
- Timestamps (mtime, atime, ctime)
- SHA256 content hash
- Hostname and IP address

### Content Deduplication
Save bandwidth and storage with automatic deduplication:
- SHA256-based duplicate detection
- Upload files only once
- Metadata stored separately for each location

### File Clone Detection (New in v0.4.0)
Discover and track duplicate files across your entire infrastructure:
- **Cross-user clone detection** - Find files with identical content across all users
- **Epoch file tracking** - Identify the original/canonical copy of each file
- **Interactive web browser** - Tree-based file explorer with clone visualization
- **Visual highlighting** - Green badges and styling for epoch files
- **Zero-length file handling** - Special indicators for empty files

### Interactive Web Interface (New in v0.4.0)
Manage your files through an intuitive web interface:
- **User authentication** - Secure JWT-based login system
- **File browser** - Tree layout organized by hostname and directory
- **File details modal** - View comprehensive metadata for any file
- **Clone modal** - See all instances of duplicate files
- **Real-time clone counts** - Button badges showing number of duplicates

### Flexible Storage
Choose the storage backend that fits your needs:
- **Local Filesystem** - Simple, fast, no external dependencies
- **AWS S3** - Scalable, durable, cloud-native storage
- **Pluggable Architecture** - Easy to add new backends

### Secure Authentication
API key-based authentication:
- SHA256-hashed key storage
- Per-application/server keys
- Key rotation and revocation
- Audit trail with usage timestamps

### REST API
Clean, well-documented REST API:
- OpenAPI/Swagger documentation
- JSON request/response format
- Comprehensive error handling
- Health check endpoints
- New endpoints: `/api/clones/{sha256}`, `/api/my_files`

### Client Features (Updated in v0.4.0)
Powerful command-line client with enhanced usability:
- **Graceful interrupt handling** - Ctrl-C finishes current file before exiting
- **Partial completion status** - See progress when interrupted
- **Configuration flexibility** - CLI, environment, or file-based config
- **Rich console output** - Progress bars and colorized status
- **Pattern-based exclusions** - Skip unwanted files efficiently

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Client    │         │   Client    │         │   Client    │
│  (Server A) │         │  (Server B) │         │  (Server C) │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                        │
       │    X-API-Key Auth     │                        │
       └───────────┬───────────┴────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  PutPlace API   │
         │   (FastAPI)     │
         └────────┬────────┘
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼
   ┌────────────┐   ┌────────────┐
   │  MongoDB   │   │  Storage   │
   │ (Metadata) │   │  Backend   │
   └────────────┘   └────────────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
            ┌──────────┐  ┌──────────┐
            │  Local   │  │   AWS    │
            │   FS     │  │    S3    │
            └──────────┘  └──────────┘
```

## Use Cases

### Configuration Management
Track configuration files across your infrastructure:
- Detect unauthorized changes
- Monitor configuration drift
- Centralized configuration inventory

### Backup Verification
Verify backup integrity without storing duplicate data:
- SHA256 verification
- Deduplication across backup sets
- Metadata-only comparison

### Compliance & Auditing
Maintain audit trails of file changes:
- Track file modifications
- User and permission changes
- Timestamp tracking

### Distributed File Inventory
Keep inventory of files across multiple servers:
- Centralized file database
- Cross-server deduplication
- Quick location lookup by SHA256

## System Requirements

### Server Requirements
- Python 3.10 - 3.14
- MongoDB 4.4 or higher
- 1GB+ RAM (depending on usage)
- Network connectivity

### Client Requirements
- Python 3.10 - 3.14
- Network access to PutPlace server

### Optional
- AWS account (for S3 storage)
- HTTPS/TLS certificate (for production)

## License

See [LICENSE](../LICENSE) file for details.

## Support

- **Documentation**: [https://putplace.readthedocs.io](https://putplace.readthedocs.io)
- **Issues**: [GitHub Issues](https://github.com/jdrumgoole/putplace/issues)
- **Source**: [GitHub Repository](https://github.com/jdrumgoole/putplace)

## Table of Contents

```{toctree}
:maxdepth: 2
:caption: Getting Started

installation
quickstart
CLIENT_QUICKSTART
```

```{toctree}
:maxdepth: 2
:caption: Configuration

configuration
AUTHENTICATION
storage
```

```{toctree}
:maxdepth: 2
:caption: User Guide

client-guide
api-reference
FILE_UPLOAD_WORKFLOW
```

```{toctree}
:maxdepth: 2
:caption: Operations

deployment
SECURITY
troubleshooting
```

```{toctree}
:maxdepth: 2
:caption: Development

development
architecture
```

## Indices and Tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
