#!/usr/bin/env python3
"""
Test script to verify multi-turn file handling is fixed
"""

import requests
import os
import time
import tempfile
from pathlib import Path

BASE_URL = "http://localhost:8001"
TEST_USER_ID = "test_multiturn_fix"

def create_test_image(filename: str, content: str = None) -> str:
    """Create a test file simulating an image"""
    test_dir = Path("test_uploads")
    test_dir.mkdir(exist_ok=True)
    file_path = test_dir / filename

    if content is None:
        content = f"Test image content for {filename}\n" * 100  # Make it substantial

    file_path.write_text(content)
    print(f"Created test file: {file_path}")
    return str(file_path)

def test_multiturn_with_files():
    """Test multi-turn conversation with file uploads in turn 2"""

    print("\n=== Turn 1: Start conversation without files ===")

    # Turn 1: No files
    data = {
        "message": "Hello, I want to analyze some images in the next turn",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    response = requests.post(f"{BASE_URL}/chat-queue", data=data)

    if response.status_code != 200:
        print(f"✗ Turn 1 failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

    result = response.json()
    session_id = result['session_id']
    print(f"✓ Turn 1 successful!")
    print(f"  Session ID: {session_id}")
    print(f"  Turn Number: {result['turn_number']}")

    # Wait for turn 1 to complete
    print("\nWaiting for turn 1 to process...")
    time.sleep(5)

    print("\n=== Turn 2: Upload files ===")

    # Create test files for turn 2
    test_file1 = create_test_image("Screenshot 2025-09-04 at 13.17.11.jpg")
    test_file2 = create_test_image("data_analysis.png")

    # Turn 2: Upload files
    data = {
        "session_id": session_id,
        "message": "Please analyze these screenshot images",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("Screenshot 2025-09-04 at 13.17.11.jpg", open(test_file1, "rb"), "image/jpeg")),
        ("files", ("data_analysis.png", open(test_file2, "rb"), "image/png"))
    ]

    response = requests.post(f"{BASE_URL}/continue-session", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code != 200:
        print(f"✗ Turn 2 failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

    result = response.json()
    turn_session_id = result.get('turn_session_id')
    print(f"✓ Turn 2 successful!")
    print(f"  Turn Session ID: {turn_session_id}")
    print(f"  Turn Number: {result['turn_number']}")
    print(f"  Uploaded Files: {result.get('uploaded_files', 0)}")
    print(f"  S3 Files: {result.get('s3_files', [])}")

    # Wait and check status
    print("\nWaiting for turn 2 to process...")
    time.sleep(5)

    # Check status
    status_response = requests.get(
        f"{BASE_URL}/status/{turn_session_id}",
        params={"user_id": TEST_USER_ID}
    )

    if status_response.status_code == 200:
        status = status_response.json()
        print(f"\nTurn 2 Status: {status.get('status')}")
        if status.get('error'):
            print(f"  Error: {status['error']}")
            return False
        else:
            print("  ✓ Processing without file errors!")
            return True
    else:
        print(f"✗ Status check failed: {status_response.status_code}")
        return False

def cleanup_test_files():
    """Clean up test files"""
    test_dir = Path("test_uploads")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print("\n✓ Cleaned up test files")

def main():
    """Run the multi-turn file handling test"""
    print("=" * 60)
    print("MULTI-TURN FILE HANDLING TEST")
    print("Testing file upload in turn 2")
    print("=" * 60)

    try:
        success = test_multiturn_with_files()

        if success:
            print("\n" + "=" * 60)
            print("✓ TEST PASSED! Files handled correctly in multi-turn.")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("✗ TEST FAILED! Check error messages above.")
            print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_test_files()

if __name__ == "__main__":
    main()