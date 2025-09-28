#!/usr/bin/env python3
"""
Test script for file size validation in the FastAPI server

Tests:
1. Uploading files under 10MB (should succeed)
2. Uploading files over 10MB (should be rejected)
3. Mixed uploads (some accepted, some rejected)
"""

import requests
import os
import json
from pathlib import Path

# Server configuration
BASE_URL = "http://localhost:8001"
TEST_USER_ID = "test_user_filesize"

def create_file_with_size(filename: str, size_mb: float) -> str:
    """Create a test file with specific size in MB"""
    test_dir = Path("test_uploads")
    test_dir.mkdir(exist_ok=True)
    file_path = test_dir / filename

    # Create file with specific size
    size_bytes = int(size_mb * 1024 * 1024)

    # For small files, write actual content
    if size_mb < 1:
        content = "x" * size_bytes
        file_path.write_text(content)
    else:
        # For larger files, write in chunks to avoid memory issues
        with open(file_path, 'wb') as f:
            chunk_size = 1024 * 1024  # 1MB chunks
            remaining = size_bytes
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(b'x' * write_size)
                remaining -= write_size

    actual_size = os.path.getsize(file_path) / (1024 * 1024)
    print(f"Created {filename}: {actual_size:.2f}MB")
    return str(file_path)

