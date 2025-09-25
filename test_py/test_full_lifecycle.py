#!/usr/bin/env python3
"""
Test the complete lifecycle of a session from submission to download
This will help identify where the issue is occurring
"""
import os
import sys
import time
import json
import requests
import glob
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8001"
TEST_USER_ID = "TestUser"

def print_section(title):
    """Print a section header"""
    print("\n" + "="*70)
    print(f" {title}")
    print("="*70)

def check_file_system(session_id):
    """Check file system for session files"""
    print("\n📁 File System Check:")

    # Check chat_sessions
    patterns = [
        f"chat_sessions/*{session_id[:8]}*",
        f"chat_sessions/session_*{session_id[:8]}*",
        f"chat_sessions/multiturn_*{session_id[:8]}*"
    ]

    found_folders = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            found_folders.extend(matches)

    if found_folders:
        print(f"  ✓ Found session folders: {found_folders}")
        for folder in found_folders:
            if os.path.exists(folder):
                files = os.listdir(folder)
                print(f"    Contents of {folder}:")
                for file in files[:5]:  # Show first 5 files
                    print(f"      - {file}")
                if len(files) > 5:
                    print(f"      ... and {len(files)-5} more files")
    else:
        print(f"  ❌ No session folders found for {session_id[:8]}")

    # Check session_storage
    session_storage_file = f"session_storage/{session_id}.json"
    if os.path.exists(session_storage_file):
        print(f"  ✓ Found session storage file: {session_storage_file}")
        with open(session_storage_file, 'r') as f:
            data = json.load(f)
            stored_path = data.get('session_path', 'NOT SET')
            print(f"    Stored session_path: {stored_path}")
            print(f"    Status: {data.get('status', 'unknown')}")
            print(f"    Is complete: {data.get('is_complete', False)}")
    else:
        print(f"  ❌ No session storage file found")

    # Check chat_zips
    zip_patterns = [
        f"chat_zips/*{session_id[:8]}*.zip"
    ]

    for pattern in zip_patterns:
        matches = glob.glob(pattern)
        if matches:
            print(f"  ✓ Found zip files: {matches}")
        else:
            print(f"  ❌ No zip files found")

    return found_folders

def test_simple_task():
    """Test a simple task and track its lifecycle"""
    print_section("Test 1: Simple Task Lifecycle")

    # Step 1: Submit a simple task
    print("\n1️⃣ Submitting task...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": "Write a simple Python script that prints 'Hello World' and save it to hello.py",
            "language": "en",
            "user_id": TEST_USER_ID
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✓ Task submitted: {session_id}")

    # Step 2: Monitor progress
    print("\n2️⃣ Monitoring progress...")
    start_time = time.time()
    max_wait = 30  # seconds
    session_path = None

    while time.time() - start_time < max_wait:
        progress_response = requests.get(
            f"{BASE_URL}/progress/{session_id}",
            params={"user_id": TEST_USER_ID}
        )

        if progress_response.status_code == 200:
            progress_data = progress_response.json()
            status = progress_data.get("status", "unknown")
            is_complete = progress_data.get("is_complete", False)
            session_path = progress_data.get("session_path")

            print(f"  Status: {status}, Complete: {is_complete}, Path: {session_path}")

            if is_complete:
                print(f"✓ Task completed in {time.time() - start_time:.1f} seconds")
                break

        time.sleep(2)
    else:
        print(f"⚠️ Task did not complete within {max_wait} seconds")

    # Step 3: Check file system
    print("\n3️⃣ Checking file system...")
    found_folders = check_file_system(session_id)

    # Step 4: Check session storage
    print("\n4️⃣ Checking session data...")
    progress_response = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        print(f"  Session ID: {progress_data.get('session_id')}")
        print(f"  Status: {progress_data.get('status')}")
        print(f"  Session path: {progress_data.get('session_path')}")
        print(f"  Is complete: {progress_data.get('is_complete')}")
        print(f"  Has snapshots: {len(progress_data.get('periodic_snapshots', []))} snapshots")

    # Step 5: Wait a bit for any async operations
    print("\n5️⃣ Waiting for async operations (S3 upload, zip creation)...")
    time.sleep(5)

    # Step 6: Try download URLs
    print("\n6️⃣ Testing download URLs endpoint...")
    download_urls_response = requests.get(
        f"{BASE_URL}/download-urls/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    print(f"  Response status: {download_urls_response.status_code}")
    if download_urls_response.status_code == 200:
        urls_data = download_urls_response.json()
        print(f"✓ Download URLs retrieved:")
        for key, value in urls_data.items():
            if isinstance(value, dict):
                print(f"    {key}: {value.get('filename', 'N/A')}")
    else:
        print(f"❌ Download URLs failed: {download_urls_response.text}")

        # Debug: Check what unified session manager sees
        print("\n  🔍 Debugging session lookup...")

        # Check active sessions
        sessions_response = requests.get(
            f"{BASE_URL}/sessions",
            params={"user_id": TEST_USER_ID}
        )
        if sessions_response.status_code == 200:
            sessions = sessions_response.json()
            matching = [s for s in sessions if s['session_id'] == session_id]
            if matching:
                print(f"    Found in sessions list: {matching[0].get('status')}")
                print(f"    Storage location: {matching[0].get('_storage_location', 'unknown')}")

    # Step 7: Try direct download
    print("\n7️⃣ Testing direct download endpoint...")
    download_response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER_ID},
        allow_redirects=True
    )

    print(f"  Response status: {download_response.status_code}")
    if download_response.status_code == 200:
        print(f"✓ Direct download successful")
        print(f"  Content size: {len(download_response.content)} bytes")
    else:
        print(f"❌ Direct download failed: {download_response.text}")

    # Step 8: Final file system check
    print("\n8️⃣ Final file system check...")
    check_file_system(session_id)

    return download_response.status_code == 200

