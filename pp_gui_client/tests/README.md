# PutPlace GUI Client - Playwright Tests

This directory contains end-to-end tests for the PutPlace Electron GUI client using Playwright.

## Test Files

### `electron-upload.spec.ts`
Basic upload tests against the dev server (app.putplace.org). Tests login, directory selection, and upload workflow with an existing user.

**Requirements:**
- `DEV_TEST_USER` - Email/username for login
- `DEV_TEST_PASSWORD` - Password for login

### `e2e-desktop-upload.spec.ts`
Tests uploading files from `~/Desktop` using the Electron GUI client.

**⚠️ Important Notes:**
- This test scans ALL files on your Desktop
- **Large files (GB+) can take several minutes to calculate SHA256 hashes**
- The test has a 5-minute timeout per test
- Test is **READ-ONLY** - does not delete, modify, or move any files

**Prerequisites:**
```bash
# Start server (if not already running)
invoke ppserver-start --port 8100

# Start daemon (if not already running)
pp_assist start

# Clean databases before test
pp_purge_data --environment test --force
```

**Running:**
```bash
# Test with 3 files (faster, recommended)
DESKTOP_UPLOAD_LIMIT=3 npm run test:desktop

# Test with 10 files
DESKTOP_UPLOAD_LIMIT=10 npm run test:desktop

# Use default limit (50 files - may timeout with large files)
npm run test:desktop
```

**Known Limitations:**
- Desktops with many large files (8GB+ videos) will timeout during SHA256 calculation
- SHA256 runs in background daemon - very large files can take 10+ minutes
- If timeout occurs, reduce `DESKTOP_UPLOAD_LIMIT` or test with a directory containing smaller files

### `e2e-bulk-upload.spec.ts`
Tests bulk upload functionality with synthetic files (3KB-150KB).

**Running:**
```bash
# Test with different file counts
npm run test:bulk:10      # 10 files
npm run test:bulk:100     # 100 files
npm run test:bulk:1000    # 1,000 files
npm run test:bulk:10000   # 10,000 files (slow!)
```

### `e2e-full-workflow.spec.ts`
Comprehensive end-to-end test that performs a complete workflow from scratch:
1. Purges pp_assist environment (local daemon database)
2. Purges server environment (remote server database)
3. Creates a new test user
4. Creates synthetic test files
5. Uploads files via the GUI
6. Verifies files exist on the server

**Requirements:**
- `ppserver.toml` config file in project root
- pp_assist daemon installed
- ppserver running locally

## Prerequisites

### Install Dependencies

```bash
cd pp_gui_client
npm install
```

### Build the App

```bash
npm run build
```

### Ensure Services are Running

For the full E2E test, you need:

1. **ppserver** running locally:
   ```bash
   # From project root
   uv run ppserver --config ppserver.toml
   ```

2. **MongoDB** running (if not using AWS DynamoDB):
   ```bash
   docker run -d -p 27017:27017 --name putplace-mongo mongo:latest
   ```

## Running Tests

### Run All Tests

```bash
npm test
```

### Run Full E2E Workflow Test

```bash
npm run test:e2e
```

### Run Tests in Headed Mode (Visible Browser)

```bash
# All tests
npm run test:headed

# E2E test only
npm run test:e2e:headed
```

### Run Tests in Debug Mode

```bash
npm run test:debug
```

### View Test Report

```bash
npm run test:report
```

## Test Output

The E2E full workflow test produces detailed console output showing:

