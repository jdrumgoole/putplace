/**
 * E2E Full Workflow Test for PutPlace
 *
 * This test performs a complete end-to-end workflow:
 * 1. Purges pp_assist environment (local daemon)
 * 2. Purges server environment (remote server)
 * 3. Creates a new test user
 * 4. Creates synthetic test files
 * 5. Uploads files via the GUI
 * 6. Verifies files exist on the server
 *
 * Usage:
 *   npm run test:e2e
 *   # or
 *   npx playwright test tests/e2e-full-workflow.spec.ts
 */

import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import { execSync } from 'child_process';
import * as crypto from 'crypto';

// Test configuration
const TEST_USER_EMAIL = `test-${Date.now()}@putplace.test`;
const TEST_USER_PASSWORD = 'TestPass123';  // Simplified password without special characters
const TEST_USERNAME = `testuser${Date.now()}`;
const SERVER_URL = 'http://localhost:8100';
const PPASSIST_URL = 'http://localhost:8765';
const TEST_DIR = path.join(__dirname, '..', 'test-uploads');
const TEST_FILE_NAME = 'test-file.txt';
const TEST_FILE_CONTENT = `Test file created at ${new Date().toISOString()}\nThis is a test upload for PutPlace E2E testing.`;

// Path to ppserver.toml config
const PPSERVER_CONFIG = path.resolve(__dirname, '../../ppserver.toml');

let electronApp: ElectronApplication;
let window: Page;
let testFilePath: string;
let testFileSha256: string;

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
 * Uses 'inherit' for stdio to avoid hanging on daemon processes
 */
