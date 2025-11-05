# PutPlace GUI - Electron Desktop App

A cross-platform desktop application for the PutPlace file metadata management system, built with Electron and TypeScript.

## Features

- **Directory Selection**: Browse and select directories to scan
- **File Scanning**: Recursive directory scanning with exclude pattern support
- **SHA256 Hashing**: Automatic calculation of file hashes
- **Metadata Upload**: Send file metadata to PutPlace server
- **Progress Tracking**: Real-time progress bars and statistics
- **Logging**: Detailed logging with color-coded messages
- **Settings Persistence**: Saves server URL, API key, and exclude patterns
- **System Detection**: Auto-detects hostname and IP address

## Prerequisites

- Node.js 16+ and npm
- Running PutPlace server (see main project README)
- API key from PutPlace server

## Installation

```bash
cd ppgui-electron
npm install
```

## Development

Build and run in development mode (with DevTools):

```bash
npm run dev
```

## Production Build

Build the application:

```bash
npm run build
```

Run the built application:

```bash
npm start
```

## Package for Distribution

Create distributable packages:

```bash
npm run package
```

This will create platform-specific installers in the `dist` directory.

## Usage

1. **Select Directory**: Click "Select Directory" to choose a folder to scan
2. **Configure Settings**:
   - Enter your PutPlace server URL (default: `http://localhost:8000/put_file`)
   - Enter your API key (required)
   - Hostname and IP address are auto-detected
3. **Add Exclude Patterns** (optional):
   - Add patterns like `.git`, `*.log`, `node_modules`
   - Supports wildcards and directory names
4. **Start Upload**: Click "Start Upload" to begin processing files
5. **Monitor Progress**: View real-time progress and logs

## Exclude Patterns

Exclude patterns support:
- Exact matches: `.git`, `__pycache__`
- Wildcards: `*.log`, `test_*`
- Directory names: `node_modules`, `dist`

## Architecture

- **Main Process** (`main.ts`): Electron main process, handles file operations and IPC
- **Preload Script** (`preload.ts`): Secure bridge between main and renderer processes
- **Renderer Process** (`renderer.ts`): UI logic and user interactions
- **HTML/CSS**: Modern, responsive interface

## Security

- Context isolation enabled
- Node integration disabled in renderer
- IPC communication via contextBridge
- API keys stored in localStorage (consider more secure options for production)

## Project Structure

```
ppgui-electron/
├── src/
│   ├── main.ts           # Main Electron process
│   ├── preload.ts        # Preload script (IPC bridge)
│   └── renderer/
│       ├── index.html    # UI structure
│       ├── styles.css    # UI styles
│       └── renderer.ts   # UI logic
├── dist/                 # Compiled output
├── package.json
├── tsconfig.json
└── README.md
```

## License

Same as main PutPlace project (see LICENSE in root directory)
