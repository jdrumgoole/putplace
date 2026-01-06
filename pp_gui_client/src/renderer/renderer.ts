// TypeScript definitions for window.electronAPI
interface UploadProgress {
  fileName: string;
  filePath: string;
  loaded: number;
  total: number;
  percentage: number;
}

interface PPassistCheckResult {
  connected: boolean;
  version?: string;
  database_ok?: boolean;
}

interface PPassistStatusResult {
  success: boolean;
  data?: {
    running: boolean;
    uptime_seconds: number;
    version: string;
    watcher_active: boolean;
    sha256_processor_active: boolean;
    paths_watched: number;
    files_tracked: number;
    pending_sha256: number;
    pending_uploads: number;
  };
  error?: string;
}

interface PPassistPathResult {
  success: boolean;
  data?: {
    id: number;
    path: string;
    recursive: boolean;
    enabled: boolean;
    file_count?: number;
  };
  error?: string;
  alreadyExists?: boolean;
}

interface PPassistListPathsResult {
  success: boolean;
  data?: {
    paths: Array<{
      id: number;
      path: string;
      recursive: boolean;
      enabled: boolean;
      file_count?: number;
    }>;
    total: number;
  };
  error?: string;
}

interface PPassistSha256StatusResult {
  success: boolean;
  data?: {
    is_running: boolean;
    pending_count: number;
    processed_today: number;
    failed_today: number;
    current_file: string | null;
  };
  error?: string;
}

interface PPassistQueueStatusResult {
  success: boolean;
  data?: {
    pending_sha256: number;
    pending_upload: number;
    in_progress: number;
    completed_today: number;
    failed_today: number;
  };
  error?: string;
}

interface ActivityEvent {
  id: number;
  event_type: string;
  filepath: string | null;
  path_id: number | null;
  message: string | null;
  details: any | null;
  created_at: string;
}

interface PPassistActivityResult {
  success: boolean;
  data?: {
    events: ActivityEvent[];
    total: number;
    has_more: boolean;
  };
  error?: string;
}

interface PPassistConfigResult {
  success: boolean;
  data?: {
    config_file: string | null;
    config: {
      server: {
        host: string;
        port: number;
        log_level: string;
      };
      remote_server: {
        name: string | null;
        url: string | null;
        username: string | null;
      };
      database: {
        path: string;
      };
      watcher: {
        enabled: boolean;
        debounce_seconds: number;
      };
      uploader: {
        parallel_uploads: number;
        retry_attempts: number;
        retry_delay_seconds: number;
        timeout_seconds?: number;
      };
      sha256: {
        chunk_size: number;
        chunk_delay_ms: number;
        batch_size: number;
        batch_delay_seconds: number;
      };
    };
  };
  error?: string;
}

interface PPassistSaveConfigResult {
  success: boolean;
  data?: {
    status: string;
    config_file: string;
    message: string;
  };
  error?: string;
}

interface ElectronAPI {
  selectDirectory: () => Promise<string | null>;
  getSystemInfo: () => Promise<{ hostname: string; ipAddress: string }>;
  getCpuCount: () => Promise<number>;
  scanFiles: (dirPath: string, excludePatterns: string[]) => Promise<any>;
  processFile: (filePath: string, hostname: string, ipAddress: string) => Promise<any>;
  login: (username: string, password: string, serverUrl: string) => Promise<any>;
  register: (username: string, email: string, password: string, fullName: string | null, serverUrl: string) => Promise<any>;
  uploadMetadata: (metadata: any, serverUrl: string, token: string) => Promise<any>;
  uploadFileContent: (filePath: string, sha256: string, hostname: string, serverUrl: string, token: string) => Promise<any>;
  onUploadProgress: (callback: (progress: UploadProgress) => void) => void;
  removeUploadProgressListener: () => void;

  // PPassist Daemon API
  ppassistCheck: (daemonUrl?: string) => Promise<PPassistCheckResult>;
  ppassistStart: () => Promise<{success: boolean; message?: string; version?: string}>;
  ppassistStatus: (daemonUrl?: string) => Promise<PPassistStatusResult>;
  ppassistFileStats: (daemonUrl?: string) => Promise<any>;
  ppassistSha256Status: (daemonUrl?: string) => Promise<PPassistSha256StatusResult>;
  ppassistQueueStatus: (daemonUrl?: string) => Promise<PPassistQueueStatusResult>;
  ppassistListPaths: (daemonUrl?: string) => Promise<PPassistListPathsResult>;
  ppassistRegisterPath: (path: string, recursive: boolean, daemonUrl?: string) => Promise<PPassistPathResult>;
  ppassistDeletePath: (pathId: number, daemonUrl?: string) => Promise<any>;
  ppassistScanPath: (pathId: number, daemonUrl?: string) => Promise<any>;
  ppassistScanAll: (daemonUrl?: string) => Promise<any>;
  ppassistListExcludes: (daemonUrl?: string) => Promise<any>;
  ppassistAddExclude: (pattern: string, daemonUrl?: string) => Promise<any>;
  ppassistDeleteExclude: (excludeId: number, daemonUrl?: string) => Promise<any>;
  ppassistTriggerUploads: (uploadContent: boolean, pathPrefix?: string, limit?: number, daemonUrl?: string) => Promise<any>;
  ppassistAddServer: (name: string, url: string, username: string, password: string, daemonUrl?: string) => Promise<any>;
  ppassistListServers: (daemonUrl?: string) => Promise<any>;
  ppassistGetActivity: (limit?: number, sinceId?: number, eventType?: string, daemonUrl?: string) => Promise<PPassistActivityResult>;
  ppassistGetConfig: (daemonUrl?: string) => Promise<PPassistConfigResult>;
  ppassistSaveConfig: (config: any, daemonUrl?: string) => Promise<PPassistSaveConfigResult>;
  ppassistGetFileByPath: (filePath: string, daemonUrl?: string) => Promise<any>;
}

interface UploadHistoryItem {
  filePath: string;
  fileName: string;
  status: 'in-progress' | 'completed' | 'failed';
  percentage: number;
  fileSize: number;
  errorMessage?: string;
  timestamp: Date;
}

declare const electronAPI: ElectronAPI;

// State
let selectedPath: string | null = null;
let excludePatterns: string[] = [];
let isUploading = false;
let shouldStop = false;
let accessToken: string | null = null;
let serverUrl: string = 'https://app.putplace.org';
let currentUsername: string | null = null;

// PPassist daemon state
let daemonConnected = false;
let daemonVersion: string | null = null;
let registeredPathId: number | null = null;
let statusRefreshInterval: ReturnType<typeof setInterval> | null = null;
let daemonReconnectInterval: ReturnType<typeof setInterval> | null = null;
let daemonStartAttempted = false;

// Configuration
const DAEMON_RECONNECT_INTERVAL_MS = 10000; // 10 seconds - configurable
const STATUS_REFRESH_INTERVAL_MS = 2000; // 2 seconds

// DOM elements
const authSection = document.getElementById('auth-section') as HTMLElement;
const loginForm = document.getElementById('login-form') as HTMLElement;
const registerForm = document.getElementById('register-form') as HTMLElement;
const mainContent = document.getElementById('main-content') as HTMLElement;
const authBtn = document.getElementById('auth-btn') as HTMLButtonElement;
const authMessage = document.getElementById('auth-message') as HTMLDivElement;

