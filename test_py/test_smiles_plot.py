#!/usr/bin/env python3
"""
Test script to trace the complete process of plotting SMILES molecules
and verify they are included in the session zip
"""
import os
import sys
import time
import json
import requests
import zipfile
import tempfile
import glob
from datetime import datetime

BASE_URL = "http://localhost:8001"
TEST_USER = "test_smiles_user"

def monitor_files(start_time):
    """Monitor what files are created during execution"""
    new_files = []
    for root, dirs, files in os.walk("."):
        # Skip system directories
        if any(skip in root for skip in ['chat_sessions', 'chat_zips', '.git', '__pycache__', 'venv']):
            continue
        for file in files:
            filepath = os.path.join(root, file)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > start_time:
                    size = os.path.getsize(filepath) / 1024  # KB
                    new_files.append((filepath, size))
            except:
                pass
    return new_files

def main():
    print("="*70)
    print(" SMILES PLOTTING TEST - FULL PROCESS TRACE")
    print("="*70)

    # Record start time
    start_time = time.time()
    print(f"\nStart time: {datetime.now()}")

    # Step 1: Submit the plotting request
    print("\n1️⃣ SUBMITTING PLOTTING REQUEST")
    print("-"*40)

    message = """Please plot the molecular structures for these SMILES:
1. CC (Ethane)
2. CCC (Propane)

Create visualizations showing:
- 2D molecular structure diagrams
- Label each molecule clearly
- Save the plots as PNG files
- Make sure to save all generated plots"""

    print(f"Message: {message[:100]}...")

    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": message,
            "language": "en",
            "user_id": TEST_USER
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to submit: {response.status_code}")
        print(f"Response: {response.text}")
        return 1

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Session ID: {session_id}")

    # Step 2: Monitor progress
    print("\n2️⃣ MONITORING TASK PROGRESS")
    print("-"*40)

    session_path = None
    for i in range(30):  # Wait up to 60 seconds
        time.sleep(2)

        # Check progress
        progress = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if progress.status_code == 200:
            data = progress.json()
            status = data.get("status", "unknown")
            is_complete = data.get("is_complete", False)
            session_path = data.get("session_path")

            print(f"  [{i*2}s] Status: {status}, Complete: {is_complete}")

            if is_complete:
                print(f"✅ Task completed!")
                print(f"Session path: {session_path}")
                break
    else:
        print("⚠️ Task didn't complete in 60 seconds")

    # Step 3: Check what files were created
    print("\n3️⃣ CHECKING FILES CREATED DURING EXECUTION")
    print("-"*40)

    new_files = monitor_files(start_time)
    if new_files:
        print(f"Found {len(new_files)} new files:")
        for filepath, size in sorted(new_files):
            if any(ext in filepath.lower() for ext in ['.png', '.jpg', '.svg']):
                print(f"  🖼️ {filepath} ({size:.1f} KB)")
            else:
                print(f"  📄 {filepath} ({size:.1f} KB)")
    else:
        print("❌ No new files found in working directory")

    # Step 4: Check session folder contents
    print("\n4️⃣ CHECKING SESSION FOLDER")
    print("-"*40)

    if session_path and os.path.exists(session_path):
        print(f"✅ Session folder exists: {session_path}")
        files = os.listdir(session_path)
        print(f"Contents ({len(files)} files):")
        for file in files:
            filepath = os.path.join(session_path, file)
            size = os.path.getsize(filepath) / 1024
            if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg']):
                print(f"  🖼️ {file} ({size:.1f} KB)")
            else:
                print(f"  📄 {file} ({size:.1f} KB)")
    else:
        print(f"❌ Session folder not found: {session_path}")

    # Step 5: Wait for async operations
    print("\n5️⃣ WAITING FOR ZIP CREATION")
    print("-"*40)
    time.sleep(5)

    # Step 6: Check zip file
    print("\n6️⃣ CHECKING ZIP FILE")
    print("-"*40)

    # Look for zip file
    zip_pattern = f"chat_zips/*{session_id[:8]}*.zip"
    zip_files = glob.glob(zip_pattern)

    if zip_files:
        zip_path = zip_files[0]
        print(f"✅ Zip file found: {zip_path}")

        # List contents
        with zipfile.ZipFile(zip_path, 'r') as zf:
            files = zf.namelist()
            print(f"Zip contents ({len(files)} files):")

            image_files = []
            other_files = []

            for file in files:
                info = zf.getinfo(file)
                size = info.file_size / 1024
                if any(ext in file.lower() for ext in ['.png', '.jpg', '.svg']):
                    image_files.append((file, size))
                else:
                    other_files.append((file, size))

            if image_files:
                print("\n  Images/Plots:")
                for file, size in image_files:
                    print(f"    🖼️ {file} ({size:.1f} KB)")
            else:
                print("\n  ❌ NO IMAGES/PLOTS IN ZIP!")

            if other_files:
                print("\n  Other files:")
                for file, size in other_files[:5]:  # Show first 5
                    print(f"    📄 {file} ({size:.1f} KB)")
    else:
        print(f"❌ No zip file found matching pattern: {zip_pattern}")

    # Step 7: Download test
    print("\n7️⃣ TESTING DOWNLOAD")
    print("-"*40)

    download_response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER},
        allow_redirects=True
    )

    if download_response.status_code == 200:
        print(f"✅ Download successful ({len(download_response.content)} bytes)")

        # Save and check downloaded zip
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(download_response.content)
            tmp_path = tmp.name

        with zipfile.ZipFile(tmp_path, 'r') as zf:
            files = zf.namelist()
            image_count = sum(1 for f in files if any(ext in f.lower() for ext in ['.png', '.jpg', '.svg']))
            print(f"Downloaded zip contains {len(files)} files ({image_count} images)")

        os.unlink(tmp_path)
    else:
        print(f"❌ Download failed: {download_response.status_code}")

    # Step 8: Check for orphaned files
    print("\n8️⃣ CHECKING FOR ORPHANED FILES")
    print("-"*40)

    # Check if any plot files are left in working directory
    orphaned = []
    for pattern in ['*.png', '*.jpg', '*.svg', '*.pdf']:
        for file in glob.glob(pattern):
            if os.path.getmtime(file) > start_time:
                orphaned.append(file)

    if orphaned:
        print(f"⚠️ Found {len(orphaned)} orphaned files in working directory:")
        for file in orphaned:
            size = os.path.getsize(file) / 1024
            print(f"  {file} ({size:.1f} KB)")
    else:
        print("✅ No orphaned files found")

    # Summary
    print("\n" + "="*70)
    print(" SUMMARY")
    print("="*70)

    issues = []

    if not new_files:
        issues.append("No files were created during execution")

    if session_path and not os.path.exists(session_path):
        issues.append("Session folder doesn't exist")

    if not zip_files:
        issues.append("No zip file was created")
    elif zip_files:
        with zipfile.ZipFile(zip_files[0], 'r') as zf:
            files = zf.namelist()
            if not any(any(ext in f.lower() for ext in ['.png', '.jpg', '.svg']) for f in files):
                issues.append("Zip file contains no images/plots")

    if orphaned:
        issues.append(f"{len(orphaned)} files were not moved to session folder")

    if issues:
        print("❌ ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ ALL CHECKS PASSED!")
        print("Plots were successfully created, moved to session folder, and included in zip")

    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())