import { app, BrowserWindow, ipcMain, dialog, Menu } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import * as os from 'os';
import { spawn } from 'child_process';
import axios from 'axios';

// Set the application name BEFORE app is ready (required for macOS menu bar)
app.setName('PutPlace Client');

// Global error handlers to prevent crashes
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
  // Don't exit - try to keep the app running
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  // Don't exit - try to keep the app running
});

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
    height: 920,
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

// Login via pp_assist (which proxies to the remote server)
ipcMain.handle('login', async (
  event,
  username: string,
  password: string,
  ppassistUrl: string
) => {
  try {
    const loginUrl = `${ppassistUrl.replace(/\/$/, '')}/login`;
    const response = await axios.post(loginUrl, {
      email: username,  // Server expects email field
      password,
    }, {
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    // pp_assist returns { success, token, user_id, error }
    if (response.data.success) {
      return { success: true, token: response.data.token };
    } else {
      return { success: false, error: response.data.error || 'Login failed' };
    }
  } catch (error: any) {
    let errorMsg = 'Unknown error';
    if (error.response?.data?.error) {
      errorMsg = error.response.data.error;
    } else if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      errorMsg = typeof detail === 'string' ? detail : JSON.stringify(detail);
    } else if (error.message) {
      errorMsg = error.message;
    } else if (error.code) {
      errorMsg = `Connection error: ${error.code}`;
    }
    return {
      success: false,
      error: errorMsg,
    };
  }
});

// Register new user via pp_assist (which proxies to the remote server)
ipcMain.handle('register', async (
  event,
  username: string,
  email: string,
  password: string,
  fullName: string | null,
  ppassistUrl: string
) => {
  try {
    const registerUrl = `${ppassistUrl.replace(/\/$/, '')}/register`;
    const requestData: any = {
      username,
      email,
      password,
    };

    if (fullName) {
      requestData.full_name = fullName;
    }

    const response = await axios.post(registerUrl, requestData, {
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000,
    });

    // pp_assist returns { success, user_id, error }
    if (response.data.success) {
      return { success: true };
    } else {
      return { success: false, error: response.data.error || 'Registration failed' };
    }
  } catch (error: any) {
    let errorMsg = 'Unknown error';
    if (error.response?.data?.error) {
      errorMsg = error.response.data.error;
    } else if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      errorMsg = typeof detail === 'string' ? detail : JSON.stringify(detail);
    } else if (error.message) {
      errorMsg = error.message;
    } else if (error.code) {
      errorMsg = `Connection error: ${error.code}`;
    }
    return {
      success: false,
      error: errorMsg,
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

// Get CPU count for parallel uploads
ipcMain.handle('get-cpu-count', async () => {
  return os.cpus().length;
});

// ===== PPassist Daemon API =====
const DEFAULT_PPASSIST_URL = 'http://localhost:8765';

// Check if ppassist daemon is running
ipcMain.handle('ppassist-check', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/health`, { timeout: 5000 });
    return {
      connected: true,
      version: response.data.version,
      database_ok: response.data.database_ok,
    };
  } catch (error) {
    return { connected: false };
  }
});

// Start ppassist daemon
ipcMain.handle('ppassist-start', async () => {
  try {
    console.log('Starting pp_assist daemon...');

    // Start daemon in background using uv run
    const process = spawn('uv', ['run', 'pp_assist', 'start'], {
      detached: true,
      stdio: 'ignore',
      shell: true
    });

    // Unref so the parent process can exit independently
    process.unref();

    console.log('pp_assist daemon start command sent');

    // Wait a bit for the daemon to start
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Check if it's running
    try {
      const response = await axios.get(`${DEFAULT_PPASSIST_URL}/health`, { timeout: 5000 });
      return {
        success: true,
        message: 'Daemon started successfully',
        version: response.data.version
      };
    } catch (checkError) {
      return {
        success: false,
        message: 'Daemon start command sent but not responding yet. Please wait...'
      };
    }
  } catch (error: any) {
    console.error('Failed to start pp_assist daemon:', error);
    return {
      success: false,
      message: `Failed to start daemon: ${error.message}`
    };
  }
});

// Get ppassist daemon status
ipcMain.handle('ppassist-status', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/status`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get file statistics
ipcMain.handle('ppassist-file-stats', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/files/stats`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get SHA256 processor status
ipcMain.handle('ppassist-sha256-status', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/sha256/status`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get upload queue status
ipcMain.handle('ppassist-queue-status', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/uploads/queue`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// List registered paths
ipcMain.handle('ppassist-list-paths', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/paths`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Register a path with ppassist
ipcMain.handle('ppassist-register-path', async (_event, pathStr: string, recursive: boolean, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/paths`, {
      path: pathStr,
      recursive,
    }, { timeout: 30000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    if (error.response?.status === 409) {
      return { success: true, data: { message: 'Path already registered' }, alreadyExists: true };
    }
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Delete a registered path
ipcMain.handle('ppassist-delete-path', async (_event, pathId: number, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    await axios.delete(`${url}/paths/${pathId}`, { timeout: 10000 });
    return { success: true };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Trigger scan of a path
ipcMain.handle('ppassist-scan-path', async (_event, pathId: number, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/paths/${pathId}/scan`, {}, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Trigger full scan of all paths
ipcMain.handle('ppassist-scan-all', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/scan`, {}, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// List exclude patterns
ipcMain.handle('ppassist-list-excludes', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/excludes`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Add exclude pattern
ipcMain.handle('ppassist-add-exclude', async (_event, pattern: string, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/excludes`, { pattern }, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    if (error.response?.status === 409) {
      return { success: true, alreadyExists: true };
    }
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Delete exclude pattern
ipcMain.handle('ppassist-delete-exclude', async (_event, excludeId: number, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    await axios.delete(`${url}/excludes/${excludeId}`, { timeout: 10000 });
    return { success: true };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Trigger uploads
ipcMain.handle('ppassist-trigger-uploads', async (_event, uploadContent: boolean, pathPrefix?: string, limit?: number, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const payload: any = { upload_content: uploadContent };
    if (pathPrefix) {
      payload.path_prefix = pathPrefix;
    }
    if (limit !== undefined) {
      payload.limit = limit;
    }
    const response = await axios.post(`${url}/uploads`, payload, { timeout: 30000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Configure remote server in ppassist
ipcMain.handle('ppassist-add-server', async (
  _event,
  name: string,
  serverUrl: string,
  username: string,
  password: string,
  daemonUrl?: string
) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/servers`, {
      name,
      url: serverUrl,
      username,
      password,
    }, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    if (error.response?.status === 409) {
      return { success: true, alreadyExists: true };
    }
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// List configured servers
ipcMain.handle('ppassist-list-servers', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/servers`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get recent activity
ipcMain.handle('ppassist-get-activity', async (_event, limit: number = 50, sinceId?: number, eventType?: string, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    // Build query params
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (sinceId !== undefined) {
      params.append('since_id', sinceId.toString());
    }
    if (eventType) {
      params.append('event_type', eventType);
    }

    const response = await axios.get(`${url}/activity?${params.toString()}`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get daemon configuration
ipcMain.handle('ppassist-get-config', async (_event, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/config`, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Save daemon configuration
ipcMain.handle('ppassist-save-config', async (_event, config: any, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.post(`${url}/config`, config, { timeout: 10000 });
    return { success: true, data: response.data };
  } catch (error: any) {
    return { success: false, error: error.message };
  }
});

// Get file info by filepath from daemon
ipcMain.handle('ppassist-get-file-by-path', async (_event, filePath: string, daemonUrl?: string) => {
  const url = daemonUrl || DEFAULT_PPASSIST_URL;
  try {
    const response = await axios.get(`${url}/files`, {
      params: { path_prefix: filePath, limit: 1 },
      timeout: 5000
    });
    if (response.data.entries && response.data.entries.length > 0) {
      return { success: true, data: response.data.entries[0] };
    }
    return { success: false, error: 'File not found' };
  } catch (error: any) {
    return { success: false, error: error.response?.data?.detail || error.message };
  }
});

// Upload file content to server using native Node.js streaming
// This avoids buffering the entire file in memory, supporting files > 4GB
ipcMain.handle('upload-file-content', async (
  event,
  filePath: string,
  sha256: string,
  hostname: string,
  serverUrl: string,
  token: string
) => {
  return new Promise((resolve) => {
    try {
      const stats = fs.statSync(filePath);
      const fileSize = stats.size;
      const fileName = path.basename(filePath);

      // Build multipart form data manually to avoid buffering
      const boundary = `----FormBoundary${Date.now()}`;
      const formHeader = Buffer.from(
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="file"; filename="${fileName}"\r\n` +
        `Content-Type: application/octet-stream\r\n\r\n`
      );
      const formFooter = Buffer.from(`\r\n--${boundary}--\r\n`);
      const contentLength = formHeader.length + fileSize + formFooter.length;

      // Parse the server URL
      const url = new URL(`${serverUrl.replace(/\/$/, '')}/upload_file/${sha256}?hostname=${encodeURIComponent(hostname)}&filepath=${encodeURIComponent(filePath)}`);
      const isHttps = url.protocol === 'https:';
      const httpModule = isHttps ? require('https') : require('http');

      const options = {
        hostname: url.hostname,
        port: url.port || (isHttps ? 443 : 80),
        path: url.pathname + url.search,
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': `multipart/form-data; boundary=${boundary}`,
          'Content-Length': contentLength,
        },
      };

      let uploadedBytes = 0;

      const req = httpModule.request(options, (res: any) => {
        let responseData = '';
        res.on('data', (chunk: Buffer) => {
          responseData += chunk.toString();
        });
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ success: true, data: responseData, status: res.statusCode });
          } else {
            resolve({
              success: false,
              error: `Request failed with status code ${res.statusCode}`,
              status: res.statusCode,
            });
          }
        });
      });

      // Increase timeout for large files (1 hour)
      req.setTimeout(3600000);

      // Write form header
      req.write(formHeader);

      // Stream file content with progress tracking and backpressure handling
      const fileStream = fs.createReadStream(filePath, { highWaterMark: 64 * 1024 }); // 64KB chunks

      // Handle request errors - clean up file stream
      req.on('error', (error: Error) => {
        console.error(`Request error for ${filePath}:`, error);
        fileStream.destroy();
        resolve({
          success: false,
          error: error.message,
          status: undefined,
        });
      });

      fileStream.on('data', (chunk: Buffer | string) => {
        const chunkBuffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        uploadedBytes += chunkBuffer.length;
        const percentage = Math.round((uploadedBytes / fileSize) * 100);

        // Safely send progress - check if sender is still valid
        try {
          if (event.sender && !event.sender.isDestroyed()) {
            event.sender.send('upload-progress', {
              fileName,
              filePath,
              loaded: uploadedBytes,
              total: fileSize,
              percentage,
            });
          }
        } catch (sendError) {
          // Ignore errors when sending progress - renderer may have been closed
          console.warn('Could not send progress update:', sendError);
        }

        // Handle backpressure - pause file stream if write buffer is full
        const canContinue = req.write(chunkBuffer);
        if (!canContinue) {
          fileStream.pause();
          req.once('drain', () => {
            fileStream.resume();
          });
        }
      });

      fileStream.on('end', () => {
        req.write(formFooter);
        req.end();
      });

      fileStream.on('error', (error: Error) => {
        console.error(`File stream error for ${filePath}:`, error);
        req.destroy();
        resolve({
          success: false,
          error: `File read error: ${error.message}`,
          status: undefined,
        });
      });

      // Handle request errors during streaming
      req.on('error', (error: Error) => {
        console.error(`Request error for ${filePath}:`, error);
        fileStream.destroy();
        resolve({
          success: false,
          error: error.message,
          status: undefined,
        });
      });

    } catch (error: any) {
      resolve({
        success: false,
        error: error.message || 'Unknown error',
        status: undefined,
      });
    }
  });
});
