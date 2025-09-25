#!/usr/bin/env python3
"""
Test to verify session path consistency and download functionality after fixes
"""
import os
import sys
import time
import json
import requests
import tempfile
import zipfile
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
TEST_USER_ID = "test_user_path_fix"

def test_session_path_consistency():
    """Test that session paths remain consistent through cancellation and download"""
    print("\n" + "="*70)
    print("Testing Session Path Consistency")
    print("="*70)

    # Step 1: Start a long-running task
    print("\n1. Starting a long-running task...")
    start_response = requests.post(
        f"{BASE_URL}/chat-queue",
        json={
            "message": "Run this Python code: import time; for i in range(100): print(f'Iteration {i}'); time.sleep(1)",
            "language": "en",
            "user_id": TEST_USER_ID
        }
    )

    if start_response.status_code != 200:
        print(f"❌ Failed to start task: {start_response.text}")
        return False

    result = start_response.json()
    session_id = result["session_id"]
    print(f"✓ Session started: {session_id}")

    # Step 2: Wait a bit then check progress to get session path
    print("\n2. Checking progress to verify session path...")
    time.sleep(3)

    progress_response = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        session_path = progress_data.get("session_path")
        print(f"✓ Session path: {session_path}")
    else:
        session_path = None
        print("⚠ Could not get session path from progress")

    # Step 3: Cancel the task
    print("\n3. Cancelling the task...")
    stop_response = requests.post(
        f"{BASE_URL}/stop/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if stop_response.status_code != 200:
        print(f"❌ Failed to stop task: {stop_response.text}")
        return False

    print("✓ Task cancelled")

    # Step 4: Wait for cancellation to complete
    print("\n4. Waiting for cancellation to complete...")
    time.sleep(3)

    # Step 5: Check that session path hasn't changed
    print("\n5. Verifying session path consistency...")
    progress_response = requests.get(
        f"{BASE_URL}/progress/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if progress_response.status_code == 200:
        progress_data = progress_response.json()
        new_session_path = progress_data.get("session_path")

        if session_path and new_session_path:
            if session_path == new_session_path:
                print(f"✓ Session path unchanged: {new_session_path}")
            else:
                print(f"❌ Session path changed!")
                print(f"   Original: {session_path}")
                print(f"   New:      {new_session_path}")
                return False
        else:
            print("⚠ Could not verify session paths")

    # Step 6: Test download URLs
    print("\n6. Testing download URLs...")
    download_urls_response = requests.get(
        f"{BASE_URL}/download-urls/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if download_urls_response.status_code == 200:
        print("✓ Download URLs accessible")
        urls_data = download_urls_response.json()
        if "session_zip" in urls_data:
            print(f"  Session zip available: {urls_data['session_zip'].get('filename', 'N/A')}")
    else:
        print(f"❌ Download URLs failed: {download_urls_response.status_code}")
        print(f"   Response: {download_urls_response.text}")
        return False

    # Step 7: Test direct download
    print("\n7. Testing direct download...")
    download_response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER_ID},
        allow_redirects=True
    )

    if download_response.status_code == 200:
        print("✓ Direct download successful")

        # Verify it's a valid zip file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(download_response.content)
            tmp_path = tmp.name

        try:
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                file_list = zf.namelist()
                print(f"  Zip contains {len(file_list)} files")
                os.unlink(tmp_path)
        except Exception as e:
            print(f"❌ Downloaded file is not a valid zip: {e}")
            os.unlink(tmp_path)
            return False
    else:
        print(f"❌ Direct download failed: {download_response.status_code}")
        print(f"   Response: {download_response.text}")
        return False

    print("\n✅ All tests passed!")
    return True

def test_multiturn_session_paths():
    """Test that multi-turn sessions maintain consistent paths"""
    print("\n" + "="*70)
    print("Testing Multi-Turn Session Path Consistency")
    print("="*70)

    # Step 1: Start first turn
    print("\n1. Starting first turn...")
    response = requests.post(
        f"{BASE_URL}/multiturn/start",
        json={
            "message": "Create a test file called test1.txt with content 'Hello World'",
            "language": "en",
            "user_id": TEST_USER_ID
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to start multi-turn session: {response.text}")
        return False

    result = response.json()
    multiturn_id = result["multiturn_session_id"]
    turn1_id = result["turn_session_id"]
    print(f"✓ Multi-turn session: {multiturn_id}")
    print(f"  Turn 1 ID: {turn1_id}")

    # Wait for completion
    print("  Waiting for turn 1 to complete...")
    time.sleep(10)

    # Get turn 1 session path
    progress_response = requests.get(
        f"{BASE_URL}/progress/{turn1_id}",
        params={"user_id": TEST_USER_ID}
    )

    turn1_path = None
    if progress_response.status_code == 200:
        turn1_path = progress_response.json().get("session_path")
        print(f"  Turn 1 path: {turn1_path}")

    # Step 2: Add second turn
    print("\n2. Adding second turn...")
    response = requests.post(
        f"{BASE_URL}/multiturn/{multiturn_id}/continue",
        json={
            "message": "Create another file test2.txt with content 'Turn 2'",
            "user_id": TEST_USER_ID
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to continue session: {response.text}")
        return False

    result = response.json()
    turn2_id = result["turn_session_id"]
    print(f"  Turn 2 ID: {turn2_id}")

    # Wait for completion
    print("  Waiting for turn 2 to complete...")
    time.sleep(10)

    # Get turn 2 session path
    progress_response = requests.get(
        f"{BASE_URL}/progress/{turn2_id}",
        params={"user_id": TEST_USER_ID}
    )

    turn2_path = None
    if progress_response.status_code == 200:
        turn2_path = progress_response.json().get("session_path")
        print(f"  Turn 2 path: {turn2_path}")

    # Step 3: Verify paths are consistent
    print("\n3. Verifying path consistency...")
    if turn1_path and turn2_path:
        if turn1_path == turn2_path:
            print(f"✓ Both turns use same session path: {turn1_path}")
        else:
            print(f"❌ Turns have different paths!")
            print(f"   Turn 1: {turn1_path}")
            print(f"   Turn 2: {turn2_path}")
            return False
    else:
        print("⚠ Could not verify paths")

    # Step 4: Test download for multi-turn session
    print("\n4. Testing multi-turn session download...")

    # Try downloading turn 2 (should have all files)
    download_response = requests.get(
        f"{BASE_URL}/download/{turn2_id}",
        params={"user_id": TEST_USER_ID},
        allow_redirects=True
    )

    if download_response.status_code == 200:
        print("✓ Multi-turn session download successful")
    else:
        print(f"❌ Download failed: {download_response.status_code}")
        return False

    print("\n✅ Multi-turn session tests passed!")
    return True

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("Session Path Fix Verification Tests")
    print("="*70)
    print(f"Target: {BASE_URL}")
    print(f"User: {TEST_USER_ID}")

    # Check if server is running
    try:
        health = requests.get(f"{BASE_URL}/health")
        if health.status_code != 200:
            print("\n❌ Server is not healthy")
            return 1
    except Exception as e:
        print(f"\n❌ Cannot connect to server: {e}")
        print("Please make sure the FastAPI server is running on port 8000")
        return 1

    print("\n✓ Server is running")

    # Run tests
    tests_passed = 0
    tests_total = 0

    # Test 1: Session path consistency
    tests_total += 1
    if test_session_path_consistency():
        tests_passed += 1

    # Test 2: Multi-turn session paths
    tests_total += 1
    if test_multiturn_session_paths():
        tests_passed += 1

    # Final summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    print(f"Tests passed: {tests_passed}/{tests_total}")

    if tests_passed == tests_total:
        print("\n🎉 All tests passed! Session path consistency has been fixed.")
        return 0
    else:
        print(f"\n⚠ {tests_total - tests_passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())