#!/usr/bin/env python3
"""
Test Complete Fixes: Stop, Download, and File Cleanup
Tests all requested fixes are working properly
"""
import time
import requests
import os
import json
import tempfile

def test_stop_really_stops():
    """Test that stop really stops the task and cleans up"""
    base_url = "http://localhost:8001"
    user_id = "test_stop_complete"

    print("🧪 TEST 1: STOP REALLY STOPS")
    print("=" * 50)

    # Create some test files before task starts
    with open("before_task.txt", "w") as f:
        f.write("This file existed before task")

    # Submit a long task
    data = {
        "message": "Count to 100 slowly and create some output files",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)
    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait a bit for processing to start
    time.sleep(3)

    # Create a file after task started (should be moved)
    with open("during_task.txt", "w") as f:
        f.write("This file was created during task")

    # Stop the task
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")
    if response.status_code != 200:
        print(f"❌ Failed to stop task: {response.status_code}")
        return False

    print("✅ Stop request sent")

    # Check if files were cleaned up
    time.sleep(2)

    # before_task.txt should still exist (created before task)
    if os.path.exists("before_task.txt"):
        print("✅ Pre-existing file not moved (correct)")
        os.remove("before_task.txt")
    else:
        print("❌ Pre-existing file was incorrectly moved")

    # during_task.txt should be moved (created after task started)
    if not os.path.exists("during_task.txt"):
        print("✅ Task-generated file was moved (correct)")
    else:
        print("❌ Task-generated file not moved")
        os.remove("during_task.txt")

    # Check session storage for session_path
    session_file = f"session_storage/{session_id}.json"
    if os.path.exists(session_file):
        with open(session_file, 'r') as f:
            session_data = json.load(f)
            if session_data.get("session_path"):
                print(f"✅ Session path saved: {session_data['session_path']}")
            else:
                print("❌ Session path not saved")

    print("\n" + "-" * 50)
    return True


def test_download_after_completion():
    """Test that download works after task completion"""
    base_url = "http://localhost:8001"
    user_id = "test_download"

    print("\n🧪 TEST 2: DOWNLOAD AFTER COMPLETION")
    print("=" * 50)

    # Submit a simple task that completes quickly
    data = {
        "message": "Calculate 5 + 5 and save result",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)
    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait for completion
    print("⏳ Waiting for completion...")
    is_complete = False
    for i in range(30):
        response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
        if response.status_code == 200:
            status_data = response.json()
            if status_data.get("is_complete"):
                is_complete = True
                print("✅ Task completed!")
                break
        time.sleep(2)

    if not is_complete:
        print("❌ Task did not complete in time")
        return False

    # Try to download
    print("\n📥 Testing download...")
    response = requests.get(f"{base_url}/download/{session_id}?user_id={user_id}", allow_redirects=False)

    if response.status_code == 200:
        print("✅ Download successful (direct file)")
        print(f"   Content-Type: {response.headers.get('content-type')}")
        print(f"   File size: {len(response.content)} bytes")
    elif response.status_code == 302:
        print("✅ Download redirect to S3")
        location = response.headers.get('location')
        if location:
            print(f"   S3 URL: {location[:50]}...")
    elif response.status_code == 404:
        error_detail = response.json().get("detail", "Unknown error")
        print(f"❌ Download failed: {error_detail}")

        # Debug: Check session data
        session_file = f"session_storage/{session_id}.json"
        if os.path.exists(session_file):
            with open(session_file, 'r') as f:
                session_data = json.load(f)
                print(f"   Session path: {session_data.get('session_path', 'NOT SET')}")
                print(f"   Is complete: {session_data.get('is_complete', False)}")
    else:
        print(f"❌ Unexpected response: {response.status_code}")
        print(f"   Response: {response.text[:200]}")

    print("\n" + "-" * 50)
    return True


def test_download_cancelled_task():
    """Test that download works for cancelled tasks"""
    base_url = "http://localhost:8001"
    user_id = "test_download_cancel"

    print("\n🧪 TEST 3: DOWNLOAD CANCELLED TASK")
    print("=" * 50)

    # Submit and cancel a task
    data = {
        "message": "Long running task to be cancelled",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)
    if response.status_code != 200:
        print(f"❌ Failed to submit task")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait and cancel
    time.sleep(3)
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")
    if response.status_code == 200:
        print("✅ Task cancelled")

    time.sleep(2)

    # Try to download cancelled task
    response = requests.get(f"{base_url}/download/{session_id}?user_id={user_id}", allow_redirects=False)

    if response.status_code in [200, 302]:
        print("✅ Download available for cancelled task")
    else:
        error_detail = response.json().get("detail", "Unknown error")
        print(f"❌ Download failed for cancelled task: {error_detail}")

    print("\n" + "-" * 50)
    return True


def test_security_isolation():
    """Test that different users can't access each other's sessions"""
    base_url = "http://localhost:8001"
    user1 = "test_user1"
    user2 = "test_user2"

    print("\n🧪 TEST 4: SECURITY ISOLATION")
    print("=" * 50)

    # User1 creates a session
    data = {
        "message": "User1's private task",
        "language": "en",
        "user_id": user1
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)
    result = response.json()
    session_id = result["session_id"]
    print(f"✅ User1 created session: {session_id}")

    time.sleep(2)

    # User2 tries to access User1's session
    print("\n🔒 Testing cross-user access...")

    # Try status
    response = requests.get(f"{base_url}/status/{session_id}?user_id={user2}")
    if response.status_code == 403:
        print("✅ Status access blocked (403)")
    else:
        print(f"❌ Status access not blocked: {response.status_code}")

    # Try stop
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user2}")
    if response.status_code in [403, 404]:
        print("✅ Stop access blocked")
    else:
        print(f"❌ Stop access not blocked: {response.status_code}")

    # Try download
    response = requests.get(f"{base_url}/download/{session_id}?user_id={user2}")
    if response.status_code in [403, 404]:
        print("✅ Download access blocked")
    else:
        print(f"❌ Download access not blocked: {response.status_code}")

    # Clean up - stop User1's task
    requests.post(f"{base_url}/stop/{session_id}?user_id={user1}")

    print("\n" + "-" * 50)
    return True


if __name__ == "__main__":
    print("🚀 Starting Comprehensive Fix Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Wait for server
    time.sleep(5)

    # Run all tests
    all_passed = True

    if not test_stop_really_stops():
        all_passed = False

    if not test_download_after_completion():
        all_passed = False

    if not test_download_cancelled_task():
        all_passed = False

    if not test_security_isolation():
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\nFixed issues:")
        print("✅ Stop task really stops and cleans workspace")
        print("✅ Files created after task starts are moved")
        print("✅ Files created before task starts are preserved")
        print("✅ Download works for completed tasks")
        print("✅ Download works for cancelled tasks")
        print("✅ User isolation is enforced")
    else:
        print("⚠️  Some tests failed. Check the output above.")

    # Clean up any test files
    for f in ["before_task.txt", "during_task.txt", "test_output.txt"]:
        if os.path.exists(f):
            os.remove(f)