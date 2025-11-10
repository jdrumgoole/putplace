// TypeScript definitions for window.electronAPI
interface ElectronAPI {
  selectDirectory: () => Promise<string | null>;
  getSystemInfo: () => Promise<{ hostname: string; ipAddress: string }>;
  scanFiles: (dirPath: string, excludePatterns: string[]) => Promise<any>;
  processFile: (filePath: string, hostname: string, ipAddress: string) => Promise<any>;
  login: (username: string, password: string, serverUrl: string) => Promise<any>;
  register: (username: string, email: string, password: string, fullName: string | null, serverUrl: string) => Promise<any>;
  uploadMetadata: (metadata: any, serverUrl: string, token: string) => Promise<any>;
}

declare const electronAPI: ElectronAPI;

// State
let selectedPath: string | null = null;
let excludePatterns: string[] = [];
let isUploading = false;
let shouldStop = false;
let accessToken: string | null = null;
let serverUrl: string = 'http://localhost:8000';
let currentUsername: string | null = null;

// DOM elements
const authSection = document.getElementById('auth-section') as HTMLElement;
const loginForm = document.getElementById('login-form') as HTMLElement;
const registerForm = document.getElementById('register-form') as HTMLElement;
const mainContent = document.getElementById('main-content') as HTMLElement;
const authStatus = document.getElementById('auth-status') as HTMLDivElement;
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
const hostnameInput = document.getElementById('hostname') as HTMLInputElement;
const ipAddressInput = document.getElementById('ip-address') as HTMLInputElement;
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

// Initialize
async function init() {
  const systemInfo = await electronAPI.getSystemInfo();
  hostnameInput.value = systemInfo.hostname;
  ipAddressInput.value = systemInfo.ipAddress;

  // Load saved settings from localStorage
  const savedToken = localStorage.getItem('accessToken');
  const savedUsername = localStorage.getItem('username');
  const savedServer = localStorage.getItem('serverUrl');
  const savedPatterns = localStorage.getItem('excludePatterns');

  if (savedServer) {
    serverUrl = savedServer;
    loginServer.value = savedServer;
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

  log('Application initialized', 'info');
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
  authStatus.textContent = `Logged in as ${currentUsername}`;
  authStatus.classList.add('logged-in');
}

function showAuthSection() {
  authSection.style.display = 'block';
  mainContent.style.display = 'none';
  loginBtn.style.display = 'block';
  logoutBtn.style.display = 'none';
  authStatus.textContent = 'Not logged in';
  authStatus.classList.remove('logged-in');
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

// Start upload
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

  isUploading = true;
  shouldStop = false;
  startBtn.disabled = true;
  stopBtn.disabled = false;

  const hostname = hostnameInput.value;
  const ipAddress = ipAddressInput.value;

  log('Starting file scan...', 'info');

  // Scan files
  const scanResult = await electronAPI.scanFiles(selectedPath, excludePatterns);

  if (!scanResult.success) {
    log(`Error scanning files: ${scanResult.error}`, 'error');
    resetUploadState();
    return;
  }

  const files = scanResult.files;
  const total = files.length;

  log(`Found ${total} files to process`, 'info');

  if (total === 0) {
    log('No files to upload', 'warning');
    resetUploadState();
    return;
  }

  let current = 0;
  let success = 0;
  let failed = 0;

  // Process files
  for (const filePath of files) {
    if (shouldStop) {
      log('Upload cancelled by user', 'warning');
      break;
    }

    // Process file
    const processResult = await electronAPI.processFile(filePath, hostname, ipAddress);

    if (!processResult.success) {
      log(`Error processing ${filePath}: ${processResult.error}`, 'error');
      failed++;
      current++;
      updateProgress(current, total, success, failed);
      continue;
    }

    // Upload metadata
    const uploadResult = await electronAPI.uploadMetadata(
      processResult.metadata,
      serverUrl,
      accessToken!
    );

    if (uploadResult.success) {
      const fileName = filePath.split(/[/\\]/).pop();
      log(`✓ Uploaded: ${fileName}`, 'success');
      success++;
    } else {
      const fileName = filePath.split(/[/\\]/).pop();
      log(`✗ Failed to upload ${fileName}: ${uploadResult.error}`, 'error');
      failed++;
    }

    current++;
    updateProgress(current, total, success, failed);
  }

  // Summary
  log('---', 'info');
  log(`Upload complete: ${success} uploaded, ${failed} failed, ${current} total`, 'info');

  resetUploadState();
}

function resetUploadState() {
  isUploading = false;
  shouldStop = false;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  progressText.textContent = 'Ready';
  progressFill.style.width = '0%';
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