def test_cancelled_task():
    """Test a task that gets cancelled"""
    print_section("Test 2: Cancelled Task Lifecycle")

    # Step 1: Submit a long-running task
    print("\n1️⃣ Submitting long-running task...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": "Run this Python code: import time; for i in range(60): print(f'Count: {i}'); time.sleep(1)",
            "language": "en",
            "user_id": TEST_USER_ID
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✓ Task submitted: {session_id}")

    # Step 2: Wait a bit then cancel
    print("\n2️⃣ Waiting 5 seconds then cancelling...")
    time.sleep(5)

    # Get initial session path before cancellation
    progress_response = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER_ID}
    )
    initial_path = None
    if progress_response.status_code == 200:
        initial_path = progress_response.json().get("session_path")
        print(f"  Initial session path: {initial_path}")

    # Cancel the task
    stop_response = requests.post(
        f"{BASE_URL}/stop/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if stop_response.status_code != 200:
        print(f"❌ Failed to stop task: {stop_response.text}")
        return False

    print("✓ Task cancelled")

    # Step 3: Wait for cancellation to complete
    print("\n3️⃣ Waiting for cancellation to complete...")
    time.sleep(3)

    # Step 4: Check session path after cancellation
    progress_response = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        final_path = progress_data.get("session_path")
        print(f"  Final session path: {final_path}")

        if initial_path and final_path and initial_path != final_path:
            print(f"⚠️ Session path changed during cancellation!")

        print(f"  Status: {progress_data.get('status')}")
        print(f"  Is cancelled: {progress_data.get('is_cancelled')}")

    # Step 5: Check file system
    print("\n4️⃣ Checking file system...")
    check_file_system(session_id)

    # Step 6: Try download
    print("\n5️⃣ Testing download after cancellation...")
    time.sleep(3)  # Wait for any async operations

    download_response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER_ID},
        allow_redirects=True
    )

    print(f"  Response status: {download_response.status_code}")
    if download_response.status_code == 200:
        print(f"✓ Download successful for cancelled task")
    else:
        print(f"❌ Download failed: {download_response.text}")

    return download_response.status_code == 200

def main():
    """Run all lifecycle tests"""
    print("\n" + "="*70)
    print(" FULL SESSION LIFECYCLE TEST")
    print("="*70)
    print(f"Target: {BASE_URL}")
    print(f"User: {TEST_USER_ID}")

    # Check server
    try:
        health = requests.get(f"{BASE_URL}/health")
        if health.status_code != 200:
            print("\n❌ Server is not healthy")
            return 1
    except Exception as e:
        print(f"\n❌ Cannot connect to server: {e}")
        print("Please ensure the FastAPI server is running on port 8000")
        return 1

    print("\n✓ Server is running")

    # Run tests
    results = []

    # Test 1: Simple task
    print("\n" + "-"*70)
    result1 = test_simple_task()
    results.append(("Simple Task", result1))

    # Test 2: Cancelled task
    print("\n" + "-"*70)
    result2 = test_cancelled_task()
    results.append(("Cancelled Task", result2))

    # Summary
    print_section("TEST SUMMARY")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed < total:
        print("\n⚠️ Some tests failed. The issue is likely in:")
        print("  1. Session path not being saved correctly to session_storage")
        print("  2. Files being moved to wrong location during completion")
        print("  3. Unified session manager not finding the session files")
        print("\n🔍 Check the debug output above to identify the exact issue")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())