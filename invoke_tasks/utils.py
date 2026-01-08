"""Utility tasks for PutPlace development.

This module contains miscellaneous utility tasks for managing
DNS, installing clients, and other helper functions.
"""

from invoke import task


@task
def flush_dns(c):
    """Flush the local DNS cache (macOS only).

    Clears the DNS resolver cache to pick up recent DNS changes.
    Useful after updating Route53 or other DNS records.

    Examples:
        invoke flush-dns
    """
    import platform

    if platform.system() != "Darwin":
        print("❌ This command only works on macOS")
        return

    print("Flushing DNS cache...")
    result = c.run(
        "sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder",
        pty=True,
        warn=True,
    )

    if result.ok:
        print("✓ DNS cache flushed")
    else:
        print("❌ Failed to flush DNS cache")


@task
def install_electron_client(c, arch="arm64"):
    """Download and install the latest PutPlace Electron Client (macOS only).

    Downloads the latest DMG from GitHub releases, removes quarantine attribute,
    and installs to /Applications.

    Args:
        arch: Architecture to download (arm64 or x64). Default: arm64

    Examples:
        invoke install-electron-client              # Install Apple Silicon version
        invoke install-electron-client --arch=x64   # Install Intel version
    """
    import platform
    import os

    if platform.system() != "Darwin":
        print("❌ This command only works on macOS")
        return

    # Validate architecture
    if arch not in ["arm64", "x64"]:
        print(f"❌ Invalid architecture: {arch}. Use 'arm64' or 'x64'")
        return

    # Determine the download URL pattern based on architecture
    if arch == "arm64":
        dmg_pattern = "PutPlace.Client-*-arm64.dmg"
        dmg_name = "PutPlace-Client-arm64.dmg"
    else:
        dmg_pattern = "PutPlace.Client-*.dmg"
        dmg_name = "PutPlace-Client-x64.dmg"

    print(f"\n📦 Installing PutPlace Electron Client ({arch})...\n")

    # Step 1: Get latest release info from GitHub
    print("1️⃣  Fetching latest release info from GitHub...")
    result = c.run(
        "curl -s https://api.github.com/repos/jdrumgoole/putplace/releases | "
        "python3 -c \"import sys, json; "
        "releases = json.load(sys.stdin); "
        "electron_releases = [r for r in releases if r['tag_name'].startswith('electron-v')]; "
        "print(electron_releases[0]['tag_name'] if electron_releases else '')\"",
        hide=True,
    )

    latest_tag = result.stdout.strip()
    if not latest_tag:
        print("❌ Could not find latest Electron release")
        return

    version = latest_tag.replace("electron-v", "")
    print(f"   Latest version: {version}")

    # Step 2: Construct download URL (note: filenames use dots, not spaces)
    if arch == "arm64":
        download_url = f"https://github.com/jdrumgoole/putplace/releases/download/{latest_tag}/PutPlace.Client-{version}-arm64.dmg"
    else:
        download_url = f"https://github.com/jdrumgoole/putplace/releases/download/{latest_tag}/PutPlace.Client-{version}.dmg"

    download_path = os.path.expanduser(f"~/Downloads/{dmg_name}")

    # Step 3: Download the DMG
    print(f"\n2️⃣  Downloading DMG to ~/Downloads/{dmg_name}...")
    result = c.run(
        f'curl -L -o "{download_path}" "{download_url}"',
        warn=True,
    )

    if not result.ok:
        print("❌ Download failed")
        return

    print(f"   ✓ Downloaded to {download_path}")

    # Step 4: Remove quarantine attribute
    print("\n3️⃣  Removing quarantine attribute...")
    result = c.run(f'xattr -cr "{download_path}"', warn=True)

    if result.ok:
        print("   ✓ Quarantine attribute removed")
    else:
        print("   ⚠️  Could not remove quarantine attribute (may not be needed)")

    # Step 5: Mount the DMG
    print("\n4️⃣  Mounting DMG...")
    result = c.run(f'hdiutil attach "{download_path}" -quiet', hide=True, warn=True)

    if not result.ok:
        print("❌ Failed to mount DMG")
        return

    print("   ✓ DMG mounted")

    # Step 6: Copy to Applications
    print("\n5️⃣  Installing to /Applications...")

    # Find the mounted volume
    result = c.run(
        "ls -d /Volumes/PutPlace* 2>/dev/null | head -1",
        hide=True,
        warn=True,
    )

    if not result.ok or not result.stdout.strip():
        print("❌ Could not find mounted DMG volume")
        c.run(f'hdiutil detach /Volumes/PutPlace* 2>/dev/null', warn=True, hide=True)
        return

    volume_path = result.stdout.strip()

    # Remove old version if it exists
    c.run('rm -rf "/Applications/PutPlace Client.app"', warn=True, hide=True)

    # Copy new version
    result = c.run(
        f'cp -R "{volume_path}/PutPlace Client.app" /Applications/',
        warn=True,
    )

    if result.ok:
        print("   ✓ Installed to /Applications/PutPlace Client.app")
    else:
        print("❌ Failed to copy app to /Applications")
        c.run(f'hdiutil detach "{volume_path}" 2>/dev/null', warn=True, hide=True)
        return

    # Step 7: Unmount the DMG
    print("\n6️⃣  Unmounting DMG...")
    c.run(f'hdiutil detach "{volume_path}" -quiet', warn=True, hide=True)
    print("   ✓ DMG unmounted")

    # Step 8: Remove quarantine from installed app
    print("\n7️⃣  Removing quarantine from installed app...")
    c.run('xattr -cr "/Applications/PutPlace Client.app"', warn=True, hide=True)
    print("   ✓ App is ready to use")

    print("\n✅ Installation complete!")
    print("\nYou can now run PutPlace Client from:")
    print("   • Applications folder")
    print("   • Spotlight (Cmd+Space, type 'PutPlace')")
    print("   • Command: open -a 'PutPlace Client'")
    print(f"\nDownloaded DMG saved at: {download_path}")
