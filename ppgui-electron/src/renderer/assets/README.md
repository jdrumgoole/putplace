# Renderer Assets Directory

This directory contains static assets for the Electron renderer process (UI).

## Directory Purpose

Assets placed here are bundled with the Electron application and displayed in the client interface.

## Usage in HTML

```html
<!-- In src/renderer/index.html -->
<img src="assets/putplace-logo.png" alt="PutPlace">
```

## Build Process

Assets are copied to `dist/renderer/assets/` during the build process.

Update `package.json` build script to include:

```json
"build": "tsc && mkdir -p dist/renderer/assets && cp src/renderer/*.html dist/renderer/ && cp src/renderer/*.css dist/renderer/ && cp -r src/renderer/assets dist/renderer/"
```

## Recommended Files

- `putplace-logo.png` - Application logo
- `putplace-icon.png` - Small icon for UI elements
- `google-logo.svg` - Google Sign-In button icon (if customizing)
- Other UI images and icons
