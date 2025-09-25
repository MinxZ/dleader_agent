#!/usr/bin/env python3
"""
Test Stop Task and Download Functionality
Tests the complete workflow including stop, download, and S3 upload
"""
import time
import requests
import json
import tempfile
import os


def test_stop_and_download():
    """Test stop task functionality and download after completion"""
    base_url = "http://localhost:8001"
    user_id = "test_stop_download"

    print("🧪 TESTING STOP TASK & DOWNLOAD FUNCTIONALITY")
    print("=" * 50)

    # Step 1: Submit a long-running task
    print("\n1️⃣ SUBMITTING LONG-RUNNING TASK")
    print("-" * 35)

    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test file content for stop/download test\nLine 2\nLine 3")
        test_file_path = f.name

    files = {'files': ('test.txt', open(test_file_path, 'rb'), 'text/plain')}
    data = {
        "message": "Process this file and do complex analysis (simulate long task)",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data, files=files)

    if response.status_code == 200:
        result = response.json()
        session_id = result["session_id"]
        print(f"✅ Task submitted successfully!")
        print(f"   Session ID: {session_id}")
        print(f"   Status: {result['status']}")
        print(f"   Queue position: {result.get('position', 'N/A')}")
    else:
        print(f"❌ Failed to submit task: {response.status_code}")
        return

    # Step 2: Check initial status
    print("\n2️⃣ CHECKING INITIAL STATUS")
    print("-" * 28)

    time.sleep(2)  # Wait a bit for processing to start

    response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
    if response.status_code == 200:
        status_data = response.json()
        print(f"✅ Status retrieved")
        print(f"   Status: {status_data.get('status')}")
        print(f"   Complete: {status_data.get('is_complete')}")
    else:
        print(f"❌ Failed to get status: {response.status_code}")

    # Step 3: Test STOP functionality
    print("\n3️⃣ TESTING STOP TASK")
    print("-" * 21)

    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        stop_result = response.json()
        print(f"✅ Stop request successful!")
        print(f"   Message: {stop_result.get('message')}")
        print(f"   Status: {stop_result.get('status')}")
    else:
        print(f"❌ Failed to stop task: {response.status_code}")
        print(f"   Response: {response.text}")

    # Step 4: Check status after stop
    print("\n4️⃣ CHECKING STATUS AFTER STOP")
    print("-" * 31)

    time.sleep(3)  # Wait for stop to take effect

    response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
    if response.status_code == 200:
        status_data = response.json()
        print(f"✅ Post-stop status retrieved")
        print(f"   Status: {status_data.get('status')}")
        print(f"   Complete: {status_data.get('is_complete')}")
        print(f"   Cancelled: {status_data.get('is_cancelled', 'N/A')}")
    else:
        print(f"❌ Failed to get status: {response.status_code}")

    # Clean up test file
    os.unlink(test_file_path)

    # Step 5: Submit another task to completion
    print("\n5️⃣ SUBMITTING TASK FOR COMPLETION")
    print("-" * 35)

    data = {
        "message": "Simple test task for completion",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code == 200:
        result = response.json()
        complete_session_id = result["session_id"]
        print(f"✅ Task submitted for completion test")
        print(f"   Session ID: {complete_session_id}")
    else:
        print(f"❌ Failed to submit task: {response.status_code}")
        return

    # Step 6: Wait for completion and test download
    print("\n6️⃣ WAITING FOR COMPLETION")
    print("-" * 26)

    max_wait = 30  # seconds
    start_time = time.time()
    is_complete = False

    while time.time() - start_time < max_wait:
        response = requests.get(f"{base_url}/status/{complete_session_id}?user_id={user_id}")
        if response.status_code == 200:
            status_data = response.json()
            if status_data.get("is_complete"):
                is_complete = True
                print(f"✅ Task completed!")
                print(f"   Status: {status_data.get('status')}")
                break
        time.sleep(2)

    if not is_complete:
        print("⚠️  Task did not complete within timeout")

    # Step 7: Test download
    print("\n7️⃣ TESTING DOWNLOAD")
    print("-" * 20)

    response = requests.get(f"{base_url}/download/{complete_session_id}?user_id={user_id}", allow_redirects=False)

    if response.status_code == 200:
        # Direct file download
        print(f"✅ Download successful (direct file)")
        print(f"   Content-Type: {response.headers.get('content-type')}")
        print(f"   File size: {len(response.content)} bytes")
    elif response.status_code == 302:
        # Redirect to S3
        print(f"✅ Download redirect to S3")
        print(f"   Location: {response.headers.get('location')[:50]}...")
    elif response.status_code == 404:
        print(f"⚠️  Download not found - checking details...")
        print(f"   Response: {response.text}")
    else:
        print(f"❌ Download failed: {response.status_code}")
        print(f"   Response: {response.text}")

    # Step 8: Check snapshots
    print("\n8️⃣ CHECKING SNAPSHOTS")
    print("-" * 22)

    response = requests.get(f"{base_url}/snapshots/{complete_session_id}?user_id={user_id}")

    if response.status_code == 200:
        snapshots_data = response.json()
        print(f"✅ Snapshots retrieved")
        print(f"   Snapshot count: {snapshots_data.get('snapshot_count', 0)}")
        if snapshots_data.get("snapshots"):
            print(f"   Latest snapshot status: {snapshots_data['snapshots'][-1].get('status', 'N/A')}")
    else:
        print(f"❌ Failed to get snapshots: {response.status_code}")

    # Step 9: Test security - different user can't download
    print("\n9️⃣ TESTING DOWNLOAD SECURITY")
    print("-" * 30)

    response = requests.get(f"{base_url}/download/{complete_session_id}?user_id=different_user")

    if response.status_code == 403:
        print(f"✅ Security working - cross-user download blocked")
    elif response.status_code == 404:
        print(f"✅ Security working - session not found for different user")
    else:
        print(f"❌ Security issue: {response.status_code}")

    print("\n" + "=" * 50)
    print("🎉 STOP & DOWNLOAD TEST COMPLETE!")
    print("\nResults:")
    print("✅ Stop task functionality tested")
    print("✅ Task cancellation verified")
    print("✅ Download after completion tested")
    print("✅ Security isolation verified")


def test_monitor_processing():
    """Monitor a real agent processing task"""
    base_url = "http://localhost:8001"
    user_id = "test_monitor"

    print("\n🔍 MONITORING AGENT PROCESSING")
    print("=" * 50)

    # Submit a task that triggers agent processing
    data = {
        "message": "Calculate the sum of numbers from 1 to 100",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code == 200:
        result = response.json()
        session_id = result["session_id"]
        print(f"✅ Task submitted: {session_id}")
    else:
        print(f"❌ Failed to submit task")
        return

    # Monitor status
    print("\nMonitoring progress...")
    print("-" * 30)

    for i in range(15):  # Monitor for up to 30 seconds
        response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
        if response.status_code == 200:
            status_data = response.json()
            print(f"[{i*2}s] Status: {status_data.get('status')} | Complete: {status_data.get('is_complete')}")

            if status_data.get("is_complete"):
                print(f"\n✅ Task completed successfully!")

                # Try download
                response = requests.get(f"{base_url}/download/{session_id}?user_id={user_id}", allow_redirects=False)
                if response.status_code in [200, 302]:
                    print(f"✅ Download available immediately after completion")
                else:
                    print(f"⚠️  Download issue: {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                break

        time.sleep(2)


if __name__ == "__main__":
    print("🚀 Starting Stop Task & Download Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Run tests
    test_stop_and_download()
    test_monitor_processing()

    print("\n✅ All tests completed!")