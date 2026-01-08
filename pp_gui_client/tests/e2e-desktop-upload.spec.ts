/**
 * E2E test for uploading files from ~/Desktop using Electron GUI.
 *
 * This test uses the Electron GUI client to scan and upload files from the
 * user's Desktop directory, verifying the full upload workflow.
 *
 * ⚠️  SAFETY NOTICE:
 * This test is READ-ONLY. It does NOT:
 * - Delete any files
 * - Modify any files
 * - Move any files
 * - Change any file permissions
 *
 * It only:
 * - Reads file metadata (path, size, mtime)
 * - Calculates SHA256 hashes (reads file content)
 * - Uploads metadata to the test server
 *
 * All original files remain completely untouched.
 *
 * ⚠️  PERFORMANCE WARNING:
 * - Large files (GB+) take significant time to calculate SHA256 hashes
 * - Example: 8GB video file = ~5-10 minutes for SHA256
 * - Test has 5-minute timeout which may not be enough for very large files
 * - Use DESKTOP_UPLOAD_LIMIT=3 env var to limit file count and speed up test
 * - If your Desktop has many large files, consider using e2e-bulk-upload.spec.ts instead
 *
 * Prerequisites:
 * 1. pp_assist daemon running: pp_assist start
 * 2. pp_server running: invoke ppserver-start --port 8100
 * 3. Clean databases: pp_purge_data --environment test --force
 */

import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import * as path from 'path';
import * as os from 'os';
import * as fs from 'fs';

// Configuration
const UPLOAD_LIMIT = parseInt(process.env.DESKTOP_UPLOAD_LIMIT || '50', 10);
const DESKTOP_PATH = path.join(os.homedir(), 'Desktop');
const DAEMON_URL = 'http://localhost:8765';
const SERVER_URL = 'http://localhost:8100';
const TEST_USER_EMAIL = 'desktop-test@putplace.test';
const TEST_USER_PASSWORD = 'TestPass123';

let electronApp: ElectronApplication;
let window: Page;

