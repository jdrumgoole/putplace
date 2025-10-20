# PyPI Publishing Setup Guide

This guide explains how to set up GitHub Actions for automated publishing to PyPI and TestPyPI.

## Overview

Two GitHub Actions workflows are configured:

- **`publish-testpypi.yml`** - Publishes to TestPyPI (for testing)
- **`publish-pypi.yml`** - Publishes to production PyPI (on version tags)

## Prerequisites

You need API tokens from both PyPI and TestPyPI.

### 1. Create TestPyPI Account and API Token

1. **Create account**: https://test.pypi.org/account/register/
2. **Verify email**: Check your email and verify the account
3. **Create API token**:
   - Go to: https://test.pypi.org/manage/account/token/
   - Click "Add API token"
   - Token name: `putplace-github-actions`
   - Scope: "Entire account" (or specific to putplace project)
   - Click "Add token"
   - **⚠️ COPY THE TOKEN NOW** - You won't see it again!

### 2. Create PyPI Account and API Token

1. **Create account**: https://pypi.org/account/register/
2. **Verify email**: Check your email and verify the account
3. **Create API token**:
   - Go to: https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Token name: `putplace-github-actions`
   - Scope: "Entire account" (or specific to putplace project)
   - Click "Add token"
   - **⚠️ COPY THE TOKEN NOW** - You won't see it again!

## Configure GitHub Secrets

1. **Go to GitHub repository settings**:
   - Navigate to: https://github.com/jdrumgoole/putplace/settings/secrets/actions

2. **Add TEST_PYPI_API_TOKEN secret**:
   - Click "New repository secret"
   - Name: `TEST_PYPI_API_TOKEN`
   - Value: Paste the TestPyPI token (starts with `pypi-`)
   - Click "Add secret"

3. **Add PYPI_API_TOKEN secret**:
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: Paste the PyPI token (starts with `pypi-`)
   - Click "Add secret"

## Usage

### Publishing to TestPyPI (Testing)

**Method 1: Manual trigger via GitHub UI**

1. Go to: https://github.com/jdrumgoole/putplace/actions/workflows/publish-testpypi.yml
2. Click "Run workflow"
3. Select branch (usually `main`)
4. Click "Run workflow"

**Method 2: Trigger on push (optional)**

Uncomment the `push` trigger in `publish-testpypi.yml`:

```yaml
on:
  workflow_dispatch:
  push:
    branches:
      - main
```

This will publish to TestPyPI on every push to main (useful for testing).

**Method 3: Use invoke command**

```bash
invoke publish-test
```

### Publishing to Production PyPI

**⚠️ IMPORTANT: Only publish to production when ready for a real release!**

The production workflow is triggered by **version tags only**:

```bash
# Ensure version is updated in pyproject.toml
# Example: version = "0.4.0"

# Create and push a version tag
git tag -a v0.4.0 -m "Release version 0.4.0"
git push origin v0.4.0
```

The workflow will:
1. Verify the tag version matches `pyproject.toml`
2. Build the package
3. Publish to PyPI automatically

**Manual trigger** is also available (use with caution):
1. Go to: https://github.com/jdrumgoole/putplace/actions/workflows/publish-pypi.yml
2. Click "Run workflow"

## Verifying Publications

### After TestPyPI Publication

```bash
# View the package
open https://test.pypi.org/project/putplace/

# Test installation
pip install --index-url https://test.pypi.org/simple/ putplace

# Or with dependencies from PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple putplace
```

### After PyPI Publication

```bash
# View the package
open https://pypi.org/project/putplace/

# Install
pip install putplace

# Verify version
python -c "import putplace; print(putplace.__version__)"
```

## Workflow Details

### TestPyPI Workflow (`publish-testpypi.yml`)

- **Trigger**: Manual via workflow_dispatch
- **Builds**: Package using `python -m build`
- **Checks**: Validates package with `twine check`
- **Publishes**: To test.pypi.org
- **Skip existing**: Yes (won't fail if version exists)

### PyPI Workflow (`publish-pypi.yml`)

- **Trigger**: Git tags matching `v*` (e.g., `v0.4.0`)
- **Version check**: Ensures tag matches `pyproject.toml`
- **Builds**: Package using `python -m build`
- **Checks**: Validates package with `twine check`
- **Publishes**: To pypi.org

## Release Workflow Example

Complete workflow for releasing a new version:

```bash
# 1. Update version in pyproject.toml
# Edit: version = "0.4.0"

# 2. Update version in src/putplace/version.py (if exists)
# Edit: __version__ = "0.4.0"

# 3. Update CHANGELOG.md (if exists)
# Add release notes

# 4. Commit version bump
git add pyproject.toml src/putplace/version.py CHANGELOG.md
git commit -m "Bump version to 0.4.0"

# 5. Push to main
git push origin main

# 6. Test with TestPyPI first (optional but recommended)
invoke publish-test

# 7. Create and push version tag
git tag -a v0.4.0 -m "Release version 0.4.0"
git push origin v0.4.0

# 8. GitHub Actions will automatically publish to PyPI

# 9. Verify publication
open https://pypi.org/project/putplace/

# 10. Create GitHub release (optional)
# Go to: https://github.com/jdrumgoole/putplace/releases/new
# - Tag: v0.4.0
# - Release title: "PutPlace v0.4.0"
# - Description: Copy from CHANGELOG.md
```

## Troubleshooting

### Error: "Invalid or non-existent authentication information"

**Problem**: GitHub secret not configured correctly

**Solution**:
1. Check secret name matches exactly: `TEST_PYPI_API_TOKEN` or `PYPI_API_TOKEN`
2. Regenerate API token and update secret
3. Ensure token has correct scope

### Error: "File already exists"

**Problem**: Version already published to PyPI

**Solution**:
1. Increment version in `pyproject.toml`
2. Create new tag with new version
3. PyPI doesn't allow replacing existing versions (immutable)

### Error: "Version mismatch"

**Problem**: Git tag version doesn't match `pyproject.toml`

**Solution**:
1. Check version in `pyproject.toml`: `grep version pyproject.toml`
2. Delete incorrect tag: `git tag -d v0.4.0 && git push origin :refs/tags/v0.4.0`
3. Fix version and create new tag

### Error: "Package build failed"

**Problem**: Build process error

**Solution**:
1. Test build locally: `python -m build`
2. Check `pyproject.toml` configuration
3. Ensure all required files are committed
4. Check GitHub Actions logs for details

## Security Best Practices

1. **Never commit API tokens** to the repository
2. **Use GitHub Secrets** for all sensitive credentials
3. **Scope tokens** to specific projects when possible
4. **Rotate tokens** periodically
5. **Review workflow logs** for any exposed secrets (GitHub auto-redacts them)
6. **Enable 2FA** on PyPI and TestPyPI accounts

## Alternative: Local Publishing

If you prefer to publish manually from your machine:

```bash
# TestPyPI
invoke publish-test

# Production PyPI
invoke publish
```

These commands are configured in `tasks.py` and use your local credentials from `~/.pypirc`.

## Further Reading

- **PyPI Help**: https://pypi.org/help/
- **TestPyPI**: https://test.pypi.org/
- **GitHub Actions**: https://docs.github.com/en/actions
- **PyPA Publish Action**: https://github.com/pypa/gh-action-pypi-publish
- **Python Packaging Guide**: https://packaging.python.org/

## Need Help?

- **GitHub Issues**: https://github.com/jdrumgoole/putplace/issues
- **PyPI Support**: https://pypi.org/help/#support