// Login elements
const loginUsername = document.getElementById('login-username') as HTMLInputElement;
const loginPassword = document.getElementById('login-password') as HTMLInputElement;
const loginServer = document.getElementById('login-server') as HTMLInputElement;
const loginBtn = document.getElementById('login-btn') as HTMLButtonElement;
const logoutBtn = document.getElementById('logout-btn') as HTMLButtonElement;
const togglePasswordBtn = document.getElementById('toggle-password') as HTMLButtonElement;
const eyeIcon = document.getElementById('eye-icon') as HTMLElement;
const eyeOffIcon = document.getElementById('eye-off-icon') as HTMLElement;
const showRegisterLink = document.getElementById('show-register') as HTMLAnchorElement;
const showLoginLink = document.getElementById('show-login') as HTMLAnchorElement;

// Remember email checkbox
const rememberEmailCheckbox = document.getElementById('remember-email') as HTMLInputElement;

// Register elements
const registerUsername = document.getElementById('register-username') as HTMLInputElement;
const registerEmail = document.getElementById('register-email') as HTMLInputElement;
const registerPassword = document.getElementById('register-password') as HTMLInputElement;
const registerFullname = document.getElementById('register-fullname') as HTMLInputElement;
const registerServer = document.getElementById('register-server') as HTMLInputElement;
const registerBtn = document.getElementById('register-btn') as HTMLButtonElement;
const toggleRegisterPasswordBtn = document.getElementById('toggle-register-password') as HTMLButtonElement;

const selectDirBtn = document.getElementById('select-dir-btn') as HTMLButtonElement;
const selectedPathEl = document.getElementById('selected-path') as HTMLDivElement;
const patternInput = document.getElementById('pattern-input') as HTMLInputElement;
const addPatternBtn = document.getElementById('add-pattern-btn') as HTMLButtonElement;
const patternsList = document.getElementById('patterns-list') as HTMLDivElement;
const progressText = document.getElementById('progress-text') as HTMLDivElement;
const progressFill = document.getElementById('progress-fill') as HTMLDivElement;
const statTotal = document.getElementById('stat-total') as HTMLSpanElement;
const statSuccess = document.getElementById('stat-success') as HTMLSpanElement;
const statFailed = document.getElementById('stat-failed') as HTMLSpanElement;
const logOutput = document.getElementById('log-output') as HTMLDivElement;
const startBtn = document.getElementById('start-btn') as HTMLButtonElement;
const stopBtn = document.getElementById('stop-btn') as HTMLButtonElement;
const clearLogBtn = document.getElementById('clear-log-btn') as HTMLButtonElement;
const clearHistoryBtn = document.getElementById('clear-history-btn') as HTMLButtonElement;
const uploadContentCheckbox = document.getElementById('upload-content') as HTMLInputElement;
const activeUploadsContainer = document.getElementById('active-uploads-container') as HTMLDivElement;

// Config modal elements
const configBtn = document.getElementById('config-btn') as HTMLButtonElement;
const configModal = document.getElementById('config-modal') as HTMLDivElement;
const configModalClose = document.getElementById('config-modal-close') as HTMLButtonElement;
const configSaveBtn = document.getElementById('config-save-btn') as HTMLButtonElement;
const configCancelBtn = document.getElementById('config-cancel-btn') as HTMLButtonElement;
const modalConfigFile = document.getElementById('modal-config-file') as HTMLSpanElement;
const configServerHostInput = document.getElementById('config-server-host-input') as HTMLInputElement;
const configServerPortInput = document.getElementById('config-server-port-input') as HTMLInputElement;
const configServerLoglevelInput = document.getElementById('config-server-loglevel-input') as HTMLSelectElement;
const configRemoteNameInput = document.getElementById('config-remote-name-input') as HTMLInputElement;
const configRemoteUrlInput = document.getElementById('config-remote-url-input') as HTMLInputElement;
const configRemoteUsernameInput = document.getElementById('config-remote-username-input') as HTMLInputElement;
const configRemotePasswordInput = document.getElementById('config-remote-password-input') as HTMLInputElement;
const configUploaderParallelInput = document.getElementById('config-uploader-parallel-input') as HTMLInputElement;
const configUploaderRetryInput = document.getElementById('config-uploader-retry-input') as HTMLInputElement;
const configUploaderRetryDelayInput = document.getElementById('config-uploader-retry-delay-input') as HTMLInputElement;
const configUploaderTimeoutInput = document.getElementById('config-uploader-timeout-input') as HTMLInputElement;
const configDatabasePathInput = document.getElementById('config-database-path-input') as HTMLInputElement;
const configWatcherEnabledInput = document.getElementById('config-watcher-enabled-input') as HTMLInputElement;
const configWatcherDebounceInput = document.getElementById('config-watcher-debounce-input') as HTMLInputElement;
const toggleConfigPasswordBtn = document.getElementById('toggle-config-password') as HTMLButtonElement;
const configHostnameInput = document.getElementById('config-hostname-input') as HTMLInputElement;
const configIpAddressInput = document.getElementById('config-ip-address-input') as HTMLInputElement;

// Track active uploads by file path
const activeUploads = new Map<string, HTMLElement>();

// Upload history tracking (session only)
const uploadHistory: UploadHistoryItem[] = [];

// Initialize
async function init() {
  // Load saved settings from localStorage
  const savedToken = localStorage.getItem('accessToken');
  const savedUsername = localStorage.getItem('username');
  const savedServer = localStorage.getItem('serverUrl');
  const savedPatterns = localStorage.getItem('excludePatterns');
  const savedEmail = localStorage.getItem('rememberedEmail');
  const rememberEmail = localStorage.getItem('rememberEmail') === 'true';

  if (savedServer) {
    serverUrl = savedServer;
    loginServer.value = savedServer;
  }

  // Restore remembered email if enabled
  if (rememberEmail && savedEmail) {
    loginUsername.value = savedEmail;
    rememberEmailCheckbox.checked = true;
  }

  if (savedPatterns) {
    excludePatterns = JSON.parse(savedPatterns);
    renderPatterns();
  }

  // Check if user is already logged in
  if (savedToken && savedUsername) {
    accessToken = savedToken;
    currentUsername = savedUsername;
    showMainContent();
    log('Restored previous login session', 'info');
  }

  // Check ppassist daemon connection
  await checkDaemonConnection();

  // Start periodic status refresh
  startStatusRefresh();

  log('Application initialized', 'info');
}

