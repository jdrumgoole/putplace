"""Electron GUI tasks for PutPlace Client.

This module contains tasks for building, packaging, and running the
Electron-based desktop GUI client.
"""

from invoke import task


@task
def pp_gui_build(c):
    """Build the Electron GUI desktop app.

    Builds the TypeScript source files and copies assets to dist directory.
    The Electron app provides a modern cross-platform desktop interface.

    Requirements:
        - Node.js and npm must be installed
        - Run from project root directory
    """
    import os
    electron_dir = "pp_gui_client"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        print("Make sure you're running from the project root directory")
        return

    print("🔨 Building Electron GUI app...")
    with c.cd(electron_dir):
        # Check if node_modules exists
        if not os.path.exists(f"{electron_dir}/node_modules"):
            print("📦 Installing npm dependencies...")
            c.run("npm install")

        print("🔧 Compiling TypeScript and copying assets...")
        c.run("npm run build")

    print("✓ Electron GUI build complete!")
    print(f"  Build output: {electron_dir}/dist/")


@task
def pp_gui_package(c):
    """Package the Electron GUI app into a distributable .app bundle.

    Creates a properly signed macOS application with correct menu names.
    Output will be in pp_gui_client/release/ directory.

    Requirements:
        - Node.js and npm must be installed
        - electron-builder package installed
    """
    import os
    electron_dir = "pp_gui_client"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        return

    print("📦 Packaging Electron GUI app...")
    with c.cd(electron_dir):
        # Check if node_modules exists
        if not os.path.exists(f"{electron_dir}/node_modules"):
            print("📦 Installing npm dependencies...")
            c.run("npm install")

        print("🔧 Building and packaging app...")
        c.run("npm run package")

    print("✓ Packaging complete!")
    print(f"  macOS app: {electron_dir}/release/mac-arm64/PutPlace Client.app")
    print(f"  DMG installer: {electron_dir}/release/PutPlace Client-*.dmg")


