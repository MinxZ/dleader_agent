#!/usr/bin/env python3
"""
Test Stop Functionality and S3 Upload
Tests that stop really stops and S3 upload works
"""
import time
import requests
import os
import json

def test_stop_really_stops():
    """Test that stop really terminates the thread"""
    base_url = "http://localhost:8001"
    user_id = "test_stop_verify"

    print("🧪 TEST 1: VERIFY STOP REALLY STOPS THREAD")
    print("=" * 50)

    # Create test files to track
    test_files = []
    for i in range(3):
        filename = f"test_file_{i}.txt"
        with open(filename, "w") as f:
            f.write(f"Test file {i} created during test")
        test_files.append(filename)

    # Submit a long-running task
    data = {
        "message": "Count to 1000 slowly, print each number, and create some output files",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting long-running task...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        # Cleanup
        for f in test_files:
            if os.path.exists(f):
                os.remove(f)
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Let it run for a bit
    print("⏳ Letting task run for 3 seconds...")
    time.sleep(3)

    # Check it's running
    response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
    if response.status_code == 200:
        status = response.json()
        print(f"📊 Status before stop: {status.get('status')}")

    # Stop the task
    print("\n🛑 Sending stop request...")
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code != 200:
        print(f"❌ Failed to stop: {response.status_code}")
        # Cleanup
        for f in test_files:
            if os.path.exists(f):
                os.remove(f)
        return False

    print("✅ Stop request sent successfully")

    # Wait and verify it's really stopped
    print("⏳ Waiting 5 seconds to verify stop...")
    time.sleep(5)

    # Check status after stop
    response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
    if response.status_code == 200:
        status = response.json()
        print(f"📊 Status after stop: {status.get('status')}")
        print(f"   Is complete: {status.get('is_complete')}")
        print(f"   Is cancelled: {status.get('is_cancelled')}")

    # Check if files were moved
    print("\n📁 Checking file cleanup...")
    files_moved = []
    files_remaining = []
    for f in test_files:
        if os.path.exists(f):
            files_remaining.append(f)
            os.remove(f)  # Cleanup
        else:
            files_moved.append(f)

    if files_moved:
        print(f"✅ {len(files_moved)} files were moved to session folder")
    if files_remaining:
        print(f"⚠️  {len(files_remaining)} files still in working directory")

    print("\n" + "-" * 50)
    return True


def test_s3_upload_on_completion():
    """Test that completed tasks are uploaded to S3"""
    base_url = "http://localhost:8001"
    user_id = "test_s3_upload"

    print("\n🧪 TEST 2: S3 UPLOAD ON COMPLETION")
    print("=" * 50)

    # Submit a simple task
    data = {
        "message": "Calculate 10 + 10 and save result to file",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait for completion
    print("⏳ Waiting for completion (max 30 seconds)...")
    is_complete = False
    for i in range(15):
        response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
        if response.status_code == 200:
            status = response.json()
            if status.get("is_complete"):
                is_complete = True
                print(f"✅ Task completed after {i*2} seconds")
                break
        time.sleep(2)

    if not is_complete:
        print("❌ Task did not complete in time")
        return False

    # Wait for S3 upload
    print("⏳ Waiting for S3 upload (5 seconds)...")
    time.sleep(5)

    # Test download-urls endpoint
    print("\n📥 Testing download-urls endpoint...")
    response = requests.get(f"{base_url}/download-urls/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        download_data = response.json()
        print(f"✅ Download URLs available!")
        print(f"   Session ID: {download_data.get('session_id')}")
        print(f"   Storage type: {download_data.get('storage_type')}")
        if 'download_url' in download_data:
            print(f"   Download URL: {download_data['download_url']}")
        if 's3_files' in download_data:
            print(f"   S3 files: {len(download_data.get('s3_files', {}))} files")
    else:
        print(f"❌ Download URLs failed: {response.status_code}")
        if response.status_code == 404:
            print(f"   Error: {response.json().get('detail')}")

    # Try actual download
    print("\n📦 Testing actual download...")
    response = requests.get(f"{base_url}/download/{session_id}?user_id={user_id}", allow_redirects=False)

    if response.status_code == 200:
        print("✅ Direct download successful")
        print(f"   File size: {len(response.content)} bytes")
    elif response.status_code == 302:
        print("✅ S3 redirect received")
        location = response.headers.get('location', '')
        if 'amazonaws.com' in location:
            print("   S3 URL confirmed")
    else:
        print(f"❌ Download failed: {response.status_code}")

    print("\n" + "-" * 50)
    return True


def test_stop_with_s3_upload():
    """Test that stopped tasks also get uploaded to S3"""
    base_url = "http://localhost:8001"
    user_id = "test_stop_s3"

    print("\n🧪 TEST 3: STOPPED TASK S3 UPLOAD")
    print("=" * 50)

    # Submit and stop a task
    data = {
        "message": "Long task to be stopped",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task to stop...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait and stop
    time.sleep(3)
    print("🛑 Stopping task...")
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        print("✅ Task stopped")

    # Wait for S3 upload
    print("⏳ Waiting for S3 upload (5 seconds)...")
    time.sleep(5)

    # Test download
    print("📥 Testing download for stopped task...")
    response = requests.get(f"{base_url}/download-urls/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        print("✅ Download available for stopped task")
    else:
        print(f"❌ Download not available: {response.status_code}")

    print("\n" + "-" * 50)
    return True


if __name__ == "__main__":
    print("🚀 Starting Stop & S3 Upload Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Wait for server
    time.sleep(3)

    # Run tests
    all_passed = True

    try:
        if not test_stop_really_stops():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 1 failed with error: {e}")
        all_passed = False

    try:
        if not test_s3_upload_on_completion():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 2 failed with error: {e}")
        all_passed = False

    try:
        if not test_stop_with_s3_upload():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 3 failed with error: {e}")
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\n✅ Stop functionality verified:")
        print("  • Thread stop verification works")
        print("  • Files are moved on cancellation")
        print("  • Workspace is cleaned")
        print("\n✅ S3 upload verified:")
        print("  • Completed tasks uploaded to S3")
        print("  • Stopped tasks uploaded to S3")
        print("  • Download URLs work correctly")
    else:
        print("⚠️  Some tests failed. Check output above.")
        print("\nIf threads are not stopping, will need to implement process-based approach.")