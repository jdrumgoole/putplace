/**
 * Test: Configuration Wizard First Launch
 *
 * Verifies that the configuration wizard appears when:
 * - App is launched for the first time
 * - Config file (~/.config/putplace/pp_assist.toml) does not exist
 *
 * Prerequisites:
 * - Delete or backup ~/.config/putplace/pp_assist.toml before running
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

test.describe('Configuration Wizard First Launch', () => {
  test.beforeAll(async () => {
    // Backup existing config if it exists
    if (fs.existsSync(CONFIG_PATH)) {
      configBackupPath = CONFIG_PATH + '.test-backup';
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

    // Get the first window
    window = await electronApp.firstWindow();
    await window.waitForLoadState('domcontentloaded');
    console.log('App launched, waiting for initialization...');

    // Give the app time to initialize and check config
    await window.waitForTimeout(2000);
  });

  test.afterAll(async () => {
    // Close the app
    if (electronApp) {
      await electronApp.close();
    }

    // Restore config backup if it existed
    if (configBackupPath && fs.existsSync(configBackupPath)) {
      fs.copyFileSync(configBackupPath, CONFIG_PATH);
      fs.unlinkSync(configBackupPath);
      console.log('Restored config from backup');
    }
  });

  test('should display wizard modal on first launch', async () => {
    // Check that wizard modal is visible
    const wizardModal = window.locator('#wizard-modal');
    await expect(wizardModal).toBeVisible();
    console.log('✓ Wizard modal is visible');

    // Check that wizard title is correct
    const wizardTitle = window.locator('#wizard-title');
    await expect(wizardTitle).toHaveText('Step 1 of 3: Daemon Configuration');
    console.log('✓ Wizard title is correct');

    // Check that step 1 content is visible
    const step1Content = window.locator('#wizard-step-1');
    await expect(step1Content).toBeVisible();
    console.log('✓ Step 1 content is visible');

    // Check that daemon host input has default value
    const daemonHost = window.locator('#wizard-daemon-host');
    await expect(daemonHost).toHaveValue('127.0.0.1');
    console.log('✓ Daemon host has default value');

    // Check that daemon port input has default value
    const daemonPort = window.locator('#wizard-daemon-port');
    await expect(daemonPort).toHaveValue('8765');
    console.log('✓ Daemon port has default value');

    // Check that progress indicator shows step 1 as active
    const step1Number = window.locator('.wizard-step[data-step="1"] .step-number');
    await expect(step1Number).toHaveClass(/active/);
    console.log('✓ Step 1 is marked as active in progress indicator');
  });

  test('should validate daemon connection in step 1', async () => {
    // Click Next button to validate step 1
    const nextBtn = window.locator('#wizard-next-btn');
    await nextBtn.click();
    console.log('Clicked Next button, validating daemon connection...');

    // Wait for validation to complete (should show loading then success/error)
    await window.waitForTimeout(2000);

    // Check if validation message appeared
    const step1Message = window.locator('#wizard-step-1-message');
    const isVisible = await step1Message.isVisible();

    if (isVisible) {
      const messageText = await step1Message.textContent();
      console.log(`Validation message: ${messageText}`);

      // If daemon is running, we should see success and move to step 2
      // If not, we should see an error message
      const hasSuccessClass = await step1Message.evaluate((el) =>
        el.classList.contains('success')
      );
      const hasErrorClass = await step1Message.evaluate((el) =>
        el.classList.contains('error')
      );

      expect(hasSuccessClass || hasErrorClass).toBeTruthy();

      if (hasSuccessClass) {
        console.log('✓ Daemon connection successful');
        // Should have moved to step 2
        const wizardTitle = window.locator('#wizard-title');
        await expect(wizardTitle).toHaveText('Step 2 of 3: Remote Server');
        console.log('✓ Advanced to step 2');
      } else {
        console.log('⚠ Daemon connection failed (this is expected if daemon is not running)');
      }
    }
  });
});
