#!/usr/bin/env python3
"""
Test script for S3 file upload and retrieval in multi-turn sessions

This script tests:
1. Uploading files to S3 via the /chat-queue endpoint
2. Storing S3 metadata in session
3. Retrieving files from S3 in subsequent turns
"""

import requests
import os
import json
import time
from pathlib import Path

# Server configuration
BASE_URL = "http://localhost:8001"
TEST_USER_ID = "test_user_s3"

def create_test_file(filename: str, content: str) -> str:
    """Create a test file and return its path"""
    test_dir = Path("test_uploads")
    test_dir.mkdir(exist_ok=True)
    file_path = test_dir / filename
    file_path.write_text(content)
    print(f"Created test file: {file_path}")
    return str(file_path)

def test_initial_upload():
    """Test initial file upload with S3 storage"""
    print("\n=== Testing Initial File Upload to S3 ===")

    # Create test files
    test_file1 = create_test_file("test_data.csv", "col1,col2\n1,2\n3,4")
    test_file2 = create_test_file("test_image.txt", "This simulates an image file")

    # Prepare the request
    data = {
        "message": "Analyze these test files",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("test_data.csv", open(test_file1, "rb"), "text/csv")),
        ("files", ("test_image.txt", open(test_file2, "rb"), "text/plain"))
    ]

    # Send request
    response = requests.post(f"{BASE_URL}/chat-queue", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Initial upload successful!")
        print(f"  Session ID: {result['session_id']}")
        print(f"  Turn Number: {result['turn_number']}")
        print(f"  Uploaded Files: {result.get('uploaded_files', 0)}")
        print(f"  S3 Files: {result.get('s3_files', [])}")
        return result['session_id']
    else:
        print(f"✗ Upload failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def test_continue_session(session_id: str):
    """Test continuing a session with file retrieval from S3"""
    print("\n=== Testing Continue Session with S3 File Retrieval ===")

    # Wait for initial processing
    time.sleep(2)

    # Create a new file for the second turn
    new_file = create_test_file("additional_data.csv", "col3,col4\n5,6\n7,8")

    # Prepare continuation request
    data = {
        "session_id": session_id,
        "message": "Please analyze the previous files along with this new one",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("additional_data.csv", open(new_file, "rb"), "text/csv"))
    ]

    # Send continuation request
    response = requests.post(f"{BASE_URL}/continue-session", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Continue session successful!")
        print(f"  Session ID: {result['session_id']}")
        print(f"  Turn Number: {result['turn_number']}")
        print(f"  New Files: {result.get('uploaded_files', 0)}")
        print(f"  S3 Files: {result.get('s3_files', [])}")
        return result['turn_session_id']
    else:
        print(f"✗ Continue session failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def check_session_status(session_id: str):
    """Check the status of a session"""
    print(f"\n=== Checking Session Status: {session_id} ===")

    response = requests.get(f"{BASE_URL}/status/{session_id}", params={"user_id": TEST_USER_ID})

    if response.status_code == 200:
        result = response.json()
        print(f"  Status: {result.get('status', 'unknown')}")
        print(f"  Complete: {result.get('is_complete', False)}")
        if result.get('error'):
            print(f"  Error: {result['error']}")
        return result
    else:
        print(f"✗ Status check failed: {response.status_code}")
        return None

def test_multiturn_session_retrieval(session_id: str):
    """Test retrieving multi-turn session with S3 file metadata"""
    print(f"\n=== Testing Multi-turn Session Retrieval ===")

    response = requests.get(
        f"{BASE_URL}/multiturn-session/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Session retrieval successful!")
        print(f"  Total Turns: {result.get('total_turns', 0)}")

        # Check for S3 file metadata
        if hasattr(result, 's3_files_by_turn') or 's3_files_by_turn' in result:
            print(f"  S3 Files by Turn: {json.dumps(result.get('s3_files_by_turn', {}), indent=2)}")

        # Display turn information
        for turn in result.get('turns', []):
            print(f"\n  Turn {turn.get('turn_number', '?')}:")
            print(f"    Query: {turn.get('query', '')[:50]}...")
            print(f"    Status: {turn.get('status', 'unknown')}")
            if turn.get('files'):
                print(f"    Files: {list(turn['files'].keys())}")

        return result
    else:
        print(f"✗ Session retrieval failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def cleanup_test_files():
    """Clean up test files"""
    test_dir = Path("test_uploads")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print("\n✓ Cleaned up test files")

def main():
    """Run the complete test suite"""
    print("=" * 60)
    print("S3 FILE UPLOAD AND RETRIEVAL TEST")
    print("=" * 60)

    try:
        # Test 1: Initial upload
        session_id = test_initial_upload()
        if not session_id:
            print("\n✗ Test failed: Could not create initial session")
            return

        # Wait for processing
        print("\nWaiting for initial processing...")
        time.sleep(3)

        # Check initial status
        check_session_status(session_id)

        # Test 2: Continue session with S3 retrieval
        turn_session_id = test_continue_session(session_id)
        if not turn_session_id:
            print("\n✗ Test failed: Could not continue session")
            return

        # Wait for processing
        print("\nWaiting for continuation processing...")
        time.sleep(3)

        # Check continuation status
        check_session_status(turn_session_id)

        # Test 3: Retrieve full session
        test_multiturn_session_retrieval(session_id)

        print("\n" + "=" * 60)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_test_files()

if __name__ == "__main__":
    main()