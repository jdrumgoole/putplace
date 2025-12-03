# PutPlace Client

A command-line tool for scanning directories and uploading file metadata to a PutPlace server.

## Installation

```bash
pip install putplace-client
```

## Quick Start

```bash
# Scan a directory and send metadata to server
ppclient /path/to/scan --api-key YOUR_API_KEY

# With custom server URL
ppclient /path/to/scan --url http://your-server:8000/put_file --api-key YOUR_API_KEY

# Dry run (don't send to server)
ppclient /path/to/scan --dry-run

# With exclude patterns
ppclient /path/to/scan --exclude .git --exclude "*.log" --exclude __pycache__
```

## Features

- Recursively scans directories
- Calculates SHA256 hashes for each file
- Auto-detects hostname and IP address
- Supports exclude patterns (wildcards, directory names)
- Progress bars and colored output
- Dry-run mode for testing
- Configuration file support

## Configuration

ppclient supports configuration via:

1. **Command-line arguments**
2. **Environment variables** (`PUTPLACE_EMAIL`, `PUTPLACE_PASSWORD`, `PUTPLACE_API_KEY`)
3. **Config files** (`~/ppclient.conf` or `./ppclient.conf`)

### Config file example

```ini
[DEFAULT]
url = http://your-server:8000/put_file
api-key = your-api-key
exclude = .git
exclude = *.log
exclude = __pycache__
```

## Command-line Options

```
ppclient [OPTIONS] PATH

Arguments:
  PATH                    Directory or file to scan

Options:
  --url URL               Server URL (default: http://localhost:8000/put_file)
  --api-key KEY           API key for authentication
  --email EMAIL           Email for JWT authentication
  --password PASSWORD     Password for JWT authentication
  --exclude PATTERN       Exclude pattern (can be repeated)
  --hostname NAME         Override auto-detected hostname
  --ip ADDRESS            Override auto-detected IP
  --dry-run               Scan without sending to server
  --verbose, -v           Verbose output
  --config FILE           Config file path
  --help                  Show help message
```

## Related

- [putplace-server](https://pypi.org/project/putplace-server/) - The PutPlace API server

## License

Apache-2.0
