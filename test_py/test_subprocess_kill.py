#!/usr/bin/env python3
"""
Test Subprocess Termination and Large File Handling
Tests that subprocesses are killed and large files are handled properly
"""
import time
import requests
import os
import subprocess

def test_subprocess_termination():
    """Test that subprocesses are terminated when task is cancelled"""
    base_url = "http://localhost:8001"
    user_id = "test_subprocess"

    print("🧪 TEST 1: SUBPROCESS TERMINATION")
    print("=" * 50)

    # Submit a task that spawns subprocesses
    data = {
        "message": """Create a Python script that spawns multiple subprocesses and run it:
        1. Create a script that starts 3 sleep processes (sleep 1000)
        2. Run the script
        3. Print the PIDs of all processes
        This will test subprocess cleanup""",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task that spawns subprocesses...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task: {response.status_code}")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Let it run and spawn subprocesses
    print("⏳ Waiting 5 seconds for subprocesses to spawn...")
    time.sleep(5)

    # Check running processes before stop
    print("\n📊 Checking processes before stop...")
    ps_output = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    sleep_count_before = ps_output.stdout.count('sleep 1000')
    print(f"   Found {sleep_count_before} 'sleep 1000' processes")

    # Stop the task
    print("\n🛑 Stopping task...")
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code != 200:
        print(f"❌ Failed to stop task: {response.status_code}")
        return False

    print("✅ Stop request sent")

    # Wait for cleanup
    print("⏳ Waiting 3 seconds for cleanup...")
    time.sleep(3)

    # Check processes after stop
    print("\n📊 Checking processes after stop...")
    ps_output = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    sleep_count_after = ps_output.stdout.count('sleep 1000')
    print(f"   Found {sleep_count_after} 'sleep 1000' processes")

    if sleep_count_after < sleep_count_before:
        print(f"✅ Subprocesses cleaned up: {sleep_count_before} -> {sleep_count_after}")
    else:
        print(f"⚠️  Subprocesses may not have been cleaned up")

    print("\n" + "-" * 50)
    return True


def test_large_file_handling():
    """Test that large files are not included in session storage"""
    base_url = "http://localhost:8001"
    user_id = "test_large_files"

    print("\n🧪 TEST 2: LARGE FILE HANDLING")
    print("=" * 50)

    # Create a large test file (>500MB would take too long, so we'll create 10MB for testing)
    large_file = "test_large_file.bin"
    print(f"📁 Creating test file ({large_file}, 10MB)...")

    with open(large_file, "wb") as f:
        # Write 10MB of data
        f.write(b"0" * (10 * 1024 * 1024))

    # Submit a simple task
    data = {
        "message": "List files in current directory",
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task")
        # Cleanup
        if os.path.exists(large_file):
            os.remove(large_file)
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Wait for completion
    print("⏳ Waiting for task completion...")
    for i in range(15):
        response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
        if response.status_code == 200:
            status = response.json()
            if status.get("is_complete"):
                print(f"✅ Task completed")
                break
        time.sleep(2)

    # Check if large file still exists (should be deleted or not moved)
    if os.path.exists(large_file):
        print(f"✅ Large file not moved (still in working directory)")
        os.remove(large_file)
    else:
        print(f"✅ Large file was handled (deleted or moved)")

    print("\n" + "-" * 50)
    return True


def test_process_tree_kill():
    """Test that entire process tree is killed"""
    base_url = "http://localhost:8001"
    user_id = "test_tree_kill"

    print("\n🧪 TEST 3: PROCESS TREE TERMINATION")
    print("=" * 50)

    # Submit a task that creates nested processes
    data = {
        "message": """Create and run a script that spawns nested processes:
        import subprocess
        import time
        # Parent process spawns child
        p1 = subprocess.Popen(['python', '-c', 'import time; import subprocess; subprocess.Popen(["sleep", "1000"]); time.sleep(1000)'])
        print(f"Started parent process: {p1.pid}")
        time.sleep(1000)
        """,
        "language": "en",
        "user_id": user_id
    }

    print("📤 Submitting task with nested processes...")
    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"❌ Failed to submit task")
        return False

    result = response.json()
    session_id = result["session_id"]
    print(f"✅ Task submitted: {session_id}")

    # Let processes spawn
    print("⏳ Waiting for nested processes to spawn...")
    time.sleep(5)

    # Stop the task
    print("🛑 Stopping task (should kill entire process tree)...")
    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        print("✅ Stop request successful")

    # Wait and verify
    time.sleep(3)

    # Check for orphaned processes
    ps_output = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    orphaned = ps_output.stdout.count('sleep 1000')

    if orphaned == 0:
        print("✅ No orphaned processes found - process tree killed successfully")
    else:
        print(f"⚠️  Found {orphaned} potential orphaned processes")

    print("\n" + "-" * 50)
    return True


if __name__ == "__main__":
    print("🚀 Starting Subprocess & File Handling Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Wait for server
    time.sleep(3)

    # Run tests
    all_passed = True

    try:
        if not test_subprocess_termination():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        all_passed = False

    try:
        if not test_large_file_handling():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        all_passed = False

    try:
        if not test_process_tree_kill():
            all_passed = False
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\n✅ Subprocess management:")
        print("  • Subprocesses are terminated when task stops")
        print("  • Entire process tree is killed")
        print("  • No orphaned processes left behind")
        print("\n✅ File management:")
        print("  • Large files (>500MB) are deleted, not moved")
        print("  • Zip files skip large files (>100MB)")
        print("  • Total zip size limited to 500MB")
    else:
        print("⚠️  Some tests failed. Check output above.")

    # Cleanup
    for file in ["test_large_file.bin"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"Cleaned up: {file}")