// Check connection to ppassist daemon
async function checkDaemonConnection(): Promise<boolean> {
  try {
    const result = await electronAPI.ppassistCheck();
    daemonConnected = result.connected;
    daemonVersion = result.version || null;

    updateDaemonStatus();

    if (daemonConnected) {
      log(`Connected to ppassist daemon v${daemonVersion}`, 'success');
      // Sync exclude patterns with daemon
      await syncExcludePatterns();
      // Clear reconnect interval if it exists
      if (daemonReconnectInterval) {
        clearInterval(daemonReconnectInterval);
        daemonReconnectInterval = null;
      }
      return true;
    } else {
      // Daemon not running - try to start it (first time only)
      if (!daemonStartAttempted) {
        daemonStartAttempted = true;
        log('PPassist daemon not running. Attempting to start...', 'info');

        try {
          const startResult = await electronAPI.ppassistStart();
          if (startResult.success) {
            log(`Daemon started successfully (v${startResult.version})`, 'success');
            // Recheck connection
            return await checkDaemonConnection();
          } else {
            log(`Failed to start daemon: ${startResult.message}`, 'warning');
          }
        } catch (startError) {
          log('Could not start daemon. Please start it manually with: pp_assist start', 'warning');
        }
      }

      // Set up auto-reconnect if not already running
      if (!daemonReconnectInterval) {
        log(`Will retry connection every ${DAEMON_RECONNECT_INTERVAL_MS / 1000} seconds...`, 'info');
        daemonReconnectInterval = setInterval(async () => {
          log('Attempting to reconnect to daemon...', 'info');
          await checkDaemonConnection();
        }, DAEMON_RECONNECT_INTERVAL_MS);
      }

      return false;
    }
  } catch (error) {
    daemonConnected = false;
    daemonVersion = null;
    updateDaemonStatus();
    log('Failed to connect to ppassist daemon', 'error');

    // Set up auto-reconnect
    if (!daemonReconnectInterval) {
      daemonReconnectInterval = setInterval(async () => {
        await checkDaemonConnection();
      }, DAEMON_RECONNECT_INTERVAL_MS);
    }

    return false;
  }
}

// Update daemon status display
function updateDaemonStatus() {
  const statusEl = document.getElementById('daemon-status');
  if (statusEl) {
    if (daemonConnected) {
      statusEl.textContent = `Daemon: Connected (v${daemonVersion})`;
      statusEl.className = 'daemon-status connected';
    } else {
      statusEl.textContent = 'Daemon: Disconnected';
      statusEl.className = 'daemon-status disconnected';
    }
  }
}

// Sync exclude patterns with daemon
async function syncExcludePatterns() {
  if (!daemonConnected) return;

  // Get current patterns from daemon
  const result = await electronAPI.ppassistListExcludes();
  if (!result.success) return;

  const daemonPatterns = new Set((result.data?.patterns || []).map((p: any) => p.pattern));

  // Add any local patterns that aren't in daemon
  for (const pattern of excludePatterns) {
    if (!daemonPatterns.has(pattern)) {
      await electronAPI.ppassistAddExclude(pattern);
    }
  }
}

// Start periodic status refresh
function startStatusRefresh() {
  if (statusRefreshInterval) {
    clearInterval(statusRefreshInterval);
  }

  // Refresh at configured interval
  statusRefreshInterval = setInterval(async () => {
    if (daemonConnected) {
      await refreshDaemonStatus();
    }
  }, STATUS_REFRESH_INTERVAL_MS);
}

// Refresh daemon status display
async function refreshDaemonStatus() {
  try {
    const statusResult = await electronAPI.ppassistStatus();
    const sha256Result = await electronAPI.ppassistSha256Status();
    const queueResult = await electronAPI.ppassistQueueStatus();
    const configResult = await electronAPI.ppassistGetConfig();

    if (statusResult.success && statusResult.data) {
      updateStatusDisplay(statusResult.data, sha256Result.data, queueResult.data);
    }

    if (configResult.success && configResult.data) {
      updateConfigDisplay(configResult.data);
    }
  } catch (error) {
    // Connection may have been lost
    daemonConnected = false;
    updateDaemonStatus();
  }
}

// Update the status display with daemon info
function updateStatusDisplay(
  status: PPassistStatusResult['data'],
  sha256Status: PPassistSha256StatusResult['data'],
  queueStatus: PPassistQueueStatusResult['data']
) {
  const statsEl = document.getElementById('daemon-stats');
  if (!statsEl || !status) return;

  const pendingSha256 = sha256Status?.pending_count || queueStatus?.pending_sha256 || 0;
  const pendingUpload = queueStatus?.pending_upload || 0;
  const inProgress = queueStatus?.in_progress || 0;
  const completedToday = queueStatus?.completed_today || 0;
  const failedToday = queueStatus?.failed_today || 0;
  const currentFile = sha256Status?.current_file || null;

  // Component status indicators
  const scannerActive = status.watcher_active ? '<span class="status-active">●</span>' : '<span class="status-inactive">○</span>';
  const sha256Active = status.sha256_processor_active ? '<span class="status-active">●</span>' : '<span class="status-inactive">○</span>';

  statsEl.innerHTML = `
    <div class="stats-grid">
      <div class="stat-group">
        <h3>File Statistics</h3>
        <div class="stat-item">
          <span class="stat-label">Files Tracked:</span>
          <span class="stat-value">${status.files_tracked}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Paths Watched:</span>
          <span class="stat-value">${status.paths_watched}</span>
        </div>
      </div>

      <div class="stat-group">
        <h3>Processing Queue</h3>
        <div class="stat-item">
          <span class="stat-label">${scannerActive} Scanner → SHA256:</span>
          <span class="stat-value ${pendingSha256 > 0 ? 'pending' : ''}">${pendingSha256}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">${sha256Active} SHA256 → Upload:</span>
          <span class="stat-value ${pendingUpload > 0 ? 'pending' : ''}">${pendingUpload}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">In Progress:</span>
          <span class="stat-value ${inProgress > 0 ? 'active' : ''}">${inProgress}</span>
        </div>
        ${currentFile ? `<div class="stat-item current-file">
          <span class="stat-label">Processing:</span>
          <span class="stat-value">${currentFile.split('/').pop()}</span>
        </div>` : ''}
      </div>

      <div class="stat-group">
        <h3>Today's Activity</h3>
        <div class="stat-item">
          <span class="stat-label">Completed:</span>
          <span class="stat-value success">${completedToday}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Failed:</span>
          <span class="stat-value ${failedToday > 0 ? 'error' : ''}">${failedToday}</span>
        </div>
      </div>
    </div>
  `;
}

// Update the config display with daemon configuration
function updateConfigDisplay(configData: PPassistConfigResult['data']) {
  if (!configData) return;

  // Config file path
  const configFileEl = document.getElementById('config-file');
  if (configFileEl) {
    configFileEl.textContent = configData.config_file || 'Using defaults (no config file)';
  }

  const config = configData.config;

  // Server settings
  const serverHostEl = document.getElementById('config-server-host');
  const serverPortEl = document.getElementById('config-server-port');
  if (serverHostEl) serverHostEl.textContent = `${config.server.host}:${config.server.port}`;
  if (serverPortEl) serverPortEl.textContent = config.server.port.toString();

  // Remote server settings
  const remoteNameEl = document.getElementById('config-remote-name');
  const remoteUrlEl = document.getElementById('config-remote-url');
  const remoteUsernameEl = document.getElementById('config-remote-username');
  if (remoteNameEl) remoteNameEl.textContent = config.remote_server.name || 'Not configured';
  if (remoteUrlEl) remoteUrlEl.textContent = config.remote_server.url || 'Not configured';
  if (remoteUsernameEl) remoteUsernameEl.textContent = config.remote_server.username || 'Not configured';

  // Uploader settings
  const uploaderParallelEl = document.getElementById('config-uploader-parallel');
  const uploaderRetryEl = document.getElementById('config-uploader-retry');
  if (uploaderParallelEl) uploaderParallelEl.textContent = config.uploader.parallel_uploads.toString();
  if (uploaderRetryEl) uploaderRetryEl.textContent = config.uploader.retry_attempts.toString();
}

