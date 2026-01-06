# Bulk Upload Testing

This document describes the bulk upload end-to-end tests for the PutPlace Electron client.

## Overview

The bulk upload tests (`e2e-bulk-upload.spec.ts`) validate the client's ability to handle large-scale file uploads with varying file counts:

- **10 files** - Quick smoke test
- **100 files** - Small batch test
- **1,000 files** - Medium batch test
- **10,000 files** - Large batch stress test

## Test File Structure

### Directory Hierarchy

Files are organized in a **3-level deep directory structure**:

```
test-bulk-uploads/
└── test-{count}/
    ├── level1_1/
    │   ├── level2_1/
    │   │   ├── level3_1/
    │   │   │   ├── file_000001.txt
    │   │   │   ├── file_000002.txt
    │   │   │   └── ...
    │   │   ├── level3_2/
    │   │   └── level3_3/
    │   ├── level2_2/
    │   └── level2_3/
    ├── level1_2/
    └── level1_3/
```

**Hierarchy Details:**
- **Depth:** 3 levels
- **Breadth:** 3 directories per level
- **Total leaf directories:** 27 (3 × 3 × 3)
- **Files distributed evenly** across all leaf directories

### File Characteristics

- **Size:** ~5KB per file (5,000 bytes)
- **Content:** Random alphanumeric data with unique seed
- **Naming:** Sequential (`file_000001.txt`, `file_000002.txt`, etc.)
- **Total test data:**
  - 10 files: ~50 KB
  - 100 files: ~500 KB
  - 1,000 files: ~5 MB
  - 10,000 files: ~50 MB

## Running the Tests

### Prerequisites

1. **ppserver must be running** on `localhost:8100`:
   ```bash
   uv run ppserver --port 8100
   ```

2. **MongoDB must be running** (required by ppserver)

3. **Build the Electron app**:
   ```bash
   cd pp_gui_client
   npm run build
   ```

### Run All Bulk Tests

```bash
npm run test:bulk
```

This runs all four test cases sequentially (10, 100, 1,000, and 10,000 files).

### Run Individual Tests

```bash
# Quick 10-file test
npm run test:bulk:10

# 100-file test
npm run test:bulk:100

# 1,000-file test
npm run test:bulk:1000

# 10,000-file test
npm run test:bulk:10000
```

### Advanced Usage

```bash
# Run with visible browser (headed mode)
npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts --headed

# Run specific test with debugging
npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts -g "100 files" --debug

# Run with tracing enabled
npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts --trace on
```

## Test Flow

Each test follows this workflow:

### 1. Setup Phase (Once)
- Purge pp_assist database
- Purge server database
- Create test user account
- Configure pp_assist to use test server
- Start pp_assist daemon
- Verify ppserver is running
- Configure server credentials in pp_assist
- Launch Electron app
- Login to the application

### 2. Test Execution (Per File Count)
- **Create test files** with 3-level directory hierarchy
- **Select directory** in Electron app
- **Configure upload** settings (enable file content upload)
- **Start scan** to discover files
- **Wait for scan** to complete (SHA256 calculation)
- **Start upload** process
- **Monitor progress** with real-time statistics
- **Verify completion** (95%+ success rate required)
- **Clean up** test directory

### 3. Cleanup Phase (Once)
- Close Electron app
- Stop pp_assist daemon
- Remove all test directories

## Performance Metrics

The tests report detailed performance metrics:

- **File creation time** - How long to generate test files
- **Upload rate** - Files per second during upload
- **Total time** - End-to-end test duration
- **Success rate** - Percentage of successful uploads
- **Statistics:**
  - Total files processed
  - Successful uploads
  - Failed uploads

### Expected Performance

On a typical development machine:

| File Count | Creation Time | Upload Time | Total Time | Rate (files/sec) |
|------------|---------------|-------------|------------|------------------|
| 10         | <1s           | <5s         | ~10s       | 2-5              |
| 100        | <2s           | <30s        | ~45s       | 3-5              |
| 1,000      | ~5s           | ~3min       | ~4min      | 5-10             |
| 10,000     | ~30s          | ~15-30min   | ~30min     | 5-15             |

