import { app, BrowserWindow, ipcMain, dialog, Menu } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import * as os from 'os';
import axios from 'axios';

// Set the application name BEFORE app is ready (required for macOS menu bar)
app.setName('PutPlace Client');

let mainWindow: BrowserWindow | null = null;

function createMenu() {
  const isMac = process.platform === 'darwin';

  const template: Electron.MenuItemConstructorOptions[] = [
    // App menu (macOS only)
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' as const },
        { type: 'separator' as const },
        { role: 'services' as const },
        { type: 'separator' as const },
        { role: 'hide' as const },
        { role: 'hideOthers' as const },
        { role: 'unhide' as const },
        { type: 'separator' as const },
        { role: 'quit' as const }
      ]
    }] : []),
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { type: 'separator' },
        { role: 'front' }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer/index.html'));

  // Open DevTools in development
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createMenu();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// IPC Handlers

// Select directory dialog
ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
  });

  if (result.canceled) {
    return null;
  }

  return result.filePaths[0];
});

// Get system info
ipcMain.handle('get-system-info', async () => {
  const hostname = os.hostname();

  // Get local IP address
  const networkInterfaces = os.networkInterfaces();
  let ipAddress = '127.0.0.1';

  for (const iface of Object.values(networkInterfaces)) {
    if (!iface) continue;
    for (const alias of iface) {
      if (alias.family === 'IPv4' && !alias.internal) {
        ipAddress = alias.address;
        break;
      }
    }
    if (ipAddress !== '127.0.0.1') break;
  }

  return { hostname, ipAddress };
});

// Calculate SHA256 hash
function calculateSHA256(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const stream = fs.createReadStream(filePath);

    stream.on('error', reject);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
  });
}

// Check if path matches exclude pattern
function matchesExcludePattern(
  relativePath: string,
  patterns: string[]
): boolean {
  if (!patterns || patterns.length === 0) return false;

  const pathParts = relativePath.split(path.sep);

  for (const pattern of patterns) {
    // Exact match
    if (relativePath === pattern) return true;

    // Check if pattern matches any part
    if (pathParts.includes(pattern)) return true;

    // Wildcard matching (simple implementation)
    if (pattern.includes('*')) {
      const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
      if (regex.test(relativePath) || pathParts.some(part => regex.test(part))) {
        return true;
      }
    }
  }

  return false;
}

// Scan directory recursively
function scanDirectory(
  dirPath: string,
  basePath: string,
  excludePatterns: string[]
): string[] {
  const files: string[] = [];

  try {
    const items = fs.readdirSync(dirPath);

    for (const item of items) {
      const fullPath = path.join(dirPath, item);
      const relativePath = path.relative(basePath, fullPath);

      // Check exclude patterns
      if (matchesExcludePattern(relativePath, excludePatterns)) {
        continue;
      }

      const stats = fs.statSync(fullPath);

      if (stats.isDirectory()) {
        files.push(...scanDirectory(fullPath, basePath, excludePatterns));
      } else if (stats.isFile()) {
        files.push(fullPath);
      }
    }
  } catch (error) {
    console.error(`Error scanning directory ${dirPath}:`, error);
  }

  return files;
}

// Scan files
ipcMain.handle('scan-files', async (event, dirPath: string, excludePatterns: string[]) => {
  try {
    const files = scanDirectory(dirPath, dirPath, excludePatterns);
    return { success: true, files, count: files.length };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Process single file
ipcMain.handle('process-file', async (
  event,
  filePath: string,
  hostname: string,
  ipAddress: string
) => {
  try {
    const sha256 = await calculateSHA256(filePath);
    const stats = fs.statSync(filePath);

    const metadata = {
      filepath: filePath,
      hostname,
      ip_address: ipAddress,
      sha256,
      file_size: stats.size,
      file_mode: stats.mode,
      file_uid: stats.uid,
      file_gid: stats.gid,
      file_mtime: stats.mtimeMs / 1000,
      file_atime: stats.atimeMs / 1000,
      file_ctime: stats.ctimeMs / 1000,
      is_symlink: stats.isSymbolicLink(),
      link_target: stats.isSymbolicLink() ? fs.readlinkSync(filePath) : null,
    };

    return { success: true, metadata };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Login to server
ipcMain.handle('login', async (
  event,
  username: string,
  password: string,
  serverUrl: string
) => {
  try {
    const loginUrl = `${serverUrl.replace(/\/$/, '')}/api/login`;
    const response = await axios.post(loginUrl, {
      username,
      password,
    }, {
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    return { success: true, token: response.data.access_token };
  } catch (error: any) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
    };
  }
});

// Register new user
ipcMain.handle('register', async (
  event,
  username: string,
  email: string,
  password: string,
  fullName: string | null,
  serverUrl: string
) => {
  try {
    const registerUrl = `${serverUrl.replace(/\/$/, '')}/api/register`;
    const requestData: any = {
      username,
      email,
      password,
    };

    if (fullName) {
      requestData.full_name = fullName;
    }

    await axios.post(registerUrl, requestData, {
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    return { success: true };
  } catch (error: any) {
    return {
      success: false,
      error: error.response?.data?.detail || error.message,
    };
  }
});

// Upload metadata to server
ipcMain.handle('upload-metadata', async (
  event,
  metadata: any,
  serverUrl: string,
  token: string
) => {
  try {
    const uploadUrl = `${serverUrl.replace(/\/$/, '')}/put_file`;
    const response = await axios.post(uploadUrl, metadata, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    return { success: true, data: response.data, status: response.status };
  } catch (error: any) {
    return {
      success: false,
      error: error.message,
      status: error.response?.status,
    };
  }
});