// Config modal functions
let currentConfigData: PPassistConfigResult['data'] | null = null;

async function openConfigModal() {
  try {
    // Fetch current config from daemon
    const result = await electronAPI.ppassistGetConfig();

    if (!result.success || !result.data) {
      log('Failed to load configuration: ' + (result.error || 'Unknown error'), 'error');
      return;
    }

    currentConfigData = result.data;
    const config = result.data.config;

    // Populate modal fields
    modalConfigFile.textContent = result.data.config_file || 'Using defaults (no config file)';

    // Server settings
    configServerHostInput.value = config.server.host;
    configServerPortInput.value = config.server.port.toString();
    configServerLoglevelInput.value = config.server.log_level;

    // Remote server settings
    configRemoteNameInput.value = config.remote_server.name || '';
    configRemoteUrlInput.value = config.remote_server.url || '';
    configRemoteUsernameInput.value = config.remote_server.username || '';
    configRemotePasswordInput.value = ''; // Never show password

    // Uploader settings
    configUploaderParallelInput.value = config.uploader.parallel_uploads.toString();
    configUploaderRetryInput.value = config.uploader.retry_attempts.toString();
    configUploaderRetryDelayInput.value = config.uploader.retry_delay_seconds.toString();
    configUploaderTimeoutInput.value = (config.uploader.timeout_seconds || 600).toString();

    // Database settings
    configDatabasePathInput.value = config.database.path;

    // Watcher settings
    configWatcherEnabledInput.checked = config.watcher.enabled;
    configWatcherDebounceInput.value = config.watcher.debounce_seconds.toString();

    // System information
    const systemInfo = await electronAPI.getSystemInfo();
    configHostnameInput.value = systemInfo.hostname;
    configIpAddressInput.value = systemInfo.ipAddress;

    // Render exclude patterns (stored in localStorage)
    renderPatterns();

    // Show modal
    configModal.style.display = 'flex';
  } catch (error: any) {
    log('Error opening config modal: ' + error.message, 'error');
  }
}

function closeConfigModal() {
  configModal.style.display = 'none';
  currentConfigData = null;
}

async function saveConfig() {
  try {
    // Build config object from form inputs
    const config: any = {
      server: {
        host: configServerHostInput.value,
        port: parseInt(configServerPortInput.value),
        log_level: configServerLoglevelInput.value,
      },
      remote_server: {
        name: configRemoteNameInput.value || null,
        url: configRemoteUrlInput.value || null,
        username: configRemoteUsernameInput.value || null,
      },
      database: {
        path: configDatabasePathInput.value,
      },
      watcher: {
        enabled: configWatcherEnabledInput.checked,
        debounce_seconds: parseInt(configWatcherDebounceInput.value),
      },
      uploader: {
        parallel_uploads: parseInt(configUploaderParallelInput.value),
        retry_attempts: parseInt(configUploaderRetryInput.value),
        retry_delay_seconds: parseInt(configUploaderRetryDelayInput.value),
        timeout_seconds: parseInt(configUploaderTimeoutInput.value),
      },
    };

    // Add password if provided
    if (configRemotePasswordInput.value.trim()) {
      config.remote_server.password = configRemotePasswordInput.value;
    }

    // Save via daemon API
    const result = await electronAPI.ppassistSaveConfig(config);

    if (result.success && result.data) {
      log(`Configuration saved to ${result.data.config_file}`, 'success');
      closeConfigModal();
      // Refresh daemon status to show updated config
      await refreshDaemonStatus();
    } else {
      log('Failed to save configuration: ' + (result.error || 'Unknown error'), 'error');
    }
  } catch (error: any) {
    log('Error saving configuration: ' + error.message, 'error');
  }
}

// Save settings
function saveSettings() {
  localStorage.setItem('serverUrl', serverUrl);
  localStorage.setItem('excludePatterns', JSON.stringify(excludePatterns));
}

// Show/hide UI sections
function showMainContent() {
  authSection.style.display = 'none';
  mainContent.style.display = 'block';
  loginBtn.style.display = 'none';
  logoutBtn.style.display = 'block';
  // Update header auth button to show logout with email
  authBtn.textContent = `Logout ${currentUsername}`;
  authBtn.classList.add('logged-in');
  authBtn.title = `Click to logout from ${currentUsername}`;
}

function showAuthSection() {
  authSection.style.display = 'block';
  mainContent.style.display = 'none';
  loginBtn.style.display = 'block';
  logoutBtn.style.display = 'none';
  // Update header auth button to show login
  authBtn.textContent = 'Login';
  authBtn.classList.remove('logged-in');
  authBtn.title = 'Click to login';
}

function showLoginForm() {
  loginForm.style.display = 'block';
  registerForm.style.display = 'none';
  authMessage.className = 'message';
  authMessage.textContent = '';
}

function showRegisterForm() {
  loginForm.style.display = 'none';
  registerForm.style.display = 'block';
  authMessage.className = 'message';
  authMessage.textContent = '';
  // Sync server URL
  registerServer.value = loginServer.value;
}