```
=== SETUP PHASE ===

Step 1: Purging pp_assist environment...
[EXEC] ✓ Purge pp_assist database completed

Step 2: Purging server environment...
[EXEC] ✓ Purge server database completed

Step 3: Creating test user...
[EXEC] ✓ Create test user completed

Step 4: Creating synthetic test files...
Test file created: /path/to/test-uploads/test-file.txt
Test file SHA256: abc123...
Test file size: 123 bytes

Step 5: Starting pp_assist daemon...
[EXEC] ✓ Start pp_assist daemon completed

Step 6: Ensuring ppserver is running...
✓ Server is running

Step 7: Launching Electron app...
✓ Electron app launched

=== SETUP COMPLETE ===

=== UPLOAD WORKFLOW TEST ===

Step 1: Logging in with test user...
✓ Login successful

Step 2: Selecting test directory...
✓ Directory selected

Step 3: Configuring upload settings...
✓ Upload configured

Step 4: Starting upload...
✓ Upload started

Step 5: Waiting for upload to complete...
  Progress: 1 files uploaded
✓ Upload completed

Step 6: Verifying upload statistics...
✓ 1 files uploaded successfully

Step 7: Verifying file on server...
✓ Got access token
✓ File found on server:
  Filepath: /path/to/test-file.txt
  SHA256: abc123...
  Size: 123 bytes
  Hostname: hostname

=== TEST PASSED ===

=== CLEANUP PHASE ===

[EXEC] ✓ Stop pp_assist daemon completed
✓ Test directory cleaned up

=== CLEANUP COMPLETE ===
```

## Troubleshooting

### Test Fails with "pp_assist_purge not found"

Make sure pp_assist is installed:
```bash
cd packages/putplace-assist
uv pip install -e .
```

### Test Fails with "Server is not responding"

Start ppserver manually:
```bash
uv run ppserver --config ppserver.toml
```

### Test Fails with "Failed to create test user"

Check that ppserver.toml exists and has correct configuration:
```bash
cat ppserver.toml
```

### Test Times Out During Upload

The test has a 1-minute timeout per upload. If files are very large or network is slow, you may need to adjust the timeout in the test file:
```typescript
const maxWaitTime = 120000; // Increase to 2 minutes
```

### Clean Up After Failed Tests

If a test fails and leaves artifacts:

```bash
# Stop daemon
uv run pp_assist stop

# Clean up test directory
rm -rf pp_gui_client/test-uploads

# Purge databases
uv run pp_assist_purge --force
uv run pp_purge_data --config ppserver.toml --force
```

## Configuration

### Playwright Configuration

See `playwright.config.ts` in the project root:
- **Timeout:** 2 minutes per test
- **Workers:** 1 (sequential execution for Electron)
- **Retries:** 2 in CI, 0 locally
- **Screenshot:** On failure
- **Video:** Retained on failure

### Test Configuration

Edit test files to customize:
- `SERVER_URL` - Server endpoint (default: http://localhost:8000)
- `PPASSIST_URL` - pp_assist daemon URL (default: http://localhost:8765)
- `TEST_DIR` - Test files directory (default: pp_gui_client/test-uploads)

## CI/CD Integration

To run tests in CI:

```yaml
- name: Run E2E Tests
  run: |
    # Install dependencies
    cd pp_gui_client && npm install

    # Build app
    npm run build

    # Start services
    docker run -d -p 27017:27017 mongo:latest
    uv run ppserver --config ppserver.toml &

    # Run tests
    npm run test:e2e
```

## Writing New Tests

Use the existing tests as templates:

1. **Import required modules:**
   ```typescript
   import { test, expect, _electron as electron } from '@playwright/test';
   ```

2. **Launch Electron app:**
   ```typescript
   const electronApp = await electron.launch({
     args: [path.join(__dirname, '..', 'dist', 'main.js')],
   });
   const window = await electronApp.firstWindow();
   ```

3. **Interact with UI:**
   ```typescript
   await window.click('#button-id');
   await window.fill('#input-id', 'value');
   await expect(window.locator('#element-id')).toBeVisible();
   ```

4. **Clean up:**
   ```typescript
   await electronApp.close();
   ```

## Best Practices

1. **Use Serial Execution:** Electron tests should run sequentially
2. **Clean State:** Clear localStorage and reset state between tests
3. **Verify Server State:** Check server endpoints to verify uploads
4. **Handle Timeouts:** File uploads can be slow, set appropriate timeouts
5. **Descriptive Logging:** Console.log progress for easier debugging
6. **Error Context:** Provide detailed error messages
7. **Cleanup Resources:** Always stop daemons and remove test files

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Electron Guide](https://playwright.dev/docs/api/class-electron)
- [PutPlace API Documentation](http://localhost:8000/docs)
