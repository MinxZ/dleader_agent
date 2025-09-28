#!/usr/bin/env python3
"""
Final test to verify the file path fix for multi-turn sessions
"""

import requests
import os
import time
import tempfile

BASE_URL = "http://localhost:8001"
TEST_USER_ID = "test_final_fix"

def test_multiturn_file_handling():
    """Test that files uploaded in turn 2 are handled correctly"""
    
    print("Testing multi-turn file handling...")
    
    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content for multi-turn session")
        test_file = f.name
    
    try:
        # Turn 1: No files
        print("\nTurn 1: Starting conversation...")
        response = requests.post(f"{BASE_URL}/chat-queue", data={
            "message": "Starting conversation",
            "language": "en",
            "user_id": TEST_USER_ID
        })
        
        if response.status_code != 200:
            print(f"Turn 1 failed: {response.text}")
            return False
            
        session_id = response.json()['session_id']
        print(f"Session ID: {session_id}")
        
        # Wait a bit
        time.sleep(3)
        
        # Turn 2: Upload file
        print("\nTurn 2: Uploading file...")
        with open(test_file, 'rb') as f:
            response = requests.post(f"{BASE_URL}/continue-session", 
                data={
                    "session_id": session_id,
                    "message": "Analyze this file",
                    "language": "en", 
                    "user_id": TEST_USER_ID
                },
                files=[("files", ("test.txt", f, "text/plain"))]
            )
        
        if response.status_code != 200:
            print(f"Turn 2 failed: {response.text}")
            return False
            
        turn_id = response.json()['turn_session_id']
        print(f"Turn session ID: {turn_id}")
        
        # Check status after a moment
        time.sleep(5)
        response = requests.get(f"{BASE_URL}/status/{turn_id}", params={"user_id": TEST_USER_ID})
        
        if response.status_code == 200:
            status = response.json()
            if status.get('error'):
                print(f"ERROR: {status['error']}")
                return False
            else:
                print("SUCCESS: No file errors!")
                return True
                
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
            
    return False

if __name__ == "__main__":
    if test_multiturn_file_handling():
        print("\n✓ Test PASSED!")
    else:
        print("\n✗ Test FAILED!")