// Login handler
async function handleLogin() {
  const username = loginUsername.value.trim();
  const password = loginPassword.value.trim();
  const server = loginServer.value.trim();

  if (!username || !password) {
    showAuthMessage('Please enter username and password', 'error');
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = 'Logging in...';
  showAuthMessage('Connecting to server...', 'info');

  const result = await electronAPI.login(username, password, server);

  if (result.success) {
    accessToken = result.token;
    currentUsername = username;
    serverUrl = server;

    // Save to localStorage
    localStorage.setItem('accessToken', accessToken!);
    localStorage.setItem('username', username);
    localStorage.setItem('serverUrl', server);

    // Save or clear remembered email based on checkbox
    if (rememberEmailCheckbox.checked) {
      localStorage.setItem('rememberedEmail', username);
      localStorage.setItem('rememberEmail', 'true');
    } else {
      localStorage.removeItem('rememberedEmail');
      localStorage.setItem('rememberEmail', 'false');
    }

    showAuthMessage('Login successful!', 'success');
    setTimeout(() => {
      showMainContent();
      log(`Logged in as ${username}`, 'success');
    }, 500);
  } else {
    showAuthMessage(`Login failed: ${result.error}`, 'error');
  }

  loginBtn.disabled = false;
  loginBtn.textContent = 'Login';
}

// Logout handler
function handleLogout() {
  accessToken = null;
  currentUsername = null;

  localStorage.removeItem('accessToken');
  localStorage.removeItem('username');

  loginPassword.value = '';
  showAuthSection();
  showLoginForm();
  log('Logged out', 'info');
}

// Register handler
async function handleRegister() {
  const username = registerUsername.value.trim();
  const email = registerEmail.value.trim();
  const password = registerPassword.value.trim();
  const fullName = registerFullname.value.trim() || null;
  const server = registerServer.value.trim();

  if (!username || !email || !password) {
    showAuthMessage('Please fill in all required fields', 'error');
    return;
  }

  if (username.length < 3) {
    showAuthMessage('Username must be at least 3 characters', 'error');
    return;
  }

  if (password.length < 8) {
    showAuthMessage('Password must be at least 8 characters', 'error');
    return;
  }

  registerBtn.disabled = true;
  registerBtn.textContent = 'Registering...';
  showAuthMessage('Creating account...', 'info');

  const result = await electronAPI.register(username, email, password, fullName, server);

  if (result.success) {
    showAuthMessage('Registration successful! Logging you in...', 'success');

    // Auto-login after successful registration
    setTimeout(async () => {
      const loginResult = await electronAPI.login(username, password, server);

      if (loginResult.success) {
        accessToken = loginResult.token;
        currentUsername = username;
        serverUrl = server;

        localStorage.setItem('accessToken', accessToken!);
        localStorage.setItem('username', username);
        localStorage.setItem('serverUrl', server);

        showMainContent();
        log(`Registered and logged in as ${username}`, 'success');
      } else {
        showAuthMessage('Registration successful! Please login.', 'success');
        showLoginForm();
        loginUsername.value = username;
        loginServer.value = server;
      }

      registerBtn.disabled = false;
      registerBtn.textContent = 'Register';
    }, 1000);
  } else {
    showAuthMessage(`Registration failed: ${result.error}`, 'error');
    registerBtn.disabled = false;
    registerBtn.textContent = 'Register';
  }
}

// Show auth message
function showAuthMessage(message: string, type: 'success' | 'error' | 'info') {
  authMessage.textContent = message;
  authMessage.className = `message ${type}`;
}

// Toggle password visibility
function togglePasswordVisibility() {
  if (loginPassword.type === 'password') {
    loginPassword.type = 'text';
    eyeIcon.style.display = 'none';
    eyeOffIcon.style.display = 'block';
  } else {
    loginPassword.type = 'password';
    eyeIcon.style.display = 'block';
    eyeOffIcon.style.display = 'none';
  }
}

function toggleRegisterPasswordVisibility() {
  if (registerPassword.type === 'password') {
    registerPassword.type = 'text';
  } else {
    registerPassword.type = 'password';
  }
}

// Event Listeners
loginBtn.addEventListener('click', handleLogin);
logoutBtn.addEventListener('click', handleLogout);
registerBtn.addEventListener('click', handleRegister);
togglePasswordBtn.addEventListener('click', togglePasswordVisibility);
toggleRegisterPasswordBtn.addEventListener('click', toggleRegisterPasswordVisibility);
showRegisterLink.addEventListener('click', (e) => {
  e.preventDefault();
  showRegisterForm();
});
showLoginLink.addEventListener('click', (e) => {
  e.preventDefault();
  showLoginForm();
});

// Header auth button - toggles between login/logout
authBtn.addEventListener('click', () => {
  if (accessToken) {
    // User is logged in, so logout
    handleLogout();
  } else {
    // User is logged out, scroll to login form
    showAuthSection();
    showLoginForm();
    loginUsername.focus();
  }
});

// Config modal event listeners
configBtn.addEventListener('click', openConfigModal);
configModalClose.addEventListener('click', closeConfigModal);
configCancelBtn.addEventListener('click', closeConfigModal);
configSaveBtn.addEventListener('click', saveConfig);
toggleConfigPasswordBtn.addEventListener('click', () => {
  if (configRemotePasswordInput.type === 'password') {
    configRemotePasswordInput.type = 'text';
  } else {
    configRemotePasswordInput.type = 'password';
  }
});

// Close modal when clicking outside
configModal.addEventListener('click', (e) => {
  if (e.target === configModal) {
    closeConfigModal();
  }
});

// Allow Enter key to submit login
loginPassword.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    handleLogin();
  }
});

selectDirBtn.addEventListener('click', async () => {
  const path = await electronAPI.selectDirectory();
  if (path) {
    selectedPath = path;
    selectedPathEl.textContent = path;
    selectedPathEl.style.color = '#48bb78';
    log(`Selected directory: ${path}`, 'info');
  }
});

addPatternBtn.addEventListener('click', () => {
  const pattern = patternInput.value.trim();
  if (pattern && !excludePatterns.includes(pattern)) {
    excludePatterns.push(pattern);
    renderPatterns();
    patternInput.value = '';
    saveSettings();
    log(`Added exclude pattern: ${pattern}`, 'info');
  }
});

patternInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    addPatternBtn.click();
  }
});

startBtn.addEventListener('click', startUpload);
stopBtn.addEventListener('click', stopUpload);
clearLogBtn.addEventListener('click', () => {
  logOutput.innerHTML = '';
});

clearHistoryBtn.addEventListener('click', () => {
  clearCompletedHistory();
});

// Render exclude patterns
function renderPatterns() {
  patternsList.innerHTML = '';
  excludePatterns.forEach((pattern) => {
    const tag = document.createElement('div');
    tag.className = 'pattern-tag';
    tag.innerHTML = `
      <span>${pattern}</span>
      <button data-pattern="${pattern}">&times;</button>
    `;

    const removeBtn = tag.querySelector('button') as HTMLButtonElement;
    removeBtn.addEventListener('click', () => {
      excludePatterns = excludePatterns.filter((p) => p !== pattern);
      renderPatterns();
      saveSettings();
      log(`Removed exclude pattern: ${pattern}`, 'info');
    });

    patternsList.appendChild(tag);
  });
}

// Logging
function log(message: string, type: 'info' | 'success' | 'error' | 'warning' = 'info') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  const timestamp = new Date().toLocaleTimeString();
  entry.textContent = `[${timestamp}] ${message}`;
  logOutput.appendChild(entry);
  logOutput.scrollTop = logOutput.scrollHeight;
}

// Update progress
function updateProgress(current: number, total: number, success: number, failed: number) {
  const percentage = total > 0 ? (current / total) * 100 : 0;

  progressFill.style.width = `${percentage}%`;
  progressText.textContent = `Processing: ${current}/${total} (${percentage.toFixed(1)}%)`;
  statTotal.textContent = total.toString();
  statSuccess.textContent = success.toString();
  statFailed.textContent = failed.toString();
}

// Stop upload
function stopUpload() {
  shouldStop = true;
  log('Stopping upload...', 'warning');
  stopBtn.disabled = true;
}

// Explain HTTP status codes to users
function explainStatusCode(statusCode: number): string {
  const explanations: Record<number, string> = {
    400: 'Bad Request - The server could not understand the request',
    401: 'Unauthorized - Your session has expired. Please log in again',
    403: 'Forbidden - You do not have permission to access this resource',
    404: 'Not Found - The requested resource does not exist',
    408: 'Request Timeout - The server took too long to respond',
    409: 'Conflict - The file may already exist on the server',
    413: 'File Too Large - The file exceeds the server\'s size limit',
    422: 'Invalid Data - The server could not process the request',
    429: 'Too Many Requests - Please slow down and try again later',
    500: 'Server Error - Something went wrong on the server',
    502: 'Bad Gateway - The server is temporarily unavailable',
    503: 'Service Unavailable - The server is overloaded or under maintenance',
    504: 'Gateway Timeout - The server took too long to respond',
  };
  return explanations[statusCode] || `Error ${statusCode} - An unexpected error occurred`;
}

// Extract status code from error message
function extractStatusCode(error: string): number | null {
  const match = error.match(/status code (\d{3})/i) || error.match(/(\d{3})/);
  return match ? parseInt(match[1], 10) : null;
}

