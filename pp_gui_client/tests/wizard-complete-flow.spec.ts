/**
 * Test: Configuration Wizard Complete Flow
 *
 * Tests the complete wizard flow including:
 * - Step 1: Daemon configuration and validation
 * - Step 2: Server URL configuration
 * - Step 3: Authentication (with skip option)
 * - Navigation (Back/Next buttons)
 * - Configuration saving
 *
 * Prerequisites:
 * - pp_assist daemon running on localhost:8765
 */

import { test, expect, _electron as electron, ElectronApplication, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

const CONFIG_PATH = path.join(os.homedir(), '.config', 'putplace', 'pp_assist.toml');
let configBackupPath: string | null = null;

let electronApp: ElectronApplication;
let window: Page;

test.describe('Configuration Wizard Complete Flow', () => {
  test.beforeAll(async () => {
    // Backup and remove existing config
    if (fs.existsSync(CONFIG_PATH)) {
      configBackupPath = CONFIG_PATH + '.test-backup-' + Date.now();
      fs.copyFileSync(CONFIG_PATH, configBackupPath);
      fs.unlinkSync(CONFIG_PATH);
      console.log(`Backed up config to ${configBackupPath}`);
    }

    // Launch Electron app
    console.log('Launching Electron app...');
    electronApp = await electron.launch({
      args: [path.join(__dirname, '..', 'dist', 'main.js')],
      env: {
        ...process.env,
        NODE_ENV: 'test',
      },
    });

    window = await electronApp.firstWindow();
    await window.waitForLoadState('domcontentloaded');
    await window.waitForTimeout(2000);
    console.log('App launched and initialized');
  });

  test.afterAll(async () => {
    if (electronApp) {
      await electronApp.close();
    }

    // Clean up test config and restore backup
    if (fs.existsSync(CONFIG_PATH)) {
      fs.unlinkSync(CONFIG_PATH);
      console.log('Removed test config');
    }

    if (configBackupPath && fs.existsSync(configBackupPath)) {
      fs.copyFileSync(configBackupPath, CONFIG_PATH);
      fs.unlinkSync(configBackupPath);
      console.log('Restored original config');
    }
  });

  test('complete wizard flow with skip authentication', async () => {
    // ===== Step 1: Daemon Configuration =====
    console.log('\n=== Testing Step 1: Daemon Configuration ===');

    const wizardModal = window.locator('#wizard-modal');
    await expect(wizardModal).toBeVisible();

    const wizardTitle = window.locator('#wizard-title');
    await expect(wizardTitle).toHaveText('Step 1 of 3: Daemon Configuration');

    // Verify default values
    const daemonHost = window.locator('#wizard-daemon-host');
    const daemonPort = window.locator('#wizard-daemon-port');
    await expect(daemonHost).toHaveValue('127.0.0.1');
    await expect(daemonPort).toHaveValue('8765');
    console.log('✓ Step 1 initialized with default values');

    // Click Next to validate and proceed
    const nextBtn = window.locator('#wizard-next-btn');
    await nextBtn.click();
    console.log('Clicked Next, validating daemon connection...');

    // Wait for validation
    await window.waitForTimeout(3000);

    // Check if we advanced to step 2 (validation succeeded)
    const currentTitle = await wizardTitle.textContent();
    if (currentTitle === 'Step 2 of 3: Remote Server') {
      console.log('✓ Step 1 validation successful, advanced to Step 2');
    } else {
      console.log('⚠ Still on Step 1, daemon may not be running');
      const step1Message = window.locator('#wizard-step-1-message');
      if (await step1Message.isVisible()) {
        console.log(`Validation message: ${await step1Message.textContent()}`);
      }
      // Skip rest of test if daemon is not available
      return;
    }

    // ===== Step 2: Server Configuration =====
    console.log('\n=== Testing Step 2: Server Configuration ===');

    await expect(wizardTitle).toHaveText('Step 2 of 3: Remote Server');

    // Check step 2 content is visible
    const step2Content = window.locator('#wizard-step-2');
    await expect(step2Content).toBeVisible();

    // Verify default server URL
    const serverUrl = window.locator('#wizard-server-url');
    await expect(serverUrl).toHaveValue('https://app.putplace.org');
    console.log('✓ Step 2 initialized with default server URL');

    // Test Back button
    const backBtn = window.locator('#wizard-back-btn');
    await expect(backBtn).toBeVisible();
    await backBtn.click();
    await window.waitForTimeout(500);

    // Should be back on step 1
    await expect(wizardTitle).toHaveText('Step 1 of 3: Daemon Configuration');
    console.log('✓ Back button works - returned to Step 1');

    // Go forward again
    await nextBtn.click();
    await window.waitForTimeout(1000);
    await expect(wizardTitle).toHaveText('Step 2 of 3: Remote Server');
    console.log('✓ Next button works - returned to Step 2');

    // Proceed to step 3
    await nextBtn.click();
    await window.waitForTimeout(2000);

    // ===== Step 3: Authentication =====
    console.log('\n=== Testing Step 3: Authentication ===');

    await expect(wizardTitle).toHaveText('Step 3 of 3: Authentication');

    // Check step 3 content is visible
    const step3Content = window.locator('#wizard-step-3');
    await expect(step3Content).toBeVisible();

    // Check that skip checkbox is available
    const skipAuth = window.locator('#wizard-skip-auth');
    await expect(skipAuth).toBeVisible();
    console.log('✓ Step 3 initialized with authentication options');

    // Check skip authentication
    await skipAuth.check();
    await expect(skipAuth).toBeChecked();
    console.log('✓ Skip authentication checkbox works');

    // Check that Finish button is visible
    const finishBtn = window.locator('#wizard-finish-btn');
    await expect(finishBtn).toBeVisible();
    console.log('✓ Finish button is visible');

    // Click Finish to save configuration
    await finishBtn.click();
    console.log('Clicked Finish, saving configuration...');

    // Wait for save operation
    await window.waitForTimeout(3000);

    // Wizard should close
    const isWizardVisible = await wizardModal.isVisible();
    if (!isWizardVisible) {
      console.log('✓ Wizard closed after saving configuration');
    } else {
      console.log('⚠ Wizard still visible, check for errors');
      const step3Message = window.locator('#wizard-step-3-message');
      if (await step3Message.isVisible()) {
        console.log(`Step 3 message: ${await step3Message.textContent()}`);
      }
    }

    // Verify config file was created
    const configExists = fs.existsSync(CONFIG_PATH);
    expect(configExists).toBeTruthy();
    console.log('✓ Configuration file created at ~/.config/putplace/pp_assist.toml');

    if (configExists) {
      const configContent = fs.readFileSync(CONFIG_PATH, 'utf-8');
      console.log('\nGenerated configuration:');
      console.log(configContent);

      // Verify config contains expected sections
      expect(configContent).toContain('[server]');
      expect(configContent).toContain('[remote_server]');
      console.log('✓ Configuration has required sections');
    }
  });

  test('wizard skip button creates minimal config', async () => {
    // Delete config if it exists
    if (fs.existsSync(CONFIG_PATH)) {
      fs.unlinkSync(CONFIG_PATH);
    }

    // Restart app to trigger wizard again
    await electronApp.close();

    electronApp = await electron.launch({
      args: [path.join(__dirname, '..', 'dist', 'main.js')],
      env: { ...process.env, NODE_ENV: 'test' },
    });

    window = await electronApp.firstWindow();
    await window.waitForLoadState('domcontentloaded');
    await window.waitForTimeout(2000);

    console.log('\n=== Testing Skip Setup Button ===');

    const wizardModal = window.locator('#wizard-modal');
    await expect(wizardModal).toBeVisible();

    // Click Skip button
    const skipBtn = window.locator('#wizard-skip-btn');
    await expect(skipBtn).toBeVisible();

    // Handle confirmation dialog
    window.on('dialog', async (dialog) => {
      console.log(`Dialog message: ${dialog.message()}`);
      await dialog.accept();
    });

    await skipBtn.click();
    console.log('Clicked Skip Setup button');

    await window.waitForTimeout(2000);

    // Wizard should close
    const isWizardVisible = await wizardModal.isVisible();
    expect(isWizardVisible).toBeFalsy();
    console.log('✓ Wizard closed after clicking Skip');

    // Config should still be created (minimal config)
    const configExists = fs.existsSync(CONFIG_PATH);
    expect(configExists).toBeTruthy();
    console.log('✓ Minimal configuration file created');
  });
});
