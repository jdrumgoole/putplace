# Static Files Directory

This directory contains static assets served by the PutPlace FastAPI server.

## Directory Structure

```
static/
├── images/     # Logos, icons, and images
├── css/        # Stylesheets
└── js/         # Client-side JavaScript
```

## Usage

Static files are automatically mounted at `/static/` when the server starts.

### In HTML Templates

```html
<!-- Logo -->
<img src="/static/images/putplace-logo.png" alt="PutPlace">

<!-- Favicon -->
<link rel="icon" href="/static/images/favicon.ico">

<!-- Stylesheet -->
<link rel="stylesheet" href="/static/css/styles.css">

<!-- JavaScript -->
<script src="/static/js/app.js"></script>
```

### In API Responses

```python
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <link rel="icon" href="/static/images/favicon.ico">
        </head>
        <body>
            <img src="/static/images/putplace-logo.png">
        </body>
    </html>
    """
```

## Adding Files

1. Place files in the appropriate subdirectory
2. Reference them using `/static/<subdirectory>/<filename>`
3. No server restart needed (in development mode)

## Recommended Image Formats

- **Logos**: SVG (scalable) or PNG (with transparency)
- **Favicon**: ICO or PNG (16x16, 32x32, 48x48)
- **Icons**: SVG or PNG

## Package Distribution

These static files are included in the Python package distribution via `pyproject.toml` configuration.