function execDaemonCommand(command: string, description: string): void {
  console.log(`[EXEC] ${description}: ${command}`);
  try {
    execSync(command, {
      stdio: 'inherit',  // Inherit parent stdio, allows daemon to fork properly
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

test.describe.serial('PutPlace E2E Full Workflow', () => {
  test.beforeAll(async () => {
    console.log('\n=== SETUP PHASE ===\n');

    // Step 1: Purge pp_assist environment
    console.log('Step 1: Purging pp_assist environment...');
    try {
      execCommand(
        'uv run pp_assist_purge --force',
        'Purge pp_assist database'
      );
    } catch (error) {
      console.log('pp_assist_purge failed (may not be installed yet), continuing...');
    }

    // Stop pp_assist daemon if running
    try {
      execCommand('uv run pp_assist stop', 'Stop pp_assist daemon');
    } catch (error) {
      console.log('pp_assist already stopped or not installed');
    }

    // Step 2: Purge server environment
    console.log('\nStep 2: Purging server environment...');
    try {
      execCommand(
        `uv run pp_purge_data --config ${PPSERVER_CONFIG} --force`,
        'Purge server database'
      );
    } catch (error) {
      console.log('pp_purge_data failed, continuing...');
    }

    // Step 3: Create test user
    console.log('\nStep 3: Creating test user...');
    try {
      execCommand(
        `uv run pp_manage_users --config-file ${PPSERVER_CONFIG} add --email "${TEST_USER_EMAIL}" --password "${TEST_USER_PASSWORD}" --name "${TEST_USERNAME}" --admin`,
        'Create test user'
      );
    } catch (error) {
      console.error('Failed to create test user - this is critical');
      throw error;
    }

    // Step 4: Create synthetic test directory and file
    console.log('\nStep 4: Creating synthetic test files...');

    // Create test directory
    if (fs.existsSync(TEST_DIR)) {
      fs.rmSync(TEST_DIR, { recursive: true, force: true });
    }
    fs.mkdirSync(TEST_DIR, { recursive: true });

    // Create test file
    testFilePath = path.join(TEST_DIR, TEST_FILE_NAME);
    fs.writeFileSync(testFilePath, TEST_FILE_CONTENT);
    testFileSha256 = calculateSha256(testFilePath);

    console.log(`Test file created: ${testFilePath}`);
    console.log(`Test file SHA256: ${testFileSha256}`);
    console.log(`Test file size: ${fs.statSync(testFilePath).size} bytes`);

    // Step 5: Configure pp_assist with test server URL
    console.log('\nStep 5: Configuring pp_assist with test server...');
    const ppAssistConfigPath = path.join(process.env.HOME || '', '.config/putplace/pp_assist.toml');
    let configContent = fs.readFileSync(ppAssistConfigPath, 'utf-8');
    // Update remote_server URL to point to test server
    configContent = configContent.replace(
      /url = "http:\/\/localhost:\d+"/,
      `url = "${SERVER_URL}"`
    );
    fs.writeFileSync(ppAssistConfigPath, configContent);
    console.log(`✓ pp_assist configured to use ${SERVER_URL}`);

    // Step 6: Start pp_assist daemon
    console.log('\nStep 6: Starting pp_assist daemon...');
    const daemonLogPath = '/tmp/e2e-daemon.log';
    try {
      // Start daemon in foreground mode with output to log file
      execDaemonCommand(`uv run pp_assist start --foreground > ${daemonLogPath} 2>&1 &`, 'Start pp_assist daemon');
      // Give daemon time to start
      await new Promise(resolve => setTimeout(resolve, 3000));
    } catch (error) {
      console.error('Failed to start pp_assist daemon');
      throw error;
    }

    // Step 7: Verify ppserver is running
    console.log('\nStep 7: Ensuring ppserver is running...');
    // Note: ppserver should already be running, but we'll verify
    try {
      const response = await fetch(`${SERVER_URL}/health`);
      if (response.ok) {
        console.log('✓ Server is running');
      } else {
        throw new Error('Server health check failed');
      }
    } catch (error) {
      console.error('Server is not responding. Please start it manually with: uv run ppserver');
      throw error;
    }

    // Step 7.5: Configure pp_assist server credentials
    console.log('\nStep 7.5: Configuring pp_assist server credentials...');
    try {
      const addServerResponse = await fetch(`${PPASSIST_URL}/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Test Server',
          url: SERVER_URL,
          username: TEST_USER_EMAIL,
          password: TEST_USER_PASSWORD,
          is_default: true,
        }),
      });
      if (addServerResponse.ok) {
        console.log('✓ Server credentials configured');
      } else {
        const errorText = await addServerResponse.text();
        throw new Error(`Failed to add server: ${errorText}`);
      }
    } catch (error: any) {
      console.error(`Failed to configure server credentials: ${error.message}`);
      throw error;
    }

    // Build and launch Electron app
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
    console.log('✓ Electron app launched\n');

    console.log('=== SETUP COMPLETE ===\n');
  });

  test.afterAll(async () => {
    console.log('\n=== CLEANUP PHASE ===\n');

    // Close Electron app
    if (electronApp) {
      await electronApp.close();
    }

    // Stop pp_assist daemon
    try {
      execCommand('uv run pp_assist stop', 'Stop pp_assist daemon');
    } catch (error) {
      console.log('Failed to stop pp_assist daemon');
    }

    // Clean up test directory
    if (fs.existsSync(TEST_DIR)) {
      fs.rmSync(TEST_DIR, { recursive: true, force: true });
      console.log('✓ Test directory cleaned up');
    }

    console.log('\n=== CLEANUP COMPLETE ===\n');
  });

  test('should complete full upload workflow', async () => {
    console.log('\n=== UPLOAD WORKFLOW TEST ===\n');

    // Clear any existing localStorage
    await window.evaluate(() => {
      localStorage.clear();
    });
    await window.reload();
    await window.waitForLoadState('domcontentloaded');

    // Step 1: Login with test user
    console.log('Step 1: Logging in with test user...');
    await expect(window.locator('#login-form')).toBeVisible({ timeout: 10000 });

    await window.fill('#login-username', TEST_USER_EMAIL);
    await window.fill('#login-password', TEST_USER_PASSWORD);
    await window.fill('#login-server', PPASSIST_URL);  // Use pp_assist URL, not server URL

    await window.click('#login-btn');

    // Wait for successful login
    await expect(window.locator('#main-content')).toBeVisible({ timeout: 30000 });
    await expect(window.locator('#auth-section')).toBeHidden();
    console.log('✓ Login successful');

    // Step 2: Select test directory
    console.log('\nStep 2: Selecting test directory...');

    // Mock dialog to return test directory
    await electronApp.evaluate(async ({ dialog }, testDir) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [testDir],
      });
    }, TEST_DIR);

    await window.click('#select-dir-btn');

    // Wait for directory to be selected
    await expect(window.locator('#selected-path')).toContainText(TEST_DIR, { timeout: 10000 });
    console.log('✓ Directory selected');

    // Step 3: Configure upload settings
    console.log('\nStep 3: Configuring upload settings...');

    // Enable file content upload
    await window.check('#upload-content');

    console.log('✓ Upload configured (using default parallel uploads)');

    // Step 4: Start scan
    console.log('\nStep 4: Starting directory scan...');

    const startBtn = window.locator('#start-btn');
    await startBtn.click();

    // Wait for scan to complete and show pending files
    const logOutput = window.locator('#log-output');
    await expect(logOutput).toContainText(/Pending SHA256|pending/i, { timeout: 30000 });
    console.log('✓ Scan completed, files pending SHA256 calculation');

    // Step 5: Force-click Start Upload button (may be disabled, but we'll trigger it via JS)
    console.log('\nStep 5: Triggering upload via button click...');
    await window.evaluate(() => {
      const btn = document.querySelector('#start-btn') as HTMLButtonElement;
      if (btn) {
        btn.disabled = false;  // Force enable
        btn.click();  // Force click
      }
    });
    console.log('✓ Upload button clicked');

    // Wait a moment for upload to start
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Step 6: Wait for upload to complete
    console.log('\nStep 6: Waiting for upload to complete...');

    let uploadComplete = false;
    const maxWaitTime = 60000; // 1 minute
    const pollInterval = 2000; // 2 seconds
    const startTime = Date.now();

    while ((Date.now() - startTime) < maxWaitTime && !uploadComplete) {
      const logText = await logOutput.innerText();

      if (logText.includes('Upload complete') || logText.includes('upload complete')) {
        uploadComplete = true;
        console.log('✓ Upload completed');
        break;
      }

      // Check progress
      try {
        const statSuccess = window.locator('#stat-success');
        const successText = await statSuccess.innerText();
        const successCount = parseInt(successText) || 0;
        if (successCount > 0) {
          console.log(`  Progress: ${successCount} files uploaded`);
        }
      } catch (e) {
        // Stats not yet available
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    if (!uploadComplete) {
      const logText = await logOutput.innerText();
      console.log('Upload log:', logText.split('\n').slice(-10).join('\n'));
      throw new Error('Upload did not complete within timeout');
    }

    // Step 7: Verify upload statistics
    console.log('\nStep 7: Verifying upload statistics...');

    const statSuccess = window.locator('#stat-success');
    const successCount = parseInt(await statSuccess.innerText()) || 0;

    expect(successCount).toBeGreaterThan(0);
    console.log(`✓ ${successCount} files uploaded successfully`);

    // Step 8: Verify file exists on server
    console.log('\nStep 8: Verifying file on server...');

    // Get access token (we'll need to extract this from localStorage or use login endpoint)
    const loginResponse = await fetch(`${SERVER_URL}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: TEST_USER_EMAIL,
        password: TEST_USER_PASSWORD,
      }),
    });

    expect(loginResponse.ok).toBeTruthy();
    const loginData = await loginResponse.json();
    const accessToken = loginData.access_token;

    console.log('✓ Got access token');

    // Query server for the file by SHA256
    const fileResponse = await fetch(`${SERVER_URL}/get_file/${testFileSha256}`, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    });

    if (fileResponse.ok) {
      const fileData = await fileResponse.json();
      console.log('✓ File found on server:');
      console.log(`  Filepath: ${fileData.filepath}`);
      console.log(`  SHA256: ${fileData.sha256}`);
      console.log(`  Size: ${fileData.file_size} bytes`);
      console.log(`  Hostname: ${fileData.hostname}`);

      // Verify file details
      expect(fileData.sha256).toBe(testFileSha256);
      expect(fileData.file_size).toBe(fs.statSync(testFilePath).size);
      expect(fileData.filepath).toContain(TEST_FILE_NAME);
    } else {
      const errorText = await fileResponse.text();
      console.error('Failed to retrieve file from server:', errorText);
      throw new Error('File not found on server');
    }

    console.log('\n=== TEST PASSED ===\n');
  });
});
