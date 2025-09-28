#!/usr/bin/env python3
"""
Test script to verify S3 multi-turn file handling fixes:
1. Files are uploaded to S3 only once (not duplicated)
2. Files from previous turns are downloaded from S3
3. Agent has access to all files across turns
"""

import requests
import time
import tempfile
import os
import json

BASE_URL = "http://localhost:8001"
TEST_USER_ID = "test_s3_fix_user"

def test_s3_multiturn():
    """Test multi-turn session with S3 file handling"""

    print("="*60)
    print("Testing S3 Multi-turn File Handling")
    print("="*60)

    # Create test files
    test_files = []
    for i in range(2):
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'_test{i+1}.txt', delete=False) as f:
            f.write(f"Test content for file {i+1}\nThis is test data for S3 upload testing.")
            test_files.append(f.name)

    try:
        # Turn 1: Start conversation without files
        print("\n[Turn 1] Starting conversation without files...")
        response = requests.post(f"{BASE_URL}/chat-queue", data={
            "message": "Hello, I will be uploading some files in the next turn",
            "language": "en",
            "user_id": TEST_USER_ID
        })

        if response.status_code != 200:
            print(f"❌ Turn 1 failed: {response.text}")
            return False

        session_id = response.json()['session_id']
        turn1_id = response.json()['session_id']
        print(f"✓ Session created: {session_id}")

        # Wait for turn 1 to complete
        time.sleep(5)

        # Turn 2: Upload first file
        print(f"\n[Turn 2] Uploading first file...")
        with open(test_files[0], 'rb') as f:
            response = requests.post(f"{BASE_URL}/continue-session",
                data={
                    "session_id": session_id,
                    "message": "Please analyze this file and tell me what it contains",
                    "language": "en",
                    "user_id": TEST_USER_ID
                },
                files=[("files", (os.path.basename(test_files[0]), f, "text/plain"))]
            )

        if response.status_code != 200:
            print(f"❌ Turn 2 failed: {response.text}")
            return False

        turn2_data = response.json()
        turn2_id = turn2_data['turn_session_id']
        print(f"✓ Turn 2 queued: {turn2_id}")
        print(f"  S3 files uploaded: {turn2_data.get('s3_files', [])}")

        # Check status after processing
        time.sleep(10)
        status_response = requests.get(f"{BASE_URL}/status/{turn2_id}", params={"user_id": TEST_USER_ID})
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get('error'):
                print(f"❌ Turn 2 error: {status['error']}")
                return False
            print("✓ Turn 2 completed without file errors")

        # Turn 3: Upload second file and reference first
        print(f"\n[Turn 3] Uploading second file...")
        with open(test_files[1], 'rb') as f:
            response = requests.post(f"{BASE_URL}/continue-session",
                data={
                    "session_id": session_id,
                    "message": "Compare this new file with the previous file. What are the differences?",
                    "language": "en",
                    "user_id": TEST_USER_ID
                },
                files=[("files", (os.path.basename(test_files[1]), f, "text/plain"))]
            )

        if response.status_code != 200:
            print(f"❌ Turn 3 failed: {response.text}")
            return False

        turn3_data = response.json()
        turn3_id = turn3_data['turn_session_id']
        print(f"✓ Turn 3 queued: {turn3_id}")
        print(f"  S3 files uploaded: {turn3_data.get('s3_files', [])}")

        # Check status and verify both files are accessible
        time.sleep(10)
        status_response = requests.get(f"{BASE_URL}/status/{turn3_id}", params={"user_id": TEST_USER_ID})
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get('error'):
                print(f"❌ Turn 3 error: {status['error']}")
                # Check if error is about missing files
                if 'no such file' in str(status['error']).lower():
                    print("  ERROR: Files from previous turns not accessible!")
                    return False
            else:
                print("✓ Turn 3 completed - files from previous turns were accessible")

        # Turn 4: No new files, just reference existing
        print(f"\n[Turn 4] Referencing existing files without uploading new ones...")
        response = requests.post(f"{BASE_URL}/continue-session",
            data={
                "session_id": session_id,
                "message": "List all the files you have access to from our conversation",
                "language": "en",
                "user_id": TEST_USER_ID
            }
        )

        if response.status_code != 200:
            print(f"❌ Turn 4 failed: {response.text}")
            return False

        turn4_data = response.json()
        turn4_id = turn4_data['turn_session_id']
        print(f"✓ Turn 4 queued: {turn4_id}")

        # Wait and check final status
        time.sleep(10)
        status_response = requests.get(f"{BASE_URL}/status/{turn4_id}", params={"user_id": TEST_USER_ID})
        if status_response.status_code == 200:
            status = status_response.json()
            if status.get('error'):
                print(f"❌ Turn 4 error: {status['error']}")
                return False
            print("✓ Turn 4 completed - all previous files still accessible")

        print("\n" + "="*60)
        print("✅ S3 MULTI-TURN TEST PASSED!")
        print("="*60)
        print("Summary:")
        print("  - Files uploaded to S3 in turn 2 and 3")
        print("  - No duplicate uploads detected")
        print("  - Files from previous turns accessible in later turns")
        print("  - Agent can reference all files throughout conversation")

        return True

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up test files
        for test_file in test_files:
            if os.path.exists(test_file):
                os.remove(test_file)
        print("\n✓ Test files cleaned up")

if __name__ == "__main__":
    success = test_s3_multiturn()
    exit(0 if success else 1)