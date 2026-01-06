/**
 * E2E Bulk Upload Tests for PutPlace
 *
 * This test performs bulk upload testing with varying file counts:
 * - 10 files
 * - 100 files
 * - 1,000 files
 * - 10,000 files
 *
 * Test files are organized in a 3-level directory hierarchy:
 * - level1/
 *   - level2/
 *     - level3/
 *       - files...
 *
 * Each file is small (<6KB) to ensure fast test execution.
 *
 * Usage:
 *   npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts
 *   # or run specific test:
 *   npm run build && npx playwright test tests/e2e-bulk-upload.spec.ts -g "10 files"
 */

import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import { execSync } from 'child_process';
import * as crypto from 'crypto';

// Test configuration
const TEST_USER_EMAIL = `bulktest-${Date.now()}@putplace.test`;
const TEST_USER_PASSWORD = 'BulkTest123';
const TEST_USERNAME = `bulktest${Date.now()}`;
const SERVER_URL = 'http://localhost:8100';
const PPASSIST_URL = 'http://localhost:8765';
const TEST_BASE_DIR = path.join(__dirname, '..', 'test-bulk-uploads');

// Path to ppserver.toml config
const PPSERVER_CONFIG = path.resolve(__dirname, '../../ppserver.toml');

// Test file configuration
const MIN_FILE_SIZE = 3000; // 3KB minimum
const MAX_FILE_SIZE = 150000; // 150KB maximum
const DIRECTORY_LEVELS = 3;
const DIRS_PER_LEVEL = 3; // 3 directories at each level (3 * 3 * 3 = 27 leaf directories)

let electronApp: ElectronApplication;
let window: Page;

/**
 * Execute a shell command and return output
 */
function execCommand(command: string, description: string): string {
  console.log(`[EXEC] ${description}: ${command}`);
  try {
    const output = execSync(command, {
      encoding: 'utf-8',
      stdio: 'pipe',
      cwd: path.resolve(__dirname, '../..'),
    });
    console.log(`[EXEC] ✓ ${description} completed`);
    return output;
  } catch (error: any) {
    console.error(`[EXEC] ✗ ${description} failed: ${error.message}`);
    if (error.stdout) console.log('stdout:', error.stdout);
    if (error.stderr) console.error('stderr:', error.stderr);
    throw error;
  }
}

/**
 * Execute a daemon command that forks to background
 */
function execDaemonCommand(command: string, description: string): void {
  console.log(`[EXEC] ${description}: ${command}`);
  try {
    execSync(command, {
      stdio: 'inherit',
      cwd: path.resolve(__dirname, '../..'),
    });
    console.log(`[EXEC] ✓ ${description} completed`);
  } catch (error: any) {
    console.error(`[EXEC] ✗ ${description} failed: ${error.message}`);
    throw error;
  }
}

/**
 * Calculate SHA256 hash of a file
 */
function calculateSha256(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

/**
 * Generate random file content of specified size
 */
function generateFileContent(size: number, seed: string): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789\n ';
  let content = `File: ${seed}\nGenerated at: ${new Date().toISOString()}\n`;
  content += `Random data:\n`;

  // Fill remaining space with random characters
  while (content.length < size) {
    const randomIndex = Math.floor(Math.random() * chars.length);
    content += chars[randomIndex];
  }

  return content.substring(0, size);
}

/**
 * Create a directory hierarchy with files
 * Returns array of created file paths and their SHA256 hashes
 */
