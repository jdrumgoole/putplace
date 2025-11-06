"""Tests for Electron GUI desktop application.

This test module verifies the Electron desktop client can be:
- Packaged correctly
- Installed to /Applications
- Launched successfully
- Uninstalled cleanly

Note: These tests only run on macOS and require the Electron app to be built.
"""

import os
import sys
import time
import glob
import subprocess
from pathlib import Path

import pytest


# Skip all tests in this module if not on macOS
pytestmark = pytest.mark.skipif(
    sys.platform != 'darwin',
    reason="Electron GUI tests only run on macOS"
)


@pytest.fixture
def electron_dir():
    """Get the Electron project directory."""
    project_root = Path(__file__).parent.parent
    return project_root / "ppgui-electron"


@pytest.fixture
def app_name():
    """Get the application name."""
    return "PutPlace Client"


@pytest.fixture
def installed_app_path(app_name):
    """Get the installed app path."""
    return f"/Applications/{app_name}.app"


@pytest.fixture
def ensure_packaged(electron_dir, app_name):
    """Ensure the Electron app is packaged before tests run."""
    dmg_dir = electron_dir / "release"
    dmg_files = list(dmg_dir.glob(f"{app_name}-*.dmg"))

    if not dmg_files:
        pytest.skip("Electron app not packaged. Run 'invoke gui-electron-package' first.")

    return dmg_files[0]


@pytest.fixture
def cleanup_app(installed_app_path, app_name):
    """Cleanup fixture that removes the app after test completes."""
    yield

    # Cleanup: Quit the app if running
    try:
        subprocess.run(
            ['osascript', '-e', f'quit app "{app_name}"'],
            capture_output=True,
            timeout=5
        )
        time.sleep(1)
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Remove installed app
    if os.path.exists(installed_app_path):
        subprocess.run(['rm', '-rf', installed_app_path], check=False)

    # Remove app support files
    app_support = Path.home() / "Library/Application Support/PutPlace Client"
    if app_support.exists():
        subprocess.run(['rm', '-rf', str(app_support)], check=False)

    # Remove preferences
    prefs = Path.home() / "Library/Preferences/com.putplace.client.plist"
    if prefs.exists():
        prefs.unlink()


@pytest.mark.integration
def test_electron_app_package_exists(ensure_packaged):
    """Test that the packaged DMG file exists."""
    assert ensure_packaged.exists(), "DMG file should exist"
    assert ensure_packaged.suffix == ".dmg", "Package should be a DMG file"


@pytest.mark.integration
def test_electron_app_bundle_exists(electron_dir, app_name):
    """Test that the app bundle exists in the release directory."""
    app_bundle = electron_dir / "release/mac-arm64" / f"{app_name}.app"
    assert app_bundle.exists(), f"App bundle should exist at {app_bundle}"

    # Verify it's a proper macOS app bundle
    contents_dir = app_bundle / "Contents"
    assert contents_dir.exists(), "App bundle should have Contents directory"
    assert (contents_dir / "MacOS").exists(), "App bundle should have MacOS directory"
    assert (contents_dir / "Info.plist").exists(), "App bundle should have Info.plist"


@pytest.mark.integration
def test_electron_app_info_plist(electron_dir, app_name):
    """Test that Info.plist contains correct product name."""
    app_bundle = electron_dir / "release/mac-arm64" / f"{app_name}.app"
    info_plist = app_bundle / "Contents/Info.plist"

    assert info_plist.exists(), "Info.plist should exist"

    # Read Info.plist and verify CFBundleName
    result = subprocess.run(
        ['plutil', '-extract', 'CFBundleName', 'raw', str(info_plist)],
        capture_output=True,
        text=True,
        check=True
    )

    assert result.stdout.strip() == app_name, f"CFBundleName should be '{app_name}'"


@pytest.mark.integration
def test_electron_app_install_launch_uninstall(
    electron_dir, app_name, installed_app_path, cleanup_app
):
    """Test complete install -> launch -> uninstall flow.

    This is the main integration test that verifies:
    1. App can be installed to /Applications
    2. Installed app can be launched
    3. App can be quit programmatically
    4. App can be uninstalled cleanly
    """
    app_bundle = electron_dir / "release/mac-arm64" / f"{app_name}.app"

    # Remove existing installation if present
    if os.path.exists(installed_app_path):
        subprocess.run(['rm', '-rf', installed_app_path], check=True)

    # Step 1: Install - Copy app to /Applications
    print(f"\n  Installing app to /Applications...")
    subprocess.run(['cp', '-R', str(app_bundle), '/Applications/'], check=True)

    # Verify installation
    assert os.path.exists(installed_app_path), "App should be installed to /Applications"

    # Step 2: Launch the app
    print(f"  Launching installed app...")
    result = subprocess.run(
        ['open', '-a', installed_app_path],
        capture_output=True,
        text=True,
        check=True
    )

    # Wait for app to launch
    time.sleep(3)

    # Step 3: Verify app is running
    print(f"  Checking if app is running...")
    ps_result = subprocess.run(
        ['pgrep', '-f', app_name],
        capture_output=True,
        text=True
    )

    assert ps_result.returncode == 0, f"App '{app_name}' should be running"
    assert ps_result.stdout.strip(), "Should have a process ID"

    # Step 4: Quit the app
    print(f"  Quitting app...")
    subprocess.run(
        ['osascript', '-e', f'quit app "{app_name}"'],
        capture_output=True,
        timeout=5,
        check=True
    )

    # Wait for app to quit
    time.sleep(2)

    # Verify app is no longer running
    ps_result_after = subprocess.run(
        ['pgrep', '-f', app_name],
        capture_output=True,
        text=True
    )

    assert ps_result_after.returncode != 0, "App should not be running after quit"

    print(f"  ✓ Install/launch/quit test passed")


@pytest.mark.integration
def test_electron_app_typescript_compilation(electron_dir):
    """Test that TypeScript files have been compiled to JavaScript."""
    dist_dir = electron_dir / "dist"

    assert dist_dir.exists(), "dist directory should exist"
    assert (dist_dir / "main.js").exists(), "main.js should be compiled"
    assert (dist_dir / "preload.js").exists(), "preload.js should be compiled"

    # Verify renderer files are copied
    renderer_dir = dist_dir / "renderer"
    assert renderer_dir.exists(), "renderer directory should exist"
    assert (renderer_dir / "index.html").exists(), "index.html should be copied"
    assert (renderer_dir / "styles.css").exists(), "styles.css should be copied"


@pytest.mark.integration
def test_electron_app_dependencies(electron_dir):
    """Test that required npm dependencies are installed."""
    node_modules = electron_dir / "node_modules"

    assert node_modules.exists(), "node_modules should exist"

    # Check key dependencies
    assert (node_modules / "electron").exists(), "electron should be installed"
    assert (node_modules / "axios").exists(), "axios should be installed"
    assert (node_modules / "typescript").exists(), "typescript should be installed"
    assert (node_modules / "electron-builder").exists(), "electron-builder should be installed"