*Note: Performance varies based on hardware, network, and system load.*

## Test Assertions

Each test validates:

1. **File count** matches expected count
2. **Success rate** ≥ 95% of files uploaded successfully
3. **Failure rate** < 5% of files
4. **No crashes** - Electron app remains responsive
5. **Progress reporting** - Statistics update correctly

## Configuration

### Test Parameters

Edit `e2e-bulk-upload.spec.ts` to modify:

```typescript
// Server URLs
const SERVER_URL = 'http://localhost:8100';
const PPASSIST_URL = 'http://localhost:8765';

// File configuration
const FILE_CONTENT_SIZE = 5000; // ~5KB per file
const DIRECTORY_LEVELS = 3;      // Directory depth
const DIRS_PER_LEVEL = 3;        // Directories per level

// Timeout configuration
const timeoutMs = 600000; // 10 minutes per test
```

### ppserver Configuration

Point to your test config file:

```typescript
const PPSERVER_CONFIG = path.resolve(__dirname, '../../ppserver.toml');
```

## Troubleshooting

### Test Timeout

If tests timeout, increase the timeout in `waitForUploadComplete()`:

```typescript
await waitForUploadComplete(window, fileCount, 900000); // 15 minutes
```

### Server Connection Issues

Verify ppserver is running:
```bash
curl http://localhost:8100/health
```

Verify pp_assist is running:
```bash
curl http://localhost:8765/status
```

### Database Issues

Purge databases manually:
```bash
uv run pp_assist_purge --force
uv run pp_purge_data --config ppserver.toml --force
```

### Electron App Issues

Build the app manually:
```bash
cd pp_gui_client
npm run build
```

Check for TypeScript errors:
```bash
tsc --noEmit
```

## Debugging

### View Test Logs

Test output includes detailed logging:
- File creation progress
- Upload statistics
- Performance metrics
- Error messages

### Playwright Debugging

```bash
# Run with debug mode
npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts --debug

# Generate trace file for analysis
npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts --trace on

# View trace file
npx playwright show-trace trace.zip
```

### Check Daemon Logs

```bash
# pp_assist logs
tail -f /tmp/e2e-bulk-daemon.log

# ppserver logs (if using file logging)
tail -f /var/log/putplace/ppserver.log
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run bulk upload tests
  run: |
    # Start services
    uv run ppserver --port 8100 &

    # Wait for server
    sleep 5

    # Run tests
    cd pp_gui_client
    npm run test:bulk:100
  env:
    CI: true
```

### Docker Testing

Run tests in Docker container:
```bash
docker run --rm \
  -v $(pwd):/app \
  -w /app/pp_gui_client \
  mcr.microsoft.com/playwright:latest \
  npm run test:bulk:100
```

## Best Practices

1. **Run tests sequentially** - Avoid parallel execution to prevent resource contention
2. **Clean environment** - Start with fresh databases for consistent results
3. **Monitor resources** - Watch CPU, memory, and disk I/O during large tests
4. **Use timeouts** - Set appropriate timeouts for different file counts
5. **Log everything** - Enable verbose logging for debugging
6. **Test incremental** - Start with small file counts before running large tests

## Known Limitations

- **Memory usage** increases with file count (expected for 10,000 files)
- **Slow on slow disks** - SSD recommended for best performance
- **Network dependent** - Performance varies with network conditions
- **Platform specific** - File creation speed varies by OS

## Future Enhancements

- [ ] Add file size variations (mix of small and large files)
- [ ] Test with deeper directory hierarchies (4-5 levels)
- [ ] Add resume/pause testing
- [ ] Test with file exclusion patterns
- [ ] Add concurrent upload testing (multiple directories)
- [ ] Performance regression testing
- [ ] Memory leak detection
