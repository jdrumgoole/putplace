# PutPlace Logo Usage

## Logo File

- **File:** `putplace-logo.svg`
- **Type:** SVG (Scalable Vector Graphics)
- **Dimensions:** 400x150 pixels (viewBox)
- **Background:** White (#ffffff)
- **Text Color:** Dark blue-gray (#2C3E50)
- **Font:** Heavy rounded (900 weight)

## Usage in Server (FastAPI)

### In HTML Responses

```html
<!-- Standard usage -->
<img src="/static/images/putplace-logo.svg" alt="PutPlace" width="200">

<!-- In header -->
<header>
  <img src="/static/images/putplace-logo.svg" alt="PutPlace" height="50">
  <h1>PutPlace</h1>
</header>
```

### Direct URL Access

```
http://localhost:8000/static/images/putplace-logo.svg
```

### In API Documentation (Swagger/ReDoc)

Add to FastAPI app configuration in `main.py`:

```python
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    openapi_tags=[...],
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
    },
    # Add logo to docs
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Customize docs with logo
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>PutPlace API</title>
            <link rel="icon" href="/static/images/putplace-logo.svg">
        </head>
        <body>
            <img src="/static/images/putplace-logo.svg" alt="PutPlace">
        </body>
    </html>
    """
```

## Logo Specifications

### Current Logo
- **Text:** "putplace" (lowercase)
- **Style:** Heavy rounded font (900 weight)
- **Stroke:** 1px outline for extra boldness
- **Letter spacing:** -1px (tight spacing)

### Transparent Background Version

To create a transparent version (recommended for overlays):

1. Edit the SVG file
2. Remove or comment out the `<rect>` element on line 4:
   ```xml
   <!-- <rect width="400" height="150" fill="#ffffff" /> -->
   ```
3. Save as `putplace-logo-transparent.svg`

### PNG Export (if needed)

To convert SVG to PNG for compatibility:

```bash
# Using ImageMagick
convert -density 300 -background white putplace-logo.svg putplace-logo.png

# Or using Inkscape
inkscape putplace-logo.svg --export-filename=putplace-logo.png --export-width=800
```

## Responsive Usage

```html
<!-- Scales with container -->
<div style="max-width: 400px;">
  <img src="/static/images/putplace-logo.svg"
       alt="PutPlace"
       style="width: 100%; height: auto;">
</div>

<!-- Fixed height, auto width -->
<img src="/static/images/putplace-logo.svg"
     alt="PutPlace"
     style="height: 60px; width: auto;">
```

## CSS Styling

```css
.logo {
  width: 200px;
  height: auto;
  display: block;
  margin: 0 auto;
}

.logo-small {
  height: 40px;
  width: auto;
}

.logo-large {
  width: 100%;
  max-width: 600px;
  height: auto;
}
```

## Locations

This logo is stored in multiple locations:

1. **Server:** `src/putplace/static/images/putplace-logo.svg`
   - Access: `http://localhost:8000/static/images/putplace-logo.svg`

2. **Electron Client:** `ppgui-electron/src/renderer/assets/putplace-logo.svg`
   - Access: `assets/putplace-logo.svg` (in HTML)

3. **Docs:** Copy to `docs/images/` for README usage

## See Also

- [LOGO_STORAGE_GUIDE.md](../../../LOGO_STORAGE_GUIDE.md) - Complete storage guide
- [static/README.md](../README.md) - Static files documentation