def test_small_files():
    """Test uploading files under 10MB (should succeed)"""
    print("\n=== Test 1: Small Files (<10MB) - Should Succeed ===")

    # Create small test files
    file1 = create_file_with_size("small_data.csv", 0.5)  # 0.5MB
    file2 = create_file_with_size("medium_data.csv", 5.0)  # 5MB
    file3 = create_file_with_size("large_data.csv", 9.9)  # 9.9MB

    # Prepare request
    data = {
        "message": "Analyze these small files",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("small_data.csv", open(file1, "rb"), "text/csv")),
        ("files", ("medium_data.csv", open(file2, "rb"), "text/csv")),
        ("files", ("large_data.csv", open(file3, "rb"), "text/csv"))
    ]

    # Send request
    response = requests.post(f"{BASE_URL}/chat-queue", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 200:
        result = response.json()
        print("✓ Small files upload successful!")
        print(f"  Uploaded: {result.get('uploaded_files', 0)} files")
        print(f"  S3 Files: {result.get('s3_files', [])}")
        if result.get('rejected_files'):
            print(f"  ⚠ Unexpected rejections: {result['rejected_files']}")
        return result['session_id']
    else:
        print(f"✗ Unexpected failure: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def test_oversized_files():
    """Test uploading files over 10MB (should be rejected)"""
    print("\n=== Test 2: Oversized Files (>10MB) - Should Be Rejected ===")

    # Create oversized test files
    file1 = create_file_with_size("huge_data.csv", 11.0)  # 11MB
    file2 = create_file_with_size("massive_data.csv", 15.0)  # 15MB

    # Prepare request
    data = {
        "message": "Try to analyze these large files",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("huge_data.csv", open(file1, "rb"), "text/csv")),
        ("files", ("massive_data.csv", open(file2, "rb"), "text/csv"))
    ]

    # Send request
    response = requests.post(f"{BASE_URL}/chat-queue", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 413:
        print("✓ Oversized files correctly rejected with 413 status!")
        print(f"  Error message: {response.json().get('detail', 'N/A')}")
        return True
    elif response.status_code == 200:
        result = response.json()
        if result.get('rejected_files'):
            print("✓ Server accepted request but rejected oversized files")
            print(f"  Rejected files: {json.dumps(result['rejected_files'], indent=2)}")
            return True
        else:
            print("✗ Oversized files were not rejected!")
            return False
    else:
        print(f"✗ Unexpected response: {response.status_code}")
        print(f"  Error: {response.text}")
        return False

def test_mixed_files():
    """Test mixed upload (some accepted, some rejected)"""
    print("\n=== Test 3: Mixed Files - Some Accepted, Some Rejected ===")

    # Create mixed test files
    file1 = create_file_with_size("ok_file1.csv", 2.0)  # 2MB - OK
    file2 = create_file_with_size("too_big.csv", 12.0)  # 12MB - Too big
    file3 = create_file_with_size("ok_file2.csv", 8.0)  # 8MB - OK
    file4 = create_file_with_size("way_too_big.csv", 20.0)  # 20MB - Too big

    # Prepare request
    data = {
        "message": "Process this mixed batch of files",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("ok_file1.csv", open(file1, "rb"), "text/csv")),
        ("files", ("too_big.csv", open(file2, "rb"), "text/csv")),
        ("files", ("ok_file2.csv", open(file3, "rb"), "text/csv")),
        ("files", ("way_too_big.csv", open(file4, "rb"), "text/csv"))
    ]

    # Send request
    response = requests.post(f"{BASE_URL}/chat-queue", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 200:
        result = response.json()
        print("✓ Mixed upload processed successfully!")
        print(f"  Uploaded: {result.get('uploaded_files', 0)} files")
        print(f"  S3 Files: {result.get('s3_files', [])}")

        if result.get('rejected_files'):
            print(f"  Rejected {len(result['rejected_files'])} files:")
            for rejected in result['rejected_files']:
                print(f"    - {rejected['filename']}: {rejected['size_mb']}MB - {rejected['reason']}")

        # Verify correct files were accepted/rejected
        expected_accepted = 2
        expected_rejected = 2

        if result.get('uploaded_files') == expected_accepted:
            print(f"  ✓ Correct number of files accepted ({expected_accepted})")
        else:
            print(f"  ✗ Wrong number of files accepted: {result.get('uploaded_files')} (expected {expected_accepted})")

        if len(result.get('rejected_files', [])) == expected_rejected:
            print(f"  ✓ Correct number of files rejected ({expected_rejected})")
        else:
            print(f"  ✗ Wrong number of files rejected: {len(result.get('rejected_files', []))} (expected {expected_rejected})")

        return result['session_id']
    else:
        print(f"✗ Unexpected response: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

def test_continue_session_with_size_limit(session_id: str):
    """Test file size validation in continue-session endpoint"""
    print("\n=== Test 4: Continue Session with Size Validation ===")

    # Create test files for continuation
    file1 = create_file_with_size("continue_ok.csv", 3.0)  # 3MB - OK
    file2 = create_file_with_size("continue_too_big.csv", 11.0)  # 11MB - Too big

    # Prepare continuation request
    data = {
        "session_id": session_id,
        "message": "Continue with more files",
        "language": "en",
        "user_id": TEST_USER_ID
    }

    files = [
        ("files", ("continue_ok.csv", open(file1, "rb"), "text/csv")),
        ("files", ("continue_too_big.csv", open(file2, "rb"), "text/csv"))
    ]

    # Send continuation request
    response = requests.post(f"{BASE_URL}/continue-session", data=data, files=files)

    # Close file handles
    for _, (_, f, _) in files:
        f.close()

    if response.status_code == 200:
        result = response.json()
        print("✓ Continue session processed successfully!")
        print(f"  Turn: {result.get('turn_number')}")
        print(f"  Uploaded: {result.get('uploaded_files', 0)} files")
        print(f"  S3 Files: {result.get('s3_files', [])}")

        if result.get('rejected_files'):
            print(f"  Rejected {len(result['rejected_files'])} files:")
            for rejected in result['rejected_files']:
                print(f"    - {rejected['filename']}: {rejected['size_mb']}MB")

        return True
    else:
        print(f"✗ Continue session failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return False

def cleanup_test_files():
    """Clean up test files"""
    test_dir = Path("test_uploads")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print("\n✓ Cleaned up test files")

def main():
    """Run all file size validation tests"""
    print("=" * 60)
    print("FILE SIZE VALIDATION TEST SUITE")
    print("Maximum file size: 10MB")
    print("=" * 60)

    try:
        # Test 1: Small files
        session_id = test_small_files()

        # Test 2: Oversized files
        test_oversized_files()

        # Test 3: Mixed files
        mixed_session_id = test_mixed_files()

        # Test 4: Continue session with size validation
        if mixed_session_id:
            test_continue_session_with_size_limit(mixed_session_id)

        print("\n" + "=" * 60)
        print("✓ FILE SIZE VALIDATION TESTS COMPLETED!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_test_files()

if __name__ == "__main__":
    main()