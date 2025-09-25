#!/usr/bin/env python3
"""
Test Snapshot Functionality in Process-based Execution
Verifies that snapshots are captured and saved periodically
"""
import time
import requests
import os
import json
import glob

def test_snapshot_capture():
    """Test that snapshots are captured during task execution"""
    base_url = "http://localhost:8001"
    user_id = "test_snapshots"

    print("🧪 TEST: SNAPSHOT CAPTURE IN PROCESS MODE")
    print("=" * 50)

    # Submit a task that takes some time
    data = {
        "message": """Do the following step by step:
        1. Count from 1 to 10, printing each number
        2. Wait 1 second between each number
        3. Create a summary at the end
        This should generate multiple snapshots""",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task that should generate snapshots...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Monitor for snapshots
    print("\n📸 Monitoring for snapshots...")
    snapshot_count = 0
    last_snapshot = None

    for i in range(15):  # Check for 30 seconds
        time.sleep(2)

        # Check status
        response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
        if response.status_code == 200:
            status_data = response.json()

            # Check for snapshots in response
            if "periodic_snapshots" in status_data and status_data["periodic_snapshots"]:
                current_count = len(status_data["periodic_snapshots"])
                if current_count > snapshot_count:
                    snapshot_count = current_count
                    print(f"   ✅ Snapshot #{snapshot_count} received")
                    last_snapshot = status_data["periodic_snapshots"][-1]

            # Check if completed
            if status_data.get("is_complete"):
                print(f"\n✅ Task completed")
                break

    # Check session folder for snapshot files
    print("\n📁 Checking session folder for snapshot files...")

    # Find session folder
    session_folders = glob.glob(f"chat_sessions/*{session_id[:8]}*")
    if session_folders:
        session_path = session_folders[0]
        print(f"   Session folder: {session_path}")

        # Look for snapshot files
        snapshot_files = glob.glob(os.path.join(session_path, "snapshot_*.json"))
        if snapshot_files:
            print(f"   ✅ Found {len(snapshot_files)} snapshot file(s):")
            for snap_file in snapshot_files[:3]:  # Show first 3
                print(f"      - {os.path.basename(snap_file)}")

            # Read and verify a snapshot
            with open(snapshot_files[-1], 'r') as f:
                snapshot_data = json.load(f)
                if "session_id" in snapshot_data and "timestamp" in snapshot_data:
                    print(f"   ✅ Snapshot file is valid")
                    if "content" in snapshot_data and snapshot_data["content"].get("thinking_content"):
                        print(f"   ✅ Snapshot contains thinking content")
        else:
            print(f"   ⚠️  No snapshot files found in session folder")
    else:
        print(f"   ⚠️  Session folder not found")

    # Summary
    print("\n" + "=" * 50)
    if snapshot_count > 0:
        print(f"✅ SUCCESS: {snapshot_count} snapshot(s) captured during execution")
        if last_snapshot:
            print(f"   Last snapshot status: {last_snapshot.get('status', 'unknown')}")
        return True
    else:
        print(f"❌ FAILED: No snapshots captured")
        return False


def test_snapshot_on_cancel():
    """Test that snapshots are saved when task is cancelled"""
    base_url = "http://localhost:8001"
    user_id = "test_snap_cancel"

    print("\n🧪 TEST: SNAPSHOTS ON CANCELLATION")
    print("=" * 50)

    # Submit long task
    data = {
        "message": "Count to 100 slowly with 0.5 second delays",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting long task...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait for some snapshots
    print("⏳ Waiting 6 seconds for snapshots...")
    time.sleep(6)

    # Cancel task
    print("🛑 Cancelling task...")
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        print("✅ Task cancelled")

    # Check for snapshots
    time.sleep(2)

    # Find session folder
    session_folders = glob.glob(f"chat_sessions/*{session_id[:8]}*")
    if session_folders:
        session_path = session_folders[0]
        snapshot_files = glob.glob(os.path.join(session_path, "snapshot_*.json"))

        if snapshot_files:
            print(f"✅ {len(snapshot_files)} snapshot(s) saved even after cancellation")
            return True
        else:
            print("❌ No snapshots found after cancellation")
            return False
    else:
        print("❌ Session folder not found")
        return False


if __name__ == "__main__":
    print("🚀 Starting Snapshot Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Wait for server
    time.sleep(3)

    # Run tests
    all_passed = True

    try:
        if not test_snapshot_capture():
            all_passed = False
    except Exception as e:
        print(f"❌ Snapshot capture test failed: {e}")
        all_passed = False

    try:
        if not test_snapshot_on_cancel():
            all_passed = False
    except Exception as e:
        print(f"❌ Snapshot on cancel test failed: {e}")
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL SNAPSHOT TESTS PASSED!")
        print("\n✅ Snapshot functionality working:")
        print("  • Snapshots captured periodically during execution")
        print("  • Snapshots saved to session folder")
        print("  • Snapshots preserved on cancellation")
        print("  • Process-based execution with IPC working")
    else:
        print("⚠️  Some tests failed. Snapshots may not be working correctly.")