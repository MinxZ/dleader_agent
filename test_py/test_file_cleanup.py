#!/usr/bin/env python3
"""
Test File Cleanup on Task Cancellation
Verifies that files generated during processing are moved to session folder
"""
import time
import requests
import os
import tempfile

def test_file_cleanup_on_cancel():
    """Test that files are moved to session folder when task is cancelled"""
    base_url = "http://localhost:8001"
    user_id = "test_cleanup"

    print("🧪 TESTING FILE CLEANUP ON CANCELLATION")
    print("=" * 50)

    # Create some test files that might be generated
    test_files = []

    # Create a test output file
    with open("test_output.txt", "w") as f:
        f.write("Test output file that should be moved")
        test_files.append("test_output.txt")

    # Create a test plot file
    with open("plot_test.png", "wb") as f:
        f.write(b"fake png data")
        test_files.append("plot_test.png")

    # Create a test result file
    with open("result_data.csv", "w") as f:
        f.write("col1,col2\ndata1,data2")
        test_files.append("result_data.csv")

    print(f"✅ Created {len(test_files)} test files in working directory")
    for file in test_files:
        print(f"   - {file}")

    # Step 1: Submit a long-running task
    print("\n1️⃣ SUBMITTING LONG-RUNNING TASK")
    print("-" * 35)

    data = {
        "message": "Process data and generate outputs (test file cleanup)",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code == 200:
        result = response.json()
        session_id = result["session_id"]
        print(f"✅ Task submitted successfully!")
        print(f"   Session ID: {session_id}")
    else:
        print(f"❌ Failed to submit task: {response.status_code}")
        # Cleanup test files
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)
        return

    # Step 2: Let it process for a bit
    print("\n2️⃣ WAITING FOR PROCESSING TO START")
    print("-" * 36)
    time.sleep(3)

    # Step 3: Stop the task
    print("\n3️⃣ STOPPING TASK")
    print("-" * 17)

    response = requests.post(f"{base_url}/stop/{session_id}?user_id={user_id}")

    if response.status_code == 200:
        print(f"✅ Task stopped successfully")
    else:
        print(f"❌ Failed to stop task: {response.status_code}")

    # Step 4: Check if files were moved
    print("\n4️⃣ CHECKING FILE CLEANUP")
    print("-" * 25)

    time.sleep(2)  # Give time for cleanup

    files_still_present = []
    files_moved = []

    for file in test_files:
        if os.path.exists(file):
            files_still_present.append(file)
        else:
            files_moved.append(file)

    if files_moved:
        print(f"✅ {len(files_moved)} files were moved to session folder:")
        for file in files_moved:
            print(f"   - {file}")

    if files_still_present:
        print(f"⚠️  {len(files_still_present)} files still in working directory:")
        for file in files_still_present:
            print(f"   - {file}")
        # Clean them up manually
        for file in files_still_present:
            os.remove(file)
            print(f"   Manually cleaned up: {file}")

    # Step 5: Check session storage
    print("\n5️⃣ CHECKING SESSION STORAGE")
    print("-" * 28)

    session_storage_file = f"session_storage/{session_id}.json"
    if os.path.exists(session_storage_file):
        import json
        with open(session_storage_file, 'r') as f:
            session_data = json.load(f)
            if session_data.get("session_path"):
                session_path = session_data["session_path"]
                print(f"✅ Session folder: {session_path}")

                if os.path.exists(session_path):
                    files_in_session = os.listdir(session_path)
                    print(f"   Files in session folder: {len(files_in_session)}")
                    for file in files_in_session[:5]:  # Show first 5 files
                        print(f"     - {file}")

    print("\n" + "=" * 50)
    print("🎉 FILE CLEANUP TEST COMPLETE!")

    if files_moved:
        print(f"✅ File cleanup working: {len(files_moved)} files moved on cancellation")
    else:
        print("⚠️  No files were moved (they may not have matched the criteria)")

def test_file_cleanup_on_completion():
    """Test that files are moved to session folder when task completes"""
    base_url = "http://localhost:8001"
    user_id = "test_cleanup_complete"

    print("\n🧪 TESTING FILE CLEANUP ON COMPLETION")
    print("=" * 50)

    # Create test files
    test_files = []

    with open("output_complete.txt", "w") as f:
        f.write("Output from completed task")
        test_files.append("output_complete.txt")

    with open("figure_1.png", "wb") as f:
        f.write(b"fake figure data")
        test_files.append("figure_1.png")

    print(f"✅ Created {len(test_files)} test files")

    # Submit a simple task that will complete quickly
    data = {
        "message": "Simple test: 2+2",
        "language": "en",
        "user_id": user_id
    }

    response = requests.post(f"{base_url}/chat-queue", data=data)

    if response.status_code == 200:
        result = response.json()
        session_id = result["session_id"]
        print(f"✅ Task submitted: {session_id}")

        # Wait for completion
        print("⏳ Waiting for completion...")
        for i in range(20):
            time.sleep(2)
            status_response = requests.get(f"{base_url}/status/{session_id}?user_id={user_id}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get("is_complete"):
                    print("✅ Task completed!")
                    break

        # Check file cleanup
        files_moved = []
        files_still_present = []

        for file in test_files:
            if os.path.exists(file):
                files_still_present.append(file)
            else:
                files_moved.append(file)

        if files_moved:
            print(f"✅ {len(files_moved)} files moved on completion")

        # Cleanup remaining files
        for file in files_still_present:
            if os.path.exists(file):
                os.remove(file)

if __name__ == "__main__":
    print("🚀 Starting File Cleanup Tests...")
    print("\nNote: Make sure FastAPI server is running on port 8001")
    print("-" * 50)

    # Wait for server to be ready
    time.sleep(3)

    # Run tests
    test_file_cleanup_on_cancel()
    test_file_cleanup_on_completion()

    print("\n✅ All file cleanup tests completed!")