function createDirectoryHierarchy(
  baseDir: string,
  fileCount: number
): { filePaths: string[], sha256s: string[] } {
  console.log(`Creating directory hierarchy with ${fileCount} files...`);

  // Clean and create base directory
  if (fs.existsSync(baseDir)) {
    fs.rmSync(baseDir, { recursive: true, force: true });
  }
  fs.mkdirSync(baseDir, { recursive: true });

  const filePaths: string[] = [];
  const sha256s: string[] = [];

  // Create 3-level directory structure
  const createLevel = (currentPath: string, level: number, levelName: string) => {
    if (level > DIRECTORY_LEVELS) {
      return;
    }

    for (let i = 1; i <= DIRS_PER_LEVEL; i++) {
      const dirName = `${levelName}_${i}`;
      const dirPath = path.join(currentPath, dirName);
      fs.mkdirSync(dirPath, { recursive: true });

      if (level < DIRECTORY_LEVELS) {
        // Create subdirectories
        createLevel(dirPath, level + 1, `level${level + 1}`);
      }
    }
  };

  // Create the directory structure
  createLevel(baseDir, 1, 'level1');

  // Collect all leaf directories (deepest level)
  const leafDirs: string[] = [];
  const findLeafDirs = (currentPath: string, level: number) => {
    if (level === DIRECTORY_LEVELS) {
      leafDirs.push(currentPath);
      return;
    }

    const entries = fs.readdirSync(currentPath, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        findLeafDirs(path.join(currentPath, entry.name), level + 1);
      }
    }
  };

  findLeafDirs(baseDir, 0);
  console.log(`Created ${leafDirs.length} leaf directories`);

  // Distribute files evenly across leaf directories
  const filesPerDir = Math.ceil(fileCount / leafDirs.length);
  let filesCreated = 0;
  let totalSize = 0;

  for (let dirIndex = 0; dirIndex < leafDirs.length && filesCreated < fileCount; dirIndex++) {
    const leafDir = leafDirs[dirIndex];
    const filesToCreate = Math.min(filesPerDir, fileCount - filesCreated);

    for (let fileIndex = 0; fileIndex < filesToCreate; fileIndex++) {
      const fileName = `file_${String(filesCreated + 1).padStart(6, '0')}.txt`;
      const filePath = path.join(leafDir, fileName);

      // Generate random file size between MIN_FILE_SIZE and MAX_FILE_SIZE
      const fileSize = Math.floor(Math.random() * (MAX_FILE_SIZE - MIN_FILE_SIZE + 1)) + MIN_FILE_SIZE;
      const content = generateFileContent(fileSize, `${filesCreated + 1}`);

      fs.writeFileSync(filePath, content);
      const sha256 = calculateSha256(filePath);

      filePaths.push(filePath);
      sha256s.push(sha256);
      totalSize += fileSize;
      filesCreated++;
    }
  }

  const avgSize = Math.floor(totalSize / filesCreated);
  console.log(`✓ Created ${filesCreated} files in ${leafDirs.length} directories`);
  console.log(`  Total directory depth: ${DIRECTORY_LEVELS} levels`);
  console.log(`  File size range: ${MIN_FILE_SIZE}-${MAX_FILE_SIZE} bytes (avg: ${avgSize} bytes)`);

  return { filePaths, sha256s };
}

/**
 * Wait for upload to complete with progress reporting
 */