@task
def pp_gui(c, dev=False, packaged=False):
    """Run the Electron GUI desktop app.

    Launches the cross-platform desktop application for PutPlace.

    Args:
        dev: Run in development mode with DevTools (default: False)
        packaged: Use packaged .app with correct menu names (default: False)

    Features:
        - Native directory picker
        - File scanning with exclude patterns
        - SHA256 hash calculation
        - Real-time progress tracking
        - JWT authentication
        - Settings persistence

    Requirements:
        - Node.js and npm must be installed
        - App will be built automatically if needed
    """
    import os
    import sys
    electron_dir = "pp_gui_client"

    if not os.path.exists(electron_dir):
        print(f"❌ Error: {electron_dir} directory not found")
        return

    # Use packaged app if requested (has correct menu names)
    if packaged and sys.platform == 'darwin':
        app_path = f"{electron_dir}/release/mac-arm64/PutPlace Client.app"

        if not os.path.exists(app_path):
            print("⚠️  Packaged app not found. Building package...")
            pp_gui_package(c)

        # Convert to absolute path for 'open' command
        abs_app_path = os.path.abspath(app_path)

        print("🚀 Launching PutPlace Client (packaged app)...")
        if dev:
            # Open with DevTools
            c.run(f'open "{abs_app_path}" --args --dev')
        else:
            c.run(f'open "{abs_app_path}"')
    else:
        # Development mode - build and run directly
        print("🔨 Building Electron app...")
        with c.cd(electron_dir):
            # Install dependencies if needed
            if not os.path.exists("node_modules"):
                print("📦 Installing dependencies...")
                c.run("npm install")

            # Build TypeScript files
            result = c.run("npm run build", warn=True, hide=True)
            if not result.ok:
                print("❌ Build failed. Showing output:")
                c.run("npm run build")
                return

        print("🚀 Launching Electron app...")
        if dev:
            # Run with visible output for debugging
            with c.cd(electron_dir):
                c.run("npx electron . --dev")
        else:
            # Launch in background
            import subprocess
            abs_electron_dir = os.path.abspath(electron_dir)
            subprocess.Popen(
                ["npx", "electron", "."],
                cwd=abs_electron_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            print("✅ Electron app launched")
            print("   Check your dock for the PutPlace window")


@task
def pp_gui_test_install(c, automated=False):
    """Test the packaged Electron app installation and uninstallation.

    Args:
        automated: If True, copy app directly without manual DMG installation (default: False)

    This task:
    1. Packages the app if not already packaged
    2. Installs to /Applications (automated or via DMG)
    3. Tests launching the installed app
    4. Automatically quits the app
    5. Provides uninstallation instructions

    Semi-automated test - some manual verification required.
    """
    import os
    import sys
    import time

    if sys.platform != 'darwin':
        print("❌ This test is only for macOS")
        return

    electron_dir = "pp_gui_client"
    app_name = "PutPlace Client"

    # Step 1: Ensure app is packaged
    print("Step 1: Checking for packaged app...")
    dmg_dir = f"{electron_dir}/release"

    # Check if any DMG files exist
    import glob
    dmg_files = glob.glob(f"{dmg_dir}/{app_name}-*.dmg")

    if not dmg_files:
        print("⚠️  DMG not found. Packaging now...")
        pp_gui_package(c)
        # Re-check for DMG files
        dmg_files = glob.glob(f"{dmg_dir}/{app_name}-*.dmg")

    if not dmg_files:
        print("❌ Failed to create DMG file")
        return

    dmg_path = dmg_files[0]
    print(f"✓ Found DMG: {dmg_path}\n")

    # Step 2: Install the app
    installed_app = f"/Applications/{app_name}.app"
    app_bundle = f"{electron_dir}/release/mac-arm64/{app_name}.app"

    if automated:
        print("Step 2: Installing app to /Applications (automated)...")
        # Remove existing installation if present
        if os.path.exists(installed_app):
            print(f"  Removing existing installation...")
            c.run(f'rm -rf "{installed_app}"', warn=True)

        # Copy the app bundle directly
        print(f"  Copying app to /Applications...")
        c.run(f'cp -R "{app_bundle}" /Applications/')
        print("✓ App installed\n")
    else:
        print("Step 2: Opening DMG installer...")
        c.run(f'open "{dmg_path}"')
        print("✓ DMG opened\n")

        print("=" * 60)
        print("MANUAL STEP REQUIRED:")
        print("1. Drag 'PutPlace Client' to the Applications folder")
        print("2. Wait for the copy to complete")
        print("3. Press Enter here to continue...")
        print("=" * 60)
        try:
            input()
        except EOFError:
            print("\n⚠️  Running in non-interactive mode. Switching to automated install...")
            automated = True
            if os.path.exists(installed_app):
                c.run(f'rm -rf "{installed_app}"', warn=True)
            c.run(f'cp -R "{app_bundle}" /Applications/')
            print("✓ App installed")

    # Step 3: Test launching the installed app
    print("\nStep 3: Testing installed app...")
    installed_app = f"/Applications/{app_name}.app"

    if os.path.exists(installed_app):
        print(f"✓ Found installed app: {installed_app}")
        print("🚀 Launching installed app...")
        c.run(f'open -a "{installed_app}"')
        print("✓ App launched\n")

        print("Please check:")
        print("  - Does the menu bar show 'PutPlace Client' (not 'Electron')?")
        print("  - Can you login successfully?")
        print("  - Does file scanning work?")

        if not automated:
            print("\nPress Enter to quit the app and continue...")
            try:
                input()
            except EOFError:
                print("\n⚠️  Running in non-interactive mode. Continuing automatically...")
        else:
            print("\nWaiting 5 seconds for testing...")
            time.sleep(5)

        # Quit the app
        print("\n🛑 Quitting PutPlace Client...")
        c.run(f'osascript -e \'quit app "{app_name}"\'', warn=True)
        time.sleep(1)
        print("✓ App quit\n")

        # Step 4: Uninstallation instructions
        print("\n" + "=" * 60)
        print("UNINSTALLATION INSTRUCTIONS:")
        print("=" * 60)
        print("To remove the app, run these commands:")
        print(f'  1. Quit the app if running')
        print(f'  2. rm -rf "{installed_app}"')
        print(f'  3. rm -rf ~/Library/Application\\ Support/PutPlace\\ Client')
        print(f'  4. rm -rf ~/Library/Preferences/com.putplace.client.plist')
        print(f'  5. Eject the DMG volume if mounted')

        if automated:
            print("\n⚠️  Automated mode: Automatically uninstalling...")
            choice = 'y'
        else:
            print("\nWould you like to uninstall now? (y/N): ", end='')
            try:
                choice = input().strip().lower()
            except EOFError:
                print("\n⚠️  Running in non-interactive mode. Skipping uninstall.")
                choice = 'n'

        if choice == 'y':
            print("\nUninstalling...")
            c.run(f'rm -rf "{installed_app}"', warn=True)
            c.run(f'rm -rf ~/Library/Application\\ Support/PutPlace\\ Client', warn=True)
            c.run(f'rm -rf ~/Library/Preferences/com.putplace.client.plist', warn=True)
            print("✓ App uninstalled")
        else:
            print("\nSkipping uninstallation.")
            print("The app will remain in /Applications/")
    else:
        print(f"❌ App not found at {installed_app}")
        print("Installation may have failed.")

    print("\n✓ Test complete!")
