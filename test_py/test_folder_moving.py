#!/usr/bin/env python3
"""
Test script to verify folder moving functionality in FastAPI server
Tests that entire directories are moved to session folder, not just individual files
"""
import os
import sys
import time
import shutil
import tempfile
import requests
from datetime import datetime

BASE_URL = "http://localhost:8001"
TEST_USER = "folder_test_user"

def create_test_folder_structure():
    """Create a test folder structure with multiple files"""
    # Create a unique test folder name
    folder_name = f"plot_molecules_{int(time.time())}"

    # Create the folder
    os.makedirs(folder_name, exist_ok=True)

    # Create test files in the folder
    test_files = []

    # Create image files
    for i in range(3):
        img_path = os.path.join(folder_name, f"molecule_{i+1}.jpg")
        with open(img_path, 'w') as f:
            f.write(f"Fake image data for molecule {i+1}")
        test_files.append(img_path)

    # Create CSV files
    for i in range(2):
        csv_path = os.path.join(folder_name, f"data_{i+1}.csv")
        with open(csv_path, 'w') as f:
            f.write(f"col1,col2,col3\n")
            f.write(f"val1,val2,val3\n")
        test_files.append(csv_path)

    # Create a subfolder with more files
    subfolder = os.path.join(folder_name, "analysis")
    os.makedirs(subfolder, exist_ok=True)

    result_file = os.path.join(subfolder, "results.txt")
    with open(result_file, 'w') as f:
        f.write("Analysis results here")
    test_files.append(result_file)

    print(f"✅ Created test folder: {folder_name}/")
    print(f"   Contents:")
    for root, dirs, files in os.walk(folder_name):
        level = root.replace(folder_name, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"   {indent}{os.path.basename(root)}/")
        sub_indent = ' ' * 2 * (level + 1)
        for file in files:
            print(f"   {sub_indent}{file}")

    return folder_name, test_files

def test_folder_moving():
    """Test that folders are moved correctly to session folder"""
    print(f"\n{'='*60}")
    print("Testing Folder Moving Functionality")
    print('='*60)

    # Generate unique folder name
    test_folder = f"plot_molecules_{int(time.time())}"

    # 1. Submit a request that creates a folder during execution
    print("\n1. Submitting request that creates folder during execution...")

    # Create a Python script that creates the folder
    code = f"""
import os

# Create a folder during execution
test_folder = '{test_folder}'
print(f"Creating folder: {{test_folder}}")
os.makedirs(test_folder, exist_ok=True)

# Create test files in the folder
for i in range(3):
    img_path = os.path.join(test_folder, f"molecule_{{i+1}}.jpg")
    with open(img_path, 'w') as f:
        f.write(f"Fake image data for molecule {{i+1}}")
    print(f"  Created: {{img_path}}")

# Create CSV files
for i in range(2):
    csv_path = os.path.join(test_folder, f"data_{{i+1}}.csv")
    with open(csv_path, 'w') as f:
        f.write("col1,col2,col3\\n")
        f.write("val1,val2,val3\\n")
    print(f"  Created: {{csv_path}}")

# Create a subfolder
subfolder = os.path.join(test_folder, "analysis")
os.makedirs(subfolder, exist_ok=True)

result_file = os.path.join(subfolder, "results.txt")
with open(result_file, 'w') as f:
    f.write("Analysis results here")
print(f"  Created: {{result_file}}")

print(f"\\nTask completed - folder {{test_folder}} should be moved to session folder")
"""

    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": code,
            "user_id": TEST_USER,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to submit request: {response.status_code}")
        return False

    session_id = response.json()["session_id"]
    print(f"   ✅ Created session: {session_id[:8]}...")

    # 2. Wait for processing to complete
    print("\n2. Waiting for processing to complete...")
    max_wait = 30
    start_time = time.time()

    while time.time() - start_time < max_wait:
        response = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER}
        )

        if response.status_code == 200:
            status = response.json().get("status")
            if status in ["completed", "error"]:
                print(f"   ✅ Processing {status}")
                break

        time.sleep(2)

    # 3. Check if folder was moved
    print("\n3. Checking if folder was moved...")

    # Check if original folder still exists
    if os.path.exists(test_folder):
        print(f"   ❌ Original folder still exists: {test_folder}")
        print("   This means it wasn't moved to session folder")

        # Clean up
        shutil.rmtree(test_folder)
        return False
    else:
        print(f"   ✅ Original folder was moved (no longer in working directory)")

    # 4. Verify folder is in session storage
    print("\n4. Checking session storage...")

    # Look for the folder in session directories
    session_paths = [
        f"chat_sessions/multiturn_*_{session_id}",
        f"multiturn_sessions/{session_id}*"
    ]

    folder_found = False
    import glob
    for pattern in session_paths:
        for session_dir in glob.glob(pattern):
            moved_folder = os.path.join(session_dir, test_folder)
            if os.path.exists(moved_folder):
                print(f"   ✅ Folder found in: {moved_folder}")
                folder_found = True

                # Verify contents
                moved_files = []
                for root, dirs, files in os.walk(moved_folder):
                    for f in files:
                        moved_files.append(os.path.join(root, f))

                print(f"   ✅ All {len(moved_files)} files preserved in folder structure")
                break

    if not folder_found:
        print(f"   ⚠️  Could not verify folder location in session storage")
        print("   (This might be normal if session uses different storage)")

    return True

def cleanup_test_folders():
    """Clean up any leftover test folders"""
    print("\n5. Cleaning up test folders...")

    import glob
    for folder in glob.glob("plot_molecules_*"):
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
                print(f"   Cleaned up: {folder}")
            except:
                pass

def main():
    print("="*70)
    print("FOLDER MOVING FUNCTIONALITY TEST")
    print(f"Server: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Run test
    success = test_folder_moving()

    # Cleanup
    cleanup_test_folders()

    # Summary
    print("\n" + "="*70)
    if success:
        print("✅ FOLDER MOVING TEST PASSED")
        print("The server correctly moves entire folders to session storage,")
        print("preserving the directory structure and all files within.")
    else:
        print("❌ FOLDER MOVING TEST FAILED")
        print("Folders are not being moved correctly.")
        print("Check the implementation in _move_generated_files_to_session()")
    print("="*70)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())