// Format error message with explanation
function formatErrorMessage(error: string): string {
  const statusCode = extractStatusCode(error);
  if (statusCode) {
    return explainStatusCode(statusCode);
  }
  return error;
}

// Check if error indicates authentication failure
function isAuthError(error: string): boolean {
  return error.includes('401') || error.toLowerCase().includes('unauthorized');
}

// Prompt user to re-authenticate
async function promptReauthentication(): Promise<boolean> {
  return new Promise((resolve) => {
    // Stop the upload
    shouldStop = true;

    // Show auth section with a message
    log('Session expired. Please log in again to continue.', 'warning');
    showAuthSection();
    showLoginForm();
    showAuthMessage('Your session has expired. Please log in again to continue uploading.', 'error');

    // Clear the stored token
    accessToken = null;
    localStorage.removeItem('accessToken');

    // The user will need to manually restart the upload after logging in
    resolve(false);
  });
}

// Process a single file (metadata + optional content)
async function processAndUploadFile(
  filePath: string,
  hostname: string,
  ipAddress: string,
  uploadContent: boolean
): Promise<{ success: boolean; fileName: string; error?: string; authRequired?: boolean }> {
  const fileName = filePath.split(/[/\\]/).pop() || filePath;

  // Process file to get metadata
  const processResult = await electronAPI.processFile(filePath, hostname, ipAddress);

  if (!processResult.success) {
    return { success: false, fileName, error: `Processing error: ${processResult.error}` };
  }

  // Upload metadata
  const uploadResult = await electronAPI.uploadMetadata(
    processResult.metadata,
    serverUrl,
    accessToken!
  );

  if (!uploadResult.success) {
    // Check for authentication error
    if (isAuthError(uploadResult.error)) {
      return { success: false, fileName, error: 'Session expired', authRequired: true };
    }
    return { success: false, fileName, error: formatErrorMessage(uploadResult.error) };
  }

  // Optionally upload file content
  if (uploadContent) {
    const contentResult = await electronAPI.uploadFileContent(
      filePath,
      processResult.metadata.sha256,
      hostname,
      serverUrl,
      accessToken!
    );

    if (!contentResult.success) {
      // Check for authentication error
      if (isAuthError(contentResult.error)) {
        return { success: false, fileName, error: 'Session expired', authRequired: true };
      }
      return { success: false, fileName, error: formatErrorMessage(contentResult.error) };
    }
  }

  return { success: true, fileName };
}

// Format bytes to human readable
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Create a progress bar element for a file (table row format)
function createProgressElement(filePath: string, fileName: string): HTMLElement {
  const item = document.createElement('div');
  item.className = 'file-progress-item';
  item.dataset.filePath = filePath;
  item.innerHTML = `
    <div class="col-status">
      <span class="status-icon-placeholder"></span>
    </div>
    <div class="col-file">
      <span class="file-name" title="${filePath}">${fileName}</span>
    </div>
    <div class="col-size">
      <span class="file-size">0 B</span>
    </div>
    <div class="col-timestamp">
      <span class="file-timestamp">--</span>
    </div>
    <div class="col-progress">
      <div class="progress-cell">
        <span class="file-percentage">0%</span>
        <div class="file-progress-bar">
          <div class="file-progress-fill" style="width: 0%"></div>
        </div>
      </div>
    </div>
  `;
  return item;
}

// Update file progress UI - handles multiple concurrent uploads
function updateFileProgress(progress: UploadProgress) {
  let progressElement = activeUploads.get(progress.filePath);

  // Create new progress element if doesn't exist
  if (!progressElement) {
    progressElement = createProgressElement(progress.filePath, progress.fileName);
    // Prepend (add to top) for reverse chronological order
    if (activeUploadsContainer.firstChild) {
      activeUploadsContainer.insertBefore(progressElement, activeUploadsContainer.firstChild);
    } else {
      activeUploadsContainer.appendChild(progressElement);
    }
    activeUploads.set(progress.filePath, progressElement);

    // Add to history as in-progress
    uploadHistory.push({
      filePath: progress.filePath,
      fileName: progress.fileName,
      status: 'in-progress',
      percentage: 0,
      fileSize: progress.total,
      timestamp: new Date()
    });

    // Mark as in-progress
    progressElement.classList.add('in-progress');
  }

  // Update the progress
  const sizeEl = progressElement.querySelector('.file-size') as HTMLSpanElement;
  const percentEl = progressElement.querySelector('.file-percentage') as HTMLSpanElement;
  const fillEl = progressElement.querySelector('.file-progress-fill') as HTMLDivElement;

  // Handle 0-byte files specially
  const isZeroByteFile = progress.total === 0;
  const displayPercentage = isZeroByteFile ? 100 : progress.percentage;

  sizeEl.textContent = formatBytes(progress.total);
  percentEl.textContent = `${displayPercentage}%`;
  fillEl.style.width = `${displayPercentage}%`;

  // Update history
  const historyItem = uploadHistory.find(h => h.filePath === progress.filePath);
  if (historyItem) {
    historyItem.percentage = displayPercentage;
  }

  // If complete, mark as completed and keep in history
  // For 0-byte files, consider them complete immediately
  if (displayPercentage >= 100 || isZeroByteFile) {
    progressElement.classList.remove('in-progress');
    progressElement.classList.add('completed');

    // Add checkmark icon to status column
    const statusCol = progressElement.querySelector('.col-status');
    if (statusCol && !statusCol.querySelector('.status-icon')) {
      const placeholder = statusCol.querySelector('.status-icon-placeholder');
      if (placeholder) {
        placeholder.remove();
      }
      const icon = document.createElement('span');
      icon.className = 'status-icon success-icon';
      icon.innerHTML = '✓';
      icon.title = 'Upload successful';
      statusCol.appendChild(icon);
    }

    // Query file size from daemon and update display
    electronAPI.ppassistGetFileByPath(progress.filePath).then(result => {
      if (result.success && result.data && result.data.file_size !== undefined) {
        const sizeEl = progressElement.querySelector('.file-size') as HTMLSpanElement;
        if (sizeEl) {
          sizeEl.textContent = formatBytes(result.data.file_size);
        }
      }
    }).catch(err => {
      console.warn('Failed to get file size:', err);
    });

    // Add completion timestamp
    const timestampEl = progressElement.querySelector('.file-timestamp') as HTMLSpanElement;
    if (timestampEl) {
      const now = new Date();
      const timeStr = now.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
      timestampEl.textContent = timeStr;
    }

    // Hide the progress bar once upload is complete
    const progressCell = progressElement.querySelector('.col-progress') as HTMLElement;
    if (progressCell) {
      progressCell.style.display = 'none';
    }

    // Mark as completed in history (keep it visible)
    const historyItem = uploadHistory.find(h => h.filePath === progress.filePath);
    if (historyItem) {
      historyItem.status = 'completed';
      historyItem.percentage = 100;
    }

    // Do NOT remove - keep it in the history list
  }
}

// Remove a file's progress bar
function removeFileProgress(filePath: string) {
  const element = activeUploads.get(filePath);
  if (element) {
    element.remove();
    activeUploads.delete(filePath);
  }
}