test.describe('Desktop Upload via Electron GUI', () => {
  test.beforeAll(async () => {
    // Check if Desktop exists
    if (!fs.existsSync(DESKTOP_PATH)) {
      test.skip(true, `Desktop directory not found at ${DESKTOP_PATH}`);
    }

    const { exec } = require('child_process');
    const util = require('util');
    const execPromise = util.promisify(exec);

    // Create test user
    try {
      console.log('\n👤 Creating test user...');
      await execPromise(
        `uv run pp_manage_users add --email "${TEST_USER_EMAIL}" --password "${TEST_USER_PASSWORD}" --admin`
      );
      console.log('✓ Test user created');
    } catch (err) {
      // User might already exist, that's okay
      console.log('ℹ️  Test user may already exist');
    }

    // Add server to daemon
    try {
      console.log('⚙️  Configuring server in daemon...');
      const response = await fetch(`${DAEMON_URL}/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'test-server',
          url: SERVER_URL,
          username: TEST_USER_EMAIL,
          password: TEST_USER_PASSWORD
        })
      });

      if (response.ok || response.status === 409) {
        console.log('✓ Server configured');
      }
    } catch (err) {
      console.log(`⚠️  Server config warning: ${err}`);
    }

    // Launch Electron app
    electronApp = await electron.launch({
      args: [path.join(__dirname, '../dist/main.js')],
      env: {
        ...process.env,
        NODE_ENV: 'test'
      }
    });

    // Get the first window
    window = await electronApp.firstWindow();

    // Wait for app to load
    await window.waitForLoadState('domcontentloaded');
  });

  test.afterAll(async () => {
    if (electronApp) {
      await electronApp.close();
    }
  });

  test('should count files on Desktop', async () => {
    // Quick sanity check - count files on Desktop
    console.log(`\nScanning ${DESKTOP_PATH}...`);

    let fileCount = 0;
    let totalSize = 0;

    function scanDirectory(dirPath: string) {
      const items = fs.readdirSync(dirPath);

      for (const item of items) {
        const fullPath = path.join(dirPath, item);
        try {
          const stat = fs.statSync(fullPath);

          if (stat.isFile()) {
            fileCount++;
            totalSize += stat.size;
          } else if (stat.isDirectory()) {
            scanDirectory(fullPath);
          }
        } catch (err) {
          // Skip files we can't access
          continue;
        }
      }
    }

    scanDirectory(DESKTOP_PATH);

    console.log(`Found ${fileCount} files`);
    console.log(`Total size: ${totalSize.toLocaleString()} bytes (${(totalSize / 1024 / 1024).toFixed(2)} MB)`);

    expect(fileCount).toBeGreaterThan(0);
  });

  test('should upload Desktop files through GUI', async () => {
    // Test timeout managed by Playwright config, not embedded here
    console.log(`\n📦 Testing Desktop upload via Electron GUI`);
    console.log(`Desktop path: ${DESKTOP_PATH}`);
    console.log(`Upload limit: ${UPLOAD_LIMIT} files`);

    // Wait for daemon status to be checked
    await window.waitForSelector('#daemon-status', { timeout: 10000 });

    // Check daemon connection
    const daemonStatus = await window.textContent('#daemon-status');
    console.log(`Daemon status: ${daemonStatus}`);

    if (daemonStatus?.includes('Disconnected') || daemonStatus?.includes('Checking')) {
      test.skip(true, 'pp_assist daemon is not running. Start with: pp_assist start');
    }

    // Check if already logged in
    const mainContent = await window.locator('#main-content').isVisible().catch(() => false);

    if (!mainContent) {
      // Need to log in
      console.log('\n🔐 Logging in...');
      await window.fill('#login-username', TEST_USER_EMAIL);
      await window.fill('#login-password', TEST_USER_PASSWORD);
      await window.fill('#login-server', DAEMON_URL);

      // Click login
      await window.click('#login-btn');

      // Wait for main content to appear
      await window.waitForSelector('#main-content', { state: 'visible', timeout: 10000 });
      console.log('✓ Logged in successfully');
    } else {
      console.log('✓ Already logged in');
    }

    // Register directory directly with daemon API
    console.log('\n📂 Registering Desktop directory with daemon...');

    let pathId: number;

    // Try to register the path
    const registerResponse = await fetch(`${DAEMON_URL}/paths`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: DESKTOP_PATH,
        recursive: true
      })
    });

    if (registerResponse.ok) {
      // Path registered successfully
      const pathData = await registerResponse.json();
      pathId = pathData.id;
      console.log(`✓ Registered path (ID: ${pathId}): ${DESKTOP_PATH}`);
    } else if (registerResponse.status === 409) {
      // Path already registered - find its ID
      console.log('⚠️  Path already registered, finding ID...');
      const pathsResponse = await fetch(`${DAEMON_URL}/paths`);
      const pathsData = await pathsResponse.json();
      const paths = pathsData.paths || [];

      const existing = paths.find((p: any) => p.path === DESKTOP_PATH);
      if (existing) {
        pathId = existing.id;
        console.log(`✓ Using existing path (ID: ${pathId})`);
      } else {
        throw new Error('Path already registered but could not find ID');
      }
    } else {
      throw new Error(`Failed to register path: ${await registerResponse.text()}`);
    }

    // Trigger scan via daemon API
    console.log('\n🔍 Triggering scan...');
    const scanResponse = await fetch(`${DAEMON_URL}/paths/${pathId}/scan`, {
      method: 'POST'
    });

    if (!scanResponse.ok) {
      throw new Error(`Failed to trigger scan: ${await scanResponse.text()}`);
    }

    console.log('✓ Scan initiated, waiting for SHA256 calculation...');
    console.log('  (Note: Large video files may take several minutes to hash)');

    // Wait for SHA256 calculation to complete (or at least some files ready)
    let filesReady = 0;
    let totalFiles = 0;
    for (let i = 0; i < 120; i++) { // Wait up to 2 minutes
      await new Promise(resolve => setTimeout(resolve, 1000));

      const statsResponse = await fetch(`${DAEMON_URL}/files/stats`);
      if (statsResponse.ok) {
        const stats = await statsResponse.json();
        const pendingSHA = stats.pending_sha256 || 0;
        filesReady = stats.ready_for_upload || 0;
        totalFiles = stats.total_files || 0;

        if (i % 10 === 0 || pendingSHA === 0 || filesReady > 0) { // Log every 10 seconds or when significant change
          console.log(`  [${i}s] Files: ${totalFiles}, Pending SHA256: ${pendingSHA}, Ready: ${filesReady}`);
        }

        // If we have at least UPLOAD_LIMIT files ready, that's enough
        if (filesReady >= UPLOAD_LIMIT) {
          console.log(`✓ ${filesReady} files ready for upload (need ${UPLOAD_LIMIT})`);
          break;
        }

        // Or if all SHA256s are done
        if (pendingSHA === 0 && filesReady > 0) {
          console.log('✓ All SHA256 calculations complete');
          break;
        }
      }
    }

    if (filesReady === 0) {
      console.log(`⚠️  No files ready for upload after waiting 2 minutes`);
      console.log(`   Files scanned: ${totalFiles}`);
      console.log(`   This usually means files are very large and SHA256 calculation is still in progress`);
      console.log(`   Suggestion: Use DESKTOP_UPLOAD_LIMIT=1 for faster testing, or use e2e-bulk-upload.spec.ts`);
      test.skip(true, 'SHA256 calculation timeout - Desktop likely has very large files (8GB+ videos). Reduce DESKTOP_UPLOAD_LIMIT or use smaller test directory.');
    }

    // Trigger upload via daemon API
    const uploadContent = process.env.UPLOAD_CONTENT === 'true';
    console.log(`\n⬆️  Triggering upload (limit: ${UPLOAD_LIMIT}, content: ${uploadContent})...`);

    const uploadResponse = await fetch(`${DAEMON_URL}/uploads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_content: uploadContent,
        path_prefix: DESKTOP_PATH,
        limit: UPLOAD_LIMIT
      })
      // No timeout - will wait indefinitely for all files to be queued
    });

    if (!uploadResponse.ok) {
      throw new Error(`Failed to trigger upload: ${await uploadResponse.text()}`);
    }

    const uploadData = await uploadResponse.json();
    console.log(`✓ Upload queued: ${uploadData.files_queued} files`);

    // Wait for upload to start
    await window.waitForTimeout(2000);

    // Monitor upload progress (no overall timeout - per-file timeout is configured in daemon)
    console.log('Monitoring progress...');
    let lastProgress = '';
    let stableCount = 0;

    while (true) {
      // Get progress text
      const progressText = await window.textContent('#progress-text');

      // Get upload stats
      const totalStat = await window.textContent('#stat-total');
      const successStat = await window.textContent('#stat-success');
      const failedStat = await window.textContent('#stat-failed');

      const currentProgress = `${progressText} | Total: ${totalStat}, Success: ${successStat}, Failed: ${failedStat}`;

      if (currentProgress !== lastProgress) {
        console.log(`  ${currentProgress}`);
        lastProgress = currentProgress;
        stableCount = 0;
      } else {
        stableCount++;
      }

      // Check if upload is complete (progress is stable)
      if (stableCount >= 3 && progressText?.includes('Ready')) {
        console.log('✓ Upload appears complete');
        break;
      }

      await window.waitForTimeout(2000);
    }

    // Get final stats
    const finalTotal = await window.textContent('#stat-total');
    const finalSuccess = await window.textContent('#stat-success');
    const finalFailed = await window.textContent('#stat-failed');

    const totalUploaded = parseInt(finalTotal || '0', 10);
    const successUploaded = parseInt(finalSuccess || '0', 10);
    const failedUploaded = parseInt(finalFailed || '0', 10);

    console.log(`\n✅ Upload complete:`);
    console.log(`  Total: ${totalUploaded}`);
    console.log(`  Success: ${successUploaded}`);
    console.log(`  Failed: ${failedUploaded}`);
    console.log(`  Success rate: ${totalUploaded > 0 ? (successUploaded / totalUploaded * 100).toFixed(1) : 0}%`);

    // Verify upload history is visible
    const uploadHistory = await window.locator('.file-progress-item');
    const historyCount = await uploadHistory.count();
    console.log(`\nUpload history entries: ${historyCount}`);

    // Take a screenshot
    await window.screenshot({ path: 'test-results/desktop-upload-complete.png' });
    console.log('📸 Screenshot saved: test-results/desktop-upload-complete.png');

    // Assertions
    expect(totalUploaded).toBeGreaterThan(0);
    expect(successUploaded).toBeGreaterThan(0);
    expect(successUploaded).toBeGreaterThanOrEqual(totalUploaded * 0.8); // At least 80% success rate
  });

  test('should display upload history with timestamps', async () => {
    // Check that completed uploads show timestamps
    const completedItems = await window.locator('.file-progress-item.completed');
    const count = await completedItems.count();

    if (count > 0) {
      console.log(`\n✓ Found ${count} completed uploads in history`);

      // Check first completed item has a timestamp
      const firstItem = completedItems.first();
      const timestamp = await firstItem.locator('.file-timestamp').textContent();

      console.log(`  Example timestamp: ${timestamp}`);

      expect(timestamp).not.toBe('--');
      expect(timestamp).toMatch(/\d{1,2}:\d{2}\s+(AM|PM)/);
    } else {
      console.log('\nNo completed uploads found in history');
    }
  });
});
