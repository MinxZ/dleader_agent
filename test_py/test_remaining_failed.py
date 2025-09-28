#!/usr/bin/env python3
"""
Test remaining failed endpoints with longer wait times for session completion
"""

import requests
import json
import os
import time
from datetime import datetime

# Configuration
BASE_URL = "http://52.192.211.135:8001"
TEST_USER_ID = "test_user_final"
OUTPUT_DIR = "test_api_payloads"

def save_payload(endpoint: str, input_data, output_data, test_name: str):
    """Save request and response payloads to files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_endpoint = endpoint.replace("/", "_").replace("{", "").replace("}", "")

    # Save input
    input_file = f"{OUTPUT_DIR}/inputs/{test_name}_{safe_endpoint}_{timestamp}_final.json"
    with open(input_file, 'w') as f:
        json.dump({
            "endpoint": endpoint,
            "timestamp": timestamp,
            "data": input_data
        }, f, indent=2, default=str)

    # Save output
    output_file = f"{OUTPUT_DIR}/outputs/{test_name}_{safe_endpoint}_{timestamp}_final.json"
    with open(output_file, 'w') as f:
        json.dump({
            "endpoint": endpoint,
            "status_code": output_data.get("status_code", 0),
            "timestamp": timestamp,
            "response": output_data.get("response", {})
        }, f, indent=2, default=str)

    print(f"  ✓ Saved: {os.path.basename(input_file)}")

def main():
    print("="*60)
    print("Testing Remaining Failed Endpoints with Proper Timing")
    print("="*60)

    # Create a new session with simple code
    print("\n1. Creating test session...")
    response = requests.post(
        f"{BASE_URL}/chat-queue",
        data={
            "message": "print('Test complete')",
            "user_id": TEST_USER_ID,
            "language": "en"
        }
    )

    if response.status_code != 200:
        print(f"Failed to create session: {response.text}")
        return

    session_id = response.json()["session_id"]
    print(f"   Session ID: {session_id}")

    # Wait for completion with status checks
    print("\n2. Waiting for session to complete...")
    for i in range(30):  # Wait up to 30 seconds
        time.sleep(1)
        status_resp = requests.get(
            f"{BASE_URL}/status/{session_id}",
            params={"user_id": TEST_USER_ID}
        )

        if status_resp.status_code == 200:
            status_data = status_resp.json()
            status = status_data.get("status", "unknown")
            is_complete = status_data.get("is_complete", False)

            if i % 5 == 0:  # Print status every 5 seconds
                print(f"   {i}s: Status = {status}, Complete = {is_complete}")

            if is_complete or status == "completed":
                print(f"   ✓ Session completed after {i+1} seconds")
                break
    else:
        print("   ⚠ Session did not complete in 30 seconds, testing anyway...")

    # Test /results endpoint
    print("\n3. Testing /results endpoint...")
    response = requests.get(
        f"{BASE_URL}/results/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    save_payload(
        f"/results/{session_id}",
        {"params": {"user_id": TEST_USER_ID}},
        {"status_code": response.status_code, "response": response.json() if response.content else {}},
        "results_final"
    )

    if response.status_code == 200:
        print(f"   ✓ SUCCESS: Got results (Status: {response.status_code})")
        print(f"   Output preview: {str(response.json())[:100]}...")
    else:
        print(f"   ✗ FAILED: Status {response.status_code}")
        print(f"   Error: {response.json()}")

    # Test /download endpoint
    print("\n4. Testing /download endpoint...")
    response = requests.get(
        f"{BASE_URL}/download/{session_id}",
        params={"user_id": TEST_USER_ID},
        allow_redirects=True
    )

    save_payload(
        f"/download/{session_id}",
        {"params": {"user_id": TEST_USER_ID}},
        {
            "status_code": response.status_code,
            "response": {
                "content_type": response.headers.get("content-type", ""),
                "content_length": len(response.content) if response.content else 0,
                "is_zip": response.headers.get("content-type") == "application/zip",
                "is_redirect": len(response.history) > 0
            }
        },
        "download_final"
    )

    if response.status_code == 200:
        print(f"   ✓ SUCCESS: Download worked (Status: {response.status_code})")
        print(f"   Content type: {response.headers.get('content-type', 'unknown')}")
        print(f"   Content size: {len(response.content)} bytes")

        # Save downloaded file if it's a zip
        if response.headers.get("content-type") == "application/zip":
            download_file = f"{OUTPUT_DIR}/downloaded_session_{session_id}.zip"
            with open(download_file, "wb") as f:
                f.write(response.content)
            print(f"   ✓ Saved download to: {download_file}")
    else:
        print(f"   ✗ FAILED: Status {response.status_code}")

    # Test /download-urls endpoint (might not exist)
    print("\n5. Testing /download-urls endpoint...")
    response = requests.get(
        f"{BASE_URL}/download-urls/{session_id}",
        params={"user_id": TEST_USER_ID}
    )

    save_payload(
        f"/download-urls/{session_id}",
        {"params": {"user_id": TEST_USER_ID}},
        {"status_code": response.status_code, "response": response.json() if response.content else {}},
        "download_urls_final"
    )

    if response.status_code == 200:
        print(f"   ✓ SUCCESS: Endpoint exists (Status: {response.status_code})")
        print(f"   Response: {response.json()}")
    elif response.status_code == 404:
        print(f"   ℹ INFO: Endpoint does not exist (404)")
    else:
        print(f"   ✗ FAILED: Unexpected status {response.status_code}")

    # Test hard delete with confirm (expected behavior)
    print("\n6. Testing /hard-delete with confirm=false (should fail)...")
    response = requests.delete(
        f"{BASE_URL}/hard-delete/{session_id}",
        params={"user_id": TEST_USER_ID, "confirm": "false"}
    )

    if response.status_code == 400:
        print(f"   ✓ EXPECTED: Correctly requires confirmation (Status: 400)")
    else:
        print(f"   ✗ UNEXPECTED: Status {response.status_code}")

    print("\n7. Testing /hard-delete with confirm=true (should succeed)...")
    response = requests.delete(
        f"{BASE_URL}/hard-delete/{session_id}",
        params={"user_id": TEST_USER_ID, "confirm": "true"}
    )

    save_payload(
        f"/hard-delete/{session_id}",
        {"params": {"user_id": TEST_USER_ID, "confirm": "true"}},
        {"status_code": response.status_code, "response": response.json() if response.content else {}},
        "hard_delete_final"
    )

    if response.status_code == 200:
        print(f"   ✓ SUCCESS: Session deleted (Status: {response.status_code})")
        result = response.json()
        if "deleted_items" in result:
            print(f"   Deleted files: {result['deleted_items']}")
    else:
        print(f"   ✗ FAILED: Status {response.status_code}")

    print("\n" + "="*60)
    print("FINAL TEST SUMMARY")
    print("="*60)
    print("All critical endpoints have been tested with proper parameters.")
    print("Check test_api_payloads/ for all saved request/response payloads.")

if __name__ == "__main__":
    main()