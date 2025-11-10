# Logo Storage Guide for PutPlace

This guide documents where to store logos and static assets in the PutPlace project.

## Directory Structure

```
putplace/
├── src/putplace/static/          # Server-side static files (FastAPI)
│   ├── images/                   # Logos, icons, favicons
│   ├── css/                      # Stylesheets
│   └── js/                       # Client-side JavaScript
│
├── ppgui-electron/
│   ├── src/renderer/assets/      # Electron UI assets
│   │   └── (logos, images, icons)
│   └── build/                    # Electron app icons (create this)
│       ├── icon.icns             # macOS app icon
│       ├── icon.ico              # Windows app icon
│       └── icon.png              # Linux app icon (512x512)
│
└── docs/
    ├── images/                   # Documentation images
    └── _static/                  # Sphinx static assets (if using)
```

## 1. Server-Side Assets (FastAPI)

**Location:** `src/putplace/static/`

**Purpose:** Static files served by the FastAPI server

**Access URL:** `http://localhost:8000/static/<path>`

**Usage Example:**
```html
<img src="/static/images/putplace-logo.png" alt="PutPlace">
<link rel="icon" href="/static/images/favicon.ico">
```

**Configuration:**
- ✅ Automatically mounted in `src/putplace/main.py`
- ✅ Included in Python package via `pyproject.toml`
- ✅ Works when installed via pip

**Recommended Files:**
```
static/
├── images/
│   ├── putplace-logo.png         # Main logo (PNG with transparency)
│   ├── putplace-logo.svg         # Scalable vector logo
│   ├── favicon.ico               # Browser favicon (16x16, 32x32, 48x48)
│   └── icon-192.png              # PWA icon (if needed)
├── css/
│   └── custom.css                # Custom styles for web UI
└── js/
    └── app.js                    # Client-side JavaScript
```

## 2. Electron Client Assets

### 2a. Renderer Assets (UI Images)

**Location:** `ppgui-electron/src/renderer/assets/`

**Purpose:** Images and logos displayed in the Electron UI

**Usage Example:**
```html
<!-- In src/renderer/index.html -->
<img src="assets/putplace-logo.png" alt="PutPlace">
```

**Build Process:**
- Assets are copied to `dist/renderer/assets/` during build
- Build script updated in `package.json`

**Recommended Files:**
```
assets/
├── putplace-logo.png             # Application logo
├── putplace-icon.png             # Small UI icon
└── google-logo.svg               # Custom Google icon (optional)
```

### 2b. Application Icons (Installers)

**Location:** `ppgui-electron/build/` (create this directory)

**Purpose:** Icons for the installed application (dock, taskbar, installer)

**Create directory:**
```bash
mkdir -p ppgui-electron/build
```

**Required Files:**
```
build/
├── icon.icns                     # macOS dock icon (512x512 source)
├── icon.ico                      # Windows taskbar icon (256x256 source)
└── icon.png                      # Linux icon (512x512)
```

**Icon Generation:**
- Use a 1024x1024 PNG as source
- electron-builder automatically generates all sizes
- Tools: [iconutil](https://developer.apple.com/library/archive/documentation/GraphicsAnimation/Conceptual/HighResolutionOSX/Optimizing/Optimizing.html) (macOS), [png2icns](https://www.npmjs.com/package/png2icns), [electron-icon-builder](https://www.npmjs.com/package/electron-icon-builder)

## 3. Documentation Assets

**Location:** `docs/images/` or `docs/_static/`

**Purpose:** Images for README, documentation site

**Usage Example:**
```markdown
![PutPlace Logo](docs/images/putplace-logo.png)
```

**Recommended Files:**
```
docs/images/
├── putplace-logo.png             # Logo for README
├── architecture-diagram.png      # Architecture diagrams
└── screenshots/                  # Application screenshots
```

## Quick Reference Table

| Use Case | Location | Access Method | Packaged? |
|----------|----------|---------------|-----------|
| **FastAPI web UI** | `src/putplace/static/images/` | `/static/images/logo.png` | ✅ Yes (pip package) |
| **Electron UI elements** | `ppgui-electron/src/renderer/assets/` | `assets/logo.png` | ✅ Yes (Electron build) |
| **Electron app icon** | `ppgui-electron/build/` | Auto-detected by electron-builder | ✅ Yes (installer) |
| **Documentation** | `docs/images/` | Markdown: `![](docs/images/logo.png)` | ✅ Yes (git) |

## Adding New Logos

### For FastAPI Server:

1. Place logo in `src/putplace/static/images/`
2. Reference in HTML: `/static/images/your-logo.png`
3. No restart needed in development mode

### For Electron Client:

1. Place logo in `ppgui-electron/src/renderer/assets/`
2. Reference in HTML: `assets/your-logo.png`
3. Rebuild: `cd ppgui-electron && npm run build`

### For App Icons:

1. Create 1024x1024 PNG logo
2. Generate platform icons:
   ```bash
   # macOS
   iconutil -c icns icon.iconset -o ppgui-electron/build/icon.icns

   # Or use electron-icon-builder
   npm install -g electron-icon-builder
   electron-icon-builder --input=./logo.png --output=./ppgui-electron/build
   ```
3. electron-builder will use them automatically during packaging

## Current Setup Status

✅ **Completed:**
- Server static directory created: `src/putplace/static/`
- Static files mounted in FastAPI (`main.py:338-341`)
- Package configuration updated (`pyproject.toml:71-72`)
- Electron assets directory created: `ppgui-electron/src/renderer/assets/`
- Electron build script updated to copy assets

❌ **TODO:**
- Add actual logo files (currently empty directories)
- Create `ppgui-electron/build/` directory for app icons
- Generate app icons from logo source

## File Format Recommendations

### Logos
- **SVG** - Preferred for logos (scalable, small file size)
- **PNG** - With transparency, multiple sizes (256x256, 512x512)
- **Avoid JPG** - No transparency support

### Favicons
- **ICO** - Multi-size (16x16, 32x32, 48x48)
- **PNG** - Alternative modern browsers support PNG favicons

### App Icons
- **PNG** - 1024x1024 source for all platforms
- **ICNS** - macOS (generated from PNG)
- **ICO** - Windows (generated from PNG)

## Testing Static Files

### Test Server Static Files:

```bash
# Start server
invoke quickstart

# Visit in browser
open http://localhost:8000/static/images/putplace-logo.png

# Or test with curl
curl -I http://localhost:8000/static/images/putplace-logo.png
```

### Test Electron Assets:

```bash
# Build and run
cd ppgui-electron
npm run build
npm start

# Check DevTools Console for asset loading errors
```

## See Also

- [src/putplace/static/README.md](src/putplace/static/README.md) - Server static files
- [ppgui-electron/src/renderer/assets/README.md](ppgui-electron/src/renderer/assets/README.md) - Electron assets
- [Electron Builder Icons](https://www.electron.build/icons) - Icon requirements
- [FastAPI Static Files](https://fastapi.tiangolo.com/tutorial/static-files/) - Official docs
