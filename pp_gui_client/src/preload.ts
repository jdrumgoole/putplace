import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  getSystemInfo: () => ipcRenderer.invoke('get-system-info'),
  getCpuCount: () => ipcRenderer.invoke('get-cpu-count'),
  scanFiles: (dirPath: string, excludePatterns: string[]) =>
    ipcRenderer.invoke('scan-files', dirPath, excludePatterns),
  processFile: (filePath: string, hostname: string, ipAddress: string) =>
    ipcRenderer.invoke('process-file', filePath, hostname, ipAddress),
  login: (username: string, password: string, serverUrl: string) =>
    ipcRenderer.invoke('login', username, password, serverUrl),
  register: (username: string, email: string, password: string, fullName: string | null, serverUrl: string) =>
    ipcRenderer.invoke('register', username, email, password, fullName, serverUrl),
  uploadMetadata: (metadata: any, serverUrl: string, token: string) =>
    ipcRenderer.invoke('upload-metadata', metadata, serverUrl, token),
  uploadFileContent: (filePath: string, sha256: string, hostname: string, serverUrl: string, token: string) =>
    ipcRenderer.invoke('upload-file-content', filePath, sha256, hostname, serverUrl, token),
  onUploadProgress: (callback: (progress: { fileName: string; filePath: string; loaded: number; total: number; percentage: number }) => void) => {
    ipcRenderer.on('upload-progress', (_event, progress) => callback(progress));
  },
  removeUploadProgressListener: () => {
    ipcRenderer.removeAllListeners('upload-progress');
  },

  // ===== PPassist Daemon API =====
  ppassistCheck: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-check', daemonUrl),
  ppassistStart: () =>
    ipcRenderer.invoke('ppassist-start'),
  ppassistStatus: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-status', daemonUrl),
  ppassistFileStats: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-file-stats', daemonUrl),
  ppassistSha256Status: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-sha256-status', daemonUrl),
  ppassistQueueStatus: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-queue-status', daemonUrl),
  ppassistListPaths: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-list-paths', daemonUrl),
  ppassistRegisterPath: (path: string, recursive: boolean, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-register-path', path, recursive, daemonUrl),
  ppassistDeletePath: (pathId: number, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-delete-path', pathId, daemonUrl),
  ppassistScanPath: (pathId: number, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-scan-path', pathId, daemonUrl),
  ppassistScanAll: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-scan-all', daemonUrl),
  ppassistListExcludes: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-list-excludes', daemonUrl),
  ppassistAddExclude: (pattern: string, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-add-exclude', pattern, daemonUrl),
  ppassistDeleteExclude: (excludeId: number, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-delete-exclude', excludeId, daemonUrl),
  ppassistTriggerUploads: (uploadContent: boolean, pathPrefix?: string, limit?: number, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-trigger-uploads', uploadContent, pathPrefix, limit, daemonUrl),
  ppassistAddServer: (name: string, url: string, username: string, password: string, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-add-server', name, url, username, password, daemonUrl),
  ppassistListServers: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-list-servers', daemonUrl),
  ppassistGetActivity: (limit?: number, sinceId?: number, eventType?: string, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-get-activity', limit, sinceId, eventType, daemonUrl),
  ppassistGetConfig: (daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-get-config', daemonUrl),
  ppassistSaveConfig: (config: any, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-save-config', config, daemonUrl),
  checkConfigExists: () =>
    ipcRenderer.invoke('check-config-exists'),
  ppassistGetFileByPath: (filePath: string, daemonUrl?: string) =>
    ipcRenderer.invoke('ppassist-get-file-by-path', filePath, daemonUrl),
});