// Clear all file progress bars
function clearAllFileProgress() {
  activeUploads.forEach((element) => element.remove());
  activeUploads.clear();
}

// Clear completed and failed uploads from history (keep in-progress)
function clearCompletedHistory() {
  // Remove completed and failed items (keep in-progress)
  const toRemove = uploadHistory.filter(h => h.status === 'completed' || h.status === 'failed');

  toRemove.forEach(item => {
    const element = activeUploads.get(item.filePath);
    if (element) {
      element.remove();
      activeUploads.delete(item.filePath);
    }
  });

  // Keep only in-progress items in history
  uploadHistory.splice(0, uploadHistory.length,
    ...uploadHistory.filter(h => h.status === 'in-progress')
  );

  log('Upload history cleared', 'info');
}

// Mark an upload as failed and add to history
function markUploadFailed(filePath: string, fileName: string, errorMessage: string) {
  let progressElement = activeUploads.get(filePath);

  if (!progressElement) {
    progressElement = createProgressElement(filePath, fileName);
    // Prepend (add to top) for reverse chronological order
    if (activeUploadsContainer.firstChild) {
      activeUploadsContainer.insertBefore(progressElement, activeUploadsContainer.firstChild);
    } else {
      activeUploadsContainer.appendChild(progressElement);
    }
    activeUploads.set(filePath, progressElement);
  }

  progressElement.classList.remove('in-progress');
  progressElement.classList.add('failed');

  // Add error icon to status column
  const statusCol = progressElement.querySelector('.col-status');
  if (statusCol && !statusCol.querySelector('.status-icon')) {
    const placeholder = statusCol.querySelector('.status-icon-placeholder');
    if (placeholder) {
      placeholder.remove();
    }
    const icon = document.createElement('span');
    icon.className = 'status-icon error-icon';
    icon.innerHTML = '✗';
    icon.title = errorMessage;
    statusCol.appendChild(icon);
  }

  // Update fill bar to red
  const fillEl = progressElement.querySelector('.file-progress-fill') as HTMLDivElement;
  if (fillEl) {
    fillEl.classList.add('error');
  }

  // Update or add to history
  const historyItem = uploadHistory.find(h => h.filePath === filePath);
  if (historyItem) {
    historyItem.status = 'failed';
    historyItem.errorMessage = errorMessage;
  } else {
    uploadHistory.push({
      filePath,
      fileName,
      status: 'failed',
      percentage: 0,
      fileSize: 0,
      errorMessage,
      timestamp: new Date()
    });
  }
}

// Start upload - now uses ppassist daemon
async function startUpload() {
  if (isUploading) {
    log('Upload already in progress', 'warning');
    return;
  }

  if (!selectedPath) {
    log('Error: No directory selected', 'error');
    return;
  }

  if (!accessToken) {
    log('Error: Not logged in', 'error');
    return;
  }

  // Check daemon connection
  if (!daemonConnected) {
    log('Checking daemon connection...', 'info');
    const connected = await checkDaemonConnection();
    if (!connected) {
      log('Error: PPassist daemon is not running. Start it with: ppassist start', 'error');
      return;
    }
  }

  isUploading = true;
  shouldStop = false;
  startBtn.disabled = true;
  stopBtn.disabled = false;

  const uploadContent = uploadContentCheckbox.checked;

  log('Starting ppassist workflow...', 'info');

  // Step 1: Register the path with daemon
  log(`Registering path: ${selectedPath}`, 'info');
  const registerResult = await electronAPI.ppassistRegisterPath(selectedPath, true);

  if (!registerResult.success && !registerResult.alreadyExists) {
    log(`Error registering path: ${registerResult.error}`, 'error');
    resetUploadState();
    return;
  }

  if (registerResult.alreadyExists) {
    log('Path already registered with daemon', 'info');
    // Get path ID from the list
    const pathsResult = await electronAPI.ppassistListPaths();
    if (pathsResult.success && pathsResult.data) {
      const existingPath = pathsResult.data.paths.find(p => p.path === selectedPath);
      if (existingPath) {
        registeredPathId = existingPath.id;
      }
    }
  } else {
    registeredPathId = registerResult.data?.id || null;
    log(`Path registered with ID: ${registeredPathId}`, 'success');
  }

  // Step 2: Sync exclude patterns
  log('Syncing exclude patterns...', 'info');
  for (const pattern of excludePatterns) {
    const result = await electronAPI.ppassistAddExclude(pattern);
    if (result.success) {
      log(`Added exclude pattern: ${pattern}`, 'info');
    }
  }

  // Step 3: Trigger scan
  log('Starting file scan...', 'info');
  if (registeredPathId) {
    const scanResult = await electronAPI.ppassistScanPath(registeredPathId);
    if (!scanResult.success) {
      log(`Error starting scan: ${scanResult.error}`, 'error');
      resetUploadState();
      return;
    }
    log('Scan initiated - daemon is processing files', 'success');
  }

  // Step 4: Trigger uploads with inline SHA256 calculation
  // Background SHA256 processor is disabled for immediate feedback
  // Files will be processed inline during upload
  log(`Triggering ${uploadContent ? 'full content' : 'metadata'} uploads with inline SHA256 calculation...`, 'info');
  // Set limit to 1000 to support large bulk uploads
  const uploadResult = await electronAPI.ppassistTriggerUploads(uploadContent, selectedPath, 1000);

  if (!uploadResult.success) {
    log(`Upload trigger failed: ${uploadResult.error}`, 'error');
    resetUploadState();
    return;
  }

  const filesQueued = uploadResult.data?.files_queued || 0;
  log(`Queued ${filesQueued} files for upload`, 'success');

  // Step 7: Monitor upload progress (always monitor, even if 0 queued)
  log('Monitoring upload progress...', 'info');

  // Get initial queue status to establish baseline and total
  const initialStatus = await electronAPI.ppassistQueueStatus();
  if (!initialStatus.success || !initialStatus.data) {
    log('Failed to get queue status', 'error');
    resetUploadState();
    return;
  }

  const initialCompleted = initialStatus.data.completed_today || 0;
  const initialFailed = initialStatus.data.failed_today || 0;
  const initialPending = initialStatus.data.pending_upload || 0;

  // Calculate total files for this upload session
  const totalFiles = filesQueued > 0 ? filesQueued : initialPending;

  log(`Starting monitoring: ${totalFiles} total files, ${initialPending} pending`, 'info');

  let lastLoggedProgress = -1;
  let pollCount = 0;
  let lastActivityId: number | undefined = undefined;

  while (!shouldStop) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    pollCount++;

    // Fetch new activity events to track individual files
    const activityResult = await electronAPI.ppassistGetActivity(50, lastActivityId);
    if (activityResult.success && activityResult.data) {
      const events = activityResult.data.events;

      // Process events in chronological order (oldest first)
      for (const event of events.reverse()) {
        if (event.filepath) {
          const fileName = event.filepath.split('/').pop() || event.filepath;

          switch (event.event_type) {
            case 'upload_started':
              // Create progress element for this file
              const fileSize = event.details?.file_size || 0;
              updateFileProgress({
                fileName,
                filePath: event.filepath,
                loaded: 0,
                total: fileSize,
                percentage: fileSize === 0 ? 100 : 0  // 0-byte files are instantly "complete"
              });
              break;

            case 'upload_progress':
              // Update progress
              if (event.details) {
                const totalBytes = event.details.total_bytes || 0;
                const bytesUploaded = event.details.bytes_uploaded || 0;
                let progressPercent = event.details.progress_percent || 0;

                // Calculate percentage for 0-byte files
                if (totalBytes === 0) {
                  progressPercent = 100;
                } else if (progressPercent === 0 && bytesUploaded > 0) {
                  // Fallback calculation if daemon doesn't provide percentage
                  progressPercent = Math.min(100, Math.round((bytesUploaded / totalBytes) * 100));
                }

                updateFileProgress({
                  fileName,
                  filePath: event.filepath,
                  loaded: bytesUploaded,
                  total: totalBytes,
                  percentage: progressPercent
                });
              }
              break;

            case 'upload_complete':
              // Mark as completed
              const completedSize = event.details?.file_size || 0;
              updateFileProgress({
                fileName,
                filePath: event.filepath,
                loaded: completedSize,
                total: completedSize,
                percentage: 100
              });
              break;

            case 'upload_failed':
              // Mark as failed
              markUploadFailed(
                event.filepath,
                fileName,
                event.message || event.details?.error || 'Upload failed'
              );
              break;
          }
        }

        // Update last activity ID
        if (event.id > (lastActivityId || 0)) {
          lastActivityId = event.id;
        }
      }
    }

    const queueStatus = await electronAPI.ppassistQueueStatus();
    if (!queueStatus.success || !queueStatus.data) {
      log('Queue status check failed, retrying...', 'warning');
      continue;
    }

    const pendingUpload = queueStatus.data.pending_upload || 0;
    const inProgress = queueStatus.data.in_progress || 0;
    const completedToday = queueStatus.data.completed_today || 0;
    const failedToday = queueStatus.data.failed_today || 0;

    // Calculate uploads from this session
    const completed = completedToday - initialCompleted;
    const failed = failedToday - initialFailed;
    const processed = completed + failed;

    // Update stats
    updateProgress(processed, totalFiles, completed, failed);

    // Update progress text
    if (inProgress > 0) {
      progressText.textContent = `Uploading: ${processed}/${totalFiles} (${inProgress} in progress)`;
    } else if (pendingUpload > 0) {
      progressText.textContent = `Queued: ${pendingUpload} files waiting to upload`;
    } else {
      progressText.textContent = `Complete: ${completed} successful, ${failed} failed`;
    }

    // Log progress every 10 polls (every 10 seconds) or when state changes
    if (pollCount % 10 === 0 || processed !== lastLoggedProgress) {
      log(`Progress: ${processed}/${totalFiles} completed, ${pendingUpload} pending, ${inProgress} in progress`, 'info');
      lastLoggedProgress = processed;
    }

    // Check if all uploads are complete
    if (pendingUpload === 0 && inProgress === 0 && processed > 0) {
      log(`Upload complete: ${completed} successful, ${failed} failed`, 'success');
      break;
    }

    // Safety check: if nothing is happening for a while, check if we're stuck
    if (pendingUpload === 0 && inProgress === 0 && processed === 0 && pollCount > 5) {
      log('No uploads detected. Workflow may already be complete.', 'warning');
      break;
    }
  }

  if (shouldStop) {
    log('Upload cancelled by user', 'warning');
  } else {
    // Summary
    log('---', 'info');
    const contentMode = uploadContent ? 'with content' : 'metadata only';
    log(`Workflow complete (${contentMode})`, 'info');
  }

  resetUploadState();
}

