# PutPlace Documentation

This directory contains the complete documentation for PutPlace in Markdown format using the MyST parser for Sphinx.

## Documentation Structure

```
docs/
├── index.md                    # Main documentation index
├── installation.md             # Installation guide
├── quickstart.md               # Quick start guide (5 minutes)
├── CLIENT_QUICKSTART.md        # Client quick start
├── configuration.md            # Configuration reference
├── client-guide.md             # Complete client guide
├── api-reference.md            # REST API documentation
├── FILE_UPLOAD_WORKFLOW.md     # File upload workflow
├── AUTHENTICATION.md           # Authentication guide
├── storage.md                  # Storage backends
├── deployment.md               # Production deployment
├── troubleshooting.md          # Troubleshooting guide
├── development.md              # Development guide
├── architecture.md             # System architecture
├── SECURITY.md                 # Security best practices (in parent dir)
├── conf.py                     # Sphinx configuration
├── requirements.txt            # Documentation dependencies
├── Makefile                    # Build commands
└── README.md                   # This file
```

## Building Documentation

### Prerequisites

Install documentation dependencies:

```bash
pip install -r docs/requirements.txt
```

### Build HTML Documentation

```bash
# Navigate to docs directory
cd docs

# Build HTML
make html

# View documentation
open _build/html/index.html  # macOS
xdg-open _build/html/index.html  # Linux
start _build/html/index.html  # Windows
```

### Live Rebuild (Development)

For automatic rebuilding during documentation development:

```bash
# Install sphinx-autobuild
pip install sphinx-autobuild

# Start live rebuild server
make livehtml

# Open browser to http://127.0.0.1:8000
```

Changes to documentation files will automatically trigger rebuilds and refresh the browser.

### Clean Build

```bash
make clean
make html
```

## Documentation Format

All documentation is written in **Markdown** using the **MyST** (Markedly Structured Text) parser.

### MyST Features

- Standard Markdown syntax
- Extended syntax for Sphinx directives
- Code blocks with syntax highlighting
- Cross-references between documents
- Table of contents generation

### Example MyST Syntax

**Code blocks:**
````markdown
```python
def hello():
    print("Hello, world!")
```
````

**Cross-references:**
```markdown
See [Configuration Guide](configuration.md) for details.
```

**Directives:**
```markdown
:::{note}
This is a note
:::
```

**Table of contents:**
```markdown
```{toctree}
:maxdepth: 2

installation
quickstart
```
```

## Contributing to Documentation

### Adding New Documentation

1. Create new `.md` file in `docs/`
2. Add to appropriate `toctree` in `index.md`
3. Follow existing documentation style
4. Build and verify

### Documentation Style Guide

- Use clear, concise language
- Include code examples
- Use headings hierarchically (# → ## → ###)
- Add links to related documentation
- Include troubleshooting sections where appropriate

### Documentation Checklist

When adding new features:

- [ ] Update relevant documentation files
- [ ] Add to API reference if needed
- [ ] Update configuration reference if needed
- [ ] Add examples
- [ ] Update table of contents in index.md
- [ ] Build and verify documentation

## Publishing Documentation

### GitHub Pages (Recommended)

```bash
# Install gh-pages
pip install ghp-import

# Build documentation
make html

# Publish to GitHub Pages
ghp-import -n -p -f _build/html
```

Documentation will be available at: https://jdrumgoole.github.io/putplace/

### Read the Docs

1. Sign up at https://readthedocs.org/
2. Import putplace repository
3. Configure build settings:
   - Requirements file: `docs/requirements.txt`
   - Configuration file: `docs/conf.py`
4. Documentation will auto-build on commits

## Viewing Documentation

### Online

- **GitHub Pages**: https://jdrumgoole.github.io/putplace/ (after publishing)
- **Read the Docs**: https://putplace.readthedocs.io/ (after setup)

### Locally

```bash
# Build and open
cd docs
make html
open _build/html/index.html
```

### API Documentation

FastAPI provides automatic interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Documentation Versions

Documentation is maintained in Markdown format in the main repository. For versioned documentation:

1. Tag releases: `git tag v0.2.0`
2. Read the Docs automatically builds docs for each tag
3. Users can select version from documentation

## Getting Help

- **Issues**: Report documentation issues at https://github.com/jdrumgoole/putplace/issues
- **Discussions**: Ask questions at https://github.com/jdrumgoole/putplace/discussions
- **Contributing**: See [Development Guide](development.md)

## Additional Resources

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
- [Read the Docs Guide](https://docs.readthedocs.io/)
- [GitHub Pages](https://pages.github.com/)
