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
});
