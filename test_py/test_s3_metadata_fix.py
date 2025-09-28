#!/usr/bin/env python3
"""
Quick test to verify S3 metadata storage fix
"""

import requests
import tempfile
import os

BASE_URL = "http://localhost:8001"

def test_file_upload_with_s3():
    """Test that file upload doesn't crash with S3 metadata storage"""

    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content for S3 upload")
        test_file_path = f.name

    try:
        # Prepare request
        data = {
            "message": "Test S3 metadata storage",
            "language": "en",
            "user_id": "test_user_fix"
        }

        with open(test_file_path, 'rb') as f:
            files = [("files", ("test.txt", f, "text/plain"))]

            # Send request
            response = requests.post(f"{BASE_URL}/chat-queue", data=data, files=files)

        if response.status_code == 200:
            result = response.json()
            print("✓ Request successful!")
            print(f"  Session ID: {result.get('session_id')}")
            print(f"  Turn Number: {result.get('turn_number')}")
            print(f"  S3 Files: {result.get('s3_files', [])}")
            return True
        else:
            print(f"✗ Request failed: {response.status_code}")
            print(f"  Error: {response.text}")
            return False

    finally:
        # Clean up
        if os.path.exists(test_file_path):
            os.remove(test_file_path)

if __name__ == "__main__":
    print("Testing S3 metadata storage fix...")
    print("=" * 40)

    success = test_file_upload_with_s3()

    if success:
        print("\n✓ Test passed! S3 metadata storage is working.")
    else:
        print("\n✗ Test failed. Check the error messages above.")