function resetUploadState() {
  isUploading = false;
  shouldStop = false;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  progressText.textContent = 'Ready';
  progressFill.style.width = '0%';
  // Clean up progress listener
  electronAPI.removeUploadProgressListener();
  // Note: Do NOT clear file progress bars here - keep upload history visible
  // Users can manually clear using the "Clear History" button
}

// Google OAuth handling
declare const google: any;  // Google Sign-In library

// Google Sign-In configuration
const GOOGLE_CLIENT_ID = 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com';  // Will be set from server config

let googleSignInInitialized = false;

async function initializeGoogleSignIn() {
  // Wait for Google library to load
  if (typeof google === 'undefined') {
    console.log('Google Sign-In library not loaded yet, waiting...');
    setTimeout(initializeGoogleSignIn, 100);
    return;
  }

  // Don't reinitialize if already done
  if (googleSignInInitialized) {
    return;
  }

  // Fetch Google Client ID from server
  try {
    const response = await fetch(`${serverUrl}/api/oauth/config`);

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const config = await response.json();

    if (!config.google_client_id || config.google_client_id === '') {
      console.log('Google OAuth not configured on server');
      hideGoogleSignIn();
      return;
    }

    // Clear any previous content
    const googleButton = document.getElementById('google-signin-button');
    if (googleButton) {
      googleButton.innerHTML = '';
    }

    // Initialize Google Sign-In button
    google.accounts.id.initialize({
      client_id: config.google_client_id,
      callback: handleGoogleCallback
    });

    google.accounts.id.renderButton(
      googleButton,
      {
        theme: 'outline',
        size: 'large',
        text: 'signin_with',
        width: 250
      }
    );

    // Show the OAuth controls
    showGoogleSignIn();
    googleSignInInitialized = true;
    console.log('Google Sign-In initialized successfully');
  } catch (error) {
    console.log('Could not initialize Google Sign-In:', error);
    hideGoogleSignIn();
  }
}

function showGoogleSignIn() {
  const oauthControls = document.querySelector('.oauth-controls') as HTMLElement;
  const separator = document.querySelector('.oauth-separator') as HTMLElement;

  if (oauthControls) oauthControls.style.display = 'flex';
  if (separator) separator.style.display = 'flex';
}

function hideGoogleSignIn() {
  const oauthControls = document.querySelector('.oauth-controls') as HTMLElement;
  const separator = document.querySelector('.oauth-separator') as HTMLElement;

  if (oauthControls) oauthControls.style.display = 'none';
  if (separator) separator.style.display = 'none';
}

async function handleGoogleCallback(response: any) {
  const idToken = response.credential;

  loginBtn.disabled = true;
  showAuthMessage('Signing in with Google...', 'info');

  try {
    // Send ID token to backend
    const result = await fetch(`${serverUrl}/api/auth/google`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ id_token: idToken })
    });

    const data = await result.json();

    if (result.ok && data.access_token) {
      accessToken = data.access_token;

      // Decode JWT to get username (simple base64 decode)
      const payload = JSON.parse(atob(data.access_token.split('.')[1]));
      currentUsername = payload.sub;

      // Save to localStorage
      localStorage.setItem('accessToken', accessToken!);
      localStorage.setItem('username', currentUsername!);
      localStorage.setItem('serverUrl', serverUrl);

      showAuthMessage('Successfully signed in with Google!', 'success');
      showMainContent();
    } else {
      showAuthMessage(data.detail || 'Google Sign-In failed', 'error');
      loginBtn.disabled = false;
    }
  } catch (error: any) {
    showAuthMessage(`Error: ${error.message}`, 'error');
    loginBtn.disabled = false;
  }
}

// Initialize app
init();

// Initialize Google Sign-In after a delay to ensure library is loaded
setTimeout(initializeGoogleSignIn, 500);
