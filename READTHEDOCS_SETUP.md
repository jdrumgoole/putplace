# ReadTheDocs Setup Guide

## The Issue

ReadTheDocs is trying to fetch a branch called `latest`:

```bash
git fetch origin --force --prune --prune-tags --depth 50 refs/heads/latest:refs/remotes/origin/latest
```

But this repository uses `main` as the default branch, not `latest`.

## Solution

You need to configure ReadTheDocs to track the `main` branch.

### Step-by-Step Instructions

1. **Go to ReadTheDocs Dashboard**
   - Visit: https://readthedocs.org/dashboard/
   - Sign in with your GitHub account if needed

2. **Select Your Project**
   - Click on "putplace" from your projects list

3. **Navigate to Versions**
   - Click "Admin" in the project menu
   - Click "Versions" in the left sidebar

4. **Configure the "latest" Version**
   - Find "latest" in the versions list
   - Click the "Edit" button next to it
   - Change the branch from `latest` to `main`
   - Save changes

5. **Activate the "main" Branch** (Alternative)
   - Find "main" in the versions list
   - Click "Activate" if it's not already active
   - Set it as the "Default version"

6. **Trigger a Build**
   - Go to "Builds" tab
   - Click "Build Version: latest"
   - Or push a new commit to trigger automatic build

### What the .readthedocs.yaml Does

The `.readthedocs.yaml` file in the repository root configures:
- Build environment (Python 3.11, Ubuntu 22.04)
- Documentation builder (Sphinx)
- Dependencies to install
- Output formats (HTML, PDF, ePub)

However, it **does NOT** control which branch the "latest" version tracks. That's configured in the ReadTheDocs dashboard.

## Expected Behavior After Fix

After configuring correctly:
- ReadTheDocs will fetch from `refs/heads/main`
- The "latest" documentation will build from the `main` branch
- Documentation will be available at: https://putplace.readthedocs.io/en/latest/

## Verifying the Fix

After configuration:

```bash
# Push your latest changes
git push origin main

# Wait 1-2 minutes, then check:
curl -I https://putplace.readthedocs.io/en/latest/
```

You should see `HTTP/2 200` indicating the documentation is available.

## Alternative: Use Semantic Versioning

Instead of relying on "latest", you can use version tags:

```bash
# Create a version tag
git tag -a v0.4.0 -m "Version 0.4.0"
git push origin v0.4.0
```

ReadTheDocs will automatically build documentation for each tag, making them available at URLs like:
- https://putplace.readthedocs.io/en/v0.4.0/
- https://putplace.readthedocs.io/en/stable/ (latest stable release)

## Common ReadTheDocs Issues

### Build Fails with Import Errors

**Problem**: Can't import `putplace` module

**Solution**: The `.readthedocs.yaml` installs the package with:
```yaml
python:
  install:
    - method: pip
      path: .
```

This installs the package in editable mode from the repository root.

### Sphinx Build Warnings

**Problem**: Warnings about missing references

**Solution**: Set `fail_on_warning: false` in `.readthedocs.yaml`:
```yaml
sphinx:
  configuration: docs/conf.py
  fail_on_warning: false
```

### Missing Dependencies

**Problem**: Build fails because of missing Python packages

**Solution**: Ensure all doc dependencies are in `docs/requirements.txt`:
```txt
sphinx>=7.2.0
sphinx-rtd-theme>=2.0.0
myst-parser>=2.0.0
sphinx-autodoc-typehints>=1.25.0
```

## Need Help?

- **ReadTheDocs Docs**: https://docs.readthedocs.io/
- **Build Logs**: Check the build logs in the ReadTheDocs dashboard for detailed errors
- **GitHub Issues**: https://github.com/jdrumgoole/putplace/issues