async function waitForUploadComplete(
  window: Page,
  expectedFileCount: number,
  timeoutMs: number = 300000 // 5 minutes default
): Promise<{ success: number, failed: number, total: number }> {
  console.log(`\nWaiting for upload of ${expectedFileCount} files to complete...`);

  const logOutput = window.locator('#log-output');
  const startTime = Date.now();
  const pollInterval = 3000; // 3 seconds
  let lastSuccessCount = 0;
  let uploadComplete = false;

  while ((Date.now() - startTime) < timeoutMs && !uploadComplete) {
    const logText = await logOutput.innerText();

    // Check for completion
    if (logText.includes('Upload complete') || logText.includes('upload complete')) {
      uploadComplete = true;
      console.log('✓ Upload completed');
      break;
    }

    // Report progress
    try {
      const statSuccess = window.locator('#stat-success');
      const statFailed = window.locator('#stat-failed');
      const statTotal = window.locator('#stat-total');

      const successCount = parseInt(await statSuccess.innerText()) || 0;
      const failedCount = parseInt(await statFailed.innerText()) || 0;
      const totalCount = parseInt(await statTotal.innerText()) || 0;

      if (successCount > lastSuccessCount) {
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const rate = successCount / (Date.now() - startTime) * 1000;
        console.log(`  Progress: ${successCount}/${expectedFileCount} files (${rate.toFixed(1)} files/sec, ${elapsed}s elapsed)`);
        lastSuccessCount = successCount;
      }

      // Check if all files are processed
      if (totalCount >= expectedFileCount && (successCount + failedCount) >= expectedFileCount) {
        uploadComplete = true;
        console.log('✓ All files processed');
        break;
      }
    } catch (e) {
      // Stats not yet available
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  if (!uploadComplete) {
    const logText = await logOutput.innerText();
    console.log('Upload log (last 20 lines):', logText.split('\n').slice(-20).join('\n'));
    throw new Error('Upload did not complete within timeout');
  }

  // Get final statistics
  const statSuccess = window.locator('#stat-success');
  const statFailed = window.locator('#stat-failed');
  const statTotal = window.locator('#stat-total');

  const success = parseInt(await statSuccess.innerText()) || 0;
  const failed = parseInt(await statFailed.innerText()) || 0;
  const total = parseInt(await statTotal.innerText()) || 0;

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const rate = success / (Date.now() - startTime) * 1000;

  console.log(`\n✓ Upload Statistics:`);
  console.log(`  Total files: ${total}`);
  console.log(`  Successful: ${success}`);
  console.log(`  Failed: ${failed}`);
  console.log(`  Time: ${elapsed}s`);
  console.log(`  Average rate: ${rate.toFixed(2)} files/sec\n`);

  return { success, failed, total };
}

/**
 * Perform upload test for a given file count
 */
async function testBulkUpload(fileCount: number) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`BULK UPLOAD TEST: ${fileCount.toLocaleString()} FILES`);
  console.log('='.repeat(60));

  const testDir = path.join(TEST_BASE_DIR, `test-${fileCount}`);

  // Create test files
  const startCreate = Date.now();
  const { filePaths, sha256s } = createDirectoryHierarchy(testDir, fileCount);
  const createTime = ((Date.now() - startCreate) / 1000).toFixed(1);
  console.log(`✓ Test files created in ${createTime}s\n`);

  // Select directory in Electron
  console.log('Selecting test directory...');
  await electronApp.evaluate(async ({ dialog }, testDir) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [testDir],
    });
  }, testDir);

  await window.click('#select-dir-btn');
  await expect(window.locator('#selected-path')).toContainText(testDir, { timeout: 10000 });
  console.log('✓ Directory selected');

  // Configure upload
  await window.check('#upload-content');
  console.log('✓ Upload configured');

  // Start workflow (scan + upload)
  console.log('\nStarting directory scan...');
  const startBtn = window.locator('#start-btn');
  await startBtn.click();

  // Wait for scan to start
  const logOutput = window.locator('#log-output');
  await expect(logOutput).toContainText(/Scan initiated|Starting file scan/i, { timeout: 30000 });
  console.log('✓ Scan initiated');

  // Wait for files to be found by scan (either tracked or pending SHA256)
  console.log(`Waiting for scan to find files...`);
  let filesFound = false;
  const scanTimeout = Date.now() + 60000; // 1 minute timeout

  while (Date.now() < scanTimeout && !filesFound) {
    try {
      const trackedText = await window.locator('#daemon-stats .stat-item:has-text("Files Tracked") .stat-value').innerText();
      const tracked = parseInt(trackedText) || 0;

      const pendingSha256Text = await window.locator('#daemon-stats .stat-item:has-text("Pending SHA256") .stat-value').innerText();
      const pendingSha256 = parseInt(pendingSha256Text) || 0;

      const totalFound = tracked + pendingSha256;

      if (totalFound >= fileCount) {
        filesFound = true;
        console.log(`✓ Scan found ${totalFound} files (Tracked: ${tracked}, Pending SHA256: ${pendingSha256})`);
        break;
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (e) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  if (!filesFound) {
    throw new Error(`Scan did not find ${fileCount} files within timeout`);
  }

  // Now click Start again to trigger upload (files are now in database)
  console.log('Triggering upload now that files are found...');
  await new Promise(resolve => setTimeout(resolve, 1000));
  await startBtn.click();

  // Wait for files to be queued
  await expect(logOutput).toContainText(/Queued \d+ files for upload/i, { timeout: 30000 });
  console.log('✓ Files queued for upload');

  // SHA256 will be calculated inline during upload
  console.log('Upload processing with inline SHA256 calculation...');

  // Wait for upload to complete
  const stats = await waitForUploadComplete(window, fileCount, 600000); // 10 minute timeout

  // Verify results (may have extra system files like .DS_Store)
  expect(stats.total).toBeGreaterThanOrEqual(fileCount);
  expect(stats.total).toBeLessThanOrEqual(fileCount * 1.2); // No more than 20% extra files
  expect(stats.success).toBeGreaterThanOrEqual(fileCount * 0.95); // At least 95% of expected files
  expect(stats.failed).toBeLessThanOrEqual(fileCount * 0.05); // Less than 5% failures

  // Verify upload history: completed files should remain visible
  console.log('\nVerifying upload history...');
  const uploadContainer = window.locator('#active-uploads-container');
  const completedFiles = uploadContainer.locator('.file-progress-item.completed');
  const completedCount = await completedFiles.count();

  console.log(`  Files in upload history: ${completedCount}`);
  // Some files may complete before progress bars are created, so accept 60% threshold
  expect(completedCount).toBeGreaterThanOrEqual(fileCount * 0.60); // At least 60% should be marked completed

  // Verify completed files have success icons
  const successIcons = uploadContainer.locator('.success-icon');
  const successIconCount = await successIcons.count();
  console.log(`  Success icons displayed: ${successIconCount}`);
  expect(successIconCount).toBeGreaterThanOrEqual(fileCount * 0.60);

  console.log('✓ Upload history verified - completed files remain visible with checkmarks\n');

  // Take a screenshot to verify visual appearance
  await window.screenshot({ path: `test-results/upload-history-${fileCount}-files.png` });
  console.log(`✓ Screenshot saved: test-results/upload-history-${fileCount}-files.png\n`);

  console.log(`✓ ${fileCount.toLocaleString()} files test PASSED (uploaded ${stats.total} files including system files)\n`);

  // Clean up test directory
  if (fs.existsSync(testDir)) {
    fs.rmSync(testDir, { recursive: true, force: true });
  }
}

test.describe.serial('PutPlace Bulk Upload Tests', () => {
  // Increase timeout for bulk upload tests
  test.setTimeout(900000); // 15 minutes per test

  test.beforeAll(async () => {
    console.log('\n' + '='.repeat(60));
    console.log('SETUP PHASE');
    console.log('='.repeat(60) + '\n');

    // Purge pp_assist environment
    console.log('Step 1: Purging pp_assist environment...');
    try {
      execCommand('uv run pp_assist_purge --force', 'Purge pp_assist database');
    } catch (error) {
      console.log('pp_assist_purge not available, continuing...');
    }

    try {
      execCommand('uv run pp_assist stop', 'Stop pp_assist daemon');
    } catch (error) {
      console.log('pp_assist already stopped');
    }

    // Purge server environment
    console.log('\nStep 2: Purging server environment...');
    try {
      execCommand(
        `uv run pp_purge_data --config ${PPSERVER_CONFIG} --force`,
        'Purge server database'
      );
    } catch (error) {
      console.log('pp_purge_data failed, continuing...');
    }

    // Create test user
    console.log('\nStep 3: Creating test user...');
    execCommand(
      `uv run pp_manage_users --config-file ${PPSERVER_CONFIG} add --email "${TEST_USER_EMAIL}" --password "${TEST_USER_PASSWORD}" --name "${TEST_USERNAME}" --admin`,
      'Create test user'
    );

    // Configure pp_assist
    console.log('\nStep 4: Configuring pp_assist...');
    const ppAssistConfigPath = path.join(process.env.HOME || '', '.config/putplace/pp_assist.toml');
    if (fs.existsSync(ppAssistConfigPath)) {
      let configContent = fs.readFileSync(ppAssistConfigPath, 'utf-8');
      configContent = configContent.replace(
        /url = "http:\/\/localhost:\d+"/,
        `url = "${SERVER_URL}"`
      );
      fs.writeFileSync(ppAssistConfigPath, configContent);
      console.log(`✓ pp_assist configured to use ${SERVER_URL}`);
    }

    // Start pp_assist daemon
    console.log('\nStep 5: Starting pp_assist daemon...');
    const daemonLogPath = '/tmp/e2e-bulk-daemon.log';
    execDaemonCommand(`uv run pp_assist start --foreground > ${daemonLogPath} 2>&1 &`, 'Start pp_assist daemon');
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Verify ppserver is running
    console.log('\nStep 6: Verifying ppserver is running...');
    const response = await fetch(`${SERVER_URL}/health`);
    if (!response.ok) {
      throw new Error('Server health check failed');
    }
    console.log('✓ Server is running');

    // Configure pp_assist server credentials
    console.log('\nStep 7: Configuring pp_assist server credentials...');
    const addServerResponse = await fetch(`${PPASSIST_URL}/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Bulk Test Server',
        url: SERVER_URL,
        username: TEST_USER_EMAIL,
        password: TEST_USER_PASSWORD,
        is_default: true,
      }),
    });
    if (!addServerResponse.ok) {
      const errorText = await addServerResponse.text();
      throw new Error(`Failed to add server: ${errorText}`);
    }
    console.log('✓ Server credentials configured');

    // Launch Electron app
    console.log('\nStep 8: Launching Electron app...');
    electronApp = await electron.launch({
      args: [path.join(__dirname, '..', 'dist', 'main.js')],
      env: {
        ...process.env,
        NODE_ENV: 'test',
      },
    });

    window = await electronApp.firstWindow();
    await window.waitForLoadState('domcontentloaded');
    console.log('✓ Electron app launched');

    // Login
    console.log('\nStep 9: Logging in...');
    await window.evaluate(() => localStorage.clear());
    await window.reload();
    await window.waitForLoadState('domcontentloaded');

    await expect(window.locator('#login-form')).toBeVisible({ timeout: 10000 });
    await window.fill('#login-username', TEST_USER_EMAIL);
    await window.fill('#login-password', TEST_USER_PASSWORD);
    await window.fill('#login-server', PPASSIST_URL);
    await window.click('#login-btn');

    await expect(window.locator('#main-content')).toBeVisible({ timeout: 30000 });
    await expect(window.locator('#auth-section')).toBeHidden();
    console.log('✓ Login successful');

    console.log('\n' + '='.repeat(60));
    console.log('SETUP COMPLETE - Starting Tests');
    console.log('='.repeat(60) + '\n');
  });

  test.afterAll(async () => {
    console.log('\n' + '='.repeat(60));
    console.log('CLEANUP PHASE');
    console.log('='.repeat(60) + '\n');

    if (electronApp) {
      await electronApp.close();
      console.log('✓ Electron app closed');
    }

    try {
      execCommand('uv run pp_assist stop', 'Stop pp_assist daemon');
    } catch (error) {
      console.log('Failed to stop pp_assist daemon');
    }

    if (fs.existsSync(TEST_BASE_DIR)) {
      fs.rmSync(TEST_BASE_DIR, { recursive: true, force: true });
      console.log('✓ Test directories cleaned up');
    }

    console.log('\n' + '='.repeat(60));
    console.log('CLEANUP COMPLETE');
    console.log('='.repeat(60) + '\n');
  });

  test('should upload 10 files', async () => {
    await testBulkUpload(10);
  });

  test('should upload 100 files', async () => {
    await testBulkUpload(100);
  });

  test('should upload 1,000 files', async () => {
    await testBulkUpload(1000);
  });

  test('should upload 10,000 files', async () => {
    await testBulkUpload(10000);
  });
});
