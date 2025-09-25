#!/usr/bin/env python3
"""
Simulate exactly what happens when the agent creates a folder in the wrong location
This mimics the agent forgetting to create files in the session folder
"""
import os
import sys
import time
import shutil
import requests
from datetime import datetime

BASE_URL = "http://localhost:8001"
TEST_USER = "folder_test_user"

def test_agent_folder_creation():
    """Test agent creating folder in main directory instead of session folder"""
    print("="*70)
    print("SIMULATING AGENT FOLDER CREATION IN WRONG LOCATION")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Generate unique folder name
    test_folder = f"plot_molecules_{int(time.time())}"

    # Submit a request that simulates agent behavior
    print("\n1. Submitting request that creates folder in main directory...")

    # This code simulates the agent creating a folder in the current working directory
    # instead of in the session folder (which sometimes happens)
    code = f"""
import os
import time

# Simulate agent creating folder in main directory (wrong location)
# This happens when the agent forgets to use the session path
folder_name = '{test_folder}'

# Create folder in current directory (NOT in session folder)
print(f"Creating folder in current directory: {{os.getcwd()}}")
os.makedirs(folder_name, exist_ok=True)

# Create some files in the folder (simulating plot generation)
for i in range(3):
    file_path = os.path.join(folder_name, f"molecule_{{i+1}}.jpg")
    with open(file_path, 'w') as f:
        f.write(f"Simulated plot data for molecule {{i+1}}")
    print(f"  Created: {{file_path}}")

# Create CSV data files
csv_path = os.path.join(folder_name, "analysis_data.csv")
with open(csv_path, 'w') as f:
    f.write("molecule_id,property,value\\n")
    f.write("mol_1,solubility,0.85\\n")
    f.write("mol_2,solubility,0.92\\n")
print(f"  Created: {{csv_path}}")

# Create subfolder with results
results_dir = os.path.join(folder_name, "results")
os.makedirs(results_dir, exist_ok=True)
result_file = os.path.join(results_dir, "summary.txt")
with open(result_file, 'w') as f:
    f.write("Analysis complete\\nAll molecules processed")
print(f"  Created: {{result_file}}")

print(f"\\nFolder '{{folder_name}}' created with all files")
print("The folder moving system should move this entire folder to the session directory")
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
        print(f"❌ Failed to submit request: {response.status_code}")
        return False

    session_id = response.json()["session_id"]
    print(f"✅ Created session: {session_id}")

    # Wait for processing
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
                print(f"   Processing {status}")
                break

        time.sleep(2)

    # Check if folder was moved
    print("\n3. Checking if folder was moved from main directory...")

    if os.path.exists(test_folder):
        print(f"❌ FAILED: Folder '{test_folder}' still exists in main directory")
        print("   The folder moving system did not work correctly")

        # Show what's in the folder
        print("\n   Contents still in main directory:")
        for root, dirs, files in os.walk(test_folder):
            level = root.replace(test_folder, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"     {indent}{os.path.basename(root)}/")
            sub_indent = ' ' * 2 * (level + 1)
            for f in files:
                print(f"     {sub_indent}{f}")

        # Clean up
        shutil.rmtree(test_folder)
        return False
    else:
        print(f"✅ SUCCESS: Folder '{test_folder}' was moved (no longer in main directory)")

    # Try to find where it was moved to
    print("\n4. Locating moved folder in session storage...")

    # Look in session storage
    import glob
    session_patterns = [
        f"chat_sessions/*{session_id[:8]}*",
        f"chat_sessions/*",  # Check all chat sessions
        f"session_storage/*{session_id}*",
        f"multiturn_sessions/*{session_id}*"
    ]

    folder_found = False
    for pattern in session_patterns:
        for session_path in glob.glob(pattern):
            if os.path.isdir(session_path):
                moved_folder = os.path.join(session_path, test_folder)
                if os.path.exists(moved_folder):
                    print(f"✅ Folder found at: {moved_folder}")

                    # Verify contents
                    file_count = sum(len(files) for _, _, files in os.walk(moved_folder))
                    print(f"   Contains {file_count} files (structure preserved)")
                    folder_found = True
                    break
        if folder_found:
            break

    if not folder_found:
        # Check if files were moved individually instead of as a folder
        for pattern in session_patterns:
            for session_path in glob.glob(pattern):
                if os.path.isdir(session_path):
                    # Check for individual files
                    jpg_files = glob.glob(os.path.join(session_path, "*.jpg"))
                    csv_files = glob.glob(os.path.join(session_path, "*.csv"))

                    if jpg_files or csv_files:
                        print(f"⚠️  Files found individually in: {session_path}")
                        print(f"   JPG files: {len(jpg_files)}")
                        print(f"   CSV files: {len(csv_files)}")
                        print("   Note: Files were moved but folder structure was not preserved")
                        return False

    return True

def main():
    # Run the test
    success = test_agent_folder_creation()

    print("\n" + "="*70)
    if success:
        print("✅ TEST PASSED")
        print("The folder moving system correctly handles folders created")
        print("in the wrong location by the agent.")
    else:
        print("❌ TEST FAILED")
        print("The folder moving system needs to be fixed.")
        print("\nExpected behavior:")
        print("- Agent creates folder in main directory")
        print("- System detects and moves entire folder to session storage")
        print("- Folder structure is preserved")
    print("="*